#!/usr/bin/env python3
"""Android 0.9.8 catalog hardening: branded skins private-only + original national crests."""
import json, os, runpy
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
catalog_path = root / "app/src/main/res/raw/theme_catalog.json"

# Reuse 0.9.7 national/F1 additions first.
runpy.run_path("build_tools/augment_android_v097_skins.py", run_name="__main__")

data = json.loads(catalog_path.read_text(encoding="utf-8"))
themes = data.setdefault("themes", {})
groups = data.setdefault("groups", [])

PUBLIC = {"default", "epi_blue", "epi_red"}

# Real crest artwork URLs for the 20 added national-team private skins.
# Local/imported resources still have priority in the app; these are used
# for the newly-added teams that have no matching Enigma asset.
national_logo_urls = {
    "national_de": "https://www.citypng.com/public/uploads/preview/germany-football-team-logo-hd-png-701751694776779dz6nudxejm.png?v=2026031317",
    "national_it": "https://r2.thesportsdb.com/images/media/team/badge/fxijcp1726167035.png",
    "national_fr": "https://toppng.com/uploads/preview/hd-france-fff-football-soccer-team-logo-11641934801qqget96ivw.png",
    "national_es": "https://www.citypng.com/public/uploads/preview/hd-spain-national-football-team-logo-png-701751694775604irtvvwunpi.png",
    "national_en": "https://www.pngfind.com/pngs/m/456-4566341_england-national-football-team-ndash-logos-download-dream.png",
    "national_pt": "https://cdn.haitrieu.com/wp-content/uploads/2022/03/Logo-Tuyen-Bo-Dao-Nha.png",
    "national_nl": "https://footytips.io/badges/133905.png",
    "national_be": "https://i.logos-download.com/6795/32231-s640-fcb3d070014776455699f4bf3a6fbfab.png/Belgium_National_Football_Team_Logo_2000-s640.png",
    "national_hr": "https://city-png.b-cdn.net/preview/preview_public/uploads/preview/hd-croatian-football-federation-logo-transparent-png-701751712245353fngzkemhsa.png",
    "national_ar": "https://www.citypng.com/public/uploads/preview/hd-argentina-national-football-team-logo-png-701751694775057eirn7z5vcv.png",
    "national_br": "https://www.citypng.com/public/uploads/preview/download-hd-brazil-national-football-team-logo-png-701751694776765v7uoiz5kwu.png",
    "national_uy": "https://www.citypng.com/public/uploads/preview/hd-uruguay-national-football-team-logo-png-701751694775414hg6dboih93.png",
    "national_mx": "https://www.citypng.com/public/uploads/preview/mexico-national-football-team-logo-701751694775040vb3dpkoht5.png",
    "national_us": "https://toppng.com/uploads/preview/hd-usa-american-football-soccer-team-logo-11641966001f5uo7j9d6l.png",
    "national_ma": "https://www.citypng.com/public/uploads/preview/hd-morocco-national-football-team-logo-png-704081694879431oruhatuvhs.png",
    "national_tr": "https://city-png.b-cdn.net/preview/preview_public/temp/turkey-football-131776418088vfv1zka63u.webp",
    "national_jp": "https://www.citypng.com/public/uploads/preview/hd-japan-national-football-team-logo-png-701751694775535f0wmmxepd0.png",
    "national_kr": "https://www.citypng.com/public/uploads/preview/south-korea-national-football-team-logo-png-701751694775400eg6sczgsiq.png",
    "national_ch": "https://www.citypng.com/public/uploads/preview/hd-switzerland-swiss-national-football-team-logo-png-701751694775032kjhcb15fwr.png?v=2026021121",
    "national_dk": "https://www.futbox.com/img/v1/50d/c01/517/bb8/74fbb9608e2683fee8f9_zoom.png",
}

for tid, meta in themes.items():
    # Every branded/custom design is private. Only the 3 Epi standard skins
    # remain public and work before the private password is unlocked.
    meta["family"] = tid not in PUBLIC
    if tid in national_logo_urls:
        meta["logo_url"] = national_logo_urls[tid]

# Make visible catalog labels consistent even if an old Enigma catalog still
# contains the historic Family wording.
for group in groups:
    group["label"] = str(group.get("label", "")).replace("Family", "Privat").replace("FAMILY", "PRIVAT")

catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

assert all(not themes[x].get("family", False) for x in PUBLIC if x in themes)
assert all(meta.get("family", False) for tid, meta in themes.items() if tid not in PUBLIC)
assert sum(1 for tid in national_logo_urls if themes.get(tid, {}).get("logo_url")) == 20
print("Android 0.9.8 catalog: only standard skins public; branded skins private; 20 national crests configured")
