from __future__ import annotations

import re
from datetime import datetime, timedelta
from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from app import app, db, digest, iso, utcnow
from dashboard_v080 import migrate_resellers, _audit

TRIAL_DAYS = 7
RETAIL_LICENSE_PRICE_EUR_CENTS = 1000
DEFAULT_RESELLER_ID = None  # Direct customers do not consume reseller credits.

def _price_cents(value):
    """An empty price is unset; accept exact euro amounts without float rounding."""
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"[0-9]{1,6}(?:[.,][0-9]{1,2})?", value):
        raise ValueError("invalid_price")
    whole, _, fraction = value.replace(",", ".").partition(".")
    return int(whole) * 100 + int(fraction.ljust(2, "0"))

@app.template_filter("eur")
def _format_eur(cents):
    return f"{int(cents) // 100},{int(cents) % 100:02d}"

def _has_column(con, table, column):
    return column in {row[1] for row in con.execute(f"PRAGMA table_info({table})")}

def _balance(con, reseller_id):
    row=con.execute("SELECT COALESCE(SUM(amount),0) balance FROM credit_transactions WHERE reseller_id=?",(reseller_id,)).fetchone()
    return int(row["balance"] or 0)

def _admin_guard():
    return None if session.get("admin") else redirect(url_for("login",next=request.path))

def _reseller_row():
    try: reseller_id=int(session.get("reseller_id",0))
    except (TypeError,ValueError): return None
    if reseller_id<=0:return None
    with db() as con:return con.execute("SELECT * FROM resellers WHERE id=? AND enabled=1",(reseller_id,)).fetchone()

def ensure_license_schema():
    now=iso(utcnow())
    with db() as con:
        migrate_resellers(con)
        con.executescript("""
        CREATE TABLE IF NOT EXISTS credit_transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,reseller_id INTEGER NOT NULL REFERENCES resellers(id) ON DELETE CASCADE,
          amount INTEGER NOT NULL,kind TEXT NOT NULL,license_id INTEGER,note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS license_subjects(
          id INTEGER PRIMARY KEY AUTOINCREMENT,trial_key_hash TEXT NOT NULL UNIQUE,current_device_id TEXT NOT NULL DEFAULT '',
          platform TEXT NOT NULL DEFAULT 'android',trial_started_at TEXT NOT NULL,trial_expires_at TEXT NOT NULL,
          created_at TEXT NOT NULL,last_seen_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lifetime_licenses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,subject_id INTEGER NOT NULL UNIQUE REFERENCES license_subjects(id) ON DELETE CASCADE,
          reseller_id INTEGER REFERENCES resellers(id) ON DELETE RESTRICT,customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
          activated_device_id TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'ACTIVE',source TEXT NOT NULL DEFAULT 'credit',
          activated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS legacy_device_entitlements(device_id TEXT PRIMARY KEY,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS license_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS credit_orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT,reseller_id INTEGER NOT NULL REFERENCES resellers(id) ON DELETE CASCADE,
          credits INTEGER NOT NULL,amount_cents INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',
          created_at TEXT NOT NULL,processed_at TEXT,note TEXT NOT NULL DEFAULT '');
        """)
        con.execute("BEGIN IMMEDIATE")
        if not _has_column(con,"customers","reseller_id"):con.execute("ALTER TABLE customers ADD COLUMN reseller_id INTEGER")
        if not _has_column(con,"resellers","credit_price_cents"):
            con.execute("ALTER TABLE resellers ADD COLUMN credit_price_cents INTEGER CHECK(credit_price_cents >= 0)")
        if con.execute("SELECT 1 FROM license_meta WHERE key='grandfathered_existing_devices_v1'").fetchone() is None:
            con.execute("INSERT OR IGNORE INTO legacy_device_entitlements(device_id,created_at) SELECT device_id,? FROM devices",(now,))
            con.execute("INSERT INTO license_meta(key,value) VALUES('grandfathered_existing_devices_v1',?)",(now,))

