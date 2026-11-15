#!/usr/bin/env python3
"""Package offline upper-body portraits and historical badges for Android 1.0.32.

Inputs are the reviewed recovered PNG atlases, authentic photographs, and their
role mappings. Display windows crop source photographs at the waist; no facial
detection or generated replacement is used for the critical player photographs.
"""
import argparse, hashlib, io, json
from pathlib import Path
from PIL import Image

ap=argparse.ArgumentParser()
ap.add_argument('--inputs', type=Path, required=True)
args=ap.parse_args()
inputs=args.inputs.resolve()
repo=Path(__file__).resolve().parent.parent
out=repo/'android/v1.0.32'
staging=out/'artwork'
staging.mkdir(exist_ok=True)
original=inputs/'artwork-v131'
meta=json.loads((original/'assets/skin_variants_v131.json').read_text())
remaining=json.loads((inputs/'remaining-art.json').read_text())
variants={v['id']:v for t in meta['teams'] for v in t['variants']}
roles={}
files={}
sizes={}
credits=[]
source_credits=json.loads((original/'assets/licenses/skin_portraits_v131_sources.json').read_text())
library=json.loads((inputs/'recover-images-input.json').read_text())['result']['items']
key=json.loads((inputs/'key-art-map.json').read_text())

def png_path(file):
    path=Path(file)
    if path.is_absolute():
        if path.exists(): return path
        # Permit restoration into a different workspace root.
        if 'generated_images' in path.parts:
            return inputs/'generated_images'/path.name
    return inputs/path

def role_ref(row):
    return (row['variant'], row['index'])

def asset_image(path, name, atlas=False):
    im=Image.open(path).convert('RGBA')
    im.thumbnail((1280,1024) if atlas else (768,1024), Image.Resampling.LANCZOS)
    name='skin_portraits_v132/'+name+'.webp'
    target=staging/'assets'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    encoded=io.BytesIO();im.save(encoded,format='WEBP',quality=87,method=4)
    temporary=target.with_name(target.name+'.tmp');temporary.write_bytes(encoded.getvalue());temporary.replace(target)
    # Window geometry is measured on the actual encoded image.
    result=Image.open(target).convert('RGBA')
    assert result.width*result.height*4<=5_242_880
    sizes[name]=list(result.size)
    files['assets/'+name]=target.read_bytes()
    return name,result

def window(im, col=0, row=0, columns=1, rows=1, bottom_fraction=1.0):
    # Each cell is isolated before alpha analysis, so neighboring sprites cannot
    # affect the portrait rectangle. Keep the whole head, including raised hands.
    x0=round(im.width*col/columns);x1=round(im.width*(col+1)/columns)
    y0=round(im.height*row/rows);y1=round(im.height*(row+1)/rows)
    alpha=im.getchannel('A').crop((x0,y0,x1,y1)).point(lambda a:255 if a>=12 else 0)
    bbox=alpha.getbbox()
    assert bbox, (col,row,columns,rows)
    l,t,r,b=bbox
    b=min(b,round(t+(b-t)*bottom_fraction))
    l=max(x0,x0+l-2);r=min(x1,x0+r+2)
    t=max(y0,y0+t-2);b=min(y1,y0+b+2)
    assert l<r and t<b
    coords=[l/im.width,t/im.height,r/im.width,b/im.height]
    return coords,(r-l)/(b-t)

