"""Normalize provider-confirmed IPTV subscription expiries without sharing secrets.

The server-side integration may call this ONLY with a freshly authenticated
and independently verified Xtream account response. Never infer expiry from
annual app license, VPN, EpiScene analysis-playlist date, or playlist URL.

No network, database or logging of raw provider payloads in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class ProviderExpiry:
    expires_on: date | None
    status: str
    source: str = "provider_verified"

def xtream_expiry(response: object) -> ProviderExpiry:
    """Read Xtream user_info.exp_date as Unix seconds; zero/null = unknown.

    Expiry is translated to the administrator's Europe/Berlin *date*.
    Do not mark a user as expiring when provider sends malformed/unknown data.
    """
    if not isinstance(response, dict):
        return ProviderExpiry(None, "unavailable", "xtream_user_info")
    info = response.get("user_info")
    if not isinstance(info, dict):
        return ProviderExpiry(None, "unavailable", "xtream_user_info")
    raw = info.get("exp_date")
    if raw is None or raw in ("", "null", 0, "0"):
        return ProviderExpiry(None, "undated", "xtream_user_info")
    if type(raw) is bool or type(raw) not in (str, int):
        return ProviderExpiry(None, "unavailable", "xtream_user_info")
    if isinstance(raw, str) and (not raw.isascii() or not raw.isdecimal()
                                 or len(raw) > 12):
        return ProviderExpiry(None, "unavailable", "xtream_user_info")
    stamp = int(raw)
    # Strong range check to avoid accepting milliseconds, TTL, or bad units.
    if not 946684800 <= stamp <= 4102444800:  # years 2000..2100
        return ProviderExpiry(None, "unavailable", "xtream_user_info")
    try:
        local = datetime.fromtimestamp(stamp, timezone.utc).astimezone(BERLIN)
    except (ValueError, OverflowError, OSError):
        return ProviderExpiry(None, "unavailable", "xtream_user_info")
    if not 2000 <= local.year <= 2100:
        return ProviderExpiry(None, "unavailable", "xtream_user_info")
    return ProviderExpiry(local.date(), "confirmed", "xtream_user_info")


def verified_calendar_date(provider_value: object) -> ProviderExpiry:
    """For sources already delivering a verified ISO calendar date.

    Unlike provider timestamps, YYYY-MM-DD has no timezone conversion.
    Only use this when the provider itself explicitly specifies a *date*.
    """
    if not isinstance(provider_value, str) or len(provider_value) != 10:
        return ProviderExpiry(None, "unavailable", "provider_date")
    try:
        parsed = date.fromisoformat(provider_value)
    except ValueError:
        return ProviderExpiry(None, "unavailable", "provider_date")
    if parsed.isoformat() != provider_value or not 2000 <= parsed.year <= 2100:
        return ProviderExpiry(None, "unavailable", "provider_date")
    return ProviderExpiry(parsed, "confirmed", "provider_date")