def _subject_status(con, subject, now):
    lic=con.execute("""SELECT l.*,r.name reseller_name FROM lifetime_licenses l LEFT JOIN resellers r ON r.id=l.reseller_id
                       WHERE l.subject_id=? AND l.status='ACTIVE' LIMIT 1""",(subject["id"],)).fetchone()
    if lic:
        return dict(status="LIFETIME_ACTIVE",lifetime=True,license_id=lic["id"],activated_at=lic["activated_at"],
                    reseller_name=lic["reseller_name"] or "EpiMediaHub Direct",remaining_seconds=None,trial_started_at=subject["trial_started_at"],
                    trial_expires_at=subject["trial_expires_at"],credit_cost=1)
    expires=datetime.fromisoformat(subject["trial_expires_at"].replace("Z","+00:00"))
    remaining=max(0,int((expires-now).total_seconds()))
    return dict(status="TRIAL_ACTIVE" if remaining>0 else "TRIAL_EXPIRED",lifetime=False,license_id=None,activated_at=None,
                reseller_name=None,remaining_seconds=remaining,trial_started_at=subject["trial_started_at"],
                trial_expires_at=subject["trial_expires_at"],credit_cost=1)

def _activate_subject(con, subject_id, reseller_id, customer_id, device_id, *, admin_grant=False):
    # Free lifetime is a privileged *admin* operation, never a user-controlled
    # license parameter. No paid-order receipt or reseller credit is fabricated.
    if admin_grant and not session.get("admin"):
        raise PermissionError("Administrator session required for gratis activation")
    existing=con.execute("SELECT * FROM lifetime_licenses WHERE subject_id=? AND status='ACTIVE'",(subject_id,)).fetchone()
    if existing:return existing,False,None
    if reseller_id is not None:
        reseller=con.execute("SELECT id,enabled FROM resellers WHERE id=?",(reseller_id,)).fetchone()
        if reseller is None or not reseller["enabled"]:return None,False,"reseller_invalid"
        if not admin_grant and _balance(con,reseller_id)<1:return None,False,"no_credits"
    now=iso(utcnow())
    license_id=con.execute("""INSERT INTO lifetime_licenses(subject_id,reseller_id,customer_id,activated_device_id,status,source,activated_at)
                              VALUES(?,?,?,?, 'ACTIVE',?,?)""",(subject_id,reseller_id,customer_id,device_id,"admin_grant" if admin_grant else ("retail" if reseller_id is None else "credit"),now)).lastrowid
    if admin_grant:
        _audit(con,"admin",None,"free_lifetime_granted","lifetime_license",license_id,
               amount_eur_cents=0,credits_charged=0,device_id=device_id)
    elif reseller_id is not None:
        con.execute("""INSERT INTO credit_transactions(reseller_id,amount,kind,license_id,note,created_at)
                       VALUES(?,-1,'activation',?,?,?)""",(reseller_id,license_id,f"Lifetime-Aktivierung {device_id}",now))
    else:
        _audit(con,"admin",None,"retail_payment_confirmed","lifetime_license",license_id,
               amount_eur_cents=RETAIL_LICENSE_PRICE_EUR_CENTS,device_id=device_id)
    return con.execute("SELECT * FROM lifetime_licenses WHERE id=?",(license_id,)).fetchone(),True,None

@app.get("/v1/license/capabilities")
def license_capabilities():
    response=jsonify(licensing_ready=True,license_version="1.0.20",trial_days=TRIAL_DAYS,
                     activation_credits=1,retail_price_eur_cents=RETAIL_LICENSE_PRICE_EUR_CENTS,
                     manual_reseller_prices=True)
    response.headers["Cache-Control"]="no-store"
    return response

