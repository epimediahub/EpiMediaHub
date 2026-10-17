"""Pure, side-effect-free rules for EpiMediaHub Admin alerts.

Input snapshots must be sanitized: NEVER include credentials, stream URLs,
customer details, access tokens or playback contents. This module does not send
notifications, mutate databases, or restart services.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class Alert:
    key: str
    kind: str
    severity: str
    entity_id: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _list(snapshot: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = snapshot.get(key, [])
    return value if isinstance(value, list) else []


def _number(value: Any, fallback: float = 0) -> float:
    try:
        return float(value) if value is not None else fallback
    except (ValueError, TypeError):
        return fallback


def evaluate(snapshot: Mapping[str, Any], now_epoch: int) -> list[Alert]:
    """Evaluate seven user-approved alert types against one normalized snapshot.

    The caller must persist alert keys/status to suppress repeats, track
    acknowledgements and generate recovery notifications. Missing evidence
    never implies a failure. Time values are UTC Unix seconds.
    """
    result: list[Alert] = []

    for lane in _list(snapshot, "analysis_lanes"):
        lane_id = str(lane.get("id", "")).strip()
        last_progress = lane.get("last_progress_epoch")
        if not lane_id or last_progress is None:
            continue
        queued = _number(lane.get("queued_jobs"))
        age = now_epoch - _number(last_progress, now_epoch)
        if queued > 0 and not lane.get("paused", False) and age >= 900:
            result.append(Alert(
                f"analysis_stalled:{lane_id}", "analysis_stalled", "critical",
                lane_id, "EpiScene-Lane ohne Fortschritt trotz wartender Jobs",
            ))

    for playlist in _list(snapshot, "playlists"):
        playlist_id = str(playlist.get("id", "")).strip()
        if not playlist_id:
            continue
        expires_at = playlist.get("expires_at_epoch")
        unauthorized = _number(playlist.get("consecutive_auth_failures"))
        if expires_at is not None and _number(expires_at) <= now_epoch:
            result.append(Alert(
                f"playlist_access:{playlist_id}", "playlist_access", "critical",
                playlist_id, "Analyse-Playlist abgelaufen",
            ))
        elif unauthorized >= 3:
            result.append(Alert(
                f"playlist_access:{playlist_id}", "playlist_access", "critical",
                playlist_id, "Wiederholte Zugriffsfehler beim Analysezugang",
            ))
        elif expires_at is not None and 0 < _number(expires_at) - now_epoch <= 72 * 3600:
            result.append(Alert(
                f"playlist_expiring:{playlist_id}", "playlist_access", "warning",
                playlist_id, "Analyse-Playlist läuft innerhalb von 72 Stunden ab",
            ))

    for worker in _list(snapshot, "workers"):
        worker_id = str(worker.get("id", "")).strip()
        if not worker_id:
            continue
        expected = worker.get("expected_versions")
        actual = worker.get("actual_versions")
        version_mismatch = (
            isinstance(expected, dict) and isinstance(actual, dict)
            and expected != actual
        )
        preflight_failures = _number(worker.get("consecutive_preflight_failures"))
        if version_mismatch or preflight_failures >= 2:
            result.append(Alert(
                f"worker_preflight:{worker_id}", "worker_preflight", "critical",
                worker_id, "Worker nicht erreichbar oder Versionsprüfung fehlgeschlagen",
            ))

    for service in _list(snapshot, "services"):
        service_id = str(service.get("id", "")).strip()
        failures = _number(service.get("consecutive_health_failures"))
        if service_id and failures >= 3:
            result.append(Alert(
                f"service_down:{service_id}", "service_down", "critical",
                service_id, "Server oder API mehrfach nicht erreichbar",
            ))

    for build in _list(snapshot, "builds"):
        build_id = str(build.get("id", "")).strip()
        if build_id and build.get("outcome") in {"failed", "failure"}:
            result.append(Alert(
                f"build_failed:{build_id}", "build_failed", "warning",
                build_id, "Android-Build oder Release-Synchronisierung fehlgeschlagen",
            ))

    for metric in _list(snapshot, "playback_windows"):
        metric_id = str(metric.get("id", "")).strip()
        errors = _number(metric.get("errors"))
        sessions = _number(metric.get("sessions"))
        devices = _number(metric.get("distinct_affected_devices"))
        # Minimum counts prevent alerts from a single device or tiny sample.
        if metric_id and errors >= 10 and sessions >= 20 and devices >= 3 \
                and errors / sessions >= 0.20:
            result.append(Alert(
                f"playback_errors:{metric_id}", "playback_errors", "warning",
                metric_id, "Ungewöhnlich viele Wiedergabefehler bei Kunden",
            ))

    report = snapshot.get("daily_report")
    if isinstance(report, dict):
        date_today = datetime.fromtimestamp(now_epoch, BERLIN).date().isoformat()
        date_report = report.get("generated_date_berlin")
        report_id = str(report.get("id", "episcene"))
        if date_report == date_today and report.get("ready") is True:
            result.append(Alert(
                f"daily_report:{date_today}:{report_id}", "daily_report", "info",
                report_id, "Täglicher EpiScene-Bericht verfügbar",
            ))

    return result
