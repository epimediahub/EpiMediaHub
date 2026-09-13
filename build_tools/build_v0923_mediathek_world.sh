#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
BASE="$WORKSPACE/EpiMediaHub_v0.9.22.ipk"
TMP=/tmp/epimedia0923
ROOT="$TMP/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
PLUGIN="$ROOT/plugin.py"
ICONDIR="$ROOT/mediathek_picons"

rm -rf "$TMP"
mkdir -p "$TMP/ar" "$TMP/data" "$TMP/control" "$TMP/pkg" "$ICONDIR"
cd "$TMP/ar"
ar x "$BASE"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

# Persistent user data never belongs to the package.
rm -rf "$TMP/data/etc/enigma2/EpiMediaHub" "$TMP/data/etc/enigma2/epimediahub"

# Generate lightweight country/provider PNG badges using only Python stdlib.
export ICONDIR
python3 - <<'PY'
import os, struct, zlib
from pathlib import Path
out=Path(os.environ['ICONDIR']); out.mkdir(parents=True, exist_ok=True)
FONT={
'A':["01110","10001","10001","11111","10001","10001","10001"],
'B':["11110","10001","10001","11110","10001","10001","11110"],
'C':["01111","10000","10000","10000","10000","10000","01111"],
'D':["11110","10001","10001","10001","10001","10001","11110"],
'E':["11111","10000","10000","11110","10000","10000","11111"],
'F':["11111","10000","10000","11110","10000","10000","10000"],
'G':["01111","10000","10000","10111","10001","10001","01111"],
'H':["10001","10001","10001","11111","10001","10001","10001"],
'I':["11111","00100","00100","00100","00100","00100","11111"],
'J':["00111","00010","00010","00010","10010","10010","01100"],
'K':["10001","10010","10100","11000","10100","10010","10001"],
'L':["10000","10000","10000","10000","10000","10000","11111"],
'M':["10001","11011","10101","10101","10001","10001","10001"],
'N':["10001","11001","10101","10011","10001","10001","10001"],
'O':["01110","10001","10001","10001","10001","10001","01110"],
'P':["11110","10001","10001","11110","10000","10000","10000"],
'Q':["01110","10001","10001","10001","10101","10010","01101"],
'R':["11110","10001","10001","11110","10100","10010","10001"],
'S':["01111","10000","10000","01110","00001","00001","11110"],
'T':["11111","00100","00100","00100","00100","00100","00100"],
'U':["10001","10001","10001","10001","10001","10001","01110"],
'V':["10001","10001","10001","10001","10001","01010","00100"],
'W':["10001","10001","10001","10101","10101","10101","01010"],
'X':["10001","10001","01010","00100","01010","10001","10001"],
'Y':["10001","10001","01010","00100","00100","00100","00100"],
'Z':["11111","00001","00010","00100","01000","10000","11111"],
'1':["00100","01100","00100","00100","00100","00100","01110"],
'2':["01110","10001","00001","00010","00100","01000","11111"],
'3':["11110","00001","00001","01110","00001","00001","11110"],
'5':["11111","10000","10000","11110","00001","00001","11110"]}

def png(path,w,h,pixels):
    raw=b''.join(b'\x00'+bytes(pixels[y*w*4:(y+1)*w*4]) for y in range(h))
    def chunk(t,d):
        return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
    Path(path).write_bytes(data)

def make(name,text,bg,flag=None):
    w,h=96,54; pix=[]
    for y in range(h):
        for x in range(w):
            c=bg
            if flag=='de': c=(20,20,20) if y<18 else ((190,20,35) if y<36 else (240,190,35))
            elif flag=='at': c=(200,20,40) if y<18 or y>=36 else (245,245,245)
            elif flag=='it': c=(25,150,80) if x<32 else ((245,245,245) if x<64 else (205,35,45))
            elif flag=='fr': c=(30,65,150) if x<32 else ((245,245,245) if x<64 else (210,40,55))
            elif flag=='ch': c=(205,25,45)
            elif flag=='tr': c=(205,25,45)
            pix.extend((*c,255))
    # Swiss cross.
    if flag=='ch':
        for y in range(16,38):
            for x in range(43,53): pix[(y*w+x)*4:(y*w+x)*4+4]=[255,255,255,255]
        for y in range(22,32):
            for x in range(34,62): pix[(y*w+x)*4:(y*w+x)*4+4]=[255,255,255,255]
    # Dark translucent text plate for flags; normal providers use full badge.
    if flag:
        for y in range(12,43):
            for x in range(18,78):
                i=(y*w+x)*4
                pix[i:i+4]=[18,23,31,220]
    text=''.join(ch for ch in text.upper() if ch in FONT)[:5]
    scale=5 if len(text)<=3 else 4
    tw=len(text)*5*scale+(len(text)-1)*scale
    x0=max(2,(w-tw)//2); y0=(h-7*scale)//2
    for ci,ch in enumerate(text):
        glyph=FONT[ch]
        ox=x0+ci*6*scale
        for gy,row in enumerate(glyph):
            for gx,val in enumerate(row):
                if val=='1':
                    for yy in range(scale):
                        for xx in range(scale):
                            x=ox+gx*scale+xx; y=y0+gy*scale+yy
                            if 0<=x<w and 0<=y<h:
                                i=(y*w+x)*4; pix[i:i+4]=[255,255,255,255]
    png(out/(name+'.png'),w,h,pix)

# Countries
for name,text,bg,flag in [
('country_de','DE',(30,30,30),'de'),('country_at','AT',(150,25,35),'at'),('country_ch','CH',(180,20,35),'ch'),
('country_it','IT',(30,120,70),'it'),('country_tr','TR',(180,25,35),'tr'),('country_fr','FR',(40,70,140),'fr')]: make(name,text,bg,flag)
# Providers / groups
spec={
'ARD':('ARD',(0,75,145)),'ZDF':('ZDF',(230,120,10)),'3SAT':('3SAT',(55,55,65)),'KIKA':('KIKA',(90,70,165)),
'PHX':('PHX',(25,95,135)),'ARTE':('ARTE',(195,40,75)),'DW':('DW',(15,85,165)),'TAG':('TAG',(30,110,160)),
'REG':('REG',(70,90,110)),'BR':('BR',(35,110,180)),'HR':('HR',(30,105,170)),'MDR':('MDR',(40,120,155)),
'NDR':('NDR',(30,85,150)),'RB':('RB',(45,100,150)),'RBB':('RBB',(85,75,155)),'SR':('SR',(45,100,155)),
'SWR':('SWR',(50,105,150)),'WDR':('WDR',(25,105,175)),'ORF':('ORF',(190,30,35)),'SRF':('SRF',(200,30,40)),
'RAI':('RAI',(20,115,175)),'TRT':('TRT',(190,20,35)),'TABII':('TABII',(45,45,55)),'TV5':('TV5',(50,80,155))}
for name,(text,bg) in spec.items(): make('provider_'+name.lower(),text,bg)
print('Generated mediathek badges:',len(list(out.glob('*.png'))))
PY

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['PLUGIN'])
t=p.read_text(encoding='utf-8')
t=t.replace('PLUGIN_VERSION = "0.9.22"','PLUGIN_VERSION = "0.9.23"',1)
anchor='HOME_ICONS = [os.path.join(PLUGIN_DIR, "home_%s.png" % name) for name in ("live", "movies", "series", "mediathek", "playlist", "settings")]\n'
if anchor not in t: raise SystemExit('HOME_ICONS anchor missing')
t=t.replace(anchor,anchor+'MEDIATHEK_ICON_DIR = os.path.join(PLUGIN_DIR, "mediathek_picons")\n',1)

