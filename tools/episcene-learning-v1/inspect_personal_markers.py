#!/usr/bin/env python3
"""Read-only EpiScene audit for user-named shows; emits no secrets or device IDs.

Run as: python3 inspect_personal_markers.py
The source database is never modified. No labels are auto-approved.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import sqlite3
from statistics import median

SOURCE = Path("/var/lib/epimediahub/provisioning.db")
SHOWS = {
    "Lie to Me": ("lie to me",),
    "The Lincoln Lawyer": ("lincoln lawyer",),
    "MobLand": ("mobland", "mob land"),
}
USER_ORIGINS = {"device", "manual", "user", "app"}
MAX_DETAIL_PER_SHOW = 45
SEGMENT_TYPES = ('intro', 'recap', 'outro')


def durations_ms(rows):
    result = []
    for row in rows:
        try:
            value = int(row['end_ms']) - int(row['start_ms'])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < value <= 86_400_000:
            result.append(value)
    return result


def summarize_group(rows):
    seconds = [x / 1000 for x in durations_ms(rows)]
    if not seconds:
        return '0 Markierungen'
    return (f'{len(seconds)} Markierungen | Median {median(seconds):.1f}s | '
            f'Spanne {min(seconds):.1f}-{max(seconds):.1f}s')


def stamp(ms):
    try:
        ms = int(ms)
        if ms < 0:
            return "?"
        secs, frac = divmod(ms, 1000)
        hh, rem = divmod(secs, 3600)
        mm, ss = divmod(rem, 60)
        return f"{hh:02d}:{mm:02d}:{ss:02d}.{frac:03d}"
    except (ValueError, TypeError):
        return "?"


def has_columns(conn, table, columns):
    names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return columns.issubset(names)


def audit(conn):
    print("=== EPISCENE: MANUELLE MARKER / NUR LESEN ===")
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    required_records = {
        "id", "asset_key", "segment_type", "start_ms", "end_ms",
        "status", "source", "reviewed_at",
    }
    required_assets = {
        "asset_key", "playlist_id", "title", "season", "episode",
    }
    if not has_columns(conn, "skip_records", required_records):
        raise RuntimeError("skip_records: fehlende Spalten")
    if not has_columns(conn, "skip_assets", required_assets):
        raise RuntimeError("skip_assets: fehlende Spalten")

    records = conn.execute("""
        SELECT r.id, r.asset_key, COALESCE(a.title, r.title) AS title, a.playlist_id,
               COALESCE(a.season, r.season) AS season,
               COALESCE(a.episode, r.episode) AS episode, r.segment_type, r.start_ms,
               r.end_ms, r.status, r.source, r.reviewed_at
        FROM skip_records AS r
        LEFT JOIN skip_assets AS a ON r.asset_key=a.asset_key
        WHERE (a.playlist_id IN (8,10) OR a.asset_key IS NULL)
          AND (
              lower(COALESCE(a.title,r.title)) LIKE '%lie to me%'
              OR lower(COALESCE(a.title,r.title)) LIKE '%lincoln lawyer%'
              OR lower(COALESCE(a.title,r.title)) LIKE '%mobland%'
              OR lower(COALESCE(a.title,r.title)) LIKE '%mob land%'
          )
        ORDER BY a.title, a.season, a.episode, r.id
    """).fetchall()
    groups = defaultdict(list)
    for row in records:
        title = str(row["title"] or "").lower()
        for name, aliases in SHOWS.items():
            if any(alias in title for alias in aliases):
                groups[name].append(row)
                break
    has_evidence = has_columns(conn, "skip_auto_evidence", {"record_id", "human_review"})
    has_windows = has_columns(conn, "skip_app_windows", {"asset_key"})
    human_review = {}
    if has_evidence:
        for row in conn.execute("""
            SELECT e.record_id, e.human_review
            FROM skip_auto_evidence e JOIN skip_records r ON r.id=e.record_id
            LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
            WHERE (a.playlist_id IN (8,10) OR a.asset_key IS NULL)
              AND (lower(COALESCE(a.title,r.title)) LIKE '%lie to me%'
                OR lower(COALESCE(a.title,r.title)) LIKE '%lincoln lawyer%'
                OR lower(COALESCE(a.title,r.title)) LIKE '%mobland%'
                OR lower(COALESCE(a.title,r.title)) LIKE '%mob land%')
        """):
            v = row[1]
            # Provenance flag is metadata, not independently verified user identity.
            human_review[row[0]] = "ja" if str(v).lower() in ("1", "true") else "nein"
    app_counts = Counter()
    if has_windows:
        for row in conn.execute("""
            SELECT a.title, COUNT(*) AS cnt
            FROM skip_app_windows w
            JOIN skip_assets a ON a.asset_key=w.asset_key
            WHERE a.playlist_id IN (8,10)
              AND (lower(a.title) LIKE '%lie to me%'
                OR lower(a.title) LIKE '%lincoln lawyer%'
                OR lower(a.title) LIKE '%mobland%'
                OR lower(a.title) LIKE '%mob land%')
            GROUP BY a.title
        """):
            title = str(row[0]).lower()
            for show, aliases in SHOWS.items():
                if any(alias in title for alias in aliases):
                    app_counts[show] += int(row[1])
                    break

    for show in SHOWS:
        rows = groups[show]
        print("\n### " + show)
        print(f"Gesamte Markerdatensaetze aktuell: {len(rows)}")
        print(f"Davon ohne aktuellen skip_assets-Eintrag: {sum(1 for r in rows if r['playlist_id'] is None)}")
        print(f"App-Fenstereintraege: {app_counts[show]}")
        breakdown = Counter((str(r["source"]), str(r["status"])) for r in rows)
        for (src, status), n in sorted(breakdown.items()):
            print(f"  {src} / {status}: {n}")
        print('--- Segmenttypen (Intro / Rückblick / Abspann), getrennte Statistik ---')
        for kind in SEGMENT_TYPES:
            matching = [r for r in rows if str(r['segment_type']).lower() == kind]
            manually_marked = [r for r in matching
                               if str(r['source']).lower() in USER_ORIGINS
                               and str(r['status']).lower() != 'superseded']
            automatic = [r for r in matching
                         if str(r['source']).lower() not in USER_ORIGINS
                         and str(r['status']).lower() != 'superseded']
            print(f'{kind}: manuell/geraet {summarize_group(manually_marked)}; '
                  f'automatische Vorschlaege {summarize_group(automatic)}')
        print('Laufzeiten sind Beobachtungen, keine globalen Grenzwerte oder beweisbaren Freigaben.')
        candidates = sorted([r for r in rows if str(r["source"]).lower() in USER_ORIGINS],
                            key=lambda x: (str(x['segment_type']), str(x['title']),
                                           int(x['season'] or 0), int(x['episode'] or 0),
                                           int(x['id'])))
        print(f"MANUELLE/GERAETE-QUELLEN: {len(candidates)}")
        print("HINWEIS: 'device' und 'reviewed_at' beweisen alleine nicht, wer markiert hat.")
        print("Spalten: ID | Playlist | Staffel/Folge | Typ | Start - Ende | Dauer | Status | Quelle | reviewed_at? | human_review?")
        if not candidates:
            print("  Keine Quelle device/manual/user/app in dieser Datenbank-Abfrage gefunden.")
        for r in candidates[:MAX_DETAIL_PER_SHOW]:
            start, end = r["start_ms"], r["end_ms"]
            dur = (int(end)-int(start))/1000 if start is not None and end is not None else -1
            print(
                f"  #{r['id']} | P{r['playlist_id']} | S{r['season']}E{r['episode']} | "
                f"{r['segment_type']} | {stamp(start)} - {stamp(end)} | "
                f"{dur:.2f}s | {r['status']} | {r['source']} | "
                f"{'ja' if r['reviewed_at'] else 'nein'} | "
                f"{human_review.get(r['id'], 'unbekannt')}"
            )
            # Show nearest active competing hypothesis, not an automatic truth.
            similar = [
                x for x in rows
                if x["asset_key"] == r["asset_key"]
                and x["segment_type"] == r["segment_type"]
                and x["id"] != r["id"]
                and x["status"] != "superseded"
                and x["start_ms"] is not None
            ]
            similar.sort(key=lambda x: abs(int(x["start_ms"])-int(start)))
            for x in similar[:2]:
                print(
                    f"       Vergleich #{x['id']} {x['source']}/{x['status']}: "
                    f"{stamp(x['start_ms'])}-{stamp(x['end_ms'])}, "
                    f"Startabweichung {abs(int(x['start_ms'])-int(start))/1000:.2f}s"
                )
        if len(candidates) > MAX_DETAIL_PER_SHOW:
            print(f"  ... {len(candidates)-MAX_DETAIL_PER_SHOW} weitere, begrenzt.")
    print("\n=== ENDE: NUR DATENBANKLESEZUGRIFF, KEINE AENDERUNGEN ===")


def main():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        raise SystemExit("Datenbank nicht gefunden oder unerwarteter Symlink.")
    connection = sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        audit(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
