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

# Never package persistent user data.
rm -rf "$TMP/data/etc/enigma2/EpiMediaHub" "$TMP/data/etc/enigma2/epimediahub"

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path

p=Path(os.environ['PLUGIN'])
t=p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.23"' not in t:
    raise SystemExit('Expected v0.9.23 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.23"','PLUGIN_VERSION = "0.9.24"',1)

# Replace Rai loader with richer metadata handling.
start=t.find('def _rai_query(term="",limit=45):')
end=t.find('def _page_hls(page):',start)
if start<0 or end<0:
    raise SystemExit('Rai query block missing')
new_rai=r'''def _media_abs_url(value, base="https://www.raiplay.it"):
    value=clean_text(value)
    if not value:return ""
    value=value.replace("[RESOLUTION]","600x-").replace(" ","%20")
    if value.startswith("//"):return "https:"+value
    if value.startswith("/"):return base.rstrip("/")+value
    if "://" not in value:return base.rstrip("/")+"/"+value.lstrip("/")
    if value.startswith("http://www.rai.tv/"):value="https://www.rai.tv/"+value[len("http://www.rai.tv/"):]
    return value

def _rai_duration(value):
    value=clean_text(value)
    if not value:return 0
    try:
        if value.isdigit():return int(value)
        parts=[int(x) for x in value.split(":")]
        if len(parts)==3:return parts[0]*3600+parts[1]*60+parts[2]
        if len(parts)==2:return parts[0]*60+parts[1]
    except Exception:pass
    return 0

def _rai_timestamp(value):
    value=clean_text(value)
    if not value:return 0
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
        try:return int(time.mktime(time.strptime(value,fmt)))
        except Exception:pass
    return 0

def _rai_image(item):
    candidates=[]
    images=item.get("images") if isinstance(item,dict) else None
    if isinstance(images,dict):
        for key in ("portrait","landscape","horizontal","square","hero","card"):
            candidates.append(images.get(key,""))
    for key in ("masterImage","image_433","image_300","image_medium","image","thumbnail","thumb","poster","imageUrl"):
        candidates.append(item.get(key,""))
    for value in candidates:
        if isinstance(value,dict):
            value=value.get("url","") or value.get("src","")
        value=_media_abs_url(value)
        if value:return value
    return ""

def _rai_query(term="",limit=45):
    out=[];seen=set()
    for source in RAI_TGR_URLS:
        try:
            req=Request(source);req.add_header("User-Agent","Mozilla/5.0 EpiMediaHub/%s"%PLUGIN_VERSION)
            r=urlopen(req,timeout=12);data=json.loads(r.read().decode("utf-8","replace"));r.close()
            for item in data.get("list",[]):
                if not isinstance(item,dict):continue
                title=clean_text(item.get("name","") or item.get("title","") or item.get("subtitle",""))
                topic=clean_text(item.get("from","")) or clean_text((item.get("isPartOf") or {}).get("name","")) or "Rai"
                date_text=clean_text(item.get("date",""))
                desc=clean_text(item.get("desc","") or item.get("description","") or item.get("synopsis","") or item.get("summary","") or item.get("subtitle","") or item.get("subtitle2",""))
                url=clean_text(item.get("m3u8","") or item.get("mediaUri","") or item.get("h264","") or item.get("videoUrl",""))
                if not title or not url:continue
                if term and term.lower() not in (title+" "+desc+" "+topic+" "+date_text).lower():continue
                if url in seen:continue
                seen.add(url)
                if not desc:
                    desc=("%s · %s%s"%(topic,title,(" · "+date_text) if date_text else "")).strip()
                page=_media_abs_url(item.get("weblink","") or item.get("PathID","") or item.get("pathID","") or item.get("pathId",""))
                out.append({"title":title,"topic":topic,"channel":"RAI","description":desc,"duration":_rai_duration(item.get("length","") or item.get("duration",0)),"timestamp":_rai_timestamp(date_text),"url":url,"url_website":page,"poster_url":_rai_image(item),"type":"movie"})
                if len(out)>=limit:return out
        except Exception:pass
    return out

'''
t=t[:start]+new_rai+t[end:]

# Replace simple image scraper with full page metadata scraper.
start=t.find('def _mediathek_page_image(page_url):')
end=t.find('def _set_pix(widget,path):',start)
if start<0 or end<0:
    raise SystemExit('Mediathek page image block missing')