# Replace Mediathek skins with larger country/provider cards and a much larger preview.
start=t.find('MEDIATHEK_HOME_SKIN = build_fullscreen_skin(')
end=t.find('SPLASH_SKIN = build_fullscreen_skin(',start)
if start<0 or end<0: raise SystemExit('Mediathek skin block missing')
new_skins=r'''MEDIATHEK_HOME_SKIN = build_fullscreen_skin(
    "EpiMediathekHome",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) + logo_widget(w=300,h=100) +
    label_widget("title",380,28,845,48,31,"right") +
    label_widget("subtitle",380,78,845,30,18,"right",fg="#9EADBF") +
    list_widget("list",55,135,650,440,25,58) +
    ''.join('<widget name="country_icon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="5" />' % (i,pos(72,145+(i*58)),size(78,44)) for i in range(6)) +
    label_widget("provider_title",745,145,465,58,30,"left","top") +
    label_widget("provider_meta",745,212,465,58,18,"left","top",fg="#AFC0D4") +
    label_widget("provider_info",745,285,465,250,20,"left","top","#0D121B","#E7EEF7") +
    label_widget("info",55,600,1170,34,16,"center",fg="#9EADBF") +
    color_button("red",55,"#8D2830") + color_button("green",350,"#267A42") +
    color_button("yellow",645,"#8A7624") + color_button("blue",940,"#245B8F")
)

MEDIATHEK_DIRECTORY_SKIN = build_fullscreen_skin(
    "EpiMediathekDirectory",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) + logo_widget(w=300,h=100) +
    label_widget("title",380,28,845,48,31,"right") + label_widget("subtitle",380,78,845,30,18,"right",fg="#9EADBF") +
    list_widget("list",55,130,675,465,23,50) +
    ''.join('<widget name="provider_icon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="5" />' % (i,pos(72,136+(i*50)),size(72,40)) for i in range(9)) +
    '<widget name="hero_icon" position="%s" size="%s" alphatest="on" scale="1" zPosition="4" />' % (pos(790,145),size(180,100)) +
    label_widget("provider_title",790,260,410,65,28,"left","top") +
    label_widget("provider_meta",790,330,410,82,18,"left","top",fg="#AFC0D4") +
    label_widget("provider_info",790,420,410,155,18,"left","top","#0D121B","#E7EEF7") +
    label_widget("info",55,603,1170,31,16,"center",fg="#9EADBF") +
    color_button("red",55,"#8D2830") + color_button("green",350,"#267A42") +
    color_button("yellow",645,"#8A7624") + color_button("blue",940,"#245B8F")
)

MEDIATHEK_LIST_SKIN = build_fullscreen_skin(
    "EpiMediathekList",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) + logo_widget(w=300,h=100) +
    label_widget("title",380,28,845,48,29,"right") + label_widget("subtitle",380,78,845,30,17,"right",fg="#9EADBF") +
    list_widget("list",45,125,475,470,20,50) +
    '<widget name="poster" position="%s" size="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(545,138),size(305,410)) +
    label_widget("preview_title",880,138,345,88,27,"left","top") +
    label_widget("preview_meta",880,232,345,105,18,"left","top",fg="#AFC0D4") +
    label_widget("preview_overview",880,345,345,220,18,"left","top","#0D121B","#E7EEF7") +
    label_widget("poster_hint",545,555,305,34,15,"center","center",fg="#8093A8") +
    label_widget("info",45,603,1180,31,15,"center",fg="#9EADBF") +
    color_button("red",55,"#8D2830") + color_button("green",350,"#267A42") +
    color_button("yellow",645,"#8A7624") + color_button("blue",940,"#245B8F")
)

'''
t=t[:start]+new_skins+t[end:]

