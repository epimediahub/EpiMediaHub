from __future__ import annotations

import json
import os
from datetime import timedelta

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app import (
    PUBLIC_BASE_URL,
    digest,
    display_code,
    iso,
    make_code,
    migrate_receiver_sync,
    normalize_code,
    qr_data_uri,
    utcnow,
    web_auth,
)
from dashboard_v061 import UNASSIGNED_CUSTOMER_NAME, _ensure_unassigned_customer
from dashboard_v070 import _config, _playlist_config, install as install_dashboard_v070
from receiver_sync import bump_customer_devices, bump_device_config


ADMIN_PUBLIC_HOST = os.environ.get("EPIMEDIAHUB_ADMIN_HOST", "admin.epimediahub.com").strip().lower()
RESELLER_PUBLIC_HOST = os.environ.get("EPIMEDIAHUB_RESELLER_HOST", "reseller.epimediahub.com").strip().lower()


def _request_host():
    forwarded = request.headers.get("X-Forwarded-Host", "").split(",", 1)[0].strip()
    raw = forwarded or request.host
    return raw.split(":", 1)[0].strip().lower()


def _is_managed_public_host(host):
    return host == "epimediahub.com" or host.endswith(".epimediahub.com")


def migrate_resellers(con):
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS resellers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            customer_limit INTEGER NOT NULL DEFAULT 0,
            device_limit INTEGER NOT NULL DEFAULT 0,
            branding_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cols = {r[1] for r in con.execute("PRAGMA table_info(customers)")}
    if "reseller_id" not in cols:
        con.execute("ALTER TABLE customers ADD COLUMN reseller_id INTEGER REFERENCES resellers(id) ON DELETE SET NULL")
    con.execute("CREATE INDEX IF NOT EXISTS idx_customers_reseller_id ON customers(reseller_id)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_type TEXT NOT NULL,
            actor_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_type,actor_id)")


def _audit(con, actor_type, actor_id, action, entity_type, entity_id=None, **detail):
    con.execute(
        "INSERT INTO audit_log(actor_type,actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            actor_type,
            actor_id,
            action,
            entity_type,
            entity_id,
            json.dumps(detail, separators=(",", ":"), ensure_ascii=False),
            iso(utcnow()),
        ),
    )


def _reseller_from_session(db):
    reseller_id = session.get("reseller_id")
    if not reseller_id:
        return None
    with db() as con:
        migrate_resellers(con)
        return con.execute(
            "SELECT * FROM resellers WHERE id=? AND enabled=1",
            (int(reseller_id),),
        ).fetchone()


def _reseller_guard(db):
    reseller = _reseller_from_session(db)
    if reseller is None:
        session.pop("reseller_id", None)
        return None, redirect(url_for("v080_reseller_login", next=request.path))
    return reseller, None


def _owned_customer(con, reseller_id, customer_id):
    return con.execute(
        "SELECT * FROM customers WHERE id=? AND reseller_id=? AND name<>?",
        (customer_id, reseller_id, UNASSIGNED_CUSTOMER_NAME),
    ).fetchone()


def _owned_device(con, reseller_id, device_id):
    return con.execute(
        """
        SELECT d.*,c.reseller_id
        FROM devices d JOIN customers c ON c.id=d.customer_id
        WHERE d.id=? AND c.reseller_id=? AND c.name<>?
        """,
        (device_id, reseller_id, UNASSIGNED_CUSTOMER_NAME),
    ).fetchone()


def _owned_playlist(con, reseller_id, playlist_id):
    return con.execute(
        """
        SELECT p.*,c.reseller_id
        FROM customer_playlists p JOIN customers c ON c.id=p.customer_id
        WHERE p.id=? AND c.reseller_id=? AND c.name<>?
        """,
        (playlist_id, reseller_id, UNASSIGNED_CUSTOMER_NAME),
    ).fetchone()


