"""Synthetic safety tests; NEVER accesses Hetzner, systemd or real accounts."""
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location(
    'fix_customer_scope_migration',Path(__file__).with_name('fix_customer_scope_migration.py'))
fix=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)


class FakeInstaller:
    NAMES=('skip_analysis.py','skip_markers.py')
    API_SERVICE='epimediahub-provisioning.service'
    ANALYSIS_SERVICE='epimediahub-analysis-worker.service'
    EXPECTED_NEW={'skip_analysis.py':'new','skip_markers.py':'new'}
    class Stop(Exception):pass
    def __init__(self,root):
        self.PROVISION=root
        self.install_calls=0
    def run(self,apply=False,bundle=None):
        if not apply:
            return {'preflight':'PASS'}
        self.install_calls+=1
        return {'applied':True,'analysis_worker_still_active':True,
                'backup_exists':True,'api_restarted':True}
    def active(self,service):
        return True
    def digest(self,path):
        return 'new'


class SchemaFixTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.db=self.base/'source.sqlite3'
        with sqlite3.connect(self.db) as db:
            db.executescript('''
                CREATE TABLE skip_records(id INTEGER PRIMARY KEY,status TEXT);
                CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY);
                CREATE TABLE devices(id INTEGER PRIMARY KEY);
                CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY);
                INSERT INTO skip_records VALUES(1,'pending');
            ''')
        self.installer=FakeInstaller(self.base)
        self.patches=[
            patch.object(fix,'original_installer',return_value=self.installer),
            patch.object(fix.os,'geteuid',return_value=0),
        ]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_check_does_not_touch_production_db(self):
        before=self.db.read_bytes()
        result=fix.run('check',bundle=self.base,database=self.db)
        self.assertEqual(result['preflight'],'PASS')
        self.assertEqual(result['changes_made'],0)
        self.assertEqual(before,self.db.read_bytes())
        self.assertEqual(self.installer.install_calls,0)

    def test_migration_enables_existing_installer_without_api_auto_migrate(self):
        result=fix.run('apply',bundle=self.base,database=self.db)
        self.assertTrue(result['applied'])
        self.assertTrue(result['new_tables_ready'])
        self.assertEqual(self.installer.install_calls,1)
        self.assertTrue(fix.run('verify',bundle=self.base,database=self.db)['verified'])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT status FROM skip_records WHERE id=1').fetchone()[0],'pending')
            self.assertEqual(db.execute('SELECT count(*) FROM skip_customer_marker_provenance').fetchone()[0],0)

    def test_existing_conflicting_schema_stops_without_touching_rows(self):
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE skip_customer_asset_claims(incorrect TEXT)')
        with self.assertRaises(fix.Stop):
            fix.run('check',bundle=self.base,database=self.db)
        self.assertEqual(self.installer.install_calls,0)

    def test_existing_wrong_index_stops(self):
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE INDEX idx_skip_customer_provenance_account ON skip_assets(asset_key)')
        with self.assertRaises(fix.Stop):
            fix.run('apply',bundle=self.base,database=self.db)
        self.assertEqual(self.installer.install_calls,0)

    def test_only_create_ddl_and_idempotence(self):
        self.assertEqual(len(fix.DDL),3)
        self.assertTrue(all(d.lstrip().startswith('CREATE ') for d in fix.DDL))
        value=fix.migrate(self.db)
        self.assertTrue(value['schema_ready'])
        again=fix.migrate(self.db)
        self.assertFalse(again['schema_created'])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT status FROM skip_records WHERE id=1").fetchone()[0],'pending')

    def test_fail_closed_when_original_installation_fails_after_schema(self):
        self.installer.run=lambda apply=False,bundle=None: (
            {'preflight':'PASS'} if not apply else
            {'applied':False,'rollback_restored':True,'reason':'SERVICE_FAILED'})
        result=fix.run('apply',bundle=self.base,database=self.db)
        self.assertFalse(result['applied'])
        self.assertTrue(result['rollback_restored'])
        self.assertTrue(result['schema_tables_preserved'])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT status FROM skip_records WHERE id=1').fetchone()[0],'pending')

    def test_missing_db_does_not_create_file(self):
        absent=self.base/'absent.db'
        with self.assertRaises(fix.Stop):
            fix.run('check',bundle=self.base,database=absent)
        self.assertFalse(absent.exists())


if __name__=='__main__':
    unittest.main()
