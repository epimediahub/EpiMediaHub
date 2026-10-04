#!/usr/bin/env python3
"""Resolve team/portrait artwork once; Android never calls the sports catalogue API.

Candidate names are verified against provider records. Club featured players
must belong to the requested roster; national teams and F1 use the curated
country/official-grid selections. Missing artwork is reported, never replaced
with an unrelated athlete or a generic silhouette.
"""
import argparse
import concurrent.futures
import hashlib
import json
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.thesportsdb.com/api/v1/json/123/"
LOCKS = {}
GUARD = threading.Lock()

def norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)

def locked(key):
    with GUARD:
        return LOCKS.setdefault(key, threading.Lock())

class Collector:
    def __init__(self, destination):
        self.root = destination
        self.cache = destination / "api"
        self.images = destination / "images"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.images.mkdir(parents=True, exist_ok=True)

    def json(self, endpoint, **params):
        url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        file = self.cache / (key + ".json")
        with locked(key):
            if file.is_file():
                return json.loads(file.read_text())
            for attempt in range(4):
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": "EpiMediaHub-private-skin-artwork/1.0.31"})
                    with urllib.request.urlopen(request, timeout=35) as response:
                        data = json.load(response)
                    file.write_text(json.dumps(data, ensure_ascii=False))
                    time.sleep(.12)
                    return data
                except Exception:
                    if attempt == 3: raise
                    time.sleep(1 + attempt * 2)

    def image(self, url):
        if not url or not url.startswith("https://"): return None
        stem = "p_" + hashlib.sha256(url.encode()).hexdigest()[:18]
        extension = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if extension not in (".png", ".jpg", ".jpeg", ".webp"): return None
        file = self.images / (stem + extension)
        with locked(url):
            if not file.is_file():
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "EpiMediaHubArtwork/1.0 (epimediahub.com)"}), timeout=25) as response:
                            data = response.read(6_000_001)
                        assert 500 < len(data) < 6_000_000
                        file.write_bytes(data)
                        with Image.open(file) as image:
                            assert image.width >= 96 and image.height >= 96
                            image.verify()
                        break
                    except Exception:
                        file.unlink(missing_ok=True)
                        if attempt == 2: return None
                        time.sleep(1 + attempt)
            with Image.open(file) as image:
                transparent = "A" in image.getbands() and image.getchannel("A").getextrema()[0] < 200
                width, height = image.size
            return {"file": file.name, "url": url, "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                    "width": width, "height": height, "transparent": transparent}

    def portrait(self, player):
        for field in ("strCutout", "strThumb"):
            image = self.image(player.get(field))
            if image:
                return {"name": player["strPlayer"], "playerId": player["idPlayer"],
                        "providerTeam": player.get("strTeam", ""), "providerNationality": player.get("strNationality", ""), **image}
        return None

    def find_player(self, name, sport):
        aliases = {"Magic Johnson": "Earvin Johnson", "Penny Hardaway": "Anfernee Hardaway", "Ronaldo": "Ronaldo Nazario",
                   "Alex de Souza": "Alex", "Juninho Pernambucano": "Juninho", "Noureddine Naybet": "Naybet"}
        for query in dict.fromkeys((name, aliases.get(name, name))):
            try:
                players = self.json("searchplayers.php", p=query).get("player") or []
                wanted = norm(query)
                exact = [p for p in players if norm(p.get("strPlayer")) == wanted or
                         wanted in {norm(v) for v in (p.get("strPlayerAlternate") or "").split(",")}]
                for player in exact:
                    if norm(player.get("strSport")) != norm(sport): continue
                    candidate = norm(player.get("strPlayer"))
                    if not exact and not (wanted in candidate or candidate in wanted): continue
                    found = self.portrait(player)
                    if found: return found
            except Exception:
                continue
        return None

    def team(self, row):
        ident, team_name, sport, legends, preferred = row
        response = self.json("searchteams.php", t=team_name).get("teams") or []
        eligible = [t for t in response if norm(t.get("strSport")) == norm(sport) and
                    "women" not in (t.get("strTeam", "") + t.get("strLeague", "")).lower()]
        eligible.sort(key=lambda t: norm(t.get("strTeam")) != norm(team_name))
        team = eligible[0] if eligible else None
        original_logo = self.image((team or {}).get("strBadge") or (team or {}).get("strTeamBadge"))
        roster = self.json("lookup_all_players.php", id=team["idTeam"]).get("player") or [] if team else []
        roster_ids = {p.get("idPlayer") for p in roster}
        featured = []
        for name in preferred:
            player = self.find_player(name, sport)
            if player and (ident.startswith(("national_", "f1_")) or player["playerId"] in roster_ids or
                           norm(player["providerTeam"]) == norm((team or {}).get("strTeam", team_name))):
                featured.append(player)
        if len(featured) < 2:
            for player in roster:
                if any(p["playerId"] == player.get("idPlayer") for p in featured): continue
                if any(v in (player.get("strPosition") or "").lower() for v in ("manager", "coach")): continue
                portrait = self.portrait(player)
                if portrait: featured.append(portrait)
                if len(featured) >= 2: break
        historical = [self.find_player(name, sport) for name in legends]
        historical = [p for p in historical if p]
        result = {"id": ident, "providerName": team_name, "sport": sport, "providerTeamId": (team or {}).get("idTeam"),
                  "logo": original_logo, "players": featured[:2], "legends": historical[:2], "requestedLegends": legends}
        print(f"{ident}: players={len(result['players'])}, legends={len(result['legends'])}, logo={bool(original_logo)}", flush=True)
        (self.root / (ident + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("destination", type=Path); args = parser.parse_args()
    rows = []
    for line in (ROOT / "android/v1.0.31/team_roster_candidates.txt").read_text().splitlines():
        if not line or line.startswith("#"): continue
        ident, name, sport, legends, preferred = line.split("|")
        rows.append((ident, name, sport, legends.split(";"), preferred.split(";")))
    collector = Collector(args.destination)
    completed, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(collector.team, row): row[0] for row in rows}
        for future in concurrent.futures.as_completed(futures):
            try: completed.append(future.result())
            except Exception as error:
                failures.append({"id": futures[future], "error": str(error)})
                print("FAILED", futures[future], str(error), flush=True)
    output = {"collectedAt": "2026-10-04", "source": "TheSportsDB", "teams": sorted(completed, key=lambda t:t["id"]), "failures": failures}
    (args.destination / "collection.json").write_text(json.dumps(output, ensure_ascii=False, indent=2))
    incomplete = [t["id"] for t in completed if len(t["players"]) != 2 or len(t["legends"]) != 2]
    print(json.dumps({"teams": len(completed), "failures": failures, "incomplete": incomplete}), flush=True)

if __name__ == "__main__": main()
