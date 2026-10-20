from __future__ import annotations

import json
from datetime import timedelta

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from app import customer_config, form_config, iso, migrate_receiver_sync, utcnow, web_auth
from dashboard_v060 import (
    _format_timestamp,
    _parse_timestamp,
    install as install_dashboard_v060,
)
from receiver_sync import save_customer_config


UNASSIGNED_CUSTOMER_NAME = "__EPIMEDIAHUB_UNASSIGNED__"
UNASSIGNED_CONFIG = {
    "_system_role": "unassigned",
    "playlist_type": "M3U",
    "playlist_name": "Nicht zugewiesen",
    "playlist_url": "",
    "xtream_server": "",
    "xtream_username": "",
    "xtream_password": "",
    "xtream_output": "ts",
}


def _ensure_unassigned_customer(con):
    row = con.execute(
        "SELECT id FROM customers WHERE name=? ORDER BY id LIMIT 1",
        (UNASSIGNED_CUSTOMER_NAME,),
    ).fetchone()
    if row:
        return int(row["id"])
    return int(
        con.execute(
            "INSERT INTO customers(name,config_json,enabled,created_at) VALUES(?,?,1,?)",
            (
                UNASSIGNED_CUSTOMER_NAME,
                json.dumps(UNASSIGNED_CONFIG, separators=(",", ":")),
                iso(utcnow()),
            ),
        ).lastrowid
    )


def _is_system_customer(row):
    return row["name"] == UNASSIGNED_CUSTOMER_NAME or customer_config(row).get(
        "_system_role"
    ) == "unassigned"


def _selected_device_ids():
    result = []
    for value in request.form.getlist("device_ids"):
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(set(result))


def _move_device(con, device_row_id, target_customer_id):
    device = con.execute("SELECT * FROM devices WHERE id=?", (device_row_id,)).fetchone()
    if not device:
        return False
    duplicate = con.execute(
        "SELECT id FROM devices WHERE customer_id=? AND device_id=? AND id<>?",
        (target_customer_id, device["device_id"], device_row_id),
    ).fetchone()
    if duplicate:
        con.execute("DELETE FROM devices WHERE id=?", (duplicate["id"],))
    con.execute(
        """
        UPDATE devices
        SET customer_id=?,applied_config_version=0,last_sync_status='pending',last_sync_error=NULL
        WHERE id=?
        """,
        (target_customer_id, device_row_id),
    )
    return True


def _apply_device_selection(con, customer_id, selected_ids, reconcile=False):
    selected_ids = set(selected_ids)
    if reconcile:
        current_ids = {
            int(row["id"])
            for row in con.execute(
                "SELECT id FROM devices WHERE customer_id=?", (customer_id,)
            ).fetchall()
        }
        removed_ids = current_ids - selected_ids
        if removed_ids:
            unassigned_id = _ensure_unassigned_customer(con)
            for device_row_id in removed_ids:
                _move_device(con, device_row_id, unassigned_id)

    assigned = 0
    for device_row_id in selected_ids:
        if _move_device(con, device_row_id, customer_id):
            assigned += 1
    return assigned


def _preserve_customer_devices(con, customer_id):
    device_ids = [
        int(row["id"])
        for row in con.execute(
            "SELECT id FROM devices WHERE customer_id=?", (customer_id,)
        ).fetchall()
    ]
    if not device_ids:
        return 0
    unassigned_id = _ensure_unassigned_customer(con)
    for device_row_id in device_ids:
        _move_device(con, device_row_id, unassigned_id)
    return len(device_ids)


