import importlib.util,json,sqlite3,tempfile,unittest
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
  CREATE TABLE skip_analysis_playlists(id INTEGER,enabled INTEGER,archived INTEGER,paused INTEGER);
  INSERT INTO skip_analysis_playlists VALUES(8,1,0,0),(10,1,0,0);
  CREATE TABLE skip_presence(expires_at INTEGER);
  CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER);
  INSERT INTO skip_assets VALUES('opaque8',8),('opaque10',10);
  CREATE TABLE skip_jobs(asset_key TEXT,status TEXT);
  INSERT INTO skip_jobs VALUES('opaque8','queued'),('opaque10','queued');
  CREATE TABLE episcene_report_events(id INTEGER PRIMARY KEY,kind TEXT,payload TEXT);
  INSERT INTO episcene_report_events VALUES(1,'heartbeat','{}');
  """);self.sql.commit()
  self.old_db=m.DB;m.DB=self.db;self.addCleanup(lambda:setattr(m,'DB',self.old_db))
  with m.ro() as c:self.base=m.snap(c)

 def emit(self,kind,payload):
  self.sql.execute('INSERT INTO episcene_report_events(kind,payload) VALUES(?,?)',
                   (kind,json.dumps(payload)));self.sql.commit()
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
  with patch.object(m,'active',return_value=True):
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
  self.sql.execute('UPDATE skip_analysis_playlists SET paused=1 WHERE id=10');self.sql.commit()
  with m.ro() as c:
   with self.assertRaisesRegex(RuntimeError,'ANALYSIS_LANES'):m.snap(c)

 def test_database_readonly_no_markers_changed(self):
  original=self.db.read_bytes()
  with m.ro() as c:
   with self.assertRaises(sqlite3.OperationalError):
    c.execute("UPDATE skip_jobs SET status='done'")
  self.assertEqual(self.db.read_bytes(),original)

 def test_playback_refuses_restart_before_systemd_change(self):
  with patch.object(m,'cmd') as mocked:
   with self.assertRaisesRegex(RuntimeError,'PLAYBACK_ACTIVE'):
    m.guarded_restart(dict(self.base,presence=1))
   mocked.assert_not_called()

if __name__=='__main__':unittest.main()
