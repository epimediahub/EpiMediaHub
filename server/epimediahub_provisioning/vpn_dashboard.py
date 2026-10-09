"""Additive Finland VPN administration. Never stores client private keys.

The dashboard's desired state is distinct from the WireGuard agent's applied
state. App 1.0.40 imports profiles locally and does not report speedtest data.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import abort, flash, jsonify, redirect, render_template, request, session

VERSION = "1.0.0"
LEASE_SECONDS = 60
BETA_URL = "https://github.com/epimediahub/EpiMediaHub/releases/download/vpnfi40/EpiFI.apk"


def now():
    return datetime.now(timezone.utc)


def stamp(value=None):
    return (value or now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class Invalid(ValueError):
    pass


def integer(value, minimum=1, maximum=10000):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise Invalid("Bitte eine gültige ganze Zahl eingeben.") from None
    if not minimum <= result <= maximum:
        raise Invalid(f"Der Wert muss zwischen {minimum} und {maximum} liegen.")
    return result


def price(value):
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"\d{1,6}([.,]\d{1,2})?", value):
        raise Invalid("Bitte einen gültigen Eurobetrag mit höchstens zwei Nachkommastellen eingeben.")
    whole, _, fraction = value.replace(",", ".").partition(".")
    return int(whole) * 100 + int(fraction.ljust(2, "0"))


def public_key(value):
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != 32 or not any(decoded) or base64.b64encode(decoded).decode() != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise Invalid("Bitte den öffentlichen WireGuard-Geräteschlüssel eingeben (kein privates Profil).") from None
    return value


def client_address(value):
    try:
        address = ipaddress.ip_address(value.removesuffix("/32"))
        network = ipaddress.ip_network(os.environ.get("EPIMEDIAHUB_VPN_SUBNET", "10.92.0.0/24"))
        if address.version != 4 or address not in network or int(address) <= int(network.network_address) + 1 or address == network.broadcast_address:
            raise ValueError()
    except ValueError:
        raise Invalid("Bitte eine freie Geräteadresse im Finnland-VPN eingeben, z. B. 10.92.0.2.") from None
    return str(address) + "/32"


def migrate(con):
    required = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"devices", "customers", "resellers"} <= required:
        raise RuntimeError("Das bestehende Admin-/Reseller-Dashboard muss zuerst installiert sein.")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS vpn_plans(
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, days INTEGER NOT NULL CHECK(days BETWEEN 1 AND 366),
      credits INTEGER NOT NULL CHECK(credits BETWEEN 1 AND 10000), enabled INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS vpn_accounts(
      reseller_id INTEGER PRIMARY KEY REFERENCES resellers(id) ON DELETE CASCADE,
      price_cents INTEGER CHECK(price_cents >= 0));
    CREATE TABLE IF NOT EXISTS vpn_orders(
      id INTEGER PRIMARY KEY, reseller_id INTEGER REFERENCES resellers(id) ON DELETE SET NULL,
      quantity INTEGER NOT NULL, unit_price_cents INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
      created_at TEXT NOT NULL, processed_at TEXT);
    CREATE TABLE IF NOT EXISTS vpn_credits(
      id INTEGER PRIMARY KEY, reseller_id INTEGER REFERENCES resellers(id) ON DELETE SET NULL,
      amount INTEGER NOT NULL, kind TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
      note TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS vpn_devices(
      id INTEGER PRIMARY KEY, device_row_id INTEGER UNIQUE REFERENCES devices(id) ON DELETE SET NULL,
      bound_customer_id INTEGER NOT NULL, owner_reseller_id INTEGER,
      public_key TEXT NOT NULL UNIQUE, client_address TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'SUSPENDED', expires_at TEXT, revision INTEGER NOT NULL DEFAULT 1,
      applied_generation TEXT, applied_enabled INTEGER, applied_at TEXT, last_handshake INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS vpn_live_address ON vpn_devices(client_address) WHERE device_row_id IS NOT NULL;
    CREATE TABLE IF NOT EXISTS vpn_audit(
      id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS vpn_operations(id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS vpn_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)


JOINED = """SELECT v.*,d.device_id,d.display_name,d.customer_id current_customer_id,d.enabled device_enabled,c.enabled customer_enabled,
 c.name customer_name,c.reseller_id current_reseller_id,r.name reseller_name,r.enabled reseller_enabled
 FROM vpn_devices v LEFT JOIN devices d ON d.id=v.device_row_id
 LEFT JOIN customers c ON c.id=d.customer_id LEFT JOIN resellers r ON r.id=c.reseller_id"""


def desired(row, at=None):
    at = at or now()
    enabled = bool(row["device_row_id"] and row["device_enabled"] and row["customer_enabled"]
                   and row["status"] == "ACTIVE" and row["expires_at"] and instant(row["expires_at"]) > at
                   and row["owner_reseller_id"] == row["current_reseller_id"]
                   and row["bound_customer_id"] == row["current_customer_id"]
                   and (row["current_reseller_id"] is None or row["reseller_enabled"]))
    value = dict(id=row["id"], public_key=row["public_key"], client_address=row["client_address"],
                 enabled=enabled, expires_at=row["expires_at"], revision=row["revision"])
    value["generation"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value


def balance(con, reseller_id):
    return con.execute("SELECT COALESCE(SUM(amount),0) FROM vpn_credits WHERE reseller_id=?", (reseller_id,)).fetchone()[0]


def fresh(con):
    row = con.execute("SELECT value FROM vpn_meta WHERE key='agent_applied_at'").fetchone()
    return bool(row and now() - instant(row[0]) < timedelta(seconds=LEASE_SECONDS))


def install(app, db):
    if app.extensions.get("epimediahub_vpn"):
        return
    with db() as con:
        migrate(con)
    from vpn_autoprovision import install as install_vpn_auto
    install_vpn_auto(app, db)
    app.extensions["epimediahub_vpn"] = VERSION
    app.add_template_filter(lambda value: instant(value).astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y · %H:%M") if value else "–", "vpn_date")

    def actor(admin):
        if admin:
            return "admin" if session.get("admin") else None
        rid = session.get("reseller_id")
        with db() as con:
            row = con.execute("SELECT id FROM resellers WHERE id=? AND enabled=1", (rid,)).fetchone()
        return f"reseller:{row[0]}" if row else None

    def csrf():
        if "vpn_csrf" not in session:
            session["vpn_csrf"] = secrets.token_urlsafe(32)
        return session["vpn_csrf"]

    def device(con, row_id, admin):
        row = con.execute("""SELECT d.*,c.reseller_id,c.name customer_name,c.enabled customer_enabled,
                            r.enabled reseller_enabled FROM devices d JOIN customers c ON c.id=d.customer_id
                            LEFT JOIN resellers r ON r.id=c.reseller_id WHERE d.id=?""", (row_id,)).fetchone()
        if not row or (not admin and row["reseller_id"] != session.get("reseller_id")):
            abort(404)
        return row

    def usable(row):
        if not row["enabled"] or not row["customer_enabled"] or (row["reseller_id"] is not None and not row["reseller_enabled"]):
            raise Invalid("Kunde, Gerät oder Reseller ist gesperrt.")
        if "android" not in row["platform"].lower() and "fire" not in row["platform"].lower():
            raise Invalid("Die VPN-Beta ist für Android- und Fire-TV-Geräte vorgesehen.")

    def audit(con, who, action, **detail):
        con.execute("INSERT INTO vpn_audit(actor,action,detail_json,created_at) VALUES(?,?,?,?)",
                    (who, action, json.dumps(detail, ensure_ascii=False), stamp()))

    def page(admin):
        who = actor(admin)
        if not who:
            return redirect("/admin/login" if admin else "/reseller/login")
        rid = None if admin else session["reseller_id"]
        with db() as con:
            scope, args = ("", ()) if admin else (" WHERE c.reseller_id=?", (rid,))
            devices = [dict(r) for r in con.execute("""SELECT d.id,d.device_id,d.display_name,d.platform,d.enabled,
                       c.name customer_name,c.reseller_id,r.name reseller_name FROM devices d
                       JOIN customers c ON c.id=d.customer_id LEFT JOIN resellers r ON r.id=c.reseller_id"""
                       + scope + " ORDER BY c.name,d.id", args)]
            entries = [dict(r) for r in con.execute(JOINED + (" WHERE v.device_row_id IS NOT NULL" if admin else " WHERE c.reseller_id=?"), args)]
            by_device = {}
            for row in entries:
                state = desired(row)
                row["allowed"] = state["enabled"]
                row["confirmed"] = row["applied_generation"] == state["generation"] and bool(row["applied_at"]) and now() - instant(row["applied_at"]) < timedelta(seconds=LEASE_SECONDS)
                row["expired"] = bool(row["expires_at"] and instant(row["expires_at"]) <= now())
                row["state_label"] = ("Freigegeben" if state["enabled"] else "Abgelaufen" if row["expired"] else "Gesperrt") if row["confirmed"] else "Bestätigung offen"
                by_device[row["device_row_id"]] = row
            for row in devices:
                pending = con.execute("SELECT days,source FROM vpn_pending_grants WHERE device_row_id=?",
                                      (row["id"],)).fetchone()
                row["pending"] = dict(pending) if pending else None
                row["vpn"] = by_device.get(row["id"])
            plans = [dict(r) for r in con.execute("SELECT * FROM vpn_plans ORDER BY id")]
            resellers = [dict(r) for r in con.execute("SELECT r.id,r.name,r.enabled,a.price_cents FROM resellers r LEFT JOIN vpn_accounts a ON a.reseller_id=r.id ORDER BY r.name")]
            for row in resellers:
                row["credits"] = balance(con, row["id"])
            orders = [dict(r) for r in con.execute("""SELECT o.*,r.name reseller_name FROM vpn_orders o
                       LEFT JOIN resellers r ON r.id=o.reseller_id""" + ("" if admin else " WHERE o.reseller_id=?") + " ORDER BY o.id DESC LIMIT 100", args)]
            ledger = [dict(r) for r in con.execute("""SELECT t.*,r.name reseller_name FROM vpn_credits t LEFT JOIN resellers r ON r.id=t.reseller_id"""
                       + ("" if admin else " WHERE t.reseller_id=?") + " ORDER BY t.id DESC LIMIT 100", args)]
            connected = fresh(con)
            last = con.execute("SELECT value FROM vpn_meta WHERE key='agent_applied_at'").fetchone()
            events = [dict(r) for r in con.execute("SELECT * FROM vpn_audit ORDER BY id DESC LIMIT 30")] if admin else []
        return render_template("vpn_dashboard.html", admin=admin, devices=devices, plans=plans, orders=orders,
                    resellers=resellers if admin else [], account=next((r for r in resellers if r["id"] == rid), None),
                    ledger=ledger, events=events, connected=connected, last_contact=last[0] if last else None,
                    csrf=csrf(), nonce=lambda: secrets.token_urlsafe(24), beta_url=BETA_URL,
                    base="/admin/vpn" if admin else "/reseller/vpn")

    def action(admin):
        who = actor(admin)
        if not who:
            abort(401)
        if not session.get("vpn_csrf") or not hmac.compare_digest(request.form.get("csrf", ""), session["vpn_csrf"]):
            abort(403)
        operation = request.form.get("operation", "")
        request_id = request.form.get("request_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{24,80}", request_id):
            abort(400)
        allowed = {"order", "activate", "suspend", "resume"} | ({"price", "credit", "plan", "plan_update", "approve", "cancel", "bind", "grant", "transfer"} if admin else set())
        if operation not in allowed:
            abort(403)
        try:
            with db() as con:
                con.execute("BEGIN IMMEDIATE")
                previous = con.execute("SELECT actor,action FROM vpn_operations WHERE id=?", (request_id,)).fetchone()
                if previous:
                    if tuple(previous) != (who, operation):
                        abort(409)
                    flash("Die Aktion wurde bereits verarbeitet.", "success")
                    return redirect("/admin/vpn" if admin else "/reseller/vpn", code=303)
                con.execute("INSERT INTO vpn_operations VALUES(?,?,?)", (request_id, who, operation))
                data = request.form
                if operation in {"plan", "plan_update"}:
                    name = data.get("name", "").strip()[:80]
                    if not name:
                        raise Invalid("Bitte einen Tarifnamen eingeben.")
                    values = (name, integer(data.get("days"), 1, 366), integer(data.get("credits")))
                    if operation == "plan":
                        con.execute("INSERT INTO vpn_plans(name,days,credits) VALUES(?,?,?)", values)
                    else:
                        result = con.execute("UPDATE vpn_plans SET name=?,days=?,credits=?,enabled=? WHERE id=?", (*values, int(data.get("enabled") == "1"), integer(data.get("plan_id"))))
                        if not result.rowcount:
                            abort(404)
                    audit(con, who, operation, name=name)
                elif operation in {"price", "credit"}:
                    rid = integer(data.get("reseller_id"))
                    if not con.execute("SELECT 1 FROM resellers WHERE id=?", (rid,)).fetchone():
                        abort(404)
                    if operation == "price":
                        cents = price(data.get("price", ""))
                        con.execute("INSERT INTO vpn_accounts(reseller_id,price_cents) VALUES(?,?) ON CONFLICT(reseller_id) DO UPDATE SET price_cents=excluded.price_cents", (rid, cents))
                        audit(con, who, operation, reseller_id=rid, cents=cents)
                    else:
                        amount = integer(data.get("amount"), -10000, 10000)
                        note = data.get("note", "").strip()[:200]
                        if not amount or not note or balance(con, rid) + amount < 0:
                            raise Invalid("Notiz und eine Buchung ohne negatives Guthaben sind erforderlich.")
                        con.execute("INSERT INTO vpn_credits(reseller_id,amount,kind,reference,note,created_at) VALUES(?,?,'manual',?,?,?)", (rid, amount, request_id, note, stamp()))
                        audit(con, who, operation, reseller_id=rid, amount=amount)
                elif operation == "order":
                    rid = integer(data.get("reseller_id")) if admin else session["reseller_id"]
                    account = con.execute("SELECT a.* FROM vpn_accounts a JOIN resellers r ON r.id=a.reseller_id WHERE a.reseller_id=? AND r.enabled=1", (rid,)).fetchone()
                    if not account or account["price_cents"] is None:
                        raise Invalid("Der Admin muss zuerst einen VPN-Creditpreis festlegen.")
                    if str(account["price_cents"]) != data.get("unit_price_cents"):
                        raise Invalid("Der Preis hat sich geändert. Bitte die Bestellung erneut prüfen.")
                    qty = integer(data.get("quantity"))
                    con.execute("INSERT INTO vpn_orders(reseller_id,quantity,unit_price_cents,created_at) VALUES(?,?,?,?)", (rid, qty, account["price_cents"], stamp()))
                    audit(con, who, operation, reseller_id=rid, quantity=qty, unit_price_cents=account["price_cents"])
                elif operation in {"approve", "cancel"}:
                    oid = integer(data.get("order_id"))
                    row = con.execute("SELECT * FROM vpn_orders WHERE id=?", (oid,)).fetchone()
                    if not row:
                        abort(404)
                    if row["status"] != "PENDING" or not row["reseller_id"]:
                        raise Invalid("Diese Bestellung ist bereits verarbeitet oder ihr Reseller wurde gelöscht.")
                    if operation == "approve":
                        con.execute("INSERT INTO vpn_credits(reseller_id,amount,kind,reference,note,created_at) VALUES(?,?,'purchase',?,?,?)", (row["reseller_id"], row["quantity"], f"order:{oid}", f"Bezahlte VPN-Bestellung #{oid}", stamp()))
                    con.execute("UPDATE vpn_orders SET status=?,processed_at=? WHERE id=?", ("PAID" if operation == "approve" else "CANCELLED", stamp(), oid))
                    audit(con, who, operation, order_id=oid)
                else:
                    target = device(con, integer(data.get("device_row_id")), admin)
                    entry = con.execute("SELECT * FROM vpn_devices WHERE device_row_id=?", (target["id"],)).fetchone()
                    if not entry and operation in {"grant", "activate"}:
                        # Admin/reseller purchase before the device first opens the
                        # VPN settings: reserve the entitlement, not a WG secret.
                        from vpn_autoprovision import ensure_pending
                        usable(target)
                        if operation == "grant":
                            days = integer(data.get("days"), 1, 366)
                            source = "admin"
                        else:
                            if not fresh(con):
                                raise Invalid("Finnland-Server nicht erreichbar. Keine VPN-Credits abgebucht.")
                            plan_parts = data.get("plan", "").split(":")
                            if len(plan_parts) != 3:
                                raise Invalid("Bitte einen VPN-Tarif auswählen.")
                            plan = con.execute("SELECT * FROM vpn_plans WHERE id=? AND enabled=1",
                                               (integer(plan_parts[0]),)).fetchone()
                            if not plan or plan_parts[1:] != [str(plan["days"]), str(plan["credits"])]:
                                raise Invalid("Dieser VPN-Tarif wurde geändert.")
                            rid = target["reseller_id"]
                            if rid is None or balance(con, rid) < plan["credits"]:
                                raise Invalid("Nicht genügend VPN-Credits.")
                            con.execute("""INSERT INTO vpn_credits(reseller_id,amount,kind,reference,note,created_at)
                                           VALUES(?,?,'activation',?,?,?)""",
                                        (rid,-plan["credits"],request_id,
                                         f"{plan['name']} · Gerät #{target['id']} (automatisch)",stamp()))
                            days = plan["days"]
                            source = "reseller"
                        ensure_pending(con, target["id"], days, source, target["reseller_id"])
                        audit(con, who, operation+"_pending", device_row_id=target["id"], days=days)
                        flash("VPN-Laufzeit zugeordnet. Das Gerät richtet den Schlüssel beim nächsten App-Start automatisch ein.", "success")
                        return redirect("/admin/vpn" if admin else "/reseller/vpn", code=303)
                    if operation == "bind":
                        usable(target)
                        if entry:
                            raise Invalid("Das Gerät besitzt bereits einen VPN-Zugang. Für einen Wechsel die Gerätewechsel-Funktion verwenden.")
                        key, address = public_key(data.get("public_key", "").strip()), client_address(data.get("client_address", "").strip())
                        con.execute("INSERT INTO vpn_devices(device_row_id,bound_customer_id,owner_reseller_id,public_key,client_address,created_at) VALUES(?,?,?,?,?,?)", (target["id"], target["customer_id"], target["reseller_id"], key, address, stamp()))
                        audit(con, who, operation, device_row_id=target["id"])
                    else:
                        if not entry:
                            raise Invalid("Zuerst muss der Admin den öffentlichen Geräteschlüssel und die VPN-Adresse zuordnen.")
                        if not admin and (entry["owner_reseller_id"] != target["reseller_id"] or entry["bound_customer_id"] != target["customer_id"]):
                            raise Invalid("Die Gerätezuordnung hat sich geändert. Bitte den Admin kontaktieren.")
                        if operation == "suspend":
                            con.execute("UPDATE vpn_devices SET status='SUSPENDED',revision=revision+1 WHERE id=?", (entry["id"],))
                        elif operation == "resume":
                            usable(target)
                            if not entry["expires_at"] or instant(entry["expires_at"]) <= now():
                                raise Invalid("Die VPN-Laufzeit ist abgelaufen. Zuerst verlängern.")
                            con.execute("UPDATE vpn_devices SET status='ACTIVE',revision=revision+1 WHERE id=?", (entry["id"],))
                        elif operation == "transfer":
                            replacement = device(con, integer(data.get("target_device_row_id")), True)
                            usable(replacement)
                            if replacement["id"] == target["id"] or replacement["reseller_id"] != target["reseller_id"]:
                                raise Invalid("Bitte ein anderes Gerät desselben Resellers auswählen.")
                            if con.execute("SELECT 1 FROM vpn_devices WHERE device_row_id=?", (replacement["id"],)).fetchone():
                                raise Invalid("Das Zielgerät besitzt bereits einen VPN-Zugang.")
                            key, address = public_key(data.get("public_key", "").strip()), client_address(data.get("client_address", "").strip())
                            con.execute("UPDATE vpn_devices SET device_row_id=NULL,status='RETIRED',revision=revision+1 WHERE id=?", (entry["id"],))
                            con.execute("INSERT INTO vpn_devices(device_row_id,bound_customer_id,owner_reseller_id,public_key,client_address,status,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?)", (replacement["id"], replacement["customer_id"], replacement["reseller_id"], key, address, entry["status"], entry["expires_at"], stamp()))
                        else:
                            usable(target)
                            if operation == "activate":
                                if not fresh(con):
                                    raise Invalid("Der Finnland-Server hat noch keine aktuelle Bestätigung gesendet. Es wurden keine Credits abgezogen.")
                                plan_parts = data.get("plan", "").split(":")
                                if len(plan_parts) != 3:
                                    raise Invalid("Bitte einen VPN-Tarif auswählen.")
                                plan = con.execute("SELECT * FROM vpn_plans WHERE id=? AND enabled=1", (integer(plan_parts[0]),)).fetchone()
                                if not plan or plan_parts[1:] != [str(plan["days"]), str(plan["credits"])]:
                                    raise Invalid("Der Tarif wurde geändert. Bitte erneut prüfen.")
                                rid = target["reseller_id"]
                                if rid is None or balance(con, rid) < plan["credits"]:
                                    raise Invalid("Nicht genügend VPN-Credits vorhanden.")
                                days = plan["days"]
                                con.execute("INSERT INTO vpn_credits(reseller_id,amount,kind,reference,note,created_at) VALUES(?,?,'activation',?,?,?)", (rid, -plan["credits"], request_id, f"{plan['name']} · Gerät #{target['id']}", stamp()))
                            else:
                                days = integer(data.get("days"), 1, 366)
                            expiry = stamp(max(now(), instant(entry["expires_at"]) or now()) + timedelta(days=days))
                            con.execute("UPDATE vpn_devices SET status='ACTIVE',expires_at=?,bound_customer_id=?,owner_reseller_id=?,revision=revision+1 WHERE id=?", (expiry, target["customer_id"], target["reseller_id"], entry["id"]))
                        audit(con, who, operation, device_row_id=target["id"])
            flash("Gespeichert. VPN-Änderungen warten bis zur Bestätigung durch den Finnland-Server.", "success")
        except Invalid as exc:
            flash(str(exc), "error")
        except sqlite3.IntegrityError:
            flash("Schlüssel, Adresse oder Gerät ist bereits zugeordnet. Die Aktion wurde nicht gebucht.", "error")
        return redirect("/admin/vpn" if admin else "/reseller/vpn", code=303)

    app.add_url_rule("/admin/vpn", "vpn_admin", lambda: page(True))
    app.add_url_rule("/reseller/vpn", "vpn_reseller", lambda: page(False))
    app.add_url_rule("/admin/vpn/action", "vpn_admin_action", lambda: action(True), methods=["POST"])
    app.add_url_rule("/reseller/vpn/action", "vpn_reseller_action", lambda: action(False), methods=["POST"])

    def agent_auth():
        token = os.environ.get("EPIMEDIAHUB_VPN_AGENT_TOKEN", "")
        if not token:
            token_file = Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")) / "vpn-agent.token"
            if token_file.exists():
                token = token_file.read_text().strip()
        if len(token) < 32 or not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + token):
            abort(401)

    @app.get("/v1/vpn-agent/desired")
    def vpn_agent_desired():
        agent_auth()
        with db() as con:
            peers = [desired(r) for r in con.execute(JOINED)]
        return jsonify(version=1, node="finland", server_time=stamp(), lease_seconds=LEASE_SECONDS, peers=peers)

    @app.post("/v1/vpn-agent/applied")
    def vpn_agent_applied():
        agent_auth()
        if request.content_length and request.content_length > 1024 * 1024:
            abort(413)
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("peers"), list) or len(body["peers"]) > 10000:
            abort(400)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            rows = {r["id"]: r for r in con.execute(JOINED)}
            seen = set()
            for report in body["peers"]:
                if not isinstance(report, dict) or type(report.get("id")) is not int or report["id"] not in rows or report["id"] in seen:
                    abort(409)
                seen.add(report["id"])
                wanted = desired(rows[report["id"]])
                if report.get("generation") != wanted["generation"] or report.get("enabled") is not wanted["enabled"]:
                    abort(409)
                handshake = report.get("last_handshake", 0)
                if type(handshake) is not int or not 0 <= handshake <= int(now().timestamp()) + 60:
                    abort(400)
                con.execute("UPDATE vpn_devices SET applied_generation=?,applied_enabled=?,applied_at=?,last_handshake=? WHERE id=?", (wanted["generation"], int(wanted["enabled"]), stamp(), handshake, wanted["id"]))
            if seen != set(rows):
                abort(409)
            con.execute("INSERT INTO vpn_meta VALUES('agent_applied_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (stamp(),))
        return jsonify(status="recorded")

    @app.after_request
    def vpn_no_cache(response):
        if request.path.startswith(("/admin/vpn", "/reseller/vpn", "/v1/vpn-agent", "/v1/device/vpn", "/v1/device/identity")):
            response.headers["Cache-Control"] = "no-store"
        return response