def _usage(con, reseller_id):
    customers = con.execute(
        "SELECT COUNT(*) FROM customers WHERE reseller_id=? AND name<>?",
        (reseller_id, UNASSIGNED_CUSTOMER_NAME),
    ).fetchone()[0]
    devices = con.execute(
        """
        SELECT COUNT(*)
        FROM devices d JOIN customers c ON c.id=d.customer_id
        WHERE c.reseller_id=? AND c.name<>?
        """,
        (reseller_id, UNASSIGNED_CUSTOMER_NAME),
    ).fetchone()[0]
    return int(customers), int(devices)


def _dashboard_rows(con, where_sql="", params=()):
    customer_rows = con.execute(
        f"""
        SELECT c.*,r.name reseller_name
        FROM customers c
        LEFT JOIN resellers r ON r.id=c.reseller_id
        WHERE c.name<>? {where_sql}
        ORDER BY c.name COLLATE NOCASE,c.id
        """,
        (UNASSIGNED_CUSTOMER_NAME, *params),
    ).fetchall()

    customer_ids = [int(r["id"]) for r in customer_rows]
    if not customer_ids:
        return [], [], 0, 0

    placeholders = ",".join("?" for _ in customer_ids)
    device_rows = con.execute(
        f"SELECT * FROM devices WHERE customer_id IN ({placeholders}) ORDER BY display_name COLLATE NOCASE,device_id COLLATE NOCASE,id",
        customer_ids,
    ).fetchall()
    playlist_rows = con.execute(
        f"SELECT * FROM customer_playlists WHERE customer_id IN ({placeholders}) ORDER BY customer_id,id",
        customer_ids,
    ).fetchall()

    playlists_by_customer = {}
    for row in playlist_rows:
        item = dict(row)
        cfg = _config(row)
        item.update(cfg)
        item["source_display"] = str(cfg.get("xtream_server") or cfg.get("playlist_url") or "").split("?", 1)[0]
        playlists_by_customer.setdefault(int(row["customer_id"]), []).append(item)

    devices_by_customer = {}
    for row in device_rows:
        item = dict(row)
        item["sync_pending"] = int(row["applied_config_version"] or 0) != int(row["config_version"] or 1)
        devices_by_customer.setdefault(int(row["customer_id"]), []).append(item)

    customers = []
    for row in customer_rows:
        item = dict(row)
        item["devices"] = devices_by_customer.get(int(row["id"]), [])
        item["playlists"] = playlists_by_customer.get(int(row["id"]), [])
        item["playlist_count"] = len(item["playlists"])
        customers.append(item)

    pending = sum(1 for row in device_rows if int(row["applied_config_version"] or 0) != int(row["config_version"] or 1))
    return customers, device_rows, len(playlist_rows), pending


