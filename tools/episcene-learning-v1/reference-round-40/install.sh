#!/usr/bin/env bash
# Install the 40-episode reference tracking plan. Original analyzer DB remains read-only.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo "Run from the existing root console" >&2; exit 2; }
ROOT=/var/lib/episcene-learning/reference-round-40
APP=/opt/episcene-learning
DB=/var/lib/epimediahub/provisioning.db
UNIT=episcene-learning-reference-40
REV=1cb7704e29023bccf920b8de9503ef1dfd8ad446
PLAN_SHA=f96e8c6ccc05f341725cd1b8454f4dab4dd459a5741b25b212ddb4987875bd3e
TRACK_SHA=7316e4eaf13eda3d16561ed3ea9df729fc14b361ea4041f00844084d8b9e25d8
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/reference-round-40"
TMP="$(mktemp -d -t reference-round-40-XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
for tool in curl sha256sum python3 install systemctl; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 2; }
done
[[ -d /run/systemd/system && -f "$DB" && -d "$APP" &&
    -f /var/lib/episcene-learning/knowledge.sqlite3 ]] || {
      echo "Existing EpiScene server installation not found" >&2; exit 2;
}
curl -fsSL --retry 2 --max-time 45 "$BASE/plan.json" -o "$TMP/plan.json"
curl -fsSL --retry 2 --max-time 45 "$BASE/tracker.py" -o "$TMP/tracker.py"
printf '%s  %s\n' "$PLAN_SHA" "$TMP/plan.json" | sha256sum -c -
printf '%s  %s\n' "$TRACK_SHA" "$TMP/tracker.py" | sha256sum -c -
python3 - "$TMP/tracker.py" "$TMP/plan.json" <<'PY'
import sys,json,sqlite3,tempfile,pathlib,importlib.util
source,manifest=sys.argv[1:]
compile(pathlib.Path(source).read_bytes(),source,'exec')
plan=json.loads(pathlib.Path(manifest).read_text())
assert len(plan['episodes'])==40
assert len([x for x in plan['episodes'] if x['playlist_id']==8])==20
assert len([x for x in plan['episodes'] if x['playlist_id']==10])==20
spec=importlib.util.spec_from_file_location('episcene_reference_tracker',source)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder)
    state=root/'state';state.mkdir()
    state.joinpath('plan.json').write_bytes(pathlib.Path(manifest).read_bytes())
    db=root/'mock.sqlite3'
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,
              title TEXT,season INTEGER,episode INTEGER);
            CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,
              segment_type TEXT,source TEXT,status TEXT,start_ms INTEGER,
              end_ms INTEGER,created_at TEXT);
            INSERT INTO skip_assets VALUES('example',8,'MobLand',1,2);
            INSERT INTO skip_records VALUES(1,'example','intro','device','pending',
                10000,20000,'2026-10-14');
        """)
    m.scan(state,db,initialize=True)
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO skip_records VALUES(2,'example','outro','device',"
                    "'pending',900000,930000,'2026-10-14')")
    m.scan(state,db)
    report=json.loads(state.joinpath('status.json').read_text())
    assert report['episodes_with_new_or_changed_markers']==1
    assert report['new_or_changed_markers']==1
    assert report['verified_human_labels_added']==0
print("PASS: 40-episode manifest; SQLite read-only tracking; marker detection")
PY
[[ ! -L "$ROOT" && ! -L "$DB" && ! -L "$APP" ]] || { echo "Unexpected symlink, aborting" >&2; exit 2; }
install -d -o root -g root -m 0700 "$ROOT"
if [[ -e "$ROOT/plan.json" ]]; then
  cmp -s "$ROOT/plan.json" "$TMP/plan.json" || {
    echo "Existing reference plan differs; refusing overwrite" >&2; exit 2;
  }
else
  install -o root -g root -m 0600 "$TMP/plan.json" "$ROOT/plan.json"
fi
install -o root -g root -m 0644 "$TMP/tracker.py" "$APP/reference_tracker.py"
python3 "$APP/reference_tracker.py" init
cat > "/etc/systemd/system/$UNIT.service" <<'UNIT_SERVICE'
[Unit]
Description=Track EpiScene 40-episode manual-reference batch, read-only source
After=local-fs.target
[Service]
Type=oneshot
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/episcene-learning/reference_tracker.py scan
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/episcene-learning/reference-round-40
PrivateTmp=true
PrivateNetwork=true
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
UNIT_SERVICE
cat > "/etc/systemd/system/$UNIT.timer" <<'UNIT_TIMER'
[Unit]
Description=Hourly scan of manual EpiScene reference episodes
[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true
Unit=episcene-learning-reference-40.service
[Install]
WantedBy=timers.target
UNIT_TIMER
systemctl daemon-reload
systemctl start "$UNIT.service"
systemctl enable --now "$UNIT.timer" >/dev/null
echo
echo "40 REFERENZFOLGEN REGISTRIERT, davon 20 DE und 20 IT."
echo "Fortschritt wird stuendlich aus der Originaldatenbank gelesen."
echo "Keine Freigabe/kein Training. Keine Aenderung am produktiven Analyzer."
echo
python3 "$APP/reference_tracker.py" status
