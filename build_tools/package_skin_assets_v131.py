#!/usr/bin/env python3
"""Package reviewed offline artwork with bounded image dimensions and a digest.

This only transcodes provided images for Android; it does not generate or
remove portrait backgrounds. The four paired cutouts were prepared separately.
"""
import argparse,base64,gzip,hashlib,io,json,tarfile
from pathlib import Path
from PIL import Image,ImageOps
REPO=Path(__file__).resolve().parent.parent

def main():
 p=argparse.ArgumentParser();p.add_argument('collection',type=Path);p.add_argument('special',type=Path);p.add_argument('base_catalog',type=Path);a=p.parse_args()
 here=REPO/'android/v1.0.31';out=here/'artwork_parts';out.mkdir(exist_ok=True)
 cache=a.collection/'optimized_v131';cache.mkdir(exist_ok=True)
 for f in out.glob('part_*'):f.unlink()
 rows=[l.split('|')for l in(here/'team_roster_candidates.txt').read_text().splitlines()if l and not l.startswith('#')]
 base=json.loads(a.base_catalog.read_text()); additions={'groups':[],'themes':{}};meta={'teams':[]};files={};credits={}
 def encode(source,destination,maxsize=(500,620),quality=80):
  if destination in files:return
  key=hashlib.sha256((str(source)+str(maxsize)+str(quality)).encode()).hexdigest();cached=cache/(key+'.webp')
  if not cached.exists():
   with Image.open(source)as image:
    image=ImageOps.exif_transpose(image);image.thumbnail(maxsize)
    image.save(cached,'WEBP',quality=quality,method=3)
  files[destination]=cached.read_bytes()
 def photo(art):
  assert art and art.get('name') and art.get('file')
  name=Path(art['file']).stem+'.webp';asset='skin_portraits/'+name
  encode(a.collection/'images'/art['file'],'assets/'+asset)
  credits[asset]={k:art[k]for k in('name','playerId','providerTeam','sourcePage','url','sha256')if k in art}
  return {'name':art['name'],'asset':asset,'transparent':bool(art['transparent'])}
 pairs={('f1_ferrari','players'):'ferrari_drivers.webp',('f1_ferrari','legends'):'ferrari_legends.webp',('juventus','legends'):'juventus_legends.webp',('nba_los_angeles_lakers','legends'):'lakers_legends.webp'}
 for index,(ident,name,sport,legends,preferred) in enumerate(rows):
  if index % 20 == 0:print('Packaging',index,'/',len(rows),flush=True)
  team=json.loads((a.collection/(ident+'.json')).read_text())
  assert len(team['players'])==len(team['legends'])==2,(ident,'incomplete portraits')
  assert len({p['name']for p in team['players']})==len({p['name']for p in team['legends']})==2
  if ident not in base['themes']:
   group='nba'if ident.startswith('nba_')else'nfl';assert ident.startswith(('nba_','nfl_'))
   assert team.get('logo'),(ident,'logo missing')
   encode(a.collection/'images'/team['logo']['file'],'res/drawable-nodpi/official_'+ident+'.webp',(440,440),88)
   info={'label':name,'group':group,'accent':team.get('accent','#35A5FF'),'background':ident+'.png','family':True}
   additions['themes'][ident]=info
  else: info=base['themes'][ident]
  variants=[{'id':ident,'label':'Original','portraits':[]}]
  for kind in ['players','legends']:
   label=('Fahrer'if sport=='Motorsport'else'Spieler')if kind=='players'else'Legenden'
   if kind=='legends'and ident in ['f1_audi','f1_alpine','f1_aston_martin','f1_racing_bulls']:label='Team-Historie'
   if kind=='legends'and ident=='f1_cadillac':label='US-Motorsport-Ikonen'
   variant={'id':ident+'__'+kind,'label':label,'portraits':[photo(x)for x in team[kind]]}
   pair=pairs.get((ident,kind))
   if pair:
    asset='skin_portraits/'+pair;files['assets/'+asset]=(a.special/pair).read_bytes();variant['pairAsset']=asset
    credits[asset]={'source':'Prepared EpiMediaHub portrait artwork','names':[x['name']for x in team[kind]],'presentation':'Autogramm-Optik; keine verifizierten Originalsignaturen'}
   variants.append(variant)
   additions['themes'][variant['id']]={**info,'label':info['label']+' · '+label}
  meta['teams'].append({'id':ident,'variants':variants})
 for group,label in [('nba','NBA'),('nfl','NFL')]:
  additions['groups'].append({'id':group,'label':label,'themes':[r[0]for r in rows if r[0].startswith(group+'_')]})
 assert len(meta['teams'])==134 and len(additions['themes'])==330
 (here/'catalog_additions.json').write_text(json.dumps(additions,ensure_ascii=False,indent=2)+'\n')
 files['assets/skin_variants_v131.json']=(json.dumps(meta,ensure_ascii=False,separators=(',',':'))+'\n').encode()
 files['assets/licenses/skin_portraits_v131_sources.json']=(json.dumps(credits,ensure_ascii=False,indent=2)+'\n').encode()
 files['res/drawable-nodpi/skin_world_basketball.webp']=(a.special/'skin_world_basketball.webp').read_bytes()
 stream=io.BytesIO()
 with tarfile.open(fileobj=stream,mode='w')as tar:
  for name,data in sorted(files.items()):
   entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o644;entry.mtime=0;tar.addfile(entry,io.BytesIO(data))
 packed=gzip.compress(stream.getvalue(),compresslevel=9,mtime=0);encoded=base64.b64encode(packed).decode()
 for index,start in enumerate(range(0,len(encoded),72000)):(out/f'part_{index:04d}').write_text(encoded[start:start+72000]+'\n')
 manifest={'sha256':hashlib.sha256(packed).hexdigest(),'bytes':len(packed),'teamCount':134,'variantCount':402,'files':{name:hashlib.sha256(data).hexdigest()for name,data in sorted(files.items())}}
 (here/'artwork_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'teams':134,'variants':402,'uniqueAssets':len(files),'compressedBytes':len(packed),'parts':len(list(out.glob('part_*')))},indent=2))
if __name__=='__main__':main()
