"""Read-only VPN license and connection overview for admin device cards.

A license grant is not an established WireGuard tunnel. Show the entitlement,
its real expiration, server/application provisioning and observed handshake as
distinct independent facts. No private keys, WireGuard profiles or device
tokens ever enter the template context.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from flask import request, session

from app import app, db
import vpn_dashboard as vpn


GRANT_ACTIONS = frozenset({"grant_year365", "trial7_auto", "trial7", "grant", "activate"})


def _read_overview(con):
    at = vpn.now()
    devices = con.execute("""
        SELECT d.id, d.device_id, d.customer_id, c.reseller_id
          FROM devices d JOIN customers c ON c.id=d.customer_id
    """).fetchall()
    trial_history = {
        row["device_key_hash"]: row["expires_at"]
        for row in con.execute("SELECT device_key_hash,expires_at FROM vpn_trials")
    }
    trials = {
        row["device_row_id"]: row
        for row in con.execute("SELECT device_row_id,device_key_hash,expires_at FROM vpn_trial_authorizations")
    }
    annuals = {
        row["device_row_id"]: row
        for row in con.execute("SELECT device_row_id,device_key_hash,expires_at FROM vpn_annual_authorizations")
    }
    joined = {
        row["device_row_id"]: row
        for row in con.execute(vpn.JOINED + " WHERE v.device_row_id IS NOT NULL")
    }
    # Backward compatibility: annual grants on already-bound WireGuard profiles
    # were logged only in vpn_audit; they were not in the annual auth table.
    # The most recent licensing event determines the type of the current grant.
    actions = {}
    for action in con.execute("""
        SELECT action,detail_json FROM vpn_audit
         WHERE action IN ('grant_year365','trial7_auto','trial7','grant','activate')
         ORDER BY id DESC
    """):
        try:
            data = json.loads(action["detail_json"])
            row_id = data.get("device_row_id")
        except (ValueError, TypeError, AttributeError):
            continue
        if type(row_id) is int and row_id not in actions:
            actions[row_id] = action["action"]

    agent_fresh = vpn.fresh(con)
    result = {}
    for d in devices:
        row_id = int(d["id"])
        raw_device_key_hash = hashlib.sha256(d["device_id"].encode("utf-8")).hexdigest()
        bound = joined.get(row_id)
        trial = trials.get(row_id)
        annual = annuals.get(row_id)
        trial_expiry = trial["expires_at"] if trial and trial["device_key_hash"] == raw_device_key_hash else None
        annual_expiry = annual["expires_at"] if annual and annual["device_key_hash"] == raw_device_key_hash else None
        last_grant = actions.get(row_id)

        # A registered VPN profile is the actual operational entitlement; an
        # annual authorization for a not-yet-enrolled device is still pending.
        expiry = bound["expires_at"] if bound else None
        if not expiry:
            candidates = [value for value in (trial_expiry, annual_expiry) if value]
            expiry = max(candidates, key=vpn.instant) if candidates else None

        if bound:
            if last_grant == "grant_year365":
                kind = "VPN 1 Jahr"
            elif last_grant in {"trial7_auto", "trial7"}:
                kind = "VPN 7 Tage Test"
            elif annual_expiry and expiry == annual_expiry:
                kind = "VPN 1 Jahr"
            elif trial_expiry and expiry == trial_expiry:
                kind = "VPN 7 Tage Test"
            else:
                kind = "VPN-Laufzeit"
        elif annual_expiry and (not trial_expiry or vpn.instant(annual_expiry) >= vpn.instant(trial_expiry)):
            kind = "VPN 1 Jahr"
        elif trial_expiry:
            kind = "VPN 7 Tage Test"
        else:
            kind = "Keine VPN-Lizenz"

        expired = bool(expiry and vpn.instant(expiry) <= at)
        if not expiry:
            license_state = "Keine Freigabe"
        elif expired:
            license_state = "Abgelaufen"
        else:
            license_state = "Bis zum Ablaufdatum gültig"

        handshake_at = None
        handshake_recent = False
        if bound:
            last_handshake = int(bound["last_handshake"] or 0)
            if 0 < last_handshake <= int(at.timestamp()) + 60:
                timestamp = datetime.fromtimestamp(last_handshake, tz=timezone.utc)
                handshake_at = vpn.stamp(timestamp)
                handshake_recent = timedelta(0) <= (at - timestamp) <= timedelta(minutes=3)

        if not expiry:
            setup = "Nicht freigegeben"
        elif expired:
            setup = "Lizenz abgelaufen"
        elif bound is None:
            setup = "Wartet auf VPN-Einrichtung in der App"
        elif bound["status"] != "ACTIVE":
            setup = "VPN-Zugang gesperrt"
        else:
            desired = vpn.desired(bound, at)
            agent_confirmed = bool(
                desired["enabled"] and agent_fresh and bound["applied_at"]
                and bound["applied_enabled"] == 1
                and bound["applied_generation"] == desired["generation"]
                and (at - vpn.instant(bound["applied_at"])) < timedelta(seconds=vpn.LEASE_SECONDS)
            )
            if not desired["enabled"]:
                setup = "Geräte-/Kundenzuordnung prüfen"
            elif not agent_fresh:
                setup = "Finnland-Agent meldet sich nicht"
            else:
                setup = "Finnland-Server bereit" if agent_confirmed else "Wartet auf Finnland-Bestätigung"

        if bound is None:
            handshake = "Noch kein VPN-Profil"
        elif handshake_recent and agent_fresh:
            handshake = "Handshake kürzlich bestätigt"
        elif handshake_at:
            handshake = "Letzter Handshake (nicht aktuell)"
        else:
            handshake = "Noch kein Handshake bestätigt"

        result[row_id] = {
            "license": kind,
            "license_state": license_state,
            "expires_at": expiry,
            "setup": setup,
            "handshake": handshake,
            "handshake_at": handshake_at,
            "has_license": bool(expiry and not expired),
            "trial_used": raw_device_key_hash in trial_history,
        }
    return result


@app.context_processor
def vpn_admin_license_overview():
    if request.path != "/admin" or not session.get("admin"):
        return {}
    with db() as con:
        states = _read_overview(con)
    return {"vpn_license_states": states}