@app.post("/v1/license/status")
def license_status():
    body=request.get_json(silent=True) or {}
    if not isinstance(body,dict):return jsonify(error="invalid_request"),400
    device_id=str(body.get("device_id","")).strip()[:160]
    trial_key=str(body.get("trial_key","")).strip().lower()
    platform=str(body.get("platform","android")).strip()[:32] or "android"
    if not device_id or len(trial_key)<32:return jsonify(error="invalid_request"),400
    now=utcnow();trial_hash=digest("trial-key-v1:"+trial_key)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        subject=con.execute("SELECT * FROM license_subjects WHERE trial_key_hash=?",(trial_hash,)).fetchone()
        if subject is None:
            started=iso(now);expires=iso(now+timedelta(days=TRIAL_DAYS))
            sid=con.execute("""INSERT INTO license_subjects(trial_key_hash,current_device_id,platform,trial_started_at,trial_expires_at,created_at,last_seen_at)
                               VALUES(?,?,?,?,?,?,?)""",(trial_hash,device_id,platform,started,expires,started,started)).lastrowid
            subject=con.execute("SELECT * FROM license_subjects WHERE id=?",(sid,)).fetchone()
        else:
            con.execute("UPDATE license_subjects SET current_device_id=?,platform=?,last_seen_at=? WHERE id=?",
                        (device_id,platform,iso(now),subject["id"]))
            subject=con.execute("SELECT * FROM license_subjects WHERE id=?",(subject["id"],)).fetchone()
            con.execute("""UPDATE lifetime_licenses SET activated_device_id=?
                           WHERE subject_id=? AND status='ACTIVE'""",(device_id,subject["id"]))
        legacy=con.execute("SELECT 1 FROM legacy_device_entitlements WHERE device_id=?",(device_id,)).fetchone()
        active=con.execute("SELECT 1 FROM lifetime_licenses WHERE subject_id=? AND status='ACTIVE'",(subject["id"],)).fetchone()
        if legacy and active is None:
            device=con.execute("SELECT customer_id FROM devices WHERE device_id=? ORDER BY id DESC LIMIT 1",(device_id,)).fetchone()
            customer_id=device["customer_id"] if device else None;reseller_id=DEFAULT_RESELLER_ID
            if customer_id is not None:
                owner=con.execute("SELECT reseller_id FROM customers WHERE id=?",(customer_id,)).fetchone()
                if owner and owner["reseller_id"]:reseller_id=int(owner["reseller_id"])
            con.execute("""INSERT INTO lifetime_licenses(subject_id,reseller_id,customer_id,activated_device_id,status,source,activated_at)
                           VALUES(?,?,?,?, 'ACTIVE','grandfathered',?)""",(subject["id"],reseller_id,customer_id,device_id,iso(now)))
            con.execute("DELETE FROM legacy_device_entitlements WHERE device_id=?",(device_id,))
        payload=_subject_status(con,subject,now)
    return jsonify(payload)




@app.get("/reseller/credits")
def reseller_dashboard():
    reseller=_reseller_row()
    if reseller is None:return redirect(url_for("v080_reseller_login"))
    with db() as con:
        credits=_balance(con,reseller["id"])
        customers=con.execute("SELECT * FROM customers WHERE reseller_id=? ORDER BY id DESC",(reseller["id"],)).fetchall()
        devices=con.execute("""SELECT d.*,c.name customer_name,s.id subject_id,s.trial_expires_at,l.id license_id,l.status license_status
                               FROM devices d JOIN customers c ON c.id=d.customer_id
                               LEFT JOIN license_subjects s ON s.current_device_id=d.device_id
                               LEFT JOIN lifetime_licenses l ON l.subject_id=s.id AND l.status='ACTIVE'
                               WHERE c.reseller_id=? ORDER BY d.id DESC""",(reseller["id"],)).fetchall()
        transactions=con.execute("SELECT * FROM credit_transactions WHERE reseller_id=? ORDER BY id DESC LIMIT 100",(reseller["id"],)).fetchall()
        orders=con.execute("SELECT * FROM credit_orders WHERE reseller_id=? ORDER BY id DESC LIMIT 25",(reseller["id"],)).fetchall()
    return render_template("reseller_credits_v120.html",reseller=reseller,credits=credits,
                           retail_price_cents=RETAIL_LICENSE_PRICE_EUR_CENTS,
                           customers=customers,devices=devices,transactions=transactions,orders=orders,
                           notice=request.args.get("notice",""))




@app.post("/reseller/devices/<int:device_row_id>/activate-lifetime")
def reseller_activate_device(device_row_id):
    reseller=_reseller_row()
    if reseller is None:return redirect(url_for("v080_reseller_login"))
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        device=con.execute("""SELECT d.*,c.reseller_id FROM devices d JOIN customers c ON c.id=d.customer_id
                              WHERE d.id=? AND c.reseller_id=?""",(device_row_id,reseller["id"])).fetchone()
        if device is None:abort(404)
        subject=con.execute("SELECT * FROM license_subjects WHERE current_device_id=? ORDER BY id DESC LIMIT 1",(device["device_id"],)).fetchone()
        if subject is None:return redirect(url_for("reseller_dashboard",notice="license_subject_missing"))
        _,charged,error=_activate_subject(con,subject["id"],reseller["id"],device["customer_id"],device["device_id"])
        if error:return redirect(url_for("reseller_dashboard",notice=error))
    return redirect(url_for("reseller_dashboard",notice="activated" if charged else "already_active"))

