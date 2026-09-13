#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
BASE="$WORKSPACE/EpiMediaHub_v0.9.23.ipk"
TMP=/tmp/epimedia0924
ROOT="$TMP/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
PLUGIN="$ROOT/plugin.py"

rm -rf "$TMP"
mkdir -p "$TMP/ar" "$TMP/data" "$TMP/control" "$TMP/pkg"
cd "$TMP/ar"
ar x "$BASE"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary
rm -rf "$TMP/data/etc/enigma2/EpiMediaHub" "$TMP/data/etc/enigma2/epimediahub"

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path

p=Path(os.environ['PLUGIN'])
t=p.read_text(encoding='utf-8')

t=t.replace('PLUGIN_VERSION = "0.9.23"','PLUGIN_VERSION = "0.9.24"',1)

# --- richer foreign metadata helpers -------------------------------------------------
rai_start=t.find('def _rai_query(term="",limit=45):')
rai_end=t.find('\ndef _page_hls(page):',rai_start)
if rai_start<0 or rai_end<0:
    raise SystemExit('rai query block missing')
new_rai=r'''def _parse_hms_duration(value):
    value=clean_text(value)
    try:
        parts=[int(x) for x in value.split(":")]
        if len(parts)==3:return parts[0]*3600+parts[1]*60+parts[2]
        if len(parts)==2:return parts[0]*60+parts[1]
    except Exception:pass
    return 0

def _parse_dmy_timestamp(value):
    value=clean_text(value)
    for fmt in ("%d/%m/%Y","%d.%m.%Y","%Y-%m-%d"):
        try:return int(time.mktime(time.strptime(value,fmt)))
        except Exception:pass
    return 0

def _absolute_media_url(value,base="https://www.raiplay.it"):
    value=clean_text(value).replace('\\/','/')
    if not value:return ""
    if value.startswith('//'):return 'https:'+value
    if value.startswith('/'):
        return base.rstrip('/')+value
    return value if value.startswith(('http://','https://')) else ""

def _provider_fallback_for_channel(channel):
    c=clean_text(channel).upper()
    mapping=(
        ('RAI','provider_rai.png'),('ORF','provider_orf.png'),('SRF','provider_srf.png'),
        ('ARTE','provider_arte.png'),('DW','provider_dw.png'),('ZDF','provider_zdf.png'),
        ('3SAT','provider_3sat.png'),('KIKA','provider_kika.png'),('PHOENIX','provider_phx.png'),
        ('ARD','provider_ard.png'),('DAS ERSTE','provider_ard.png'),('WDR','provider_wdr.png'),
        ('NDR','provider_ndr.png'),('MDR','provider_mdr.png'),('SWR','provider_swr.png'),
        ('RBB','provider_rbb.png'),('HR','provider_hr.png'),('BR','provider_br.png'),('SR','provider_sr.png')
    )
    for key,name in mapping:
        if key in c:
            path=os.path.join(MEDIATHEK_ICON_DIR,name)
            return path if os.path.isfile(path) else ""
    return ""

def _rai_query(term="",limit=45):
    out=[];seen=set()
    for source in RAI_TGR_URLS:
        try:
            req=Request(source);req.add_header("User-Agent","Mozilla/5.0 EpiMediaHub/%s"%PLUGIN_VERSION)
            r=urlopen(req,timeout=12);data=json.loads(r.read().decode("utf-8","replace"));r.close()
            for item in data.get("list",[]):
                title=clean_text(item.get("name",""))
                topic=clean_text(item.get("from","")) or clean_text((item.get("isPartOf") or {}).get("name","")) or "Rai"
                date_text=clean_text(item.get("date",""))
                desc=clean_text(item.get("desc",""))
                if not desc:
                    desc="RaiPlay-Beitrag aus %s%s."%(topic,(" · Ausstrahlung vom "+date_text) if date_text else "")
                url=clean_text(item.get("m3u8","")) or clean_text(item.get("h264","")) or clean_text(item.get("mediaUri",""))
                if not title or not url:continue
                hay=(title+" "+desc+" "+topic).lower()
                if term and term.lower() not in hay:continue
                if url in seen:continue
                seen.add(url)
                image=""
                for key in ("masterImage","image_433","image_300","image_medium","image"):
                    image=_absolute_media_url(item.get(key,""))
                    if image:break
                out.append({
                    "title":title,"topic":topic,"channel":"RAI","description":desc,
                    "duration":_parse_hms_duration(item.get("length","")),
                    "timestamp":_parse_dmy_timestamp(date_text),"url":url,
                    "url_website":clean_text(item.get("weblink","")),"image_url":image,
                    "fallback_image":_provider_fallback_for_channel("RAI"),"type":"movie"
                })
                if len(out)>=limit:return out
        except Exception:pass
    return out
'''
t=t[:rai_start]+new_rai+t[rai_end:]

