#!/usr/bin/env python3
"""Augment imported Enigma theme catalog with private national-team and Formula 1 skins for Android 0.9.7."""
import json
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
catalog_path = root / "app/src/main/res/raw/theme_catalog.json"
if not catalog_path.is_file():
    raise SystemExit(f"theme catalog missing: {catalog_path}")

data = json.loads(catalog_path.read_text(encoding="utf-8"))
groups = data.setdefault("groups", [])
themes = data.setdefault("themes", {})

def upsert_group(group_id, label, theme_ids):
    found = next((g for g in groups if g.get("id") == group_id), None)
    if found is None:
        groups.append({"id": group_id, "label": label, "themes": theme_ids[:]})
    else:
        found["label"] = label
        existing = list(found.get("themes", []))
        for tid in theme_ids:
            if tid not in existing:
                existing.append(tid)
        found["themes"] = existing

national = [
    ("national_de", "Deutschland", "#E9C46A"),
    ("national_it", "Italien", "#008C45"),
    ("national_fr", "Frankreich", "#0055A4"),
    ("national_es", "Spanien", "#AA151B"),
    ("national_en", "England", "#CF081F"),
    ("national_pt", "Portugal", "#046A38"),
    ("national_nl", "Niederlande", "#F36C21"),
    ("national_be", "Belgien", "#FDDA24"),
    ("national_hr", "Kroatien", "#E60026"),
    ("national_ar", "Argentinien", "#74ACDF"),
    ("national_br", "Brasilien", "#FFDF00"),
    ("national_uy", "Uruguay", "#5BC0EB"),
    ("national_mx", "Mexiko", "#006847"),
    ("national_us", "USA", "#3C3B6E"),
    ("national_ma", "Marokko", "#C1272D"),
    ("national_tr", "Türkei", "#E30A17"),
    ("national_jp", "Japan", "#BC002D"),
    ("national_kr", "Südkorea", "#0047A0"),
    ("national_ch", "Schweiz", "#D52B1E"),
    ("national_dk", "Dänemark", "#C60C30"),
]

f1 = [
    ("f1_ferrari", "Ferrari F1", "#FF2800"),
    ("f1_mercedes", "Mercedes F1", "#00A19C"),
    ("f1_red_bull", "Red Bull Racing", "#1E41FF"),
    ("f1_mclaren", "McLaren F1", "#FF8700"),
    ("f1_aston_martin", "Aston Martin F1", "#006F62"),
    ("f1_alpine", "Alpine F1", "#2293D1"),
    ("f1_haas", "Haas F1", "#B6BABD"),
    ("f1_racing_bulls", "Racing Bulls", "#6692FF"),
    ("f1_williams", "Williams F1", "#005AFF"),
    ("f1_audi", "Audi F1", "#F50537"),
    ("f1_cadillac", "Cadillac F1", "#D4AF37"),
]

for tid, label, accent in national:
    themes[tid] = {
        "label": label,
        "group": "national_teams",
        "accent": accent,
        "family": True,
    }

for tid, label, accent in f1:
    themes[tid] = {
        "label": label,
        "group": "formula_1",
        "accent": accent,
        "family": True,
    }

upsert_group("national_teams", "Nationalmannschaften", [x[0] for x in national])
upsert_group("formula_1", "Formel 1", [x[0] for x in f1])

catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"Android 0.9.7 theme catalog: +{len(national)} national teams, +{len(f1)} Formula 1 teams")
