from __future__ import annotations

import json

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from app import customer_config, iso, migrate_receiver_sync, public_config, utcnow, web_auth


def _config_identity(name: str, config: dict):
    kind = str(config.get("playlist_type", "M3U")).upper()
    customer = name.strip().casefold()
    if kind == "XTREAM":
        return (
            customer,
            kind,
            str(config.get("xtream_server", "")).strip().rstrip("/").casefold(),
            str(config.get("xtream_username", "")).strip().casefold(),
        )
    return (customer, kind, str(config.get("playlist_url", "")).strip())


def _parse_bulk_playlists(raw: str):
    entries = []
    errors = []
    auto_index = 1

    for line_number, raw_line in enumerate((raw or "").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("|")]
        try:
            if len(parts) == 1:
                if not parts[0].startswith(("http://", "https://")):
                    raise ValueError("URL fehlt")
                customer_name = f"Playlist {auto_index}"
                config = {
                    "playlist_type": "M3U",
                    "playlist_name": customer_name,
                    "playlist_url": parts[0],
                    "xtream_server": "",
                    "xtream_username": "",
                    "xtream_password": "",
                    "xtream_output": "ts",
                }
                auto_index += 1

            elif len(parts) >= 3 and parts[1].upper() == "XTREAM":
                if len(parts) < 5:
                    raise ValueError("Xtream benötigt Server, Benutzername und Passwort")
                customer_name = parts[0]
                server = parts[2].rstrip("/")
                username = parts[3]
                password = parts[4]
                output = parts[5].lower() if len(parts) > 5 else "ts"
                playlist_name = parts[6] if len(parts) > 6 and parts[6] else customer_name
                if (
                    not customer_name
                    or not server.startswith(("http://", "https://"))
                    or not username
                    or not password
                ):
                    raise ValueError("Xtream-Zeile ist unvollständig")
                config = {
                    "playlist_type": "XTREAM",
                    "playlist_name": playlist_name,
                    "playlist_url": "",
                    "xtream_server": server,
                    "xtream_username": username,
                    "xtream_password": password,
                    "xtream_output": output if output in {"ts", "m3u8"} else "ts",
                }

            else:
                customer_name = parts[0]
                if len(parts) >= 3 and parts[1].upper() == "M3U":
                    url = parts[2]
                    playlist_name = parts[3] if len(parts) > 3 and parts[3] else customer_name
                elif len(parts) >= 3:
                    playlist_name = parts[1] or customer_name
                    url = parts[2]
                else:
                    playlist_name = customer_name
                    url = parts[1]

                if not customer_name or not url.startswith(("http://", "https://")):
                    raise ValueError("Kundenname oder gültige URL fehlt")
                config = {
                    "playlist_type": "M3U",
                    "playlist_name": playlist_name,
                    "playlist_url": url,
                    "xtream_server": "",
                    "xtream_username": "",
                    "xtream_password": "",
                    "xtream_output": "ts",
                }

            entries.append((customer_name, public_config(config)))
        except (IndexError, ValueError) as exc:
            errors.append(f"Zeile {line_number}: {exc}")

    return entries, errors


def _dashboard(db):
    guard = web_auth()
    if guard:
        return guard

    with db() as con:
        migrate_receiver_sync(con)
        customer_rows = con.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
        devices = con.execute(
            """
            SELECT d.*,c.name customer_name,c.config_version customer_config_version
            FROM devices d JOIN customers c ON c.id=d.customer_id
            ORDER BY d.id DESC
            """
        ).fetchall()
        device_count_rows = con.execute(
            "SELECT customer_id,COUNT(*) total FROM devices GROUP BY customer_id"
        ).fetchall()

    device_counts = {int(row["customer_id"]): int(row["total"]) for row in device_count_rows}
    customers = []
    for row in customer_rows:
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
            }
        )
        customers.append(item)

    active_devices = sum(1 for row in devices if row["enabled"])
    pending_devices = sum(
        1
        for row in devices
        if row["enabled"]
        and int(row["applied_config_version"] or 0) < int(row["customer_config_version"] or 1)
    )

    return render_template(
        "dashboard.html",
        customers=customers,
        devices=devices,
        active_devices=active_devices,
        pending_devices=pending_devices,
    )