def _transfer_license(con, license_id, reseller_id, target_device_row_id, enforce_limit=True):
    license_row=con.execute("""SELECT * FROM lifetime_licenses
                               WHERE id=? AND reseller_id IS ? AND status='ACTIVE'""",(license_id,reseller_id)).fetchone()
    if license_row is None:return None,"license_not_found"
    if enforce_limit:
        used=con.execute("""SELECT COUNT(*) count FROM credit_transactions
                            WHERE reseller_id=? AND license_id=? AND kind='license_transfer'""",
                         (reseller_id,license_id)).fetchone()["count"]
        if int(used or 0)>=2:return None,"transfer_limit"
    target=con.execute("""SELECT d.*,c.reseller_id FROM devices d JOIN customers c ON c.id=d.customer_id
                          WHERE d.id=? AND c.reseller_id IS ? AND d.enabled=1""",
                       (target_device_row_id,reseller_id)).fetchone()
    if target is None:return None,"target_invalid"
    subject=con.execute("""SELECT * FROM license_subjects WHERE current_device_id=?
                           ORDER BY id DESC LIMIT 1""",(target["device_id"],)).fetchone()
    if subject is None:return None,"license_subject_missing"
    if int(subject["id"])==int(license_row["subject_id"]):return None,"target_same"
    occupied=con.execute("""SELECT id FROM lifetime_licenses
                            WHERE subject_id=? AND status='ACTIVE' AND id<>?""",
                         (subject["id"],license_id)).fetchone()
    if occupied is not None:return None,"target_already_active"
    old_device=license_row["activated_device_id"]
    old_subject_id=license_row["subject_id"]
    now=iso(utcnow())
    con.execute("UPDATE license_subjects SET trial_expires_at=? WHERE id=?",(now,old_subject_id))
    con.execute("""UPDATE lifetime_licenses
                   SET subject_id=?,customer_id=?,activated_device_id=?,source='transfer',activated_at=?
                   WHERE id=?""",
                (subject["id"],target["customer_id"],target["device_id"],now,license_id))
    if reseller_id is not None:
        con.execute("""INSERT INTO credit_transactions(reseller_id,amount,kind,license_id,note,created_at)
                       VALUES(?,0,'license_transfer',?,?,?)""",
                    (reseller_id,license_id,f"Gerätewechsel {old_device} -> {target['device_id']}",now))
    else:
        _audit(con,"admin",None,"license_transfer","lifetime_license",license_id,
               old_device=old_device,new_device=target["device_id"])
    return target,None

@app.post("/reseller/licenses/<int:license_id>/transfer")
def reseller_transfer_license(license_id):
    reseller=_reseller_row()
    if reseller is None:return redirect(url_for("v080_reseller_login"))
    try:target_device_row_id=int(request.form.get("target_device_row_id",""))
    except ValueError:return redirect(url_for("reseller_dashboard",notice="target_invalid"))
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        _,error=_transfer_license(con,license_id,reseller["id"],target_device_row_id,enforce_limit=True)
        if error:return redirect(url_for("reseller_dashboard",notice=error))
    return redirect(url_for("reseller_dashboard",notice="license_transferred"))

@app.post("/admin/licenses/<int:license_id>/transfer")
def admin_transfer_license(license_id):
    guard=_admin_guard()
    if guard:return guard
    try:target_device_row_id=int(request.form.get("target_device_row_id",""))
    except ValueError:return redirect(url_for("admin_credits",notice="target_invalid"))
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        license_row=con.execute("SELECT reseller_id FROM lifetime_licenses WHERE id=? AND status='ACTIVE'",(license_id,)).fetchone()
        if license_row is None:abort(404)
        _,error=_transfer_license(con,license_id,license_row["reseller_id"],target_device_row_id,enforce_limit=False)
        if error:return redirect(url_for("admin_credits",notice=error))
    return redirect(url_for("admin_credits",notice="license_transferred"))

@app.post("/reseller/credit-orders")
def reseller_create_credit_order():
    reseller=_reseller_row()
    if reseller is None:return redirect(url_for("v080_reseller_login"))
    try:credits=int(request.form.get("credits","0"))
    except ValueError:credits=0
    if credits not in {10,25,50,100}:return redirect(url_for("reseller_dashboard",notice="credit_order_invalid"))
    now=iso(utcnow())
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        current=con.execute("SELECT credit_price_cents FROM resellers WHERE id=? AND enabled=1",(reseller["id"],)).fetchone()
        if current is None:return redirect(url_for("v080_reseller_login"))
        price=current["credit_price_cents"]
        if price is None:return redirect(url_for("reseller_dashboard",notice="credit_price_missing"))
        try:quoted_price=int(request.form.get("unit_price_cents",""))
        except ValueError:quoted_price=None
        if quoted_price != price:return redirect(url_for("reseller_dashboard",notice="credit_price_changed"))
        con.execute("""INSERT INTO credit_orders(reseller_id,credits,amount_cents,status,created_at)
                       VALUES(?,?,?,'PENDING',?)""",
                    (reseller["id"],credits,credits*price,now))
    return redirect(url_for("reseller_dashboard",notice="credit_order_created"))