def _dashboard(db):
    guard = web_auth()
    if guard:
        return guard

    with db() as con:
        migrate_receiver_sync(con)
        unassigned_customer_id = _ensure_unassigned_customer(con)
        customer_rows = con.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
        device_rows = con.execute(
            """
            SELECT d.*,c.name customer_name,c.config_version customer_config_version
            FROM devices d JOIN customers c ON c.id=d.customer_id
            ORDER BY d.id DESC
            """
        ).fetchall()
        device_count_rows = con.execute(
            "SELECT customer_id,COUNT(*) total FROM devices GROUP BY customer_id"
        ).fetchall()
        activation_rows = con.execute(
            """
            SELECT a.*,c.name customer_name
            FROM activations a JOIN customers c ON c.id=a.customer_id
            WHERE c.name<>?
            ORDER BY a.id DESC
            """,
            (UNASSIGNED_CUSTOMER_NAME,),
        ).fetchall()

    device_counts = {int(row["customer_id"]): int(row["total"]) for row in device_count_rows}
    customers = []
    for row in customer_rows:
        if _is_system_customer(row):
            continue
        cfg = customer_config(row)
        playlist_type = cfg.get("playlist_type", "XTREAM" if cfg.get("xtream_server") else "M3U")
        source = cfg.get("xtream_server", "") or cfg.get("playlist_url", "")
        item = dict(row)
        item.update(
            {
                "playlist_type": playlist_type,
                "playlist_name": cfg.get("playlist_name", row["name"]),
                "playlist_url": cfg.get("playlist_url", ""),
                "xtream_server": cfg.get("xtream_server", ""),
                "xtream_username": cfg.get("xtream_username", ""),
                "xtream_output": cfg.get("xtream_output", "ts"),
                "source_display": str(source).split("?", 1)[0],
                "device_count": device_counts.get(int(row["id"]), 0),
                "created_display": _format_timestamp(row["created_at"]),
            }
        )
        customers.append(item)

    devices = []
    for row in device_rows:
        item = dict(row)
        item["unassigned"] = int(row["customer_id"]) == unassigned_customer_id
        if item["unassigned"]:
            item["customer_name"] = "Nicht zugewiesen"
        devices.append(item)

    now = utcnow()
    today = now.date()
    active_devices = sum(1 for row in devices if row["enabled"])
    pending_devices = sum(
        1
        for row in devices
        if row["enabled"]
        and int(row["applied_config_version"] or 0) < int(row["customer_config_version"] or 1)
    )

    active_activation_codes = 0
    redeemed_activations = 0
    activations_today = 0
    recent_activations = []
    daily_counts = {today - timedelta(days=offset): 0 for offset in range(6, -1, -1)}
    for row in activation_rows:
        created = _parse_timestamp(row["created_at"])
        expires = _parse_timestamp(row["expires_at"])
        if created and created.date() == today:
            activations_today += 1
        if created and created.date() in daily_counts:
            daily_counts[created.date()] += 1
        if row["redeemed_at"]:
            redeemed_activations += 1
            status, status_class = "Eingelöst", "success"
        elif expires and expires <= now:
            status, status_class = "Abgelaufen", "muted"
        else:
            active_activation_codes += 1
            status, status_class = "Bereit", "warning"
        if len(recent_activations) < 6:
            recent_activations.append(
                {
                    "customer_name": row["customer_name"],
                    "device_id": row["device_id"] or "Noch keinem Gerät zugewiesen",
                    "platform": row["platform"] or "Einrichtungscode",
                    "created_display": _format_timestamp(row["created_at"]),
                    "status": status,
                    "status_class": status_class,
                }
            )

    weekday_names = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
    chart_max = max(max(daily_counts.values(), default=0), 1)
    activation_chart = [
        {
            "label": weekday_names[day.weekday()],
            "date": day.strftime("%d.%m."),
            "count": count,
            "height": max(7 if count else 3, round((count / chart_max) * 100)),
        }
        for day, count in daily_counts.items()
    ]

    return render_template(
        "dashboard.html",
        customers=customers,
        devices=devices,
        unassigned_customer_id=unassigned_customer_id,
        active_devices=active_devices,
        pending_devices=pending_devices,
        active_activation_codes=active_activation_codes,
        activations_today=activations_today,
        redeemed_activations=redeemed_activations,
        recent_activations=recent_activations,
        activation_chart=activation_chart,
    )


