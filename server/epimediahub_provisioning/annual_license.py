"""Time-limited app entitlement alongside, never replacing, Lifetime/credit licenses.

Legacy Android builds only understand TRIAL_ACTIVE; serve a 365-day compatible
active lease with an explicit entitlement_type=ANNUAL. Newer clients can opt in
to ANNUAL_ACTIVE via supported_entitlements. Server expiration is authoritative.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import abort, flash, jsonify, redirect, request, session, url_for

from app import app, db, digest, iso, utcnow
from dashboard_v080 import _audit
import license_api  # Existing credit/7-day/Lifetime routes and schema

YEAR_DAYS = 365
TABLE = "annual_device_licenses"


def _parse(text):
    return datetime.fromisoformat(str(text).replace("Z", "+00:00")).astimezone(timezone.utc)


def _migrate():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS annual_device_licenses(
                device_id TEXT PRIMARY KEY,
                granted_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                renewed_at TEXT,
                granted_by TEXT NOT NULL DEFAULT 'admin',
                bound_trial_key_hash TEXT NOT NULL DEFAULT ''
            )
        """)
        columns = {row[1] for row in con.execute("PRAGMA table_info(annual_device_licenses)")}
        if "bound_trial_key_hash" not in columns:
            con.execute("ALTER TABLE annual_device_licenses ADD COLUMN bound_trial_key_hash TEXT NOT NULL DEFAULT ''")


def _device(con, row_id):
    item = con.execute("""SELECT d.*,c.enabled customer_enabled
        FROM devices d JOIN customers c ON c.id=d.customer_id
        WHERE d.id=?""", (row_id,)).fetchone()
    if item is None:
        abort(404)
    if not item["enabled"] or not item["customer_enabled"]:
        abort(409, "Device or customer not enabled")
    # A license follows the recorded installation ID, never an unrelated
    # customer who registered a duplicate ID.
    count = con.execute("SELECT COUNT(*) FROM devices WHERE device_id=?", (item["device_id"],)).fetchone()[0]
    if count != 1:
        abort(409, "Duplicate device identity")
    return item


def _lifetime(con, device_id):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lifetime_licenses'").fetchone():
        return False
    return con.execute("""SELECT 1 FROM lifetime_licenses
        WHERE activated_device_id=? AND status='ACTIVE' LIMIT 1""", (device_id,)).fetchone() is not None


@app.post("/admin/devices/<int:row_id>/grant-year")
def admin_grant_year(row_id):
    if not session.get("admin"):
        return redirect(url_for("login", next=request.path))
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        item = _device(con, row_id)
        if _lifetime(con, item["device_id"]):
            flash("Gerät besitzt bereits eine Lifetime-Lizenz. Keine Jahreslizenz gebucht.", "warning")
            return redirect(url_for("dashboard", _anchor="device-" + str(row_id)))
        subjects = con.execute("""SELECT trial_key_hash FROM license_subjects
             WHERE current_device_id=?""", (item["device_id"],)).fetchall()
        if len(subjects) != 1:
            flash("App muss einmal den Lizenzstatus prüfen; bei mehrfachen Installationen bitte zuerst die Gerätezuordnung klären.", "warning")
            return redirect(url_for("dashboard", _anchor="device-" + str(row_id)))
        bound_hash = subjects[0]["trial_key_hash"]
        previous = con.execute("SELECT * FROM annual_device_licenses WHERE device_id=?",
                               (item["device_id"],)).fetchone()
        now = utcnow()
        if previous and not previous["revoked_at"] and _parse(previous["expires_at"]) > now:
            flash("Die Jahreslizenz ist bereits aktiv. Es wurde nichts verlängert.", "info")
            return redirect(url_for("dashboard", _anchor="device-" + str(row_id)))
        expires = iso(now + timedelta(days=YEAR_DAYS))
        con.execute("""INSERT INTO annual_device_licenses(
                            device_id,granted_at,expires_at,revoked_at,renewed_at,bound_trial_key_hash)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(device_id) DO UPDATE SET
                         expires_at=excluded.expires_at, revoked_at=NULL,
                         renewed_at=excluded.granted_at, bound_trial_key_hash=excluded.bound_trial_key_hash""",
                    (item["device_id"], iso(now), expires, None, None, bound_hash))
        _audit(con, "admin", None, "grant_annual_app_license", "device", row_id,
               days=YEAR_DAYS, expires_at=expires, charged_credits=0)
    flash("App-Jahreslizenz für 365 Tage aktiviert – keine Credits abgebucht.", "success")
    return redirect(url_for("dashboard", _anchor="device-" + str(row_id)))


