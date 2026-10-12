"""Admin-only, read-only operational diagnostics. Never expose account secrets or raw logs."""
from __future__ import annotations
from datetime import datetime, timezone
import sqlite3

from flask import jsonify, redirect, render_template, request, session, url_for
from app import app, db

def _table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def _count(con, table, where="1=1"):
    # Only call with constant SQL from this module.
    return con.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]

@app.get("/admin/diagnostics")
def dashboard_diagnostics():
    if not session.get("admin"):
        return redirect(url_for("login", next=request.path))
    with db() as con:
        state = {
            "customers": _count(con, "customers"),
            "resellers": _count(con, "resellers") if _table(con, "resellers") else 0,
            "devices": _count(con, "devices"),
            "sync_failed": _count(con, "devices", "last_sync_status='error'"),
            "sync_pending": _count(con, "devices", "COALESCE(applied_config_version,0) <> COALESCE(config_version,1)"),
            "device_disabled": _count(con, "devices", "enabled=0"),
            "vpn_active": _count(con, "vpn_devices", "status='ACTIVE'") if _table(con, "vpn_devices") else None,
            "vpn_trials_used": _count(con, "vpn_trials") if _table(con, "vpn_trials") else None,
            "lifetime_licenses": _count(con, "lifetime_licenses", "status='ACTIVE'") if _table(con, "lifetime_licenses") else None,
        }
        agent = con.execute("SELECT value FROM vpn_meta WHERE key='agent_applied_at'").fetchone() if _table(con, "vpn_meta") else None
        agent_seen = None
        agent_fresh = False
        if agent and agent[0]:
            try:
                agent_seen = datetime.fromisoformat(agent[0].replace("Z", "+00:00"))
                agent_fresh = 0 <= (datetime.now(timezone.utc) - agent_seen).total_seconds() <= 600
            except (ValueError, TypeError):
                agent_seen = None
        state["vpn_agent"] = "Aktuell" if agent_fresh else "Keine aktuelle Bestätigung"
        # Device identifiers and provider error strings are intentionally omitted.
        issues = []
        if state["sync_failed"]:
            issues.append(f"{state['sync_failed']} Gerät(e) melden Synchronisierungsfehler.")
        if state["sync_pending"]:
            issues.append(f"{state['sync_pending']} Gerät(e) haben ausstehende Konfigurationen.")
        if state["vpn_active"] and not agent_fresh:
            issues.append("VPN-Geräte sind aktiv, aber der Finnland-Agent hat keine aktuelle Bestätigung.")
        if not issues:
            issues.append("Keine Auffälligkeiten in den verfügbaren Dashboard-Zählern.")
    response = app.make_response(render_template("dashboard_diagnostics.html", state=state, issues=issues))
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response
