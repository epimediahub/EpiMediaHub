import importlib.util,json,sqlite3,tempfile,unittest,contextlib,io
from pathlib import Path
from unittest.mock import patch

SCRIPT=Path(__file__).with_name('verify_resume.py')
spec=importlib.util.spec_from_file_location('epi_verified',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Verification(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.db=Path(self.tmp.name)/'test.db'
  self.sql=sqlite3.connect(self.db);self.addCleanup(self.sql.close)
  self.sql.executescript("""
  CREATE TABLE skip_analysis_playlists(id INTEGER,name TEXT,config_json TEXT,expires_at TEXT,revision INTEGER,archived INTEGER,updated_at TEXT);
  INSERT INTO skip_analysis_playlists(id,name,config_json,archived) VALUES
    (8,'4K ANALYSE','{"enabled":true,"paused":false,"access_token":"PRIVATE"}',0),
    (10,'THE BEST','{"enabled":true,"paused":false,"access_token":"PRIVATE"}',0);
  CREATE TABLE skip_presence(expires_at INTEGER);
  CREATE TABLE skip_analysis_sources(playlist_id INTEGER PRIMARY KEY,enabled INTEGER NOT NULL);
  INSERT INTO skip_analysis_sources VALUES (8,1),(10,1);
  CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER);
  INSERT INTO skip_assets VALUES('opaque8',8),('opaque10',10);
  CREATE TABLE skip_jobs(asset_key TEXT,status TEXT,updated_at TEXT);
  INSERT INTO skip_jobs VALUES
    ('opaque8','queued','2026-10-17T07:00:00'),
    ('opaque10','queued','2026-10-17T07:00:00');
  CREATE TABLE episcene_report_events(id INTEGER PRIMARY KEY,at REAL,kind TEXT,asset_key TEXT,record_id INTEGER,payload TEXT);
  INSERT INTO episcene_report_events(id,kind,asset_key,payload) VALUES(1,'heartbeat','','{}');
  """);self.sql.commit()
  self.old_db=m.DB;m.DB=self.db;self.addCleanup(lambda:setattr(m,'DB',self.old_db))
  with m.ro() as c:self.base=m.snap(c)

 def emit(self,kind,payload,asset_key=None):
  pid=payload.get('playlist_id') or payload.get('asset',{}).get('playlist_id')
  key=asset_key if asset_key is not None else ('opaque'+str(pid) if pid in m.LANES else '')
  self.sql.execute('INSERT INTO episcene_report_events(kind,asset_key,payload) VALUES(?,?,?)',
                   (kind,key,json.dumps(payload)));self.sql.commit()
 def results(self):
  with m.ro() as c:return m.progress(c,self.base)

 def test_both_lanes_required_for_pass(self):
  self.emit('heartbeat',{'status':'running'})
  self.emit('analysis_completion',{'playlist_id':8})
  self.emit('job',{'asset':{'playlist_id':8},'job':{'status':'done'}})
  with patch.object(m,'active',return_value=True):
   self.assertEqual(m.check(self.base,seconds=0)['status'],'FAIL_NO_CONFIRMED_PROGRESS')
  self.emit('analysis_completion',{'playlist_id':10})
  self.emit('job',{'asset':{'playlist_id':10},'job':{'status':'review'}})
  with patch.object(m,'active',return_value=True),patch.object(m,'cmd',return_value='active'):
   result=m.check(self.base,seconds=0)
  self.assertEqual(result['status'],'PASS')
  self.assertEqual(result['verified_lanes'],[8,10])
  self.assertEqual(result['marker_changes'],0)

 def test_failed_jobs_do_not_pass(self):
  self.emit('heartbeat',{})
  for pid in (8,10):
   self.emit('analysis_completion',{'playlist_id':pid})
   self.emit('job',{'asset':{'playlist_id':pid},'job':{'status':'failed'}})
  with patch.object(m,'active',return_value=True):
   self.assertNotEqual(m.check(self.base,seconds=0)['status'],'PASS')

 def test_only_running_or_heartbeat_does_not_pass(self):
  self.emit('heartbeat',{})
  for pid in (8,10):self.emit('job',{'asset':{'playlist_id':pid},'job':{'status':'running'}})
  with patch.object(m,'active',return_value=True):
   self.assertNotEqual(m.check(self.base,seconds=0)['status'],'PASS')

 def test_absent_schema_or_disabled_source_blocks(self):
  self.sql.execute('UPDATE skip_analysis_sources SET enabled=0 WHERE playlist_id=10');self.sql.commit()
  with m.ro() as c:
   with self.assertRaisesRegex(RuntimeError,'INDEPENDENT_ANALYSIS_LANE'):m.snap(c)

 def test_live_like_schema_without_enabled_is_diagnosed_safely(self):
  self.sql.executescript("""
  DROP TABLE skip_analysis_playlists;
  CREATE TABLE skip_analysis_playlists(id INTEGER PRIMARY KEY, active INTEGER, archived INTEGER, paused INTEGER, secret TEXT);
  INSERT INTO skip_analysis_playlists VALUES(8,1,0,0,'DO_NOT_OUTPUT');
  INSERT INTO skip_analysis_playlists VALUES(10,1,0,0,'DO_NOT_OUTPUT');
  """)
  self.sql.commit()
  output=io.StringIO()
  with patch.object(m,'cmd',return_value='active'),contextlib.redirect_stdout(output):
   self.assertEqual(m.diagnosis(),0)
  self.assertNotIn('DO_NOT_OUTPUT',output.getvalue())
  report=json.loads(output.getvalue().split('DIAGNOSTIC ',1)[1])
  self.assertIn('active',report['tables']['skip_analysis_playlists']['columns'])
  self.assertNotIn('secret',report['tables']['skip_analysis_playlists']['lane_flags'][0])
  self.assertEqual(len(report['tables']['skip_analysis_playlists']['lane_flags']),2)
  with m.ro() as connection:
   with self.assertRaisesRegex(RuntimeError,'PLAYLIST_SCHEMA_UNSUPPORTED'):
    m.snap(connection)

 def test_mismatched_assets_do_not_pass(self):
  self.emit('heartbeat',{})
  for pid in m.LANES:
   self.emit('analysis_completion',{'playlist_id':pid},asset_key='completed'+str(pid))
   self.emit('job',{'asset':{'playlist_id':pid},'job':{'status':'done'}},asset_key='other'+str(pid))
  with patch.object(m,'active',return_value=True),patch.object(m,'cmd',return_value='active'):
   self.assertNotEqual(m.check(self.base,seconds=0)['status'],'PASS')

 def test_customer_playback_does_not_disable_dedicated_sources(self):
  self.sql.execute('INSERT INTO skip_presence VALUES(?)',(9999999999,))
  self.sql.commit()
  with m.ro() as c:
   sample=m.snap(c)
  self.assertEqual(sample['presence'],1)
  self.assertEqual(set(sample['waiting']),{8,10})

 def test_audit_uses_real_job_status_without_exposing_metadata(self):
  with m.ro() as c:
   before=m.audit_counts(c)
  self.assertEqual(before['8']['statuses']['queued'],1)
  self.sql.execute('UPDATE skip_jobs SET status=?,updated_at=? WHERE asset_key=?',
                   ('review','2026-10-17T07:30:00','opaque8'))
  self.sql.commit()
  with m.ro() as c:
   after=m.audit_counts(c)
  self.assertEqual(after['8']['statuses']['review'],1)
  self.assertNotIn('PRIVATE',json.dumps(after))
  self.assertEqual(after['10']['statuses']['queued'],1)

 def test_database_readonly_no_markers_changed(self):
  original=self.db.read_bytes()
  with m.ro() as c:
   with self.assertRaises(sqlite3.OperationalError):
    c.execute("UPDATE skip_jobs SET status='done'")
  self.assertEqual(self.db.read_bytes(),original)

 def test_playback_refuses_restart_before_systemd_change(self):
  with patch.object(m.os,'geteuid',return_value=0), patch.object(m,'cmd') as mocked:
   with self.assertRaisesRegex(RuntimeError,'PLAYBACK_ACTIVE'):
    m.guarded_restart(dict(self.base,presence=1))
   mocked.assert_not_called()

if __name__=='__main__':unittest.main()