code_start=t.find('MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"')
code_end=t.find('class EpiMediaHubHome(Screen):',code_start)
if code_start<0 or code_end<0: raise SystemExit('Mediathek code block missing')
new_code=r'''MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"


def _mi(name):
    return os.path.join(MEDIATHEK_ICON_DIR,name+".png")

MEDIATHEK_COUNTRIES=[
    {"id":"de","label":"Deutschland","icon":_mi("country_de"),"meta":"ARD · ZDF · Dritte · ARTE · DW","info":"Die größte Auswahl: nationale Sender, Spartenprogramme und alle großen Regionalprogramme."},
    {"id":"at","label":"Österreich","icon":_mi("country_at"),"meta":"ORF","info":"ORF-Sendungen über MediathekView. Einzelne Titel können außerhalb Österreichs lizenzbedingt gesperrt sein."},
    {"id":"ch","label":"Schweiz","icon":_mi("country_ch"),"meta":"SRF","info":"SRF-Inhalte über MediathekView. Auslandsverfügbarkeit ist titelabhängig."},
    {"id":"it","label":"Italien · Family","icon":_mi("country_it"),"meta":"Rai · PIN geschützt","info":"Familienbereich für frei erreichbare Rai-Inhalte. Geo-Sperren werden nicht umgangen."},
    {"id":"tr","label":"Türkei","icon":_mi("country_tr"),"meta":"TRT · tabii","info":"TRT-Angebote für türkische Inhalte. Direkte Streams werden nur verwendet, wenn TRT sie am Standort ausliefert."},
    {"id":"fr","label":"Frankreich / International","icon":_mi("country_fr"),"meta":"ARTE France · TV5MONDEplus","info":"Französische und internationale Angebote. ARTE France ist direkt integriert; TV5MONDEplus wird als internationaler Anbieter ausgewiesen."}
]

MEDIATHEK_DIRS={
"de":[
 {"id":"ard","label":"ARD / Das Erste","kind":"mvw","channel":"ARD","icon":_mi("provider_ard"),"availability":"Deutschland · frei","info":"Sendungen aus der ARD Mediathek."},
 {"id":"zdf","label":"ZDF","kind":"mvw","channel":"ZDF","icon":_mi("provider_zdf"),"availability":"Deutschland · frei","info":"ZDF, ZDFneo und ZDFinfo über die ZDF-Mediathek."},
 {"id":"3sat","label":"3sat","kind":"mvw","channel":"3sat","icon":_mi("provider_3sat"),"availability":"D/A/CH · frei","info":"3sat-Mediathek."},
 {"id":"kika","label":"KiKA","kind":"mvw","channel":"KIKA","icon":_mi("provider_kika"),"availability":"Deutschland · frei","info":"Kinderprogramme aus der KiKA-Mediathek."},
 {"id":"phoenix","label":"PHOENIX","kind":"mvw","channel":"PHOENIX","icon":_mi("provider_phx"),"availability":"Deutschland · frei","info":"Dokumentationen, Politik und Ereignisse."},
 {"id":"arte_de","label":"ARTE Deutschland","kind":"mvw","channel":"ARTE.DE","icon":_mi("provider_arte"),"availability":"Deutschland · frei/teilweise","info":"ARTE-Angebot für Deutschland."},
 {"id":"dw","label":"Deutsche Welle","kind":"mvw","channel":"DW","icon":_mi("provider_dw"),"availability":"International","info":"Internationale DW-Mediathek."},
 {"id":"regional","label":"Deutsche Regionalprogramme","kind":"dir","target":"de_regional","icon":_mi("provider_reg"),"availability":"9 Mediatheken","info":"BR, HR, MDR, NDR, Radio Bremen, RBB, SR, SWR und WDR."},
 {"id":"tag","label":"Tagesschau","kind":"mvw","channel":"Tagesschau","icon":_mi("provider_tag"),"availability":"Deutschland · frei","info":"Nachrichten und Tagesschau-Angebote."}
],
"de_regional":[
 {"id":"br","label":"BR","kind":"mvw","channel":"BR","icon":_mi("provider_br"),"availability":"Bayern","info":"BR Mediathek."},
 {"id":"hr","label":"HR","kind":"mvw","channel":"HR","icon":_mi("provider_hr"),"availability":"Hessen","info":"HR Mediathek."},
 {"id":"mdr","label":"MDR","kind":"mvw","channel":"MDR","icon":_mi("provider_mdr"),"availability":"Mitteldeutschland","info":"MDR Mediathek."},
 {"id":"ndr","label":"NDR","kind":"mvw","channel":"NDR","icon":_mi("provider_ndr"),"availability":"Norddeutschland","info":"NDR Mediathek."},
 {"id":"rb","label":"Radio Bremen TV","kind":"mvw","channel":"Radio Bremen","icon":_mi("provider_rb"),"availability":"Bremen","info":"Radio Bremen Mediathek."},
 {"id":"rbb","label":"RBB","kind":"mvw","channel":"RBB","icon":_mi("provider_rbb"),"availability":"Berlin/Brandenburg","info":"RBB Mediathek."},
 {"id":"sr","label":"SR","kind":"mvw","channel":"SR","icon":_mi("provider_sr"),"availability":"Saarland","info":"SR Mediathek."},
 {"id":"swr","label":"SWR","kind":"mvw","channel":"SWR","icon":_mi("provider_swr"),"availability":"Südwesten","info":"SWR Mediathek."},
 {"id":"wdr","label":"WDR","kind":"mvw","channel":"WDR","icon":_mi("provider_wdr"),"availability":"NRW","info":"WDR Mediathek."}
],
"at":[{"id":"orf","label":"ORF","kind":"mvw","channel":"ORF","icon":_mi("provider_orf"),"availability":"Deutschland: teilweise","info":"ORF1, ORF2, ORF3 und ORF Sport. Einige Inhalte sind außerhalb Österreichs geogeblockt."}],
"ch":[{"id":"srf","label":"SRF","kind":"mvw","channel":"SRF","icon":_mi("provider_srf"),"availability":"Deutschland: teilweise","info":"SRF1, SRF2 und SRFinfo. Rechteabhängig können einzelne Beiträge gesperrt sein."}],
"fr":[
 {"id":"arte_fr","label":"ARTE France","kind":"mvw","channel":"ARTE.FR","icon":_mi("provider_arte"),"availability":"Deutschland: meist nutzbar","info":"Französisches ARTE-Angebot; einzelne Rechte können regional variieren."},
 {"id":"tv5","label":"TV5MONDEplus","kind":"info","icon":_mi("provider_tv5"),"availability":"International · kostenlos","info":"Internationales französischsprachiges Streaming-Angebot. Direkte native Wiedergabe wird nur aktiviert, wenn eine stabile offene Stream-Schnittstelle verfügbar ist."}
],
"it":[
 {"id":"rai","label":"RaiPlay International · freie Inhalte","kind":"rai","icon":_mi("provider_rai"),"availability":"Family · Deutschland: titelabhängig","info":"Öffentlich erreichbare Rai-News/TGR-Inhalte. Keine Umgehung von Geo-Sperren."}
],
"tr":[
 {"id":"trt1","label":"TRT 1","kind":"trt","page":"https://www.trt1.com.tr/Canli-izle","icon":_mi("provider_trt"),"availability":"Deutschland: streamabhängig","info":"TRT 1. EpiMediaHub versucht nur offiziell ausgelieferte HLS-Streams zu verwenden."},
 {"id":"trthaber","label":"TRT Haber","kind":"trt","page":"https://www.trthaber.com/canli-yayin-izle.html","icon":_mi("provider_trt"),"availability":"International / streamabhängig","info":"TRT Haber Live, sofern der offizielle Webplayer einen offenen Stream liefert."},
 {"id":"tabii","label":"tabii","kind":"info","icon":_mi("provider_tabii"),"availability":"International · Konto/Region abhängig","info":"TRTs Streamingplattform für Serien, Filme und Dokumentationen. Vollzugriff und Preis/Verfügbarkeit hängen vom Land ab."}
]
}

RAI_TGR_URLS=[
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-72f5c514-26b0-41d8-958e-cbb5e36c2c47-json-V-1.html",
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-c210f09b-abbf-404a-abd5-1f524d6be645-json-V-1.html",
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-85d08f9e-08f2-4cf3-86b3-2afaaee5fa83-json-V-1.html",
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-f8905105-4b5c-4e6c-afed-e67b4703b50f-json-V-1.html"
]


def mediathek_copy(key):
    lang=current_app_language(); de={"label":"Mediathek","subtitle":"Mediatheken nach Ländern","search_all":"Alle Mediatheken durchsuchen","latest":"Neueste Beiträge","loading":"Beiträge werden geladen ...","play":"GRÜN  Abspielen","search":"GELB  Suche","reload":"BLAU  Neu laden","back":"ROT  Zurück","source":"Quelle: MediathekViewWeb","no_results":"Keine abspielbaren Beiträge gefunden.","search_title":"Mediathek durchsuchen"}
    return de.get(key,key)

def mediathek_label(): return mediathek_copy("label")

def _mediathek_duration(value):
    try: seconds=max(0,int(value or 0))
    except Exception: seconds=0
    h=seconds//3600; m=(seconds%3600)//60
    return ("%d:%02d Std."%(h,m)) if h else (("%d Min."%m) if m else "")

def _mediathek_date(value):
    try:
        stamp=int(value or 0); stamp=stamp//1000 if stamp>20000000000 else stamp
        return time.strftime("%d.%m.%Y",time.localtime(stamp)) if stamp>0 else ""
    except Exception: return ""

def _mediathek_episode_hint(title,topic):
    text="%s %s"%(clean_text(topic),clean_text(title))
    for pattern in (r'(?i)S(?:taffel)?\s*0*(\d+)\s*[/\- ]*E(?:pisode|p\.?|Folge)?\s*0*(\d+)',r'(?i)S(\d+)\s*[/\-]?E(\d+)',r'(?i)Staffel\s*(\d+).*?Folge\s*(\d+)'):
        m=re.search(pattern,text)
        if m: return "Staffel %d · Folge %d"%(int(m.group(1)),int(m.group(2)))
    return ""

def _mediathek_query(channel="",term="",offset=0,size=40):
    q=[]; channel=clean_text(channel); term=clean_text(term)
    if channel: q.append({"fields":["channel"],"query":channel})
    if term: q.append({"fields":["title","topic","description"],"query":term})
    body={"queries":q,"sortBy":"timestamp","sortOrder":"desc","future":False,"offset":int(offset or 0),"size":int(size or 40)}
    payload=json.dumps(body).encode("utf-8"); raw=None; err=None
    for ct in ("application/json","text/plain"):
        try:
            req=Request(MEDIATHEK_API_URL,data=payload); req.add_header("Content-Type",ct); req.add_header("Accept","application/json"); req.add_header("User-Agent","EpiMediaHub/%s"%PLUGIN_VERSION)
            r=urlopen(req,timeout=15); raw=r.read(); r.close(); break
        except Exception as e: err=e; raw=None
    if raw is None: raise Exception(str(err or "MediathekViewWeb nicht erreichbar"))
    text=raw if isinstance(raw,str) else raw.decode("utf-8","replace"); data=json.loads(text); rows=(data.get("result",{}) or {}).get("results",[])
    out=[]
    for item in rows:
        if not isinstance(item,dict): continue
        stream=clean_text(item.get("url_video_hd","")) or clean_text(item.get("url_video","")) or clean_text(item.get("url_video_low",""))
        if not stream: continue
        out.append({"title":clean_text(item.get("title","")) or clean_text(item.get("topic","")) or "Mediathek","topic":clean_text(item.get("topic","")),"channel":clean_text(item.get("channel","")),"description":clean_text(item.get("description","")),"duration":item.get("duration",0),"timestamp":item.get("timestamp",0),"url":stream,"url_website":clean_text(item.get("url_website","")),"type":"movie"})
    return out

def _rai_query(term="",limit=45):
    out=[]; seen=set()
    for source in RAI_TGR_URLS:
        try:
            req=Request(source); req.add_header("User-Agent","Mozilla/5.0 EpiMediaHub/%s"%PLUGIN_VERSION); r=urlopen(req,timeout=12); data=json.loads(r.read().decode("utf-8","replace")); r.close()
            for item in data.get("list",[]):
                title=clean_text(item.get("name","")); desc=clean_text(item.get("desc","")); topic=clean_text(item.get("from","")) or clean_text((item.get("isPartOf") or {}).get("name","")); url=clean_text(item.get("m3u8","")) or clean_text(item.get("mediaUri",""))
                if not title or not url: continue
                if term and term.lower() not in (title+" "+desc+" "+topic).lower(): continue
                if url in seen: continue
                seen.add(url); out.append({"title":title,"topic":topic or "Rai","channel":"RAI","description":desc,"duration":0,"timestamp":0,"url":url,"url_website":clean_text(item.get("weblink","")),"type":"movie"})
                if len(out)>=limit: return out
        except Exception: pass
    return out

def _page_hls(page):
    req=Request(page); req.add_header("User-Agent","Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s"%PLUGIN_VERSION); r=urlopen(req,timeout=12); raw=r.read(1200000); r.close(); html=raw.decode("utf-8","replace")
    html=html.replace('\\/','/').replace('&amp;','&')
    m=re.search(r'https?://[^"\'<> ]+\.m3u8(?:\?[^"\'<> ]*)?',html,re.I)
    return clean_text(m.group(0)) if m else ""

def _mediathek_page_image(page_url):
    page_url=clean_text(page_url)
    if not page_url.startswith(("http://","https://")): return ""
    try:
        req=Request(page_url); req.add_header("User-Agent","Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s"%PLUGIN_VERSION); r=urlopen(req,timeout=10); raw=r.read(700000); r.close(); html=raw.decode("utf-8","replace")
        for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
            m=re.search(pat,html,re.I)
            if m:
                image=clean_text(m.group(1)).replace('&amp;','&')
                if image.startswith('//'): image='https:'+image
                elif image.startswith('/'):
                    u=urlparse(page_url); image='%s://%s%s'%(u.scheme,u.netloc,image)
                return image
    except Exception: pass
    return ""

def _set_pix(widget,path):
    try:
        if widget.instance is not None and path and os.path.isfile(path): widget.instance.setPixmapFromFile(path); widget.show(); return True
    except Exception: pass
    try: widget.hide()
    except Exception: pass
    return False

class EpiMediathekHome(Screen):
    skin=MEDIATHEK_HOME_SKIN
    def __init__(self,session):
        Screen.__init__(self,session); self.items=list(MEDIATHEK_COUNTRIES); self["logo"]=Pixmap(); self["title"]=Label("Mediathek"); self["subtitle"]=Label("Nach Land / Nationalität auswählen"); self["list"]=MenuList(["            "+x["label"] for x in self.items]); self["provider_title"]=Label(""); self["provider_meta"]=Label(""); self["provider_info"]=Label(""); self["info"]=Label("OK = Land öffnen"); self["red"]=Label("ROT  Zurück"); self["green"]=Label("GRÜN  Öffnen"); self["yellow"]=Label(""); self["blue"]=Label("")
        for i in range(6): self["country_icon%d"%i]=Pixmap()
        self["actions"]=ActionMap(["OkCancelActions","DirectionActions","ColorActions"],{"ok":self.openSelected,"green":self.openSelected,"cancel":self.close,"red":self.close,"up":self.keyUp,"down":self.keyDown},-1)
        self.onLayoutFinish.append(self._layout)
    def _layout(self):
        for i,item in enumerate(self.items): _set_pix(self["country_icon%d"%i],item.get("icon",""))
        try: self["list"].onSelectionChanged.append(self.updateInfo)
        except Exception: pass
        self.updateInfo()
    def selected(self):
        try: i=int(self["list"].getSelectedIndex())
        except Exception: i=0
        return self.items[i] if 0<=i<len(self.items) else None
    def updateInfo(self):
        x=self.selected()
        if not x:return
        self["provider_title"].setText(x["label"]); self["provider_meta"].setText(x.get("meta","")); self["provider_info"].setText(x.get("info",""))
    def keyUp(self):
        try:self["list"].up()
        except Exception:pass
        self.updateInfo()
    def keyDown(self):
        try:self["list"].down()
        except Exception:pass
        self.updateInfo()
    def openSelected(self):
        x=self.selected()
        if not x:return
        try:self.session.open(EpiMediathekDirectory,x["id"],x["label"])
        except Exception as e:self.session.open(MessageBox,"Mediathek konnte nicht geöffnet werden:\n%s"%str(e),MessageBox.TYPE_ERROR,timeout=8)

class EpiMediathekDirectory(Screen):
    skin=MEDIATHEK_DIRECTORY_SKIN
    def __init__(self,session,directory_id,title=None):
        Screen.__init__(self,session); self.directory_id=directory_id; self.items=list(MEDIATHEK_DIRS.get(directory_id,[])); self["logo"]=Pixmap(); self["title"]=Label(title or "Mediathek"); self["subtitle"]=Label("Anbieter auswählen"); self["list"]=MenuList(["            "+x["label"] for x in self.items]); self["hero_icon"]=Pixmap(); self["provider_title"]=Label(""); self["provider_meta"]=Label(""); self["provider_info"]=Label(""); self["info"]=Label("OK = öffnen"); self["red"]=Label("ROT  Zurück"); self["green"]=Label("GRÜN  Öffnen"); self["yellow"]=Label(""); self["blue"]=Label("")
        for i in range(9): self["provider_icon%d"%i]=Pixmap()
        self["actions"]=ActionMap(["OkCancelActions","DirectionActions","ColorActions"],{"ok":self.openSelected,"green":self.openSelected,"cancel":self.close,"red":self.close,"up":self.keyUp,"down":self.keyDown},-1); self.onLayoutFinish.append(self._layout)
    def _layout(self):
        for i in range(9):
            if i<len(self.items): _set_pix(self["provider_icon%d"%i],self.items[i].get("icon",""))
            else:
                try:self["provider_icon%d"%i].hide()
                except Exception:pass
        try:self["list"].onSelectionChanged.append(self.updateInfo)
        except Exception:pass
        self.updateInfo()
    def selected(self):
        try:i=int(self["list"].getSelectedIndex())
        except Exception:i=0
        return self.items[i] if 0<=i<len(self.items) else None
    def updateInfo(self):
        x=self.selected()
        if not x:return
        _set_pix(self["hero_icon"],x.get("icon","")); self["provider_title"].setText(x["label"]); self["provider_meta"].setText(x.get("availability","")); self["provider_info"].setText(x.get("info",""))
    def keyUp(self):
        try:self["list"].up()
        except Exception:pass
        self.updateInfo()
    def keyDown(self):
        try:self["list"].down()
        except Exception:pass
        self.updateInfo()
    def _pin_done(self,pin,item):
        if pin is None:return
        if hashlib.sha256(clean_text(pin).encode("utf-8")).hexdigest()!=FAMILY_PIN_HASH:
            self.session.open(MessageBox,"PIN ist falsch.",MessageBox.TYPE_ERROR,timeout=3);return
        self._open_item(item)
    def openSelected(self):
        x=self.selected()
        if not x:return
        if x.get("kind")=="rai":
            try:self.session.openWithCallback(lambda pin:self._pin_done(pin,x),EpiPinScreen,title="Family · Rai International")
            except Exception as e:self.session.open(MessageBox,str(e),MessageBox.TYPE_ERROR,timeout=6)
            return
        self._open_item(x)
    def _open_item(self,x):
        kind=x.get("kind")
        if kind=="dir": self.session.open(EpiMediathekDirectory,x.get("target",""),x.get("label","")); return
        if kind in ("mvw","rai"): self.session.open(EpiMediathekList,x.get("channel",""),x.get("label",""),"",kind); return
        if kind=="trt":
            try:
                url=_page_hls(x.get("page",""))
                if not url: raise Exception("TRT liefert auf dieser Seite aktuell keinen direkt nutzbaren HLS-Stream aus.")
                ref=eServiceReference(4097,0,url); ref.setName(x.get("label","TRT")); self.session.open(MoviePlayer,ref) if MoviePlayer is not None else self.session.nav.playService(ref)
            except Exception as e:self.session.open(MessageBox,"TRT-Stream nicht verfügbar:\n%s"%str(e),MessageBox.TYPE_INFO,timeout=8)
            return
        self.session.open(MessageBox,"%s\n\n%s\n\n%s"%(x.get("label","Mediathek"),x.get("availability",""),x.get("info","")),MessageBox.TYPE_INFO,timeout=10)

class EpiMediathekList(Screen):
    skin=MEDIATHEK_LIST_SKIN
    def __init__(self,session,channel="",label="",term="",source_kind="mvw"):
        Screen.__init__(self,session); self.channel=clean_text(channel); self.channel_label=clean_text(label) or "Mediathek"; self.term=clean_text(term); self.source_kind=source_kind; self.results=[]; self._closing=False; self._load_job=None; self._load_result=None; self._poster_job=None; self._poster_result=None; self._poster_token=0; self._poster_decoder=None
        self["logo"]=Pixmap(); self["title"]=Label(self.channel_label); self["subtitle"]=Label(""); self["list"]=MenuList([]); self["poster"]=Pixmap(); self["preview_title"]=Label(""); self["preview_meta"]=Label(""); self["preview_overview"]=Label(""); self["poster_hint"]=Label(""); self["info"]=Label(""); self["red"]=Label("ROT  Zurück"); self["green"]=Label("GRÜN  Abspielen"); self["yellow"]=Label("GELB  Suche"); self["blue"]=Label("BLAU  Neu laden")
        self["actions"]=ActionMap(["OkCancelActions","DirectionActions","ColorActions"],{"ok":self.playSelected,"green":self.playSelected,"cancel":self.safeClose,"red":self.safeClose,"yellow":self.openSearch,"blue":self.reload,"up":self.keyUp,"down":self.keyDown,"left":self.pageUp,"right":self.pageDown},-1)
        self._load_timer=eTimer(); connect_timer(self._load_timer,self._pollLoad); self._poster_delay_timer=eTimer(); connect_timer(self._poster_delay_timer,self._startPosterLoad); self._poster_poll_timer=eTimer(); connect_timer(self._poster_poll_timer,self._pollPoster); self.onLayoutFinish.append(self._layout)
        try:self.onClose.append(self._stopWorkers)
        except Exception:pass
    def _layout(self):
        try:self["poster"].hide()
        except Exception:pass
        try:self["list"].onSelectionChanged.append(self._selectionChanged)
        except Exception:pass
        self.reload()
    def safeClose(self):
        if self._closing:return
        self._closing=True; self._stopWorkers(); self.close()
    def _stopWorkers(self):
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
    def reload(self):
        if self._closing:return
        if self._load_job is not None and self._load_job.is_alive():return
        self.results=[]; self._load_result=None; self["list"].setList(["Beiträge werden geladen ..."]); self._clearPreview(); self["subtitle"].setText("Suche: "+self.term if self.term else "Neueste Beiträge"); self._load_job=threading.Thread(target=self._loadWorker); self._load_job.daemon=True; self._load_job.start();
        try:self._load_timer.start(300,True)
        except TypeError:self._load_timer.start(300)
    def _loadWorker(self):
        try:
            items=_rai_query(self.term,45) if self.source_kind=="rai" else _mediathek_query(self.channel,self.term,0,45)
            self._load_result=(True,items,"")
        except Exception as e:self._load_result=(False,[],str(e))
    def _pollLoad(self):
        if self._closing:return
        if self._load_job is not None and self._load_job.is_alive():
            try:self._load_timer.start(300,True)
            except TypeError:self._load_timer.start(300)
            return
        result=self._load_result; self._load_job=None; self._load_result=None
        if not result:return
        ok,items,error=result
        if not ok:self["list"].setList(["Mediathek konnte nicht geladen werden"]);self["preview_overview"].setText(error);return
        self.results=list(items or [])
        if not self.results:self["list"].setList(["Keine abspielbaren Beiträge gefunden."]);return
        rows=[]
        for e in self.results:
            topic=clean_text(e.get("topic",""));title=clean_text(e.get("title",""));dur=_mediathek_duration(e.get("duration",0)); shown=title if not topic or topic.lower()==title.lower() else "%s — %s"%(topic,title); rows.append(shown+("  ·  "+dur if dur else ""))
        self["list"].setList(rows); self["info"].setText("%d Beiträge"%len(self.results)); self._selectionChanged()
    def selectedEntry(self):
        if not self.results:return None
        try:i=int(self["list"].getSelectedIndex())
        except Exception:i=0
        return self.results[i] if 0<=i<len(self.results) else None
    def _clearPreview(self):
        for n in ("preview_title","preview_meta","preview_overview","poster_hint"):
            try:self[n].setText("")
            except Exception:pass
        try:self["poster"].hide()
        except Exception:pass
    def _selectionChanged(self):
        if self._closing:return
        e=self.selectedEntry()
        if not e:return
        title=clean_text(e.get("title",""));topic=clean_text(e.get("topic",""));channel=clean_text(e.get("channel",""));date=_mediathek_date(e.get("timestamp",0));dur=_mediathek_duration(e.get("duration",0));ep=_mediathek_episode_hint(title,topic); self["preview_title"].setText(topic if topic and topic.lower()!=title.lower() else title); self["preview_meta"].setText("\n".join([x for x in (channel,ep,date,dur) if x][:4])); desc=clean_text(e.get("description","")); self["preview_overview"].setText(((title+"\n\n") if topic and topic.lower()!=title.lower() else "")+(desc or "Keine Beschreibung verfügbar.")); self._schedulePoster()
    def _schedulePoster(self):
        self._poster_token+=1
        try:self._poster_delay_timer.stop();self._poster_delay_timer.start(500,True)
        except TypeError:self._poster_delay_timer.start(500)
        except Exception:pass
    def _startPosterLoad(self):
        if self._closing:return
        if self._poster_job is not None and self._poster_job.is_alive():
            try:self._poster_delay_timer.start(500,True)
            except TypeError:self._poster_delay_timer.start(500)
            return
        e=self.selectedEntry(); page=clean_text(e.get("url_website","")) if e else ""
        if not page:return
        token=self._poster_token; self._poster_result=None; self._poster_job=threading.Thread(target=self._posterWorker,args=(token,page)); self._poster_job.daemon=True; self._poster_job.start();
        try:self._poster_poll_timer.start(250,True)
        except TypeError:self._poster_poll_timer.start(250)
    def _posterWorker(self,token,page):
        try:
            image=_mediathek_page_image(page); path=download_image_cached(image,POSTER_CACHE_DIR,key="mediathek_"+hashlib.sha1(page.encode("utf-8","ignore")).hexdigest(),timeout=10,max_bytes=4*1024*1024) if image else ""; self._poster_result=(token,path)
        except Exception:self._poster_result=(token,"")
    def _pollPoster(self):
        if self._closing:return
        if self._poster_job is not None and self._poster_job.is_alive():
            try:self._poster_poll_timer.start(250,True)
            except TypeError:self._poster_poll_timer.start(250)
            return
        result=self._poster_result;self._poster_job=None;self._poster_result=None
        if not result or result[0]!=self._poster_token:return
        if result[1]:self._showPoster(result[1])
    def _showPoster(self,path):
        if self._closing or not path or ePicLoad is None:return
        try:
            self._poster_decoder=ePicLoad()
            try:self._poster_decoder.PictureData.get().append(self._posterDecoded)
            except Exception:
                try:self._poster_decoder.PictureData.connect(self._posterDecoded)
                except Exception:return
            self._poster_decoder.setPara((sx(305),sy(410),1,1,False,1,"#00000000"));self._poster_decoder.startDecode(path)
        except Exception:pass
    def _posterDecoded(self,*args):
        if self._closing:return
        try:
            ptr=self._poster_decoder.getData() if self._poster_decoder is not None else None
            if ptr is not None and self["poster"].instance is not None:self["poster"].instance.setPixmap(ptr);self["poster"].show()
        except Exception:pass
    def _move(self,m):
        if self._closing:return
        try:getattr(self["list"],m)()
        except Exception:pass
        self._selectionChanged()
    def keyUp(self):self._move("up")
    def keyDown(self):self._move("down")
    def pageUp(self):self._move("pageUp")
    def pageDown(self):self._move("pageDown")
    def openSearch(self):
        if self._closing:return
        try:self.session.openWithCallback(self.searchEntered,VirtualKeyBoard,title="Mediathek durchsuchen",text=self.term)
        except Exception:pass
    def searchEntered(self,value=None):
        if self._closing:return
        value=clean_text(value or "")
        if value!=self.term:self.term=value;self.reload()
    def playSelected(self):
        if self._closing:return
        e=self.selectedEntry();url=clean_text(e.get("url","")) if e else ""
        if not url:return
        try:
            ref=eServiceReference(4097,0,url);ref.setName(e.get("title","Mediathek"));self.session.open(EpiMoviePlayer,ref,["deu","ger","ita","tur","eng"],"",url,0,e,[],-1) if EpiMoviePlayer is not None else (self.session.open(MoviePlayer,ref) if MoviePlayer is not None else self.session.nav.playService(ref))
        except Exception as err:self.session.open(MessageBox,"Wiedergabe fehlgeschlagen:\n%s"%str(err),MessageBox.TYPE_ERROR,timeout=7)

'''
t=t[:code_start]+new_code+t[code_end:]
p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.23/' "$TMP/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.23 country-grouped Mediathek, larger previews and safe exit/' "$TMP/control/control"