@app.get("/admin/credits")
def admin_credits():
    guard=_admin_guard()
    if guard:return guard
    with db() as con:
        resellers=[]
        for r in con.execute("SELECT * FROM resellers ORDER BY id").fetchall():
            item=dict(r);item["login_name"]=item["username"];item["credits"]=_balance(con,r["id"]);resellers.append(item)
        customers=con.execute("SELECT c.*,r.name reseller_name FROM customers c LEFT JOIN resellers r ON r.id=c.reseller_id ORDER BY c.id DESC").fetchall()
        devices=con.execute("""SELECT d.*,c.name customer_name,c.reseller_id,r.name reseller_name,s.id subject_id,s.trial_started_at,s.trial_expires_at,
                               l.id license_id,l.status license_status,l.source license_source FROM devices d JOIN customers c ON c.id=d.customer_id
                               LEFT JOIN resellers r ON r.id=c.reseller_id LEFT JOIN license_subjects s ON s.current_device_id=d.device_id
                               LEFT JOIN lifetime_licenses l ON l.subject_id=s.id AND l.status='ACTIVE' ORDER BY d.id DESC""").fetchall()
        tx=con.execute("""SELECT t.*,r.name reseller_name FROM credit_transactions t JOIN resellers r ON r.id=t.reseller_id ORDER BY t.id DESC LIMIT 200""").fetchall()
        orders=con.execute("""SELECT o.*,r.name reseller_name FROM credit_orders o JOIN resellers r ON r.id=o.reseller_id
                              ORDER BY CASE o.status WHEN 'PENDING' THEN 0 ELSE 1 END,o.id DESC LIMIT 200""").fetchall()
    return render_template("credits_v120.html",resellers=resellers,customers=customers,devices=devices,transactions=tx,orders=orders,
                           retail_price_cents=RETAIL_LICENSE_PRICE_EUR_CENTS,direct_reseller_id=DEFAULT_RESELLER_ID,
                           notice=request.args.get("notice",""))

@app.post("/admin/credit-orders/<int:order_id>/approve")
def admin_approve_credit_order(order_id):
    guard=_admin_guard()
    if guard:return guard
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        order=con.execute("SELECT * FROM credit_orders WHERE id=?",(order_id,)).fetchone()
        if order is None:abort(404)
        if order["status"]!="PENDING":return redirect(url_for("admin_credits",notice="credit_order_already_processed"))
        now=iso(utcnow())
        con.execute("UPDATE credit_orders SET status='PAID',processed_at=? WHERE id=?",(now,order_id))
        con.execute("""INSERT INTO credit_transactions(reseller_id,amount,kind,note,created_at)
                       VALUES(?,?,'purchase',?,?)""",
                    (order["reseller_id"],order["credits"],f"Credit-Bestellung #{order_id} bezahlt",now))
    return redirect(url_for("admin_credits",notice="credit_order_approved"))

@app.post("/admin/credit-orders/<int:order_id>/cancel")
def admin_cancel_credit_order(order_id):
    guard=_admin_guard()
    if guard:return guard
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        order=con.execute("SELECT status FROM credit_orders WHERE id=?",(order_id,)).fetchone()
        if order is None:abort(404)
        if order["status"]!="PENDING":return redirect(url_for("admin_credits",notice="credit_order_already_processed"))
        con.execute("UPDATE credit_orders SET status='CANCELLED',processed_at=? WHERE id=?",(iso(utcnow()),order_id))
    return redirect(url_for("admin_credits",notice="credit_order_cancelled"))


@app.post("/admin/resellers/<int:reseller_id>/price")
def admin_set_reseller_price(reseller_id):
    guard=_admin_guard()
    if guard:return guard
    try:price=_price_cents(request.form.get("credit_price_eur",""))
    except ValueError:return redirect(url_for("admin_credits",notice="credit_price_invalid"))
    with db() as con:
        if con.execute("UPDATE resellers SET credit_price_cents=? WHERE id=?",(price,reseller_id)).rowcount==0:
            abort(404)
    return redirect(url_for("admin_credits",notice="credit_price_updated"))

