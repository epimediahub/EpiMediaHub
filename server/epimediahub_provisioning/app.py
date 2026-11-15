from __future__ import annotations

import base64, hashlib, hmac, io, json, os, secrets, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import qrcode
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")); DB_PATH = BASE_DIR / "provisioning.db"
PUBLIC_BASE_URL = os.environ.get("EPIMEDIAHUB_PUBLIC_URL", "https://setup.epimediahub.com").rstrip("/")
ADMIN_TOKEN = os.environ.get("EPIMEDIAHUB_ADMIN_TOKEN", ""); ADMIN_PASSWORD = os.environ.get("EPIMEDIAHUB_ADMIN_PASSWORD", "")
SECRET_KEY = os.environ.get("EPIMEDIAHUB_SECRET_KEY", secrets.token_hex(32)); CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
app = Flask(__name__); app.secret_key = SECRET_KEY; app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

def utcnow(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def normalize_code(value): return "".join(c for c in value.upper() if c.isalnum())
def display_code(raw): return "-".join(raw[i:i+4] for i in range(0,len(raw),4))
def make_code(length=12): return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
def pairing_session_token(pairing_secret):
    return hmac.new(SECRET_KEY.encode("utf-8"), f"device-session:{pairing_secret}".encode("utf-8"), hashlib.sha256).hexdigest()
def qr_data_uri(value):
    image=qrcode.make(value); buf=io.BytesIO(); image.save(buf,format="PNG")
    return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode("ascii")
def db():
    BASE_DIR.mkdir(parents=True,exist_ok=True); con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; con.execute("PRAGMA foreign_keys=ON"); return con
def init_db():
    with db() as con: con.executescript("""
    CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,config_json TEXT NOT NULL DEFAULT '{}',enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS activations(id INTEGER PRIMARY KEY AUTOINCREMENT,customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,code_hash TEXT NOT NULL UNIQUE,token_hash TEXT NOT NULL UNIQUE,expires_at TEXT NOT NULL,redeemed_at TEXT,device_id TEXT,platform TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS devices(id INTEGER PRIMARY KEY AUTOINCREMENT,customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,device_id TEXT NOT NULL,platform TEXT NOT NULL,session_token_hash TEXT NOT NULL UNIQUE,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(customer_id,device_id));
    CREATE TABLE IF NOT EXISTS pairings(id INTEGER PRIMARY KEY AUTOINCREMENT,code_hash TEXT NOT NULL UNIQUE,secret_hash TEXT NOT NULL UNIQUE,device_id TEXT NOT NULL,device_name TEXT NOT NULL DEFAULT '',platform TEXT NOT NULL,customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,expires_at TEXT NOT NULL,claimed_at TEXT,created_at TEXT NOT NULL);""")
def require_admin_api():
    if not ADMIN_TOKEN or not secrets.compare_digest(request.headers.get("Authorization",""),f"Bearer {ADMIN_TOKEN}"): abort(401)
def web_auth():
    if not session.get("admin"): return redirect(url_for("login",next=request.path))
def customer_config(row):
    try:
        value=json.loads(row["config_json"] or "{}")
        return value if isinstance(value,dict) else {}
    except (TypeError,json.JSONDecodeError): return {}
def config_version(config):
    try:return max(1,int(config.get("_version",1)))
    except (TypeError,ValueError):return 1
def public_config(config): return {k:v for k,v in config.items() if not str(k).startswith("_")}
def form_config(previous=None):
    previous=dict(previous or {})
    kind=request.form.get("playlist_type",previous.get("playlist_type","M3U")).strip().upper()
    if kind not in {"M3U","XTREAM"}:kind="M3U"
    cfg=dict(previous)
    cfg["_version"]=config_version(previous)+1 if previous else 1
    cfg["playlist_type"]=kind
    cfg["playlist_name"]=request.form.get("playlist_name",previous.get("playlist_name","EpiMediaHub")).strip() or "EpiMediaHub"
    if kind=="XTREAM":
        cfg["playlist_url"]=""
        cfg["xtream_server"]=request.form.get("xtream_server","").strip().rstrip("/")
        cfg["xtream_username"]=request.form.get("xtream_username","").strip()
        cfg["xtream_password"]=request.form.get("xtream_password","")
        cfg["xtream_output"]=request.form.get("xtream_output","ts").strip() or "ts"
    else:
        cfg["playlist_url"]=request.form.get("playlist_url","").strip()
        cfg["xtream_server"]="";cfg["xtream_username"]="";cfg["xtream_password"]="";cfg["xtream_output"]="ts"
    return cfg
def device_session_row():
    auth=request.headers.get("Authorization","")
    if not auth.startswith("Bearer "):return None
    token=auth[7:].strip()
    if not token:return None
    with db() as con:
        return con.execute("SELECT d.*,c.config_json,c.enabled customer_enabled FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.session_token_hash=? AND d.enabled=1 AND c.enabled=1",(digest(token),)).fetchone()
def claim_activation(row,device_id,platform):
    now=utcnow()
    if row is None or not row["customer_enabled"]: return None,(jsonify(error="invalid_code"),404)
    if row["redeemed_at"] is not None: return None,(jsonify(error="already_used"),409)
    if datetime.fromisoformat(row["expires_at"].replace("Z","+00:00"))<=now: return None,(jsonify(error="expired"),410)
    session_token=secrets.token_urlsafe(48)
    return (session_token,now),None

@app.get("/health")
def health(): return jsonify(status="ok",service="epimediahub-provisioning")
@app.route("/admin/login",methods=["GET","POST"])
def login():
    error=None
    if request.method=="POST":
        if ADMIN_PASSWORD and secrets.compare_digest(request.form.get("password",""),ADMIN_PASSWORD): session["admin"]=True; return redirect(url_for("dashboard"))
        error="Passwort falsch"
    return render_template("login.html",error=error)
@app.post("/admin/logout")
def logout(): session.clear(); return redirect(url_for("login"))
@app.get("/admin")
def dashboard():
    guard=web_auth()
    if guard:return guard
    with db() as con:
        customer_rows=con.execute("SELECT * FROM customers ORDER BY id DESC").fetchall(); devices=con.execute("SELECT d.*,c.name customer_name FROM devices d JOIN customers c ON c.id=d.customer_id ORDER BY d.id DESC").fetchall()
    customers=[]
    for c in customer_rows:
        cfg=customer_config(c); item=dict(c)
        item.update({
            "playlist_type":cfg.get("playlist_type","XTREAM" if cfg.get("xtream_server") else "M3U"),
            "playlist_name":cfg.get("playlist_name",c["name"]),
            "playlist_url":cfg.get("playlist_url",""),
            "xtream_server":cfg.get("xtream_server",""),
            "xtream_username":cfg.get("xtream_username",""),
            "xtream_password":cfg.get("xtream_password",""),
            "xtream_output":cfg.get("xtream_output","ts"),
            "config_version":config_version(cfg),
        }); customers.append(item)
    return render_template("dashboard.html",customers=customers,devices=devices,notice=request.args.get("notice", ""))
@app.post("/admin/customers")
def web_create_customer():
    guard=web_auth()
    if guard:return guard
    name=request.form.get("name","").strip()
    if name:
        cfg=form_config()
        with db() as con: con.execute("INSERT INTO customers(name,config_json,created_at) VALUES(?,?,?)",(name,json.dumps(cfg,separators=(",",":")),iso(utcnow())))
    return redirect(url_for("dashboard"))
@app.post("/admin/customers/<int:customer_id>/update")
def web_update_customer(customer_id):
    guard=web_auth()
    if guard:return guard
    name=request.form.get("name","").strip()
    if not name:return redirect(url_for("dashboard"))
    with db() as con:
        row=con.execute("SELECT * FROM customers WHERE id=?",(customer_id,)).fetchone()
        if not row:abort(404)
        config=form_config(customer_config(row))
        con.execute("UPDATE customers SET name=?,config_json=? WHERE id=?",(name,json.dumps(config,separators=(",",":")),customer_id))
    return redirect(url_for("dashboard"))
@app.post("/admin/customers/<int:customer_id>/delete")
def web_delete_customer(customer_id):
    guard=web_auth()
    if guard:return guard
    if request.form.get("confirm","") != f"DELETE:{customer_id}":abort(400)
    with db() as con:
        customer=con.execute("SELECT id FROM customers WHERE id=?",(customer_id,)).fetchone()
        if not customer:abort(404)
        con.execute("DELETE FROM customers WHERE id=?",(customer_id,))
    return redirect(url_for("dashboard",notice="customer_deleted"))
@app.post("/admin/customers/<int:customer_id>/activation")
def web_activation(customer_id):
    guard=web_auth()
    if guard:return guard
    raw,token,expires=make_code(),secrets.token_urlsafe(32),utcnow()+timedelta(minutes=60)
    with db() as con:
        customer=con.execute("SELECT * FROM customers WHERE id=? AND enabled=1",(customer_id,)).fetchone()
        if not customer:abort(404)
        con.execute("INSERT INTO activations(customer_id,code_hash,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)",(customer_id,digest(raw),digest(token),iso(expires),iso(utcnow())))
    activation_url=f"{PUBLIC_BASE_URL}/connect/{token}"
    return render_template("activation.html",customer=customer,code=display_code(raw),activation_url=activation_url,expires_at=iso(expires),qr_data=qr_data_uri(activation_url))
@app.post("/admin/pairings/claim")
def web_claim_pairing():
    guard=web_auth()
    if guard:return guard
    code=normalize_code(request.form.get("code",""))
    try:customer_id=int(request.form.get("customer_id",""))
    except ValueError:return redirect(url_for("dashboard",notice="pair_invalid"))
    if len(code)!=8:return redirect(url_for("dashboard",notice="pair_invalid"))
    now=utcnow()
    with db() as con:
        customer=con.execute("SELECT id FROM customers WHERE id=? AND enabled=1",(customer_id,)).fetchone()
        if not customer:return redirect(url_for("dashboard",notice="pair_customer_invalid"))
        row=con.execute("SELECT * FROM pairings WHERE code_hash=?",(digest(code),)).fetchone()
        if row is None:return redirect(url_for("dashboard",notice="pair_invalid"))
        if datetime.fromisoformat(row["expires_at"].replace("Z","+00:00"))<=now:
            return redirect(url_for("dashboard",notice="pair_expired"))
        if row["customer_id"] is not None:return redirect(url_for("dashboard",notice="pair_used"))
        con.execute("UPDATE pairings SET customer_id=?,claimed_at=? WHERE id=? AND customer_id IS NULL",(customer_id,iso(now),row["id"]))
    return redirect(url_for("dashboard",notice="pair_claimed"))
@app.post("/admin/devices/<int:device_id>/assign")
def web_assign_device(device_id):
    guard=web_auth()
    if guard:return guard
    try: customer_id=int(request.form.get("customer_id",""))
    except ValueError:return redirect(url_for("dashboard"))
    with db() as con:
        if not con.execute("SELECT id FROM customers WHERE id=?",(customer_id,)).fetchone():abort(404)
        device=con.execute("SELECT * FROM devices WHERE id=?",(device_id,)).fetchone()
        if not device:abort(404)
        duplicate=con.execute("SELECT id FROM devices WHERE customer_id=? AND device_id=? AND id<>?",(customer_id,device["device_id"],device_id)).fetchone()
        if duplicate:abort(409)
        con.execute("UPDATE devices SET customer_id=? WHERE id=?",(customer_id,device_id))
    return redirect(url_for("dashboard"))
@app.post("/admin/devices/<int:device_id>/revoke")
def web_revoke(device_id):
    guard=web_auth()
    if guard:return guard
    with db() as con:con.execute("UPDATE devices SET enabled=0 WHERE id=?",(device_id,))
    return redirect(url_for("dashboard"))
@app.post("/admin/devices/<int:device_id>/enable")
def web_enable(device_id):
    guard=web_auth()
    if guard:return guard
    with db() as con:con.execute("UPDATE devices SET enabled=1 WHERE id=?",(device_id,))
    return redirect(url_for("dashboard"))
@app.post("/v1/admin/customers")
def create_customer():
    require_admin_api();body=request.get_json(silent=True) or {};name=str(body.get("name","")).strip();config=body.get("config",{})
    if not name or not isinstance(config,dict):return jsonify(error="invalid_customer"),400
    config=dict(config);config["_version"]=config_version(config)
    with db() as con:cid=con.execute("INSERT INTO customers(name,config_json,created_at) VALUES(?,?,?)",(name,json.dumps(config,separators=(",",":")),iso(utcnow()))).lastrowid
    return jsonify(id=cid,name=name),201
@app.post("/v1/admin/customers/<int:customer_id>/activation")
def create_activation(customer_id):
    require_admin_api();body=request.get_json(silent=True) or {};ttl=max(5,min(int(body.get("ttl_minutes",60)),1440));raw=make_code();token=secrets.token_urlsafe(32);expires=utcnow()+timedelta(minutes=ttl)
    with db() as con:
        if not con.execute("SELECT id FROM customers WHERE id=? AND enabled=1",(customer_id,)).fetchone():return jsonify(error="customer_not_found"),404
        con.execute("INSERT INTO activations(customer_id,code_hash,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)",(customer_id,digest(raw),digest(token),iso(expires),iso(utcnow())))
    url=f"{PUBLIC_BASE_URL}/connect/{token}";return jsonify(code=display_code(raw),activation_url=url,qr_payload=url,expires_at=iso(expires)),201
def redeem_by(field,value,body):
    device_id=str(body.get("device_id","")).strip();platform=str(body.get("platform","android")).strip() or "android"
    if not device_id:return jsonify(error="invalid_request"),400
    with db() as con:
        con.execute("BEGIN IMMEDIATE");row=con.execute(f"SELECT a.*,c.config_json,c.enabled customer_enabled FROM activations a JOIN customers c ON c.id=a.customer_id WHERE a.{field}=?",(digest(value),)).fetchone(); claim,error=claim_activation(row,device_id,platform)
        if error:return error
        session_token,now=claim;con.execute("UPDATE activations SET redeemed_at=?,device_id=?,platform=? WHERE id=? AND redeemed_at IS NULL",(iso(now),device_id,platform,row["id"]));con.execute("INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at) VALUES(?,?,?,?,?) ON CONFLICT(customer_id,device_id) DO UPDATE SET platform=excluded.platform,session_token_hash=excluded.session_token_hash,enabled=1",(row["customer_id"],device_id,platform,digest(session_token),iso(now)));config=customer_config(row);version=config_version(config)
    return jsonify(session_token=session_token,customer_id=row["customer_id"],config_version=version,config=public_config(config))
@app.post("/v1/setup/redeem")
def redeem():
    body=request.get_json(silent=True) or {};code=normalize_code(str(body.get("code","")))
    if not code:return jsonify(error="invalid_request"),400
    return redeem_by("code_hash",code,body)
@app.post("/v1/setup/redeem-token")
def redeem_token():
    body=request.get_json(silent=True) or {};token=str(body.get("token","")).strip()
    if not token:return jsonify(error="invalid_request"),400
    return redeem_by("token_hash",token,body)
@app.post("/v1/pair/start")
def pair_start():
    body=request.get_json(silent=True) or {}
    device_id=str(body.get("device_id","")).strip()[:160]
    device_name=str(body.get("device_name","")).strip()[:80]
    platform=str(body.get("platform","android")).strip()[:32] or "android"
    if not device_id:return jsonify(error="invalid_request"),400
    now=utcnow();expires=now+timedelta(minutes=15)
    pairing_secret=secrets.token_urlsafe(32)
    with db() as con:
        con.execute("DELETE FROM pairings WHERE expires_at<=? OR (device_id=? AND customer_id IS NULL)",(iso(now),device_id))
        for _ in range(8):
            raw=make_code(8)
            try:
                con.execute("INSERT INTO pairings(code_hash,secret_hash,device_id,device_name,platform,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",(digest(raw),digest(pairing_secret),device_id,device_name,platform,iso(expires),iso(now)))
                break
            except sqlite3.IntegrityError:
                continue
        else:return jsonify(error="pairing_unavailable"),503
    return jsonify(status="pending",code=display_code(raw),pairing_secret=pairing_secret,expires_at=iso(expires)),201
@app.post("/v1/pair/status")
def pair_status():
    body=request.get_json(silent=True) or {}
    pairing_secret=str(body.get("pairing_secret","")).strip()
    if len(pairing_secret)<32:return jsonify(error="invalid_request"),400
    now=utcnow()
    with db() as con:
        row=con.execute("SELECT p.*,c.config_json,c.enabled customer_enabled FROM pairings p LEFT JOIN customers c ON c.id=p.customer_id WHERE p.secret_hash=?",(digest(pairing_secret),)).fetchone()
        if row is None:return jsonify(error="pairing_not_found"),404
        if datetime.fromisoformat(row["expires_at"].replace("Z","+00:00"))<=now:return jsonify(error="pairing_expired"),410
        if row["customer_id"] is None:return jsonify(status="pending",expires_at=row["expires_at"]),202
        if not row["customer_enabled"]:return jsonify(error="customer_disabled"),409
        session_token=pairing_session_token(pairing_secret)
        con.execute("INSERT INTO devices(customer_id,device_id,platform,session_token_hash,enabled,created_at) VALUES(?,?,?,?,1,?) ON CONFLICT(customer_id,device_id) DO UPDATE SET platform=excluded.platform,session_token_hash=excluded.session_token_hash,enabled=1",(row["customer_id"],row["device_id"],row["platform"],digest(session_token),iso(now)))
        config=customer_config(row);version=config_version(config)
    return jsonify(status="connected",session_token=session_token,customer_id=row["customer_id"],config_version=version,config=public_config(config))
@app.post("/v1/admin/devices/<int:device_id>/revoke")
def revoke_device(device_id):
    require_admin_api()
    with db() as con:cur=con.execute("UPDATE devices SET enabled=0 WHERE id=?",(device_id,))
    if cur.rowcount==0:return jsonify(error="device_not_found"),404
    return jsonify(status="revoked")
init_db()
if __name__=="__main__":app.run(host="127.0.0.1",port=int(os.environ.get("PORT","8787")))
