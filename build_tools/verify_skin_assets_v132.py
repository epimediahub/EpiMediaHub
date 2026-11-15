#!/usr/bin/env python3
import hashlib, json, os
from pathlib import Path
root=Path(os.environ['PROJECT_ROOT'])/'app/src/main';source=Path(__file__).resolve().parent.parent/'android/v1.0.32'
manifest=json.loads((source/'artwork_manifest.json').read_text());meta=json.loads((root/'assets/skin_variants_v131.json').read_text())
catalog=json.loads((root/'res/raw/theme_catalog.json').read_text())
assert len(meta['teams'])==134 and manifest['portraitCount']==536
for name,digest in manifest['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
count=0;by_id={}
for team in meta['teams']:
    base=team['id'];original=catalog['themes'][base]
    assert [v['id']for v in team['variants']]==[base,base+'__players',base+'__legends']
    assert not team['variants'][0]['portraits'];assert any((root/'res').glob('drawable*/official_'+base+'.*'))
    for variant in team['variants'][1:]:
        by_id[variant['id']]=variant;theme=catalog['themes'][variant['id']]
        assert theme['family']and theme['group']==original['group']and theme['accent']==original['accent']
        assert len(variant['portraits'])==2 and not variant.get('pairAsset')
        for p in variant['portraits']:
            count+=1;assert p['transparent']and p['framing']=='upper_body'and p['kitTeam']==base
            assert p['asset'].startswith('skin_portraits_v132/')and '..'not in Path(p['asset']).parts
            l,t,r,b=p['window'];assert 0<=l<r<=1 and 0<=t<b<=1
            w,h=manifest['imageSizes'][p['asset']];assert w*h*4<=5_242_880
            assert abs(p['aspectRatio']-w*(r-l)/(h*(b-t)))<.00001
assert count==536
assert [p['name']for p in by_id['juventus__players']['portraits']]==['Kenan Yıldız','Gleison Bremer']
assert 'Arda Güler'in [p['name']for p in by_id['national_tr__players']['portraits']]
assert '@drawable/historical_*'in (root/'res/raw/keep.xml').read_text()
assert 'val expiry = v132RememberPlaylistExpiry'in (root/'java/de/epimediahub/app/ui/V083Home.kt').read_text()
assert 'if (!parental.settings().hasPin) leaveKids()'in (root/'java/de/epimediahub/app/ui/V130SmartTubeGate.kt').read_text()
print('Verified 134 teams, 402 variants, 536 upper-body windows, protected originals and account expiry')