new_meta=r'''def _html_meta_clean(value):
    value=clean_text(value).replace('&amp;','&').replace('&quot;','"').replace('&#39;',"'").replace('&apos;',"'")
    value=re.sub(r'<[^>]+>',' ',value)
    return re.sub(r'\s+',' ',value).strip()

def _mediathek_page_meta(page_url):
    page_url=clean_text(page_url)
    out={"image":"","description":"","title":""}
    if not page_url.startswith(("http://","https://")):return out
    try:
        req=Request(page_url);req.add_header("User-Agent","Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s"%PLUGIN_VERSION);req.add_header("Accept","text/html,application/xhtml+xml")
        r=urlopen(req,timeout=10);raw=r.read(1200000);r.close();html=raw.decode("utf-8","replace")
        image_patterns=(
            r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
            r'["\']thumbnailUrl["\']\s*:\s*["\']([^"\']+)',
            r'["\']image["\']\s*:\s*["\']([^"\']+)',
            r'["\']poster["\']\s*:\s*["\']([^"\']+)')
        for pat in image_patterns:
            m=re.search(pat,html,re.I)
            if m:
                image=_html_meta_clean(m.group(1))
                if image.startswith('//'):image='https:'+image
                elif image.startswith('/'):
                    u=urlparse(page_url);image='%s://%s%s'%(u.scheme,u.netloc,image)
                out["image"]=image;break
        desc_patterns=(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)',
            r'["\']description["\']\s*:\s*["\']([^"\']{10,1200})')
        for pat in desc_patterns:
            m=re.search(pat,html,re.I|re.S)
            if m:
                out["description"]=_html_meta_clean(m.group(1));break
        title_patterns=(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)',r'<title[^>]*>(.*?)</title>')
        for pat in title_patterns:
            m=re.search(pat,html,re.I|re.S)
            if m:
                out["title"]=_html_meta_clean(m.group(1));break
    except Exception:pass
    return out

def _mediathek_fallback_icon(channel,source_kind,label=""):
    if source_kind=="rai":return _mi("provider_rai")
    text=(clean_text(channel)+" "+clean_text(label)).upper()
    mapping=(("ORF","provider_orf"),("SRF","provider_srf"),("ARTE","provider_arte"),("DW","provider_dw"),("ZDF","provider_zdf"),("ARD","provider_ard"),("3SAT","provider_3sat"),("KIKA","provider_kika"),("WDR","provider_wdr"),("NDR","provider_ndr"),("MDR","provider_mdr"),("SWR","provider_swr"),("RBB","provider_rbb"),("BR","provider_br"),("HR","provider_hr"),("SR ","provider_sr"))
    for needle,name in mapping:
        if needle in text:return _mi(name)
    return ""

'''
t=t[:start]+new_meta+t[end:]

# Rebuild the Mediathek list close/poster section. Avoid ePicLoad completely in
# this screen: setPixmapFromFile runs on the GUI thread and does not leave a
# native decoder callback alive after BACK is pressed.
class_start=t.find('class EpiMediathekList(Screen):')
if class_start<0:raise SystemExit('Mediathek list class missing')
start=t.find('    def safeClose(self):',class_start)
end=t.find('    def reload(self):',start)
if start<0 or end<0:raise SystemExit('safeClose block missing')
new_close=r'''    def safeClose(self):
        if self._closing:return
        self._closing=True
        self._stopWorkers()
        self.close()
    def _stopWorkers(self):
        self._closing=True;self._poster_token+=1
        for timer in (self._load_timer,self._poster_delay_timer,self._poster_poll_timer):
            try:timer.stop()
            except Exception:pass
        try:
            while self._selectionChanged in self["list"].onSelectionChanged:
                self["list"].onSelectionChanged.remove(self._selectionChanged)
        except Exception:pass
        self._poster_result=None;self._load_result=None
        # Never destroy/disconnect ePicLoad during close. v0.9.24 does not use
        # ePicLoad for Mediathek posters at all, preventing native exit crashes.

'''
t=t[:start]+new_close+t[end:]