def _admin_dashboard(db):
    guard = web_auth()
    if guard:
        return guard
    with db() as con:
        migrate_receiver_sync(con)
        migrate_resellers(con)
        _ensure_unassigned_customer(con)
        customers, devices, total_playlists, pending_devices = _dashboard_rows(con)
        unassigned_id = _ensure_unassigned_customer(con)
        unassigned_devices = []
        for row in con.execute("SELECT * FROM devices WHERE customer_id=? ORDER BY display_name COLLATE NOCASE,device_id COLLATE NOCASE,id", (unassigned_id,)).fetchall():
            item = dict(row)
            item["sync_pending"] = int(row["applied_config_version"] or 0) != int(row["config_version"] or 1)
            unassigned_devices.append(item)
        reseller_rows = con.execute(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM customers c WHERE c.reseller_id=r.id AND c.name<>?) customer_count,
                   (SELECT COUNT(*) FROM devices d JOIN customers c ON c.id=d.customer_id WHERE c.reseller_id=r.id AND c.name<>?) device_count
            FROM resellers r
            ORDER BY r.name COLLATE NOCASE,r.id
            """,
            (UNASSIGNED_CUSTOMER_NAME, UNASSIGNED_CUSTOMER_NAME),
        ).fetchall()
        audit = con.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return render_template(
        "dashboard_v080.html",
        customers=customers,
        resellers=[dict(r) for r in reseller_rows],
        total_devices=len(devices),
        total_playlists=total_playlists,
        pending_devices=pending_devices,
        recent_audit=[dict(r) for r in audit],
        unassigned_devices=unassigned_devices,
        unassigned_customer_id=unassigned_id,
        reseller_portal_url=f"https://{RESELLER_PUBLIC_HOST}",
    )


def _reseller_dashboard(db, reseller):
    with db() as con:
        migrate_receiver_sync(con)
        migrate_resellers(con)
        customers, devices, total_playlists, pending_devices = _dashboard_rows(
            con, "AND c.reseller_id=?", (int(reseller["id"]),)
        )
        customer_count, device_count = _usage(con, int(reseller["id"]))
    return render_template(
        "reseller_dashboard_v080.html",
        reseller=dict(reseller),
        customers=customers,
        total_devices=device_count,
        total_playlists=total_playlists,
        pending_devices=pending_devices,
        customer_count=customer_count,
    )


def install(app, db):
    if app.extensions.get("epimediahub_dashboard_v080"):
        return

    install_dashboard_v070(app, db)
    with db() as con:
        migrate_receiver_sync(con)
        migrate_resellers(con)
        _ensure_unassigned_customer(con)

    app.extensions["epimediahub_dashboard_v080"] = True
    app.view_functions["dashboard"] = lambda: _admin_dashboard(db)

    @app.before_request
    def v081_public_host_separation():
        host = _request_host()
        if not _is_managed_public_host(host):
            return None

        path = request.path
        if path.startswith("/reseller") and host != RESELLER_PUBLIC_HOST:
            if request.method not in {"GET", "HEAD"}:
                abort(404)
            suffix = path[len("/reseller"):]
            target = f"https://{RESELLER_PUBLIC_HOST}/reseller{suffix}"
            if request.query_string:
                target += "?" + request.query_string.decode("utf-8", "ignore")
            return redirect(target, code=302)

        if path.startswith("/admin") and host == RESELLER_PUBLIC_HOST:
            if request.method not in {"GET", "HEAD"}:
                abort(404)
            return redirect(f"https://{ADMIN_PUBLIC_HOST}/admin", code=302)

        return None

    @app.get("/")
    def v081_portal_root():
        host = _request_host()
        if host == RESELLER_PUBLIC_HOST:
            return redirect(url_for("v080_reseller_dashboard"))
        if host == ADMIN_PUBLIC_HOST:
            return redirect(url_for("dashboard"))
        abort(404)
    app.view_functions["health"] = lambda: jsonify(
        status="ok", service="epimediahub-provisioning", api_version="0.8.0"
    )

    @app.post("/admin/v080/resellers")
    def v080_create_reseller():
        guard = web_auth()
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        branding_name = request.form.get("branding_name", "").strip()
        try:
            customer_limit = max(0, int(request.form.get("customer_limit", "0") or 0))
            device_limit = max(0, int(request.form.get("device_limit", "0") or 0))
        except ValueError:
            abort(400)
        if not name or not username or len(password) < 8:
            flash("Name, Benutzername und ein Passwort mit mindestens 8 Zeichen sind erforderlich.", "warning")
            return redirect(url_for("dashboard", _anchor="resellers"))
        with db() as con:
            migrate_resellers(con)
            try:
                cur = con.execute(
                    """
                    INSERT INTO resellers(name,username,password_hash,enabled,customer_limit,device_limit,branding_name,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        name,
                        username,
                        generate_password_hash(password),
                        1,
                        customer_limit,
                        device_limit,
                        branding_name,
                        iso(utcnow()),
                        iso(utcnow()),
                    ),
                )
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    flash("Dieser Reseller-Benutzername ist bereits vergeben.", "error")
                    return redirect(url_for("dashboard", _anchor="resellers"))
                raise
            rid = int(cur.lastrowid)
            _audit(con, "admin", None, "create", "reseller", rid, name=name, username=username)
        flash(f"Reseller {name} wurde angelegt.", "success")
        return redirect(url_for("dashboard", _anchor=f"reseller-{rid}"))

    @app.post("/admin/v080/resellers/<int:reseller_id>/update")
    def v080_update_reseller(reseller_id):
        guard = web_auth()
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        branding_name = request.form.get("branding_name", "").strip()
        password = request.form.get("password", "")
        try:
            customer_limit = max(0, int(request.form.get("customer_limit", "0") or 0))
            device_limit = max(0, int(request.form.get("device_limit", "0") or 0))
        except ValueError:
            abort(400)
        if not name or not username:
            abort(400)
        with db() as con:
            migrate_resellers(con)
            if not con.execute("SELECT id FROM resellers WHERE id=?", (reseller_id,)).fetchone():
                abort(404)
            if password:
                if len(password) < 8:
                    flash("Das neue Passwort muss mindestens 8 Zeichen lang sein.", "warning")
                    return redirect(url_for("dashboard", _anchor=f"reseller-{reseller_id}"))
                con.execute(
                    """
                    UPDATE resellers
                    SET name=?,username=?,branding_name=?,customer_limit=?,device_limit=?,password_hash=?,updated_at=?
                    WHERE id=?
                    """,
                    (
                        name,
                        username,
                        branding_name,
                        customer_limit,
                        device_limit,
                        generate_password_hash(password),
                        iso(utcnow()),
                        reseller_id,
                    ),
                )
            else:
                con.execute(
                    """
                    UPDATE resellers
                    SET name=?,username=?,branding_name=?,customer_limit=?,device_limit=?,updated_at=?
                    WHERE id=?
                    """,
                    (name, username, branding_name, customer_limit, device_limit, iso(utcnow()), reseller_id),
                )
            _audit(con, "admin", None, "update", "reseller", reseller_id, name=name)
        flash("Reseller gespeichert.", "success")
        return redirect(url_for("dashboard", _anchor=f"reseller-{reseller_id}"))

    @app.post("/admin/v080/resellers/<int:reseller_id>/toggle")
    def v080_toggle_reseller(reseller_id):
        guard = web_auth()
        if guard:
            return guard
        with db() as con:
            migrate_resellers(con)
            row = con.execute("SELECT enabled,name FROM resellers WHERE id=?", (reseller_id,)).fetchone()
            if not row:
                abort(404)
            enabled = 0 if row["enabled"] else 1
            con.execute("UPDATE resellers SET enabled=?,updated_at=? WHERE id=?", (enabled, iso(utcnow()), reseller_id))
            _audit(con, "admin", None, "enable" if enabled else "disable", "reseller", reseller_id)
        flash(f"Reseller {row['name']} wurde {'aktiviert' if enabled else 'gesperrt'}.", "success")
        return redirect(url_for("dashboard", _anchor=f"reseller-{reseller_id}"))

    @app.post("/admin/v080/resellers/<int:reseller_id>/delete")
    def v080_delete_reseller(reseller_id):
        guard = web_auth()
        if guard:
            return guard
        if request.form.get("confirm") != f"DELETE_RESELLER:{reseller_id}":
            abort(400)
        with db() as con:
            migrate_resellers(con)
            row = con.execute("SELECT name FROM resellers WHERE id=?", (reseller_id,)).fetchone()
            if not row:
                abort(404)
            con.execute("UPDATE customers SET reseller_id=NULL WHERE reseller_id=?", (reseller_id,))
            con.execute("DELETE FROM resellers WHERE id=?", (reseller_id,))
            _audit(con, "admin", None, "delete", "reseller", reseller_id, name=row["name"], customers_reassigned="direct")
        flash(f"Reseller {row['name']} wurde gelöscht. Seine Kunden wurden dem Hauptkonto zugeordnet.", "success")
        return redirect(url_for("dashboard", _anchor="resellers"))

    @app.post("/admin/v080/customers/<int:customer_id>/reseller")
    def v080_assign_customer_reseller(customer_id):
        guard = web_auth()
        if guard:
            return guard
        raw = request.form.get("reseller_id", "").strip()
        reseller_id = int(raw) if raw else None
        with db() as con:
            migrate_resellers(con)
            customer = con.execute(
                "SELECT id,name FROM customers WHERE id=? AND name<>?",
                (customer_id, UNASSIGNED_CUSTOMER_NAME),
            ).fetchone()
            if not customer:
                abort(404)
            if reseller_id is not None:
                reseller = con.execute("SELECT * FROM resellers WHERE id=?", (reseller_id,)).fetchone()
                if not reseller:
                    abort(404)
                customer_count, _ = _usage(con, reseller_id)
                already = con.execute("SELECT reseller_id FROM customers WHERE id=?", (customer_id,)).fetchone()[0]
                if already != reseller_id and reseller["customer_limit"] and customer_count >= reseller["customer_limit"]:
                    flash("Das Kundenlimit dieses Resellers ist erreicht.", "warning")
                    return redirect(url_for("dashboard", _anchor=f"customer-{customer_id}"))
            con.execute("UPDATE customers SET reseller_id=? WHERE id=?", (reseller_id, customer_id))
            _audit(con, "admin", None, "assign_reseller", "customer", customer_id, reseller_id=reseller_id)
        flash("Reseller-Zuordnung gespeichert.", "success")
        return redirect(url_for("dashboard", _anchor=f"customer-{customer_id}"))

    @app.route("/reseller/login", methods=["GET", "POST"])
    def v080_reseller_login():
        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            with db() as con:
                migrate_resellers(con)
                row = con.execute("SELECT * FROM resellers WHERE username=?", (username,)).fetchone()
            if row and row["enabled"] and check_password_hash(row["password_hash"], password):
                session.pop("admin", None)
                session["reseller_id"] = int(row["id"])
                return redirect(url_for("v080_reseller_dashboard"))
            error = "Anmeldedaten falsch oder Reseller gesperrt"
        return render_template("reseller_login_v080.html", error=error)

    @app.post("/reseller/logout")
    def v080_reseller_logout():
        session.pop("reseller_id", None)
        return redirect(url_for("v080_reseller_login"))

    @app.get("/reseller")
    def v080_reseller_dashboard():
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        return _reseller_dashboard(db, reseller)

    @app.post("/reseller/customers")
    def v080_reseller_create_customer():
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        if not name:
            flash("Bitte einen Kundennamen eingeben.", "warning")
            return redirect(url_for("v080_reseller_dashboard"))
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            customer_count, _ = _usage(con, rid)
            if reseller["customer_limit"] and customer_count >= reseller["customer_limit"]:
                flash("Dein Kundenlimit ist erreicht.", "warning")
                return redirect(url_for("v080_reseller_dashboard"))
            cur = con.execute(
                "INSERT INTO customers(name,config_json,created_at,reseller_id) VALUES(?,?,?,?)",
                (name, "{}", iso(utcnow()), rid),
            )
            customer_id = int(cur.lastrowid)
            migrate_receiver_sync(con)
            _audit(con, "reseller", rid, "create", "customer", customer_id, name=name)
        flash(f"Kunde {name} wurde angelegt.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{customer_id}"))

    @app.post("/reseller/customers/<int:customer_id>/rename")
    def v080_reseller_rename_customer(customer_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        if not name:
            abort(400)
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            if not _owned_customer(con, rid, customer_id):
                abort(404)
            con.execute("UPDATE customers SET name=? WHERE id=?", (name, customer_id))
            _audit(con, "reseller", rid, "rename", "customer", customer_id, name=name)
        flash("Kundenname gespeichert.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{customer_id}"))

    @app.post("/reseller/customers/<int:customer_id>/delete")
    def v080_reseller_delete_customer(customer_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        if request.form.get("confirm") != f"DELETE:{customer_id}":
            abort(400)
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            customer = _owned_customer(con, rid, customer_id)
            if not customer:
                abort(404)
            con.execute("DELETE FROM customer_playlists WHERE customer_id=?", (customer_id,))
            con.execute("DELETE FROM pairings WHERE customer_id=?", (customer_id,))
            con.execute("DELETE FROM devices WHERE customer_id=?", (customer_id,))
            con.execute("DELETE FROM customers WHERE id=?", (customer_id,))
            _audit(con, "reseller", rid, "delete", "customer", customer_id, name=customer["name"])
        flash(f"Kunde {customer['name']} wurde gelöscht.", "success")
        return redirect(url_for("v080_reseller_dashboard"))

    @app.post("/reseller/customers/<int:customer_id>/playlists")
    def v080_reseller_add_playlist(customer_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        config = _playlist_config()
        if not (config["playlist_url"] or config["xtream_server"]):
            flash("Bitte eine Playlist-Adresse oder einen Xtream-Server eintragen.", "warning")
            return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{customer_id}"))
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            if not _owned_customer(con, rid, customer_id):
                abort(404)
            now = iso(utcnow())
            cur = con.execute(
                "INSERT INTO customer_playlists(customer_id,name,config_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                (customer_id, config["playlist_name"], json.dumps(config, separators=(",", ":")), now, now),
            )
            bump_customer_devices(con, customer_id)
            _audit(con, "reseller", rid, "create", "playlist", int(cur.lastrowid), customer_id=customer_id)
        flash("Playlist hinzugefügt. Alle Geräte des Kunden übernehmen sie automatisch.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{customer_id}"))

    @app.post("/reseller/playlists/<int:playlist_id>/update")
    def v080_reseller_update_playlist(playlist_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            row = _owned_playlist(con, rid, playlist_id)
            if not row:
                abort(404)
            config = _playlist_config(_config(row))
            customer_id = int(row["customer_id"])
            con.execute(
                "UPDATE customer_playlists SET name=?,config_json=?,updated_at=? WHERE id=?",
                (config["playlist_name"], json.dumps(config, separators=(",", ":")), iso(utcnow()), playlist_id),
            )
            bump_customer_devices(con, customer_id)
            _audit(con, "reseller", rid, "update", "playlist", playlist_id, customer_id=customer_id)
        flash("Playlist gespeichert.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{customer_id}"))

    @app.post("/reseller/playlists/<int:playlist_id>/delete")
    def v080_reseller_delete_playlist(playlist_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            row = _owned_playlist(con, rid, playlist_id)
            if not row:
                abort(404)
            customer_id = int(row["customer_id"])
            name = row["name"]
            con.execute("DELETE FROM customer_playlists WHERE id=?", (playlist_id,))
            bump_customer_devices(con, customer_id)
            _audit(con, "reseller", rid, "delete", "playlist", playlist_id, customer_id=customer_id)
        flash(f"Playlist {name} wurde entfernt.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{customer_id}"))

    @app.post("/reseller/pairings/claim")
    def v080_reseller_claim_pairing():
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        code = normalize_code(request.form.get("code", ""))
        try:
            customer_id = int(request.form.get("customer_id", ""))
        except (TypeError, ValueError):
            customer_id = 0
        if len(code) != 8 or not customer_id:
            flash("Kopplungscode oder Kunde ist ungültig.", "error")
            return redirect(url_for("v080_reseller_dashboard"))
        rid = int(reseller["id"])
        now = iso(utcnow())
        with db() as con:
            migrate_resellers(con)
            customer = _owned_customer(con, rid, customer_id)
            if not customer:
                abort(404)
            _, device_count = _usage(con, rid)
            if reseller["device_limit"] and device_count >= reseller["device_limit"]:
                flash("Dein Gerätelimit ist erreicht.", "warning")
                return redirect(url_for("v080_reseller_dashboard", _anchor="pair-device"))
            row = con.execute("SELECT * FROM pairings WHERE code_hash=?", (digest(code),)).fetchone()
            if row is None:
                flash("Der Kopplungscode ist ungültig.", "error")
            elif row["expires_at"] <= now:
                flash("Der Kopplungscode ist abgelaufen.", "warning")
            elif row["customer_id"] is not None:
                flash("Dieser Kopplungscode wurde bereits verwendet.", "warning")
            else:
                con.execute(
                    "UPDATE pairings SET customer_id=?,claimed_at=? WHERE id=? AND customer_id IS NULL",
                    (customer_id, now, row["id"]),
                )
                _audit(con, "reseller", rid, "claim", "pairing", int(row["id"]), customer_id=customer_id)
                flash("Gerät wurde dem Kunden zugewiesen.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor="pair-device"))

    @app.post("/reseller/customers/<int:customer_id>/activation")
    def v080_reseller_activation(customer_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        rid = int(reseller["id"])
        raw = make_code()
        import secrets
        token = secrets.token_urlsafe(32)
        expires = utcnow() + timedelta(minutes=60)
        with db() as con:
            migrate_resellers(con)
            customer = _owned_customer(con, rid, customer_id)
            if not customer:
                abort(404)
            _, device_count = _usage(con, rid)
            if reseller["device_limit"] and device_count >= reseller["device_limit"]:
                flash("Dein Gerätelimit ist erreicht.", "warning")
                return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{customer_id}"))
            con.execute(
                "INSERT INTO activations(customer_id,code_hash,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)",
                (customer_id, digest(raw), digest(token), iso(expires), iso(utcnow())),
            )
            _audit(con, "reseller", rid, "create", "activation", None, customer_id=customer_id)
        activation_url = f"{PUBLIC_BASE_URL}/connect/{token}"
        return render_template(
            "activation.html",
            customer=customer,
            code=display_code(raw),
            activation_url=activation_url,
            expires_at=iso(expires),
            qr_data=qr_data_uri(activation_url),
        )

    @app.post("/reseller/devices/<int:device_id>/rename")
    def v080_reseller_rename_device(device_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        name = request.form.get("name", "").strip()[:80]
        if not name:
            abort(400)
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            row = _owned_device(con, rid, device_id)
            if not row:
                abort(404)
            con.execute("UPDATE devices SET display_name=? WHERE id=?", (name, device_id))
            _audit(con, "reseller", rid, "rename", "device", device_id, name=name)
        flash("Gerätename gespeichert.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"device-{device_id}"))

    @app.post("/reseller/devices/<int:device_id>/sync")
    def v080_reseller_sync_device(device_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            row = _owned_device(con, rid, device_id)
            if not row:
                abort(404)
            bump_device_config(con, device_id)
            _audit(con, "reseller", rid, "sync", "device", device_id)
        flash("Synchronisierung angefordert.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"device-{device_id}"))

    @app.post("/reseller/devices/<int:device_id>/delete")
    def v080_reseller_delete_device(device_id):
        reseller, guard = _reseller_guard(db)
        if guard:
            return guard
        if request.form.get("confirm") != f"DELETE_DEVICE:{device_id}":
            abort(400)
        rid = int(reseller["id"])
        with db() as con:
            migrate_resellers(con)
            row = _owned_device(con, rid, device_id)
            if not row:
                abort(404)
            con.execute(
                "DELETE FROM pairings WHERE customer_id=? AND device_id=?",
                (row["customer_id"], row["device_id"]),
            )
            con.execute("DELETE FROM devices WHERE id=?", (device_id,))
            _audit(con, "reseller", rid, "delete", "device", device_id, customer_id=int(row["customer_id"]))
        flash("Gerät gelöscht. Die Kunden-Playlists bleiben erhalten.", "success")
        return redirect(url_for("v080_reseller_dashboard", _anchor=f"customer-{row['customer_id']}"))
