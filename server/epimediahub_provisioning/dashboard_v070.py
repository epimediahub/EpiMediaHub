from __future__ import annotations

import json

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from app import digest, iso, migrate_receiver_sync, normalize_code, utcnow, web_auth
from dashboard_v061 import (
    UNASSIGNED_CUSTOMER_NAME,
    _ensure_unassigned_customer,
    install as install_dashboard_v061,
)
from receiver_sync import bump_device_config


def _playlist_config(previous=None):
    previous = dict(previous or {})
    kind = request.form.get("playlist_type", previous.get("playlist_type", "M3U")).upper()
    if kind not in {"M3U", "XTREAM"}:
        kind = "M3U"
    config = {
        "playlist_type": kind,
        "playlist_name": request.form.get("playlist_name", previous.get("playlist_name", "Playlist")).strip() or "Playlist",
        "playlist_url": "",
        "xtream_server": "",
        "xtream_username": "",
        "xtream_password": "",
        "xtream_output": "ts",
    }
    if kind == "M3U":
        config["playlist_url"] = request.form.get("playlist_url", "").strip()
    else:
        config["xtream_server"] = request.form.get("xtream_server", "").strip().rstrip("/")
        config["xtream_username"] = request.form.get("xtream_username", "").strip()
        password = request.form.get("xtream_password", "")
        config["xtream_password"] = password or previous.get("xtream_password", "")
        output = request.form.get("xtream_output", previous.get("xtream_output", "ts")).lower()
        config["xtream_output"] = output if output in {"ts", "m3u8"} else "ts"
    return config