@app.post("/admin/devices/<int:row_id>/revoke-year")
def admin_revoke_year(row_id):
    if not session.get("admin"):
        return redirect(url_for("login", next=request.path))
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        item = _device(con, row_id)
        changed = con.execute("""UPDATE annual_device_licenses SET revoked_at=?
              WHERE device_id=? AND revoked_at IS NULL""", (iso(utcnow()), item["device_id"])).rowcount
        if changed:
            _audit(con, "admin", None, "revoke_annual_app_license", "device", row_id)
    flash("Jahreslizenz gesperrt." if changed else "Keine aktive Jahreslizenz vorhanden.", "info")
    return redirect(url_for("dashboard", _anchor="device-" + str(row_id)))


@app.context_processor
def annual_devices_for_admin():
    if request.endpoint != "dashboard" or not session.get("admin"):
        return {}
    with db() as con:
        rows = con.execute("""SELECT d.id, s.trial_key_hash, a.expires_at, a.revoked_at,
                     l.id lifetime_id,
                     (SELECT COUNT(*) FROM license_subjects a2 WHERE a2.current_device_id=d.device_id) subjects
              FROM devices d
              LEFT JOIN license_subjects s ON s.current_device_id=d.device_id
              LEFT JOIN annual_device_licenses a ON a.device_id=d.device_id
                     AND a.bound_trial_key_hash=s.trial_key_hash
              LEFT JOIN lifetime_licenses l ON l.subject_id=s.id AND l.status='ACTIVE'""").fetchall()
    now = utcnow()
    states = {}
    for row in rows:
        ready = int(row["subjects"]) == 1
        active = bool(ready and row["expires_at"] and not row["revoked_at"]
                      and _parse(row["expires_at"]) > now)
        states[int(row["id"])] = {
            "ready":ready, "lifetime":bool(row["lifetime_id"]),
            "active":active, "expires_at":row["expires_at"] or ""
        }
    return {"annual_device_states":states}


_previous_license_status = app.view_functions["license_status"]


def annual_aware_license_status():
    original = _previous_license_status()
    if not hasattr(original, "get_json") or original.status_code != 200:
        return original
    original.headers["Cache-Control"] = "no-store, private"
    payload = original.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("status") == "LIFETIME_ACTIVE":
        return original
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return original
    device_id = str(body.get("device_id", "")).strip()[:160]
    trial_key = str(body.get("trial_key", "")).strip().lower()
    if not device_id or len(trial_key) < 32:
        return original
    trial_hash = digest("trial-key-v1:" + trial_key)
    with db() as con:
        # Permit annual use only for a unique currently enabled customer device.
        eligible = con.execute("""SELECT COUNT(*) FROM devices d
            JOIN customers c ON c.id=d.customer_id
            WHERE d.device_id=? AND d.enabled=1 AND c.enabled=1""", (device_id,)).fetchone()[0]
        all_rows = con.execute("SELECT COUNT(*) FROM devices WHERE device_id=?", (device_id,)).fetchone()[0]
        row = con.execute("""SELECT a.expires_at FROM annual_device_licenses a
            JOIN license_subjects s ON s.trial_key_hash=a.bound_trial_key_hash
            WHERE a.device_id=? AND a.bound_trial_key_hash=?
              AND s.current_device_id=? AND a.revoked_at IS NULL""",
              (device_id, trial_hash, device_id)).fetchone()
    if eligible != 1 or all_rows != 1 or row is None:
        return original
    now = utcnow()
    expiry = _parse(row["expires_at"])
    remain = max(0, int((expiry - now).total_seconds()))
    if remain == 0:
        return original  # Original trial expires normally; no lifetime promotion.
    supports = body.get("supported_entitlements")
    supports_annual = isinstance(supports, list) and "ANNUAL" in supports
    payload.update(status="ANNUAL_ACTIVE" if supports_annual else "TRIAL_ACTIVE",
                   entitlement_type="ANNUAL",
                   annual_expires_at=row["expires_at"], license_expires_at=row["expires_at"],
                   trial_expires_at=row["expires_at"] if not supports_annual else payload.get("trial_expires_at"),
                   remaining_seconds=remain, lifetime=False)
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


app.view_functions["license_status"] = annual_aware_license_status

_previous_license_capabilities = app.view_functions["license_capabilities"]


def annual_aware_capabilities():
    response = _previous_license_capabilities()
    data = response.get_json()
    data.update(annual_license_ready=True, annual_days=YEAR_DAYS,
                annual_device_bound=True, annual_manual_admin_grant=True)
    result = jsonify(data)
    result.headers["Cache-Control"] = "no-store"
    return result


app.view_functions["license_capabilities"] = annual_aware_capabilities
_migrate()
