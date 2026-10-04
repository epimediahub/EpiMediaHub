#!/usr/bin/env python3
"""Fail the release if any required team/portrait/crest is absent."""
import json,os
from pathlib import Path
root=Path(os.environ['PROJECT_ROOT'])/'app/src/main';catalog=json.loads((root/'res/raw/theme_catalog.json').read_text());metadata=json.loads((root/'assets/skin_variants_v131.json').read_text())
assert len(metadata['teams'])==134
counts={'nba':30,'nfl':32,'formula_1':11,'national_teams':20}
for group,count in counts.items():assert len(next(g['themes']for g in catalog['groups']if g['id']==group))==count
for team in metadata['teams']:
 ident=team['id'];base=catalog['themes'][ident];variants=team['variants'];assert len(variants)==3
 assert [v['id']for v in variants]==[ident,ident+'__players',ident+'__legends']
 assert next(g['themes']for g in catalog['groups']if g['id']==base['group']).count(ident)==1
 assert any((root/'res').glob('drawable*/official_'+ident+'.*')),'Missing original crest: '+ident
 for variant in variants[1:]:
  theme=catalog['themes'][variant['id']];assert theme['family']and theme['group']==base['group']and theme['accent']==base['accent']
  assert len(variant['portraits'])==2
  for p in variant['portraits']:assert (root/'assets'/p['asset']).is_file()
  if variant.get('pairAsset'):assert (root/'assets'/variant['pairAsset']).is_file()
assert 'if (!parental.settings().hasPin) leaveKids()'in(root/'java/de/epimediahub/app/ui/V130SmartTubeGate.kt').read_text()
print('Verified 134 teams / 402 variants, original crests and optional Kids PIN')