def _config(row):
    try:
        value = json.loads(row["config_json"] or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _dashboard(db):
    guard = web_auth()
    if guard:
        return guard
    with db() as con:
        migrate_receiver_sync(con)
        unassigned_id = _ensure_unassigned_customer(con)
        customer_rows = con.execute(
            "SELECT * FROM customers WHERE name<>? ORDER BY name COLLATE NOCASE,id",
            (UNASSIGNED_CUSTOMER_NAME,),
        ).fetchall()
        device_rows = con.execute(
            "SELECT * FROM devices ORDER BY device_id COLLATE NOCASE,id"
        ).fetchall()
        playlist_rows = con.execute(
            "SELECT * FROM device_playlists ORDER BY id"
        ).fetchall()

    playlists_by_device = {}
    for row in playlist_rows:
        item = dict(row)
        cfg = _config(row)
        item.update(cfg)
        item["source_display"] = str(cfg.get("xtream_server") or cfg.get("playlist_url") or "").split("?", 1)[0]
        playlists_by_device.setdefault(int(row["device_id"]), []).append(item)

    devices_by_customer = {}
    unassigned_devices = []
    for row in device_rows:
        item = dict(row)
        item["playlists"] = playlists_by_device.get(int(row["id"]), [])
        item["sync_pending"] = int(row["applied_config_version"] or 0) != int(row["config_version"] or 1)
        if int(row["customer_id"]) == unassigned_id:
            unassigned_devices.append(item)
        else:
            devices_by_customer.setdefault(int(row["customer_id"]), []).append(item)

    customers = []
    for row in customer_rows:
        item = dict(row)
        item["devices"] = devices_by_customer.get(int(row["id"]), [])
        item["playlist_count"] = sum(len(device["playlists"]) for device in item["devices"])
        customers.append(item)

    all_devices = [device for customer in customers for device in customer["devices"]] + unassigned_devices
    return render_template(
        "dashboard_v070.html",
        customers=customers,
        unassigned_devices=unassigned_devices,
        unassigned_customer_id=unassigned_id,
        total_devices=len(all_devices),
        total_playlists=len(playlist_rows),
        pending_devices=sum(1 for device in all_devices if device["sync_pending"]),
    )


def install(app, db):
    if app.extensions.get("epimediahub_dashboard_v070"):
        return
    install_dashboard_v061(app, db)
    with db() as con:
        migrate_receiver_sync(con)
        _ensure_unassigned_customer(con)

    app.extensions["epimediahub_dashboard_v070"] = True
    app.view_functions["dashboard"] = lambda: _dashboard(db)
    app.view_functions["health"] = lambda: jsonify(
        status="ok", service="epimediahub-provisioning", api_version="0.7.3"
    )

    @app.post("/admin/v070/customers")
    def v070_create_customer():
        guard = web_auth()
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        if not name:
            flash("Bitte einen Kundennamen eingeben.", "warning")
            return redirect(url_for("dashboard"))
        with db() as con:
            con.execute(
                "INSERT INTO customers(name,config_json,created_at) VALUES(?,?,?)",
                (name, "{}", iso(utcnow())),
            )
        flash(f"Kunde {name} wurde angelegt.", "success")
        return redirect(url_for("dashboard"))

    @app.post("/admin/v070/customers/<int:customer_id>/rename")
    def v070_rename_customer(customer_id):
        guard = web_auth()
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        if not name:
            abort(400)
        with db() as con:
            cur = con.execute(
                "UPDATE customers SET name=? WHERE id=? AND name<>?",
                (name, customer_id, UNASSIGNED_CUSTOMER_NAME),
            )
            if not cur.rowcount:
                abort(404)
        flash("Kundenname gespeichert.", "success")
        return redirect(url_for("dashboard", _anchor=f"customer-{customer_id}"))

    @app.post("/admin/v073/pairings/claim")
    def v073_claim_pairing():
        guard = web_auth()
        if guard:
            return guard
        code = normalize_code(request.form.get("code", ""))
        try:
            customer_id = int(request.form.get("customer_id", ""))
        except (TypeError, ValueError):
            customer_id = 0
        if len(code) != 8 or not customer_id:
            flash("Kopplungscode oder Kunde ist ungültig.", "error")
            return redirect(url_for("dashboard"))

        now = iso(utcnow())
        with db() as con:
            customer = con.execute(
                "SELECT id FROM customers WHERE id=? AND enabled=1 AND name<>?",
                (customer_id, UNASSIGNED_CUSTOMER_NAME),
            ).fetchone()
            row = con.execute(
                "SELECT * FROM pairings WHERE code_hash=?",
                (digest(code),),
            ).fetchone()
            if not customer:
                flash("Der ausgewählte Kunde ist nicht verfügbar.", "error")
            elif row is None:
                flash("Der Kopplungscode ist ungültig.", "error")
            elif row["expires_at"] <= now:
                flash("Der Kopplungscode ist abgelaufen. Bitte in der App einen neuen erzeugen.", "warning")
            elif row["customer_id"] is not None:
                flash("Dieser Kopplungscode wurde bereits verwendet.", "warning")
            else:
                con.execute(
                    "UPDATE pairings SET customer_id=?,claimed_at=? WHERE id=? AND customer_id IS NULL",
                    (customer_id, now, row["id"]),
                )
                flash("Gerät wurde dem Kunden zugewiesen und verbindet sich automatisch.", "success")
        return redirect(url_for("dashboard", _anchor="pair-device"))

    @app.post("/admin/v073/customers/<int:customer_id>/delete")
    def v073_delete_customer(customer_id):
        guard = web_auth()
        if guard:
            return guard
        if request.form.get("confirm", "") != f"DELETE:{customer_id}":
            abort(400)
        with db() as con:
            customer = con.execute(
                "SELECT id,name FROM customers WHERE id=? AND name<>?",
                (customer_id, UNASSIGNED_CUSTOMER_NAME),
            ).fetchone()
            if not customer:
                abort(404)
            con.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        flash(
            f"Kunde {customer['name']} sowie zugehörige Geräte, Playlists und Aktivierungscodes wurden gelöscht.",
            "success",
        )
        return redirect(url_for("dashboard"))

    @app.post("/admin/v070/devices/<int:device_id>/playlists")
    def v070_add_playlist(device_id):
        guard = web_auth()
        if guard:
            return guard
        config = _playlist_config()
        if not (config["playlist_url"] or config["xtream_server"]):
            flash("Bitte eine Playlist-Adresse oder einen Xtream-Server eintragen.", "warning")
            return redirect(url_for("dashboard", _anchor=f"device-{device_id}"))
        now = iso(utcnow())
        with db() as con:
            migrate_receiver_sync(con)
            if not con.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone():
                abort(404)
            con.execute(
                "INSERT INTO device_playlists(device_id,name,config_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                (device_id, config["playlist_name"], json.dumps(config, separators=(",", ":")), now, now),
            )
            bump_device_config(con, device_id)
        flash("Playlist hinzugefügt. Das Gerät übernimmt sie beim nächsten Abruf.", "success")
        return redirect(url_for("dashboard", _anchor=f"device-{device_id}"))

    @app.post("/admin/v070/playlists/<int:playlist_id>/update")
    def v070_update_playlist(playlist_id):
        guard = web_auth()
        if guard:
            return guard
        with db() as con:
            migrate_receiver_sync(con)
            row = con.execute("SELECT * FROM device_playlists WHERE id=?", (playlist_id,)).fetchone()
            if not row:
                abort(404)
            config = _playlist_config(_config(row))
            con.execute(
                "UPDATE device_playlists SET name=?,config_json=?,updated_at=? WHERE id=?",
                (config["playlist_name"], json.dumps(config, separators=(",", ":")), iso(utcnow()), playlist_id),
            )
            bump_device_config(con, int(row["device_id"]))
            device_id = int(row["device_id"])
        flash("Playlist gespeichert und zur Synchronisierung vorgemerkt.", "success")
        return redirect(url_for("dashboard", _anchor=f"device-{device_id}"))

    @app.post("/admin/v070/playlists/<int:playlist_id>/delete")
    def v070_delete_playlist(playlist_id):
        guard = web_auth()
        if guard:
            return guard
        with db() as con:
            migrate_receiver_sync(con)
            row = con.execute("SELECT device_id,name FROM device_playlists WHERE id=?", (playlist_id,)).fetchone()
            if not row:
                abort(404)
            device_id = int(row["device_id"])
            con.execute("DELETE FROM device_playlists WHERE id=?", (playlist_id,))
            bump_device_config(con, device_id)
        flash(f"Playlist {row['name']} wurde vom Gerät entfernt.", "success")
        return redirect(url_for("dashboard", _anchor=f"device-{device_id}"))

    @app.post("/admin/v070/devices/<int:device_id>/sync")
    def v070_sync_device(device_id):
        guard = web_auth()
        if guard:
            return guard
        with db() as con:
            migrate_receiver_sync(con)
            if not con.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone():
                abort(404)
            bump_device_config(con, device_id)
        flash("Synchronisierung angefordert. Das Gerät ruft die Änderung automatisch ab.", "success")
        return redirect(url_for("dashboard", _anchor=f"device-{device_id}"))

    @app.post("/admin/v070/devices/<int:device_id>/move")
    def v070_move_device(device_id):
        guard = web_auth()
        if guard:
            return guard
        try:
            customer_id = int(request.form.get("customer_id", ""))
        except ValueError:
            abort(400)
        with db() as con:
            if not con.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone():
                abort(404)
            cur = con.execute("UPDATE devices SET customer_id=? WHERE id=?", (customer_id, device_id))
            if not cur.rowcount:
                abort(404)
        flash("Gerät wurde dem Kunden zugeordnet.", "success")
        return redirect(url_for("dashboard", _anchor=f"customer-{customer_id}"))