python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.23"' "$PLUGIN"
grep -q 'class EpiMediathekDirectory' "$PLUGIN"
grep -q 'def safeClose' "$PLUGIN"
grep -q 'RaiPlay International' "$PLUGIN"
grep -q 'Deutschland' "$PLUGIN"

# Informative provider smoke test; outages/geo blocks must not block packaging.
python3 - <<'PY' || true
import json
from urllib.request import Request,urlopen
for ch in ('ARD','ORF','SRF','ARTE.FR','DW'):
    body=json.dumps({'queries':[{'fields':['channel'],'query':ch}],'sortBy':'timestamp','sortOrder':'desc','future':False,'offset':0,'size':1}).encode()
    try:
        r=Request('https://mediathekviewweb.de/api/query',data=body,headers={'Content-Type':'application/json','User-Agent':'EpiMediaHub-v0923-smoke'})
        d=json.loads(urlopen(r,timeout=10).read().decode('utf-8','replace'));print(ch,len(d.get('result',{}).get('results',[])))
    except Exception as e: print(ch,'smoke unavailable',e)
PY

tar --owner=0 --group=0 -czf "$TMP/pkg/control.tar.gz" -C "$TMP/control" .
tar --owner=0 --group=0 -czf "$TMP/pkg/data.tar.gz" -C "$TMP/data" .
cd "$TMP/pkg"; ar r "$WORKSPACE/EpiMediaHub_v0.9.23.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null; cd "$WORKSPACE"

if ar p EpiMediaHub_v0.9.23.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then echo 'ERROR: package owns persistent user-data paths' >&2; exit 1; fi
SIZE=$(stat -c%s EpiMediaHub_v0.9.23.ipk); echo "v0.9.23 size: $SIZE bytes"; [ "$SIZE" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
SHA=$(sha256sum EpiMediaHub_v0.9.23.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.23.ipk" > EpiMediaHub_v0.9.23.ipk.sha256
printf '{\n  "version": "0.9.23",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.23.ipk",\n  "sha256": "%s"\n}\n' "$SHA" > update.json
sha256sum -c EpiMediaHub_v0.9.23.ipk.sha256
rm -f EpiMediaHub_v0.9.22.ipk EpiMediaHub_v0.9.22.ipk.sha256
rm -f .github/workflows/inspect-v0922-family-pin.yml inspection/v0922-family-pin.txt

git config user.name 'github-actions[bot]'; git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A; git commit -m 'Publish EpiMediaHub v0.9.23 world Mediathek and safe exit'; git push