# Add fallback poster field to MediathekView results.
old='"url":stream,"url_website":clean_text(item.get("url_website","")),"type":"movie"}'
new='"url":stream,"url_website":clean_text(item.get("url_website","")),"image_url":"","fallback_image":_provider_fallback_for_channel(item.get("channel","")),"type":"movie"}'
if old not in t:
    raise SystemExit('mvw result anchor missing')
t=t.replace(old,new,1)

# Replace simple image scraping with richer image + description extraction.
meta_start=t.find('def _mediathek_page_image(page_url):')
meta_end=t.find('\ndef _set_pix(widget,path):',meta_start)
if meta_start<0 or meta_end<0:
    raise SystemExit('page image block missing')
new_meta=r'''def _mediathek_page_meta(page_url):
    page_url=clean_text(page_url)
    result={"image":"","description":"","title":""}
    if not page_url.startswith(("http://","https://")):return result
    try:
        req=Request(page_url);req.add_header("User-Agent","Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s"%PLUGIN_VERSION);req.add_header("Accept","text/html,application/xhtml+xml")
        r=urlopen(req,timeout=10);raw=r.read(1500000);r.close();html=raw.decode("utf-8","replace").replace('\\/','/').replace('&amp;','&')
        def grab(patterns):
            for pat in patterns:
                m=re.search(pat,html,re.I|re.S)
                if m:return clean_text(m.group(1)).replace('&quot;','"').replace('&#39;',"'").replace('&lt;','<').replace('&gt;','>')
            return ""
        image=grab((
            r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
            r'["\']thumbnailUrl["\']\s*:\s*["\']([^"\']+)',
            r'["\']poster["\']\s*:\s*["\']([^"\']+)'
        ))
        desc=grab((
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
            r'["\']description["\']\s*:\s*["\']([^"\']{20,1200})'
        ))
        title=grab((
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            r'<title[^>]*>(.*?)</title>'
        ))
        if image.startswith('//'):image='https:'+image
        elif image.startswith('/'):
            u=urlparse(page_url);image='%s://%s%s'%(u.scheme,u.netloc,image)
        result={"image":image,"description":desc,"title":title}
    except Exception:pass
    return result

def _mediathek_page_image(page_url):
    return _mediathek_page_meta(page_url).get("image","")
'''
t=t[:meta_start]+new_meta+t[meta_end:]

# --- exit safety --------------------------------------------------------------------
old_stop='''    def _stopWorkers(self):
        self._closing=True; self._poster_token+=1
        for timer in (self._load_timer,self._poster_delay_timer,self._poster_poll_timer):
            try:timer.stop()
            except Exception:pass
        try:
            while self._selectionChanged in self["list"].onSelectionChanged:self["list"].onSelectionChanged.remove(self._selectionChanged)
        except Exception:pass
        try:
            if self._poster_decoder is not None:
                try:
                    callbacks=self._poster_decoder.PictureData.get()
                    if self._posterDecoded in callbacks:callbacks.remove(self._posterDecoded)
                except Exception:pass
        except Exception:pass
        self._poster_decoder=None; self._poster_result=None; self._load_result=None
'''
new_stop='''    def _stopWorkers(self):
        # Do not destroy/disconnect ePicLoad while its native decoder is active.
        # Some Enigma2 images crash in C++ when PictureData is modified during close.
        self._closing=True; self._poster_token+=1
        for timer in (self._load_timer,self._poster_delay_timer,self._poster_poll_timer):
            try:timer.stop()
            except Exception:pass
        try:
            while self._selectionChanged in self["list"].onSelectionChanged:self["list"].onSelectionChanged.remove(self._selectionChanged)
        except Exception:pass
        self._poster_result=None; self._load_result=None
'''
if old_stop not in t:
    raise SystemExit('stopWorkers anchor missing')
t=t.replace(old_stop,new_stop,1)

