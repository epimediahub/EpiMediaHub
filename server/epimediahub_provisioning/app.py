from __future__ import annotations

import base64, hashlib, io, json, os, secrets, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import qrcode
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from receiver_sync import migrate as migrate_receiver_sync, register as register_receiver_sync, save_customer_config

BASE_DIR = Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")); DB_PATH = BASE_DIR / "provisioning.db"
PUBLIC_BASE_URL = os.environ.get("EPIMEDIAHUB_PUBLIC_URL", "https://setup.example.invalid").rstrip("/")
ADMIN_TOKEN = os.environ.get("EPIMEDIAHUB_ADMIN_TOKEN", ""); ADMIN_PASSWORD = os.environ.get("EPIMEDIAHUB_ADMIN_PASSWORD", "")
SECRET_KEY = os.environ.get("EPIMEDIAHUB_SECRET_KEY", secrets.token_hex(32)); CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
app = Flask(__name__); app.secret_key = SECRET_KEY; app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

def utcnow(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def normalize_code(value): return "".join(c for c in value.upper() if c.isalnum())
def display_code(raw): return "-".join(raw[i:i+4] for i in range(0,len(raw),4))
def make_code(length=12): return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
def qr_data_uri(value):
    image=qrcode.make(value); buf=io.BytesIO(); image.save(buf,format="PNG")
    return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode("ascii")
def db():
    BASE_DIR.mkdir(parents=True,exist_ok=True); con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; con.execute("PRAGMA foreign_keys=ON"); return con
def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,config_json TEXT NOT NULL DEFAULT '{}',enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS activations(id INTEGER PRIMARY KEY AUTOINCREMENT,customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,code_hash TEXT NOT NULL UNIQUE,token_hash TEXT NOT NULL UNIQUE,expires_at TEXT NOT NULL,redeemed_at TEXT,device_id TEXT,platform TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devices(id INTEGER PRIMARY KEY AUTOINCREMENT,customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,device_id TEXT NOT NULL,platform TEXT NOT NULL,session_token_hash TEXT NOT NULL UNIQUE,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(customer_id,device_id));""")
        migrate_receiver_sync(con)
def require_admin_api():
    if not ADMIN_TOKEN or not secrets.compare_digest(request.headers.get("Authorization",""),f"Bearer {ADMIN_TOKEN}"): abort(401)
def web_auth():
    if not session.get("admin"): return redirect(url_for("login",next=request.path))
def customer_config(row):
    try: return json.loads(row["config_json"] or "{}")
    except (TypeError, json.JSONDecodeError): return {}
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
        customer_rows=con.execute("SELECT * FROM customers ORDER BY id DESC").fetchall(); devices=con.execute("SELECT d.*,c.name customer_name,c.config_version customer_config_version FROM devices d JOIN customers c ON c.id=d.customer_id ORDER BY d.id DESC").fetchall()
    customers=[]
    for c in customer_rows:
        item=dict(c); item["playlist_url"]=customer_config(c).get("playlist_url",""); customers.append(item)
    return render_template("dashboard.html",customers=customers,devices=devices)
@app.post("/admin/customers")
def web_create_customer():
    guard=web_auth()
    if guard:return guard
    name=request.form.get("name","").strip(); playlist=request.form.get("playlist_url","").strip()
    if name:
        with db() as con: con.execute("INSERT INTO customers(name,config_json,created_at) VALUES(?,?,?)",(name,json.dumps({"playlist_url":playlist}),iso(utcnow())))
    return redirect(url_for("dashboard"))
@app.post("/admin/customers/<int:customer_id>/update")
def web_update_customer(customer_id):
    guard=web_auth()
    if guard:return guard
    name=request.form.get("name","").strip(); playlist=request.form.get("playlist_url","").strip()
    if not name:return redirect(url_for("dashboard"))
    with db() as con:
        row=con.execute("SELECT * FROM customers WHERE id=?",(customer_id,)).fetchone()
        if not row:abort(404)
        config=customer_config(row); config["playlist_url"]=playlist
        con.execute("UPDATE customers SET name=? WHERE id=?",(name,customer_id))
        if json.dumps(config,separators=(",",":")) != json.dumps(customer_config(row),separators=(",",":")):
            save_customer_config(con,customer_id,config)
    return redirect(url_for("dashboard"))
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
        con.execute("UPDATE devices SET customer_id=?,applied_config_version=0,last_sync_status=NULL,last_sync_error=NULL WHERE id=?",(customer_id,device_id))
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
        con.execute("BEGIN IMMEDIATE");row=con.execute(f"SELECT a.*,c.config_json,c.config_version,c.enabled customer_enabled FROM activations a JOIN customers c ON c.id=a.customer_id WHERE a.{field}=?",(digest(value),)).fetchone(); claim,error=claim_activation(row,device_id,platform)
        if error:return error
        session_token,now=claim;con.execute("UPDATE activations SET redeemed_at=?,device_id=?,platform=? WHERE id=? AND redeemed_at IS NULL",(iso(now),device_id,platform,row["id"]));con.execute("INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at,applied_config_version,last_seen_at,last_sync_at,last_sync_status) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(customer_id,device_id) DO UPDATE SET platform=excluded.platform,session_token_hash=excluded.session_token_hash,enabled=1,applied_config_version=excluded.applied_config_version,last_seen_at=excluded.last_seen_at,last_sync_at=excluded.last_sync_at,last_sync_status=excluded.last_sync_status,last_sync_error=NULL",(row["customer_id"],device_id,platform,digest(session_token),iso(now),int(row["config_version"]),iso(now),iso(now),"ok"));config=json.loads(row["config_json"])
    return jsonify(session_token=session_token,customer_id=row["customer_id"],config_version=int(row["config_version"]),config=config)
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
@app.post("/v1/admin/devices/<int:device_id>/revoke")
def revoke_device(device_id):
    require_admin_api()
    with db() as con:cur=con.execute("UPDATE devices SET enabled=0 WHERE id=?",(device_id,))
    if cur.rowcount==0:return jsonify(error="device_not_found"),404
    return jsonify(status="revoked")

init_db()
register_receiver_sync(app,db)
if __name__=="__main__":app.run(host="127.0.0.1",port=int(os.environ.get("PORT","8787")))
