from __future__ import annotations

from datetime import timedelta

from flask import jsonify, render_template

from app import customer_config, migrate_receiver_sync, utcnow, web_auth
from dashboard_v052 import install as install_dashboard_v052


def _parse_timestamp(value):
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _format_timestamp(value):
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "–"
    return parsed.strftime("%d.%m.%Y · %H:%M")


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
        activation_rows = con.execute(
            """
            SELECT a.*,c.name customer_name
            FROM activations a JOIN customers c ON c.id=a.customer_id
            ORDER BY a.id DESC
            """
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
                "created_display": _format_timestamp(row["created_at"]),
            }
        )
        customers.append(item)

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
            status = "Eingelöst"
            status_class = "success"
        elif expires and expires <= now:
            status = "Abgelaufen"
            status_class = "muted"
        else:
            active_activation_codes += 1
            status = "Bereit"
            status_class = "warning"

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
        active_devices=active_devices,
        pending_devices=pending_devices,
        active_activation_codes=active_activation_codes,
        activations_today=activations_today,
        redeemed_activations=redeemed_activations,
        recent_activations=recent_activations,
        activation_chart=activation_chart,
    )


def install(app, db):
    """Install the v0.6.0 admin UI while retaining the proven v0.5.2 actions."""
    if app.extensions.get("epimediahub_dashboard_v060"):
        return

    install_dashboard_v052(app, db)
    app.extensions["epimediahub_dashboard_v060"] = True
    app.view_functions["dashboard"] = lambda: _dashboard(db)
    app.view_functions["health"] = lambda: jsonify(
        status="ok", service="epimediahub-provisioning", api_version="0.6.0"
    )