@app.post("/admin/resellers/<int:reseller_id>/credits")
def admin_adjust_credits(reseller_id):
    guard=_admin_guard()
    if guard:return guard
    try:amount=int(request.form.get("amount","0"))
    except ValueError:amount=0
    note=request.form.get("note","").strip()[:180]
    if amount==0:return redirect(url_for("admin_credits",notice="credit_invalid"))
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT id FROM resellers WHERE id=?",(reseller_id,)).fetchone() is None:abort(404)
        if _balance(con,reseller_id)+amount<0:return redirect(url_for("admin_credits",notice="credit_negative"))
        con.execute("INSERT INTO credit_transactions(reseller_id,amount,kind,note,created_at) VALUES(?,?,'admin_adjustment',?,?)",
                    (reseller_id,amount,note or "Admin-Anpassung",iso(utcnow())))
    return redirect(url_for("admin_credits",notice="credits_updated"))


@app.post("/admin/devices/<int:device_row_id>/grant-lifetime")
def admin_grant_lifetime(device_row_id):
    guard=_admin_guard()
    if guard:return guard
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        device=con.execute("""SELECT d.*,c.reseller_id FROM devices d
                              JOIN customers c ON c.id=d.customer_id WHERE d.id=?""",
                           (device_row_id,)).fetchone()
        if device is None:abort(404)
        subject=con.execute("""SELECT * FROM license_subjects
                               WHERE current_device_id=? ORDER BY id DESC LIMIT 1""",
                            (device["device_id"],)).fetchone()
        if subject is None:
            return redirect(url_for("admin_credits",notice="license_subject_missing"))
        _,created,error=_activate_subject(
            con,subject["id"],device["reseller_id"],device["customer_id"],
            device["device_id"],admin_grant=True
        )
        if error:return redirect(url_for("admin_credits",notice=error))
    return redirect(url_for("admin_credits",
                            notice="admin_granted" if created else "already_active"))


@app.post("/admin/devices/<int:device_row_id>/activate-lifetime")
def admin_activate_device(device_row_id):
    guard=_admin_guard()
    if guard:return guard
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        device=con.execute("SELECT d.*,c.reseller_id FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.id=?",(device_row_id,)).fetchone()
        if device is None:abort(404)
        reseller_id=device["reseller_id"]
        if reseller_id is None and request.form.get("retail_payment_confirmed")!="yes":
            return redirect(url_for("admin_credits",notice="retail_payment_required"))
        subject=con.execute("SELECT * FROM license_subjects WHERE current_device_id=? ORDER BY id DESC LIMIT 1",(device["device_id"],)).fetchone()
        if subject is None:return redirect(url_for("admin_credits",notice="license_subject_missing"))
        _,charged,error=_activate_subject(con,subject["id"],reseller_id,device["customer_id"],device["device_id"])
        if error:return redirect(url_for("admin_credits",notice=error))
    notice="retail_activated" if charged and reseller_id is None else "activated" if charged else "already_active"
    return redirect(url_for("admin_credits",notice=notice))

@app.post("/admin/license-subjects/<int:subject_id>/reset-trial")
def admin_reset_trial(subject_id):
    guard=_admin_guard()
    if guard:return guard
    now=utcnow()
    with db() as con:
        if con.execute("UPDATE license_subjects SET trial_started_at=?,trial_expires_at=?,last_seen_at=? WHERE id=?",
                       (iso(now),iso(now+timedelta(days=TRIAL_DAYS)),iso(now),subject_id)).rowcount==0:abort(404)
    return redirect(url_for("admin_credits",notice="trial_reset"))

ensure_license_schema()

# Keep existing account-management routes and protect the newly attached history.
if "v080_delete_reseller" in app.view_functions:
    _original_delete_reseller=app.view_functions["v080_delete_reseller"]
    def _delete_reseller_with_credit_history(reseller_id):
        guard=_admin_guard()
        if guard:return guard
        with db() as con:
            has_history=any(con.execute(f"SELECT 1 FROM {table} WHERE reseller_id=? LIMIT 1",(reseller_id,)).fetchone()
                            for table in ("credit_transactions","credit_orders","lifetime_licenses"))
        if has_history:
            flash("Reseller mit Credit- oder Lizenzverlauf bitte deaktivieren; der Verlauf bleibt erhalten.","warning")
            return redirect(url_for("dashboard",_anchor="resellers"))
        return _original_delete_reseller(reseller_id)
    app.view_functions["v080_delete_reseller"]=_delete_reseller_with_credit_history