def install(app, db):
    """Install device-safe playlist assignment for dashboard v0.6.1."""
    if app.extensions.get("epimediahub_dashboard_v061"):
        return

    install_dashboard_v060(app, db)
    with db() as con:
        migrate_receiver_sync(con)
        _ensure_unassigned_customer(con)

    app.extensions["epimediahub_dashboard_v061"] = True
    app.view_functions["dashboard"] = lambda: _dashboard(db)
    app.view_functions["health"] = lambda: jsonify(
        status="ok", service="epimediahub-provisioning", api_version="0.6.1"
    )

    def create_customer_with_devices():
        guard = web_auth()
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        if not name:
            flash("Bitte einen Kundennamen eingeben.", "warning")
            return redirect(url_for("dashboard", _anchor="playlists"))
        config = form_config()
        with db() as con:
            migrate_receiver_sync(con)
            customer_id = con.execute(
                "INSERT INTO customers(name,config_json,created_at) VALUES(?,?,?)",
                (name, json.dumps(config, separators=(",", ":")), iso(utcnow())),
            ).lastrowid
            assigned = _apply_device_selection(con, int(customer_id), _selected_device_ids())
        flash(
            f"Playlist angelegt" + (f" und {assigned} Gerät(e) zugewiesen." if assigned else "."),
            "success",
        )
        return redirect(url_for("dashboard", _anchor="playlists"))

    def update_customer_with_devices(customer_id):
        guard = web_auth()
        if guard:
            return guard
        name = request.form.get("name", "").strip()
        if not name:
            flash("Bitte einen Kundennamen eingeben.", "warning")
            return redirect(url_for("dashboard", _anchor="playlists"))
        with db() as con:
            migrate_receiver_sync(con)
            row = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not row or _is_system_customer(row):
                abort(404)
            old_config = customer_config(row)
            new_config = form_config(old_config)
            con.execute("UPDATE customers SET name=? WHERE id=?", (name, customer_id))
            if json.dumps(old_config, sort_keys=True) != json.dumps(new_config, sort_keys=True):
                save_customer_config(con, customer_id, new_config)
            assigned = _apply_device_selection(
                con, customer_id, _selected_device_ids(), reconcile=True
            )
        flash(f"Playlist gespeichert · {assigned} Gerät(e) zugewiesen.", "success")
        return redirect(url_for("dashboard", _anchor="playlists"))

    def delete_customer_preserving_devices(customer_id):
        guard = web_auth()
        if guard:
            return guard
        if request.form.get("confirm_delete") != "1":
            abort(400)
        with db() as con:
            migrate_receiver_sync(con)
            row = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not row or _is_system_customer(row):
                abort(404)
            preserved = _preserve_customer_devices(con, customer_id)
            con.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        flash(
            f"Playlist {row['name']} gelöscht · {preserved} Gerät(e) bleiben erhalten und sind jetzt nicht zugewiesen.",
            "success",
        )
        return redirect(url_for("dashboard", _anchor="playlists"))

    def bulk_delete_preserving_devices():
        guard = web_auth()
        if guard:
            return guard
        if request.form.get("confirm_delete") != "1":
            abort(400)
        customer_ids = []
        for value in request.form.getlist("customer_ids"):
            try:
                customer_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        customer_ids = sorted(set(customer_ids))
        deleted = 0
        preserved = 0
        with db() as con:
            migrate_receiver_sync(con)
            for customer_id in customer_ids:
                row = con.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
                if not row or _is_system_customer(row):
                    continue
                preserved += _preserve_customer_devices(con, customer_id)
                con.execute("DELETE FROM customers WHERE id=?", (customer_id,))
                deleted += 1
        flash(
            f"{deleted} Playlist(s) gelöscht · {preserved} Gerät(e) bleiben als nicht zugewiesen erhalten.",
            "success",
        )
        return redirect(url_for("dashboard", _anchor="playlists"))

    app.view_functions["web_create_customer"] = create_customer_with_devices
    app.view_functions["web_update_customer"] = update_customer_with_devices
    app.view_functions["web_delete_customer"] = delete_customer_preserving_devices
    app.view_functions["web_bulk_delete_customers"] = bulk_delete_preserving_devices
