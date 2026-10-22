#!/usr/bin/env bash
# EpiScene: fair 4K ANALYSE / THE BEST IntroDB+TheIntroDB prefetched metadata.
# Only the EXISTING trusted-sources one-shot and timer are touched.
# No changes to Android, device lookup, video analysis worker, approval DB.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required" >&2; exit 2; }
for program in python3 curl mktemp cmp cp mv install systemctl flock; do
  command -v "$program" >/dev/null || {
    echo "STOP: missing $program" >&2; exit 2;
  }
done
NEW=cf73457141c8227c72637245ae56f9a3a1b234f8
OLD=2041ed2f7d3117364b13c9ac3716573a6f01dd5c
ROOT=https://raw.githubusercontent.com/epimediahub/EpiMediaHub
SUB=tools/episcene-learning-v1/unified-marker-bridge
DEST=/opt/episcene-learning/unified
PRIVATE=/var/lib/episcene-learning
CACHE="$PRIVATE/trusted-sources.sqlite3"
UNIT=episcene-trusted-sources.service
TIMER=episcene-trusted-sources.timer
BASE="$DEST/trusted_external_sync.py"
HELPER="$DEST/analysis_identity_balanced.py"
[[ -d "$DEST" && ! -L "$DEST" && -d "$PRIVATE" && ! -L "$PRIVATE" &&
   -f "$CACHE" && ! -L "$CACHE" && -f "$BASE" && ! -L "$BASE" &&
   -f "$DEST/analysis_identity.py" && ! -L "$DEST/analysis_identity.py" ]] || {
  echo "STOP: unexpected trusted source installation" >&2; exit 2;
}
[[ ! -e "$HELPER" && ! -L "$HELPER" ]] || {
  echo "STOP: fair prefetch helper already present; don't overwrite" >&2; exit 2;
}
systemctl is-active --quiet "$TIMER" || {
  echo "STOP: trusted prefetch timer not active" >&2; exit 2;
}
case "$(systemctl show "$UNIT" -p ActiveState --value)" in
  inactive) ;;
  *) echo "STOP: trusted prefetch run currently active; no changes made" >&2; exit 2;;
esac
systemctl show "$UNIT" -p ExecStart --value | grep -Fq "$BASE" || {
  echo "STOP: trusted prefetch service points to unexpected code" >&2; exit 2;
}

exec 9>"$PRIVATE/.balanced-trusted-prefetch-install.lock"
flock -n 9 || { echo "STOP: another EpiScene source install is active" >&2; exit 2; }
TEMP="$(mktemp -d -t episcene-balanced-source.XXXXXXXX)"
trap 'rm -rf -- "$TEMP"' EXIT
mkdir -m 0700 -- "$TEMP/baseline"
for name in analysis_identity_balanced.py trusted_external_sync.py \
            test_analysis_identity_balanced.py test_analysis_identity.py \
            test_trusted_external_sync.py test_trusted_external.py; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$ROOT/$NEW/$SUB/$name" -o "$TEMP/$name"
  [[ -s "$TEMP/$name" ]] || { echo "STOP: missing tested file $name" >&2; exit 2; }
done
for name in trusted_external_sync.py analysis_identity.py; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$ROOT/$OLD/$SUB/$name" -o "$TEMP/baseline/$name"
  [[ -s "$TEMP/baseline/$name" ]] || { echo "STOP: missing original release baseline" >&2; exit 2; }
  cmp -s "$DEST/$name" "$TEMP/baseline/$name" || {
    echo "STOP: installed $name differs from reviewed release; no changes" >&2; exit 2;
  }
done
echo "=== EpiScene two-playlist fair source regression tests ==="
(
  cd "$TEMP"
  PYTHONPATH="$TEMP:$DEST" python3 -m py_compile \
    analysis_identity_balanced.py trusted_external_sync.py \
    test_analysis_identity_balanced.py test_analysis_identity.py \
    test_trusted_external_sync.py
  PYTHONPATH="$TEMP:$DEST" python3 -m unittest -q \
    test_analysis_identity_balanced test_analysis_identity \
    test_trusted_external_sync
)
echo "=== Original trusted cache snapshot ==="
[[ ! -L "$CACHE" && -f "$CACHE" ]] || {
  echo "STOP: private trusted cache replaced" >&2; exit 2;
}
BACKUP="$(mktemp -d -p "$PRIVATE" trusted-balanced-backup.XXXXXXXX)"
chmod 700 "$BACKUP"
cp -p -- "$BASE" "$BACKUP/trusted_external_sync.py"
python3 - "$CACHE" "$BACKUP/trusted-sources-before-balanced.sqlite3" <<'PY_DB_BACKUP'
import pathlib, sqlite3, sys, os
original,output=(pathlib.Path(x) for x in sys.argv[1:])
with sqlite3.connect(original.resolve().as_uri()+"?mode=ro",uri=True,timeout=15) as source:
    with sqlite3.connect(output,timeout=15) as target:
        source.backup(target)
        if target.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise RuntimeError("STOP: trusted source cache snapshot invalid")
os.chmod(output,0o600)
print("ORIGINAL_CACHE_BACKUP_VERIFIED")
PY_DB_BACKUP
# Prevent a concurrent systemd prefetch from importing mixed old/new modules.
systemctl stop "$TIMER"
if [[ "$(systemctl show "$UNIT" -p ActiveState --value)" != inactive ]]; then
  systemctl start "$TIMER" || :
  echo "STOP: source prefetched during installation; nothing replaced" >&2
  exit 2
fi
COMPLETE=0
rollback() {
  result=$?
  if [[ "$COMPLETE" -ne 1 ]]; then
    echo "ROLLBACK: restoring original trusted source module" >&2
    cp -p -- "$BACKUP/trusted_external_sync.py" "$DEST/.trusted_external_sync.py.recover"
    mv -f -- "$DEST/.trusted_external_sync.py.recover" "$BASE"
    rm -f -- "$HELPER"
    systemctl start "$TIMER" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$TEMP"
  exit "$result"
}
trap rollback EXIT
echo "=== Install balanced source selector, retaining old cache entries ==="
install -m 0644 -o root -g root "$TEMP/analysis_identity_balanced.py" \
  "$DEST/.analysis_identity_balanced.py.new"
mv -f -- "$DEST/.analysis_identity_balanced.py.new" "$HELPER"
install -m 0644 -o root -g root "$TEMP/trusted_external_sync.py" \
  "$DEST/.trusted_external_sync.py.new"
mv -f -- "$DEST/.trusted_external_sync.py.new" "$BASE"
python3 -m py_compile "$HELPER" "$BASE"
echo "=== Test first balanced external prefetch without IPTV streams ==="
systemctl start "$UNIT"
systemctl is-failed --quiet "$UNIT" && {
  echo "STOP: balanced source service failed" >&2; exit 3;
}
systemctl start "$TIMER"
systemctl is-active --quiet "$TIMER"
COMPLETE=1
trap 'rm -rf -- "$TEMP"' EXIT
echo "EPISCENE BALANCED TRUSTED PREFETCH INSTALLED"
echo "4K and THE BEST receive independent positions and roughly equal slots."
echo "Original approved markers and device lookup code unchanged."
echo "=== Latest source aggregate output ==="
journalctl -u "$UNIT" -n 32 --no-pager -o cat |
  grep -E '"(status|analysed|analysis_playlist_candidates|8|10|trusted_segments|production_database_written|no_ip_streams_opened)"' |
  tail -n 18 || true
