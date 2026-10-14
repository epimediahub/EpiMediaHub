#!/usr/bin/env python3
"""Compare owner-attested EpiScene reference-round 40 markers with auto suggestions.

Read-only: NEVER creates verified labels, edits skip_records, or auto-releases.
A device source alone is not sufficient cryptographic proof of a human reviewer.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

DATA = Path("/var/lib/epimediahub/provisioning.db")
STATE = Path("/var/lib/episcene-learning/reference-round-40")
HUMAN_SOURCES = {"device", "manual", "app", "user"}
KINDS = {"intro", "recap", "outro"}
REJECTED_IDS = {2282}  # Owner says first of two Berlino S1E2 intros was a typo.
CONFIRMED_IDS = {2283, 2291, 2293, 2295}
MIN_DURATION = 1
MAX_DURATION = 86400000


def norm(x):
    return " ".join(str(x or "").casefold().split())


def snapshot_signature(r):
    items = [norm(r["segment_type"]), int(r["start_ms"]), int(r["end_ms"]),
             str(r["status"]), str(r["source"]), str(r["created_at"])]
    return hashlib.sha256(json.dumps(items, ensure_ascii=False).encode("utf-8")).hexdigest()


def load_rows(db):
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    for table, expected in {
        "skip_records": {"id","asset_key","title","season","episode","segment_type",
                         "start_ms","end_ms","source","status","created_at"},
        "skip_assets": {"asset_key","title","season","episode","playlist_id"}
    }.items():
        cols = {x[1] for x in db.execute("PRAGMA table_info(" + table + ")")}
        if not expected.issubset(cols):
            raise RuntimeError("Schema mismatch: " + table)
    return [dict(x) for x in db.execute("""
      SELECT r.id,r.asset_key,r.title AS marker_title,r.season AS marker_season,
             r.episode AS marker_episode,r.segment_type,r.source,r.status,
             r.start_ms,r.end_ms,r.created_at,
             a.title AS asset_title,a.season AS asset_season,
             a.episode AS asset_episode,a.playlist_id
      FROM skip_records r LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
      WHERE lower(r.segment_type) IN ('intro','recap','outro')
    """)]


def analyze(rows, plan, baseline):
    choices = defaultdict(list)
    by_ref = {e["id"]: e for e in plan["episodes"]}
    for e in plan["episodes"]:
        choices[(norm(e["series"]), int(e["season"]), int(e["episode"]))].append(e)
    autos = defaultdict(list)
    accepted = []
    quarantined = []
    old_by_ref = baseline["existing_marker_signatures"]
    for r in rows:
        source = norm(r["source"])
        kind = norm(r["segment_type"])
        try:
            start, end = int(r["start_ms"]), int(r["end_ms"])
            season = r["asset_season"] if r["asset_season"] is not None else r["marker_season"]
            episode = r["asset_episode"] if r["asset_episode"] is not None else r["marker_episode"]
            key = (norm(r["asset_title"] or r["marker_title"]), int(season), int(episode))
        except (ValueError, TypeError):
            continue
        if not (0 <= start < end <= MAX_DURATION) or kind not in KINDS:
            continue
        if source not in HUMAN_SOURCES:
            if norm(r["status"]) != "superseded":
                autos[(str(r["asset_key"]), kind)].append(r)
            continue
        possible = choices.get(key, [])
        if len(possible) != 1:
            continue  # Do not invent a playlist for ambiguous/orphaned episodes.
        episode_ref = possible[0]
        if r["playlist_id"] is not None and int(r["playlist_id"]) != int(episode_ref["playlist_id"]):
            continue
        ref_id = episode_ref["id"]
        rid = int(r["id"])
        existing = old_by_ref.get(ref_id, {}).get(str(rid))
        if existing == snapshot_signature(r):
            continue  # Baseline: not part of this new reference round.
        # Unlinked records (no skip_assets) must be provably from after baseline.
        if r["playlist_id"] is None:
            from datetime import datetime, timezone
            try:
                created = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                since = datetime.fromisoformat(str(baseline["recorded_utc"]).replace("Z", "+00:00"))
                if created.tzinfo is None or since.tzinfo is None or created < since:
                    continue
            except (ValueError, TypeError):
                continue
        item = {"ref":ref_id, "id":rid, "series":episode_ref["series"],
                "season":episode_ref["season"], "episode":episode_ref["episode"],
                "playlist_id":r["playlist_id"], "orphaned":r["playlist_id"] is None,
                "kind":kind, "start_ms":start, "end_ms":end,
                "asset_key":str(r["asset_key"])}
        if rid in REJECTED_IDS or norm(r["status"]) == "superseded":
            quarantined.append((item, "rejected_by_owner" if rid in REJECTED_IDS else "superseded"))
        else:
            accepted.append(item)

    grouped = defaultdict(list)
    for item in accepted:
        grouped[(item["ref"], item["kind"])].append(item)
    conflicts = {key for key, grp in grouped.items() if len(grp) > 1}
    # Do not average or use conflicting labels, even if timestamps look close.
    candidates = [x for x in accepted if (x["ref"],x["kind"]) not in conflicts]
    approved_records = []
    optimistic_errors = defaultdict(list)
    skipped_orphan = 0
    for x in candidates:
        if x["orphaned"]:
            skipped_orphan += 1
            continue  # No proof of the same stream/cut as other asset keys.
        comparisons = autos.get((x["asset_key"], x["kind"]), [])
        if not comparisons:
            continue
        nearest = min(comparisons, key=lambda a:
            abs(int(a["start_ms"]) - x["start_ms"]) +
            abs(int(a["end_ms"]) - x["end_ms"]))
        start_diff = (int(nearest["start_ms"]) - x["start_ms"]) / 1000
        end_diff = (int(nearest["end_ms"]) - x["end_ms"]) / 1000
        optimistic_errors[x["kind"]].append((start_diff,end_diff))
        approved_records.append((x,nearest,start_diff,end_diff))

    print("=== EPISCENE: 40er-REFERENZEN GEGEN AUTOMATIK (NUR LESEN) ===")
    print("Neue/geaenderte, exakt zugeordnete device/manuelle Marker:",len(accepted)+len(quarantined))
    print("Explizit verworfene/archivierte Marker:",len(quarantined))
    print("Moegliche Positiv-Beispiele:",len(accepted))
    print("Typen:", dict(sorted(Counter(x["kind"] for x in accepted).items())))
    print("Folgen mit neuen/geaenderten Eintraegen:",
          len({x["ref"] for x in accepted+ [q[0] for q in quarantined]}),"/40")
    print("Verwaiste Positiv-Beispiele ohne Playlist-Verknuepfung:",
          sum(x["orphaned"] for x in accepted))
    print("Mehrfachmarkierungen innerhalb derselben Folge/Art:",len(conflicts))
    for key in sorted(conflicts):
        print("  AMBIGUOUS:", key, [x["id"] for x in grouped[key]])
    print("Mit derselben Asset-Version gegen automatische Vorschlaege vergleichbar:",len(approved_records))
    print("Verwaiste Beispiele im Auto-Vergleich bewusst ausgelassen:",skipped_orphan)
    for kind in ("intro","recap","outro"):
        e = optimistic_errors[kind]
        if not e:
            print("  ",kind,": kein sicheres Paar")
            continue
        print(f"  {kind}: {len(e)} Paare; Mediane absoluter Startfehler "
              f"{median(abs(x[0]) for x in e):.2f}s; Endfehler "
              f"{median(abs(x[1]) for x in e):.2f}s; "
              f"Startfehler >5s: {sum(abs(x[0])>5 for x in e)}/{len(e)}")
    worst = sorted(approved_records,key=lambda p:abs(p[2]),reverse=True)
    print("Groesste Abweichungen START, gleiche Asset-Version (bis 12):")
    for x,a,sd,ed in worst[:12]:
        print(f"  {x['ref']} {x['series']} S{x['season']}E{x['episode']} "
              f"{x['kind']} manuell #{x['id']} auto #{a['id']}: "
              f"Start {sd:+.2f}s / Ende {ed:+.2f}s")
    print("Berlino: bestaetigt #2283, verworfen #2282")
    print("Bridgerton: bestaetigt #2291 #2293 #2295 (Orphans)")
    print("REF-37: vorhandenes automatisches Intro, KEIN neues manuelles Label")
    print("Nur BESTES bereits existierendes automatisches Match je Kandidat;")
    print("dies ist KEINE echte Precision-/Recall-Messung oder Freigabequote.")
    print("VERIFIED_LEARNING_LABELS_ADDED=0; AUTO_PUBLISHING_ENABLED=false")
    return {"total":len(accepted)+len(quarantined),"positive":len(accepted),
            "quarantine":len(quarantined),"safe_pairs":len(approved_records)}


def self_test():
    baseline={"recorded_utc":"2026-10-14T13:18:29.630874+00:00",
              "existing_marker_signatures":{}}
    plan={"episodes":[{"id":"REF-30","playlist_id":10,"series":"Berlino (Italiano)",
                       "season":1,"episode":2},
                      {"id":"REF-34","playlist_id":10,"series":"Bridgerton",
                       "season":1,"episode":1}]}
    def record(id,title,source,start,end,asset="a",playlist=10,s=1,e=2):
        return {"id":id,"asset_key":asset,"marker_title":title,"marker_season":s,
                "marker_episode":e,"asset_title":title if playlist is not None else None,
                "asset_season":s if playlist is not None else None,
                "asset_episode":e if playlist is not None else None,
                "playlist_id":playlist,"segment_type":"intro","source":source,
                "status":"pending","start_ms":start,"end_ms":end,
                "created_at":"2026-10-14T15:15:23.000000Z"}
    rows=[record(2282,"Berlino (Italiano)","device",248880,292730),
          record(2283,"Berlino (Italiano)","device",248880,294660),
          record(1998,"Berlino (Italiano)","episcene",258500,291250),
          record(2291,"Bridgerton","device",80,20080,asset="missing",
                 playlist=None,s=1,e=1)]
    result=analyze(rows,plan,baseline)
    assert result=={"total":3,"positive":2,"quarantine":1,"safe_pairs":1},result
    print("SELFTEST_PASS: typo rejected, correction retained, orphan not auto-linked")


def main():
    import sys
    if len(sys.argv)==2 and sys.argv[1]=="--self-test":
        self_test()
        return
    if len(sys.argv)!=1:
        raise SystemExit("Usage: analyze_round40.py [--self-test]")
    plan=json.loads((STATE/"plan.json").read_text(encoding="utf-8"))
    baseline=json.loads((STATE/"baseline.json").read_text(encoding="utf-8"))
    if len(plan.get("episodes",[])) != 40:
        raise RuntimeError("Unexpected reference plan")
    if DATA.is_symlink() or not DATA.is_file():
        raise RuntimeError("Original database unavailable")
    with sqlite3.connect(DATA.resolve().as_uri()+"?mode=ro",uri=True,timeout=8) as db:
        rows=load_rows(db)
    analyze(rows,plan,baseline)


if __name__=="__main__":
    main()