# --- poster worker now uses direct provider metadata, page metadata, and fallback ----
old_start='''        e=self.selectedEntry(); page=clean_text(e.get("url_website","")) if e else ""
        if not page:return
        token=self._poster_token; self._poster_result=None; self._poster_job=threading.Thread(target=self._posterWorker,args=(token,page)); self._poster_job.daemon=True; self._poster_job.start();
'''
new_start='''        e=self.selectedEntry()
        if not e:return
        token=self._poster_token; self._poster_result=None; snapshot=dict(e); self._poster_job=threading.Thread(target=self._posterWorker,args=(token,snapshot)); self._poster_job.daemon=True; self._poster_job.start();
'''
if old_start not in t:
    raise SystemExit('poster start anchor missing')
t=t.replace(old_start,new_start,1)

old_worker='''    def _posterWorker(self,token,page):
        try:
            image=_mediathek_page_image(page); path=download_image_cached(image,POSTER_CACHE_DIR,key="mediathek_"+hashlib.sha1(page.encode("utf-8","ignore")).hexdigest(),timeout=10,max_bytes=4*1024*1024) if image else ""; self._poster_result=(token,path)
        except Exception:self._poster_result=(token,"")
'''
new_worker='''    def _posterWorker(self,token,entry):
        try:
            page=clean_text(entry.get("url_website","")); image=clean_text(entry.get("image_url","")); desc=""; meta={}
            if page and (not image or not clean_text(entry.get("description",""))):
                meta=_mediathek_page_meta(page); image=image or clean_text(meta.get("image","")); desc=clean_text(meta.get("description",""))
            path=""
            if image:
                key="mediathek_"+hashlib.sha1((image or page).encode("utf-8","ignore")).hexdigest()
                path=download_image_cached(image,POSTER_CACHE_DIR,key=key,timeout=10,max_bytes=4*1024*1024)
            if not path:
                fallback=clean_text(entry.get("fallback_image",""))
                if fallback and os.path.isfile(fallback):path=fallback
            if not self._closing:self._poster_result=(token,path,desc)
        except Exception:
            if not self._closing:self._poster_result=(token,"","")
'''
if old_worker not in t:
    raise SystemExit('poster worker anchor missing')
t=t.replace(old_worker,new_worker,1)

old_poll='''        result=self._poster_result;self._poster_job=None;self._poster_result=None
        if not result or result[0]!=self._poster_token:return
        if result[1]:self._showPoster(result[1])
'''
new_poll='''        result=self._poster_result;self._poster_job=None;self._poster_result=None
        if not result or result[0]!=self._poster_token:return
        if len(result)>2 and clean_text(result[2]):
            e=self.selectedEntry()
            if e and not clean_text(e.get("description","")):
                e["description"]=clean_text(result[2]); self["preview_overview"].setText(e["description"])
        if result[1]:self._showPoster(result[1])
'''
if old_poll not in t:
    raise SystemExit('poster poll anchor missing')
t=t.replace(old_poll,new_poll,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.24/' "$TMP/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.24 Mediathek safe exit and foreign metadata/' "$TMP/control/control"

python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.24"' "$PLUGIN"
grep -q '_mediathek_page_meta' "$PLUGIN"
grep -q '_parse_hms_duration' "$PLUGIN"
grep -q 'Do not destroy/disconnect ePicLoad' "$PLUGIN"
grep -q 'fallback_image' "$PLUGIN"

tar --owner=0 --group=0 -czf "$TMP/pkg/control.tar.gz" -C "$TMP/control" .
tar --owner=0 --group=0 -czf "$TMP/pkg/data.tar.gz" -C "$TMP/data" .
cd "$TMP/pkg"
ar r "$WORKSPACE/EpiMediaHub_v0.9.24.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"

if ar p EpiMediaHub_v0.9.24.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
SIZE=$(stat -c%s EpiMediaHub_v0.9.24.ipk)
echo "v0.9.24 size: $SIZE bytes"
[ "$SIZE" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
SHA=$(sha256sum EpiMediaHub_v0.9.24.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.24.ipk" > EpiMediaHub_v0.9.24.ipk.sha256
printf '{\n  "version": "0.9.24",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.24.ipk",\n  "sha256": "%s"\n}\n' "$SHA" > update.json
sha256sum -c EpiMediaHub_v0.9.24.ipk.sha256
rm -f EpiMediaHub_v0.9.23.ipk EpiMediaHub_v0.9.23.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.24 Mediathek exit and metadata fix'
git push
