#!/usr/bin/env python3
import json,sqlite3,tempfile,unittest
from pathlib import Path
import reference_engine as x

class TestRound(unittest.TestCase):
 def test_round_is_readonly_idempotent_and_produces_private_model(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);state=root/'round';state.mkdir();src=root/'source.sqlite';out=root/'shadow.sqlite'
   eps=[dict(id=f'REF-{j+1:02}',playlist_id=8,series='MobLand',season=1,episode=j+2) for j in range(5)]
   eps+= [dict(id=f'REF-{i:02}',playlist_id=10,series='Filler',season=1,episode=i) for i in range(6,41)]
   assert len(eps)==40
   (state/'plan.json').write_text(json.dumps(dict(episodes=eps)))
   (state/'baseline.json').write_text(json.dumps(dict(recorded_utc='2026-10-14T13:18:29+00:00')))
   with sqlite3.connect(src) as db:
    db.executescript('''CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INT,title TEXT,season INT,episode INT,source_key TEXT,duration_ms INT);
      CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,title TEXT,season INT,episode INT,created_at TEXT,segment_type TEXT,start_ms INT,end_ms INT,source TEXT,status TEXT,disabled INT);''')
    for j,diff in enumerate((35133,34160,35330,34470,37025),2):
     asset='mob-'+str(j)
     db.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)',(asset,8,'MobLand',1,j,'mobland-stream',2400000))
     db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(200+j,asset,'MobLand',1,j,'2026-10-14T15:10:00Z','outro',2300000,2390000,'device','pending',0))
     db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(300+j,asset,'MobLand',1,j,'2026-10-13T08:10:00Z','outro',2300000+diff,2390000,'audio_repetition','pending',0))
    db.execute("INSERT INTO skip_assets VALUES('mob-9',8,'MobLand',1,9,'mobland-stream',2400000)")
    db.execute("INSERT INTO skip_records VALUES(409,'mob-9','MobLand',1,9,'2026-10-13T08:10:00Z','outro',2335000,2390000,'audio_repetition','pending',0)")
    db.execute("INSERT INTO skip_assets VALUES('mob-10',8,'MobLand',1,10,'mobland-stream',2400000)")
    db.execute("INSERT INTO skip_records VALUES(410,'mob-10','MobLand',1,10,'2026-10-13T08:10:00Z','outro',2335000,2390000,'audio_repetition','pending',0)")
    db.execute("INSERT INTO skip_records VALUES(411,'mob-10','MobLand',1,10,'2026-10-12T08:10:00Z','outro',2300000,2390000,'device','pending',0)")
    db.commit()
   before=src.read_bytes()
   a=x.run(src,state,out);b=x.run(src,state,out)
   self.assertEqual(a,b)
   self.assertEqual(src.read_bytes(),before)
   self.assertEqual(a['attested_examples'],5)
   self.assertEqual(a['shadow_calibrations'],1)
   self.assertEqual(a['new_shadow_outro_candidates'],1)
   self.assertEqual(a['verified_backend_labels'],0)
   with sqlite3.connect(out) as d:
    self.assertEqual(d.execute('SELECT COUNT(*) FROM owner_attested_round40 WHERE verified_backend=1').fetchone()[0],0)
    self.assertEqual(d.execute('SELECT suggested_start_ms FROM shadow_outro_candidates').fetchone()[0],2299867)
    self.assertEqual(d.execute('SELECT shift_ms FROM shadow_outro_models').fetchone()[0],35133)

 def test_typo_and_orphan_are_not_promoted(self):
  plan=dict(episodes=[dict(id='REF-30',playlist_id=10,series='Berlino (Italiano)',season=1,episode=2),dict(id='REF-34',playlist_id=10,series='Bridgerton',season=1,episode=1)])
  baseline=dict(recorded_utc='2026-10-14T13:18:29+00:00')
  def row(i,title,start,end,asset):
   return dict(id=i,asset_key=asset,marker_title=title,marker_season=1,marker_episode=2 if title.startswith('Berlino') else 1,
      created_at='2026-10-14T15:00:00Z',segment_type='intro',start_ms=start,end_ms=end,source='device',status='pending',disabled=0,
      asset_title=title if asset!='missing' else None,asset_season=1 if asset!='missing' else None,
      asset_episode=2 if title.startswith('Berlino') else 1,playlist_id=10 if asset!='missing' else None,
      source_key='s' if asset!='missing' else None,duration_ms=4000000)
  rows=[row(2282,'Berlino (Italiano)',248880,292730,'a'),row(2283,'Berlino (Italiano)',248880,294660,'a'),row(2291,'Bridgerton',0,20000,'missing')]
  refs,_,conflicts=x.choose(rows,plan,baseline)
  self.assertEqual({v['id'] for v in refs},{2283,2291})
  self.assertEqual(len(conflicts),0)
  self.assertIsNone(next(r for r in refs if r['id']==2291)['playlist_id'])

if __name__=='__main__':unittest.main(verbosity=2)