start=t.find('    def _startPosterLoad(self):',class_start)
end=t.find('    def _move(self,m):',start)
if start<0 or end<0:raise SystemExit('poster block missing')
new_poster=r'''    def _startPosterLoad(self):
        if self._closing:return
        if self._poster_job is not None and self._poster_job.is_alive():
            try:self._poster_delay_timer.start(500,True)
            except TypeError:self._poster_delay_timer.start(500)
            return
        e=self.selectedEntry()
        if not e:return
        token=self._poster_token;self._poster_result=None;snapshot=dict(e)
        self._poster_job=threading.Thread(target=self._posterWorker,args=(token,snapshot));self._poster_job.daemon=True;self._poster_job.start()
        try:self._poster_poll_timer.start(250,True)
        except TypeError:self._poster_poll_timer.start(250)
    def _posterWorker(self,token,entry):
        try:
            page=clean_text(entry.get("url_website",""));image=clean_text(entry.get("poster_url",""));meta={"image":"","description":"","title":""}
            if page:
                meta=_mediathek_page_meta(page)
                if not image:image=clean_text(meta.get("image",""))
            path=""
            if image:
                key="mediathek_"+hashlib.sha1((image or page).encode("utf-8","ignore")).hexdigest()
                path=download_image_cached(image,POSTER_CACHE_DIR,key=key,timeout=10,max_bytes=5*1024*1024)
            self._poster_result=(token,path,clean_text(meta.get("description","")),clean_text(entry.get("url","")))
        except Exception:
            self._poster_result=(token,"","",clean_text(entry.get("url","")))
    def _pollPoster(self):
        if self._closing:return
        if self._poster_job is not None and self._poster_job.is_alive():
            try:self._poster_poll_timer.start(250,True)
            except TypeError:self._poster_poll_timer.start(250)
            return
        result=self._poster_result;self._poster_job=None;self._poster_result=None
        if not result or result[0]!=self._poster_token:return
        token,path,page_desc,source_url=result
        current=self.selectedEntry()
        if not current or clean_text(current.get("url",""))!=source_url:return
        if page_desc and not clean_text(current.get("description","")):
            current["description"]=page_desc
            try:self["preview_overview"].setText(page_desc)
            except Exception:pass
        if path:
            self._showPoster(path);return
        fallback=_mediathek_fallback_icon(self.channel,self.source_kind,self.channel_label)
        if fallback:self._showPoster(fallback)
        else:
            try:self["poster"].hide();self["poster_hint"].setText("Kein Vorschaubild verfügbar")
            except Exception:pass
    def _showPoster(self,path):
        if self._closing or not path:return
        try:
            if self["poster"].instance is not None:
                self["poster"].instance.setPixmapFromFile(path)
                self["poster"].show();self["poster_hint"].setText("")
        except Exception:
            try:self["poster"].hide()
            except Exception:pass

'''
t=t[:start]+new_poster+t[end:]

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.24/' "$TMP/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.24 Mediathek metadata, images and native-safe back navigation/' "$TMP/control/control"

python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.24"' "$PLUGIN"
grep -q 'def _mediathek_page_meta' "$PLUGIN"
grep -q 'poster_url' "$PLUGIN"
grep -q 'setPixmapFromFile(path)' "$PLUGIN"
if grep -A170 'class EpiMediathekList' "$PLUGIN" | grep -q 'PictureData'; then
  echo 'ERROR: Mediathek list still contains ePicLoad/PictureData callback' >&2
  exit 1
fi

# Informative metadata smoke tests.
python3 - <<'PY' || true
import json
from urllib.request import Request,urlopen
for ch in ('ORF','SRF','ARTE.FR'):
    body=json.dumps({'queries':[{'fields':['channel'],'query':ch}],'sortBy':'timestamp','sortOrder':'desc','future':False,'offset':0,'size':1}).encode()
    try:
        r=Request('https://mediathekviewweb.de/api/query',data=body,headers={'Content-Type':'application/json','User-Agent':'EpiMediaHub-v0924-smoke'})
        d=json.loads(urlopen(r,timeout=10).read().decode('utf-8','replace'))
        rows=d.get('result',{}).get('results',[])
        if rows:
            row=rows[0];print(ch,'desc=',bool(row.get('description')),'website=',bool(row.get('url_website')))
    except Exception as e:print(ch,'smoke unavailable',e)
PY

tar --owner=0 --group=0 -czf "$TMP/pkg/control.tar.gz" -C "$TMP/control" .
tar --owner=0 --group=0 -czf "$TMP/pkg/data.tar.gz" -C "$TMP/data" .
cd "$TMP/pkg"
ar r "$WORKSPACE/EpiMediaHub_v0.9.24.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"

if ar p EpiMediaHub_v0.9.24.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2;exit 1
fi
SIZE=$(stat -c%s EpiMediaHub_v0.9.24.ipk);echo "v0.9.24 size: $SIZE bytes"
[ "$SIZE" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2;exit 1; }
SHA=$(sha256sum EpiMediaHub_v0.9.24.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.24.ipk" > EpiMediaHub_v0.9.24.ipk.sha256
printf '{\n  "version": "0.9.24",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.24.ipk",\n  "sha256": "%s"\n}\n' "$SHA" > update.json
sha256sum -c EpiMediaHub_v0.9.24.ipk.sha256

rm -f EpiMediaHub_v0.9.23.ipk EpiMediaHub_v0.9.23.ipk.sha256
# Historical v0.9.17 slim workflow is obsolete and was failing on every push.
rm -f .github/workflows/publish-enigma-v0917-slim.yml

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.24 Mediathek metadata and safe exit'
git push