def assign(ref, asset, im, cell=0, columns=1, rows=1, bottom_fraction=1.0, source=None):
    coords,aspect=window(im,cell%columns,cell//columns,columns,rows,bottom_fraction)
    roles[tuple(ref)]={'asset':asset,'window':coords,'aspectRatio':aspect}
    if source:
        credits.append({'variant':ref[0],'position':ref[1],'source':source,'asset':asset,'window':coords})

# Reviewed generated atlases recovered from the existing Library files.
mapping=json.loads((inputs/'recovered-atlas-map.json').read_text())
for raw_index, entries in mapping.items():
    index=int(raw_index)
    item=library[index]
    path=inputs/'recovered-images'/item['path'].lstrip('/')
    asset,im=asset_image(path,'recovered_%02d'%index,atlas=True)
    count=len(entries)
    columns=4 if count in (4,8) else count
    rows=2 if count==8 else 1
    for cell,ref in enumerate(entries):
        if ref is not None:
            assign(ref,asset,im,cell,columns,rows,
                   .96 if index==0 else 1.0,
                   {'type':'reviewed_generated_upper_body','referenceAtlas':index})

# Preserve the three genuine existing upper-body pairs.
for variant, source in [
    ('juventus__legends','juventus_legends.webp'),
    ('f1_ferrari__players','ferrari_drivers.webp'),
    ('nba_los_angeles_lakers__legends','lakers_legends.webp'),
]:
    asset,im=asset_image(original/'assets/skin_portraits'/source,'original_'+variant,atlas=True)
    for cell in range(2):
        assign((variant,cell),asset,im,cell,2,1,source={'type':'existing_reviewed_team_upper_body','sourceAsset':source})

# Original photographs whose jersey and framing were checked.
reuse=json.loads((inputs/'reuse-art-indices.json').read_text())
for index in reuse:
    row=remaining[index];ref=role_ref(row)
    if ref in roles: continue
    asset,im=asset_image(original/'assets'/row['asset'],'source_%03d'%index)
    assign(ref,asset,im,source={'type':'existing_team_photograph','credit':source_credits.get(row['asset'],{})})

# Newly reviewed team/era corrections; nulls retain their original atlas cell.
for path in sorted(inputs.glob('new-art-[0-9][0-9].json')):
    group=json.loads(path.read_text())
    asset,im=asset_image(png_path(group['file']),'corrected_%02d'%group['group'],atlas=True)
    for cell,index in enumerate(group['indices']):
        if index is not None:
            assign(role_ref(remaining[index]),asset,im,cell,group['columns'],group['rows'],
                   source={'type':'reviewed_generated_team_upper_body','referenceAsset':remaining[index]['asset']})

# Authentic photographs; the coefficient trims full-body source photos at the
# waist inside the native display window, while retaining the whole head.
authentic=[
 ('juventus__players',0,'kenan_yildiz',1.0),
 ('juventus__players',1,'gleison_bremer',1.0),
 ('inter__players',1,'barella_inter',1.0),
 ('national_it__players',1,'barella_italy',1.0),
 ('barcelona__legends',1,'ronaldinho_barcelona',1.0),
 ('real_madrid__legends',0,'zidane_real',.45),
 ('national_tr__players',0,'arda_guler',.65),
 ('national_en__legends',0,'beckham_england',.55),
 ('national_de__legends',1,'schweinsteiger_germany',.50),
 ('galatasaray__players',1,'icardi_galatasaray',1.0),
 ('fenerbahce__legends',1,'roberto_fenerbahce',.47),
 ('basaksehir__legends',1,'visca_basaksehir',.485),
 ('national_fr__players',0,'mbappe_france',.46),
 ('national_ar__players',0,'messi_argentina',.52),
 ('napoli__legends',1,'hamsik_napoli',.50),
 ('real_madrid__legends',1,'ronaldo_real',.83),
 ('national_hr__legends',0,'suker_croatia',.85),
 ('atletico__legends',1,'godin_atletico',1.0),
 ('sevilla__legends',0,'kanoute_sevilla',.49),
 ('national_ma__players',0,'hakimi_morocco',.45),
 ('barcelona__legends',0,'messi_barcelona',.57),
 ('leipzig__legends',1,'poulsen_leipzig',.67),
]
for variant,index,name,bottom in authentic:
    info=key[name]
    path=png_path(info['file'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256']
    asset,im=asset_image(path,'authentic_'+name)
    assign((variant,index),asset,im,bottom_fraction=bottom,
           source={'type':'authentic_team_photograph','url':info['source'],'sourceSha256':info['sha256']})

# Preserve authentic Schneider and Forsberg rather than retrying an unavailable
# generated replacement. Schneider's source is framed at the waist.
for index,bottom in [(46,.90),(50,1.0)]:
    row=remaining[index]
    asset,im=asset_image(original/'assets'/row['asset'],'authentic_original_%03d'%index)
    assign(role_ref(row),asset,im,bottom_fraction=bottom,
           source={'type':'authentic_team_photograph','credit':source_credits.get(row['asset'],{})})

# Correct the reviewed Portugal Eusebio jersey independently of the old atlas.
info=json.loads((inputs/'eusebio-portugal-art.json').read_text())
asset,im=asset_image(png_path(info['file']),'corrected_eusebio_portugal')
assign(('national_pt__legends',1),asset,im,source={'type':'reviewed_generated_team_upper_body','kit':'Portugal historical burgundy national shirt'})

names={
 ('juventus__players',0):'Kenan Yıldız',('juventus__players',1):'Gleison Bremer',
 ('national_es__players',1):'Pedri',('national_tr__players',0):'Arda Güler',
 ('f1_mercedes__legends',1):'Lewis Hamilton',
 ('national_pt__legends',1):'Eusébio',
}
missing=[]
for team in meta['teams']:
    for variant in team['variants']:
        variant.pop('pairAsset',None)
        if variant['id']=='f1_cadillac__legends':variant['label']='US-Legenden'
        for index,portrait in enumerate(variant['portraits']):
            ref=(variant['id'],index)
            if ref not in roles:
                missing.append((ref,portrait['name']))
                continue
            portrait.update(roles[ref],transparent=True,framing='upper_body',kitTeam=team['id'])
            if ref in names:portrait['name']=names[ref]
assert not missing, missing
assert sum(len(v['portraits'])for t in meta['teams']for v in t['variants'])==536

# Historic team marks were downloaded and visually checked separately.
marks=json.loads((inputs/'historical-art-map.json').read_text())
for team,info in marks.items():
    path=png_path(info['rendered'])
    im=Image.open(path).convert('RGBA')
    im.thumbnail((512,512),Image.Resampling.LANCZOS)
    target=staging/'res/drawable-nodpi'/('historical_'+team+'.webp')
    target.parent.mkdir(parents=True,exist_ok=True)
    encoded=io.BytesIO();im.save(encoded,format='WEBP',lossless=True,method=4)
    temporary=target.with_name(target.name+'.tmp');temporary.write_bytes(encoded.getvalue());temporary.replace(target)
    files['res/drawable-nodpi/'+target.name]=target.read_bytes()
    credits.append({'historicalTeam':team,'url':info['source'],'sourceSha256':hashlib.sha256(png_path(info['file']).read_bytes()).hexdigest()})

def add_json(name,value):
    data=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    target=staging/name;target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.tmp');temporary.write_bytes(data);temporary.replace(target);files[name]=data
add_json('assets/skin_variants_v131.json',meta)
add_json('assets/licenses/skin_artwork_v132_sources.json',{
    'version':'1.0.32',
    'notes':'Private sport skins. Existing source credits remain bundled. Generated upper-body portraits were reviewed for identity, kit and era; authentic corrections use the recorded team photographs. Logo and photograph ownership is retained by their respective owners.',
    'entries':credits,
})
manifest={
 'version':'1.0.32','storage':'git_assets',
 'teamCount':134,'portraitCount':536,'historicalMarkCount':len(marks),
 'files':{n:hashlib.sha256(d).hexdigest()for n,d in sorted(files.items())},'imageSizes':sizes,
}
(out/'artwork_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'portraitWindows':536,'historicalMarks':len(marks),'bytes':sum(map(len,files.values())),'assets':len(files)},indent=2))