def install(app, db):
    """Install the v0.5.2 admin dashboard without changing the device API contract."""
    if app.extensions.get("epimediahub_dashboard_v052"):
        return
    app.extensions["epimediahub_dashboard_v052"] = True

    app.view_functions["dashboard"] = lambda: _dashboard(db)
    app.view_functions["health"] = lambda: jsonify(
        status="ok", service="epimediahub-provisioning", api_version="0.5.2"
    )

    @app.post("/admin/customers/bulk", endpoint="web_bulk_create_customers")
    def web_bulk_create_customers():
        guard = web_auth()
        if guard:
            return guard

        entries, errors = _parse_bulk_playlists(request.form.get("bulk_playlists", ""))
        if not entries:
            flash("Es wurde keine gültige Playlist gefunden.", "error")
            if errors:
                flash(" · ".join(errors[:4]), "error")
            return redirect(url_for("dashboard", _anchor="playlists"))

        created = 0
        duplicates = 0
        with db() as con:
            migrate_receiver_sync(con)
            existing = {
                _config_identity(row["name"], customer_config(row))
                for row in con.execute("SELECT * FROM customers").fetchall()
            }
            for name, config in entries:
                identity = _config_identity(name, config)
                if identity in existing:
                    duplicates += 1
                    continue
                con.execute(
                    "INSERT INTO customers(name,config_json,created_at) VALUES(?,?,?)",
                    (name, json.dumps(config, separators=(",", ":")), iso(utcnow())),
                )
                existing.add(identity)
                created += 1

        flash(
            f"{created} Playlist(s) hinzugefügt · {duplicates} Duplikat(e) übersprungen.",
            "success",
        )
        if errors:
            flash(
                f"{len(errors)} Zeile(n) konnten nicht importiert werden: " + " · ".join(errors[:4]),
                "warning",
            )
        return redirect(url_for("dashboard", _anchor="playlists"))

    @app.post("/admin/customers/<int:customer_id>/delete", endpoint="web_delete_customer")
    def web_delete_customer(customer_id: int):
        guard = web_auth()
        if guard:
            return guard
        if request.form.get("confirm_delete") != "1":
            abort(400)

        with db() as con:
            migrate_receiver_sync(con)
            row = con.execute("SELECT id,name FROM customers WHERE id=?", (customer_id,)).fetchone()
            if not row:
                abort(404)
            linked_devices = con.execute(
                "SELECT COUNT(*) total FROM devices WHERE customer_id=?", (customer_id,)
            ).fetchone()["total"]
            con.execute("DELETE FROM customers WHERE id=?", (customer_id,))

        suffix = (
            f"; {linked_devices} Gerätezuordnung(en) wurden mit entfernt" if linked_devices else ""
        )
        flash(f"Playlist/Kunde {row['name']} gelöscht{suffix}.", "success")
        return redirect(url_for("dashboard", _anchor="playlists"))

    @app.post("/admin/customers/bulk-delete", endpoint="web_bulk_delete_customers")
    def web_bulk_delete_customers():
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
        if not customer_ids:
            flash("Keine Playlists zum Löschen ausgewählt.", "warning")
            return redirect(url_for("dashboard", _anchor="playlists"))

        placeholders = ",".join("?" for _ in customer_ids)
        with db() as con:
            migrate_receiver_sync(con)
            rows = con.execute(
                f"SELECT id,name FROM customers WHERE id IN ({placeholders})", customer_ids
            ).fetchall()
            if rows:
                con.execute(f"DELETE FROM customers WHERE id IN ({placeholders})", customer_ids)

        flash(
            f"{len(rows)} Playlist(s) inklusive zugehöriger Aktivierungen/Gerätezuordnungen gelöscht.",
            "success",
        )
        return redirect(url_for("dashboard", _anchor="playlists"))
