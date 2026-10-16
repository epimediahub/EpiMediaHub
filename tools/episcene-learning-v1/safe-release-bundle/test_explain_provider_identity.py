import json
import sqlite3
import unittest

import explain_provider_identity as mod


class ProviderIdentityAuditTests(unittest.TestCase):
    def test_precise_hash_mismatch_without_printing_url(self):
        row={'mapped_stream':'123','mapped_extension':'mkv',
             'config_json':'{"username":"SECRET_USER","password":"SECRET_PASS"}',
             'media_type':'episode','asset_key':'OLD_HASH'}
        def source_url(config,r):
            self.assertIn('SECRET_PASS',config['config_json'])
            self.assertEqual(r['stream_id'],'123')
            self.assertEqual(r['extension'],'mkv')
            return 'https://secret.invalid/SECRET_USER/SECRET_PASS/123.mkv'
        def hash_key(url,kind):
            self.assertIn('SECRET_PASS',url)
            return 'NEW_HASH'
        self.assertEqual(mod.reason(row,source_url,hash_key),
                         'PROVIDER_IDENTITY_CHANGED')
        self.assertEqual(mod.reason(dict(row,asset_key='NEW_HASH'),
                                    source_url,hash_key),'MATCH')
        self.assertEqual(mod.reason(dict(row,mapped_stream='abc'),
                                    source_url,hash_key),'STREAM_ID_UNUSABLE')
        self.assertEqual(mod.reason(dict(row,mapped_extension='exe'),
                                    source_url,hash_key),'EXTENSION_UNSUPPORTED')
        self.assertEqual(mod.reason(dict(row,config_json=None),
                                    source_url,hash_key),'ANALYSIS_PROVIDER_CONFIG_UNAVAILABLE')

    def test_network_or_resolver_error_never_printed(self):
        row={'mapped_stream':'123','mapped_extension':'mp4',
             'config_json':'TOP_SECRET_CONFIG','media_type':'episode','asset_key':'old'}
        def broken(*args):
            raise ValueError('https://secret.example/USER/PASS')
        self.assertEqual('SOURCE_URL_INVALID_INPUT',
                         mod.reason(row,broken,lambda u,k:u))

    def test_missing_field_name_is_sanitized(self):
        row={'mapped_stream':'123','mapped_extension':'mkv',
             'config_json':'secret','media_type':'episode','asset_key':'old'}
        def expected_field(*args):
            raise KeyError('server_url')
        self.assertEqual('SOURCE_URL_REQUIRED_FIELD_SERVER_URL',
                         mod.reason(row,expected_field,lambda u,k:u))
        def untrusted_field(*args):
            raise KeyError('secret-actual-provider-account-name')
        self.assertEqual('SOURCE_URL_MISSING_FIELD',
                         mod.reason(row,untrusted_field,lambda u,k:u))

    def test_output_contains_only_aggregate_reasons(self):
        db=sqlite3.connect(':memory:')
        db.executescript("""
        CREATE TABLE skip_records(
            id INTEGER,asset_key TEXT,media_type TEXT,source_key TEXT,
            season INTEGER,episode INTEGER,duration_ms INTEGER,title TEXT,
            start_ms INTEGER,end_ms INTEGER,segment_type TEXT,disabled INTEGER,
            device_id INTEGER,customer_id INTEGER,status TEXT,source TEXT
        );
        CREATE TABLE skip_assets(
            asset_key TEXT,playlist_id INTEGER,media_type TEXT,source_key TEXT,
            season INTEGER,episode INTEGER,duration_ms INTEGER,title TEXT,
            stream_id TEXT,extension TEXT
        );
        CREATE TABLE devices(id INTEGER,customer_id INTEGER,enabled INTEGER);
        CREATE TABLE customers(id INTEGER,enabled INTEGER);
        CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
        CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER,config_json TEXT);
        CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
        INSERT INTO devices VALUES(10,20,1);
        INSERT INTO customers VALUES(20,1);
        INSERT INTO skip_analysis_playlists VALUES(8,0,'SECRET_PASS');
        INSERT INTO skip_analysis_sources VALUES(8,1);
        INSERT INTO skip_assets VALUES
            ('OLD_ASSET_KEY',8,'episode','SECRET_SOURCE',1,1,1000000,
             'SECRET_SERIES','123','mkv');
        INSERT INTO skip_records VALUES
            (9,'OLD_ASSET_KEY','episode','SECRET_SOURCE',1,1,1000000,
             'SECRET_SERIES',0,30000,'intro',0,10,20,'pending','device');
        """)
        def full_object_resolver(provider, asset):
            self.assertEqual(provider['id'],8)
            self.assertEqual(asset['playlist_id'],8)
            self.assertEqual(asset['stream_id'],'123')
            return 'https://secret.invalid/USER/PASS'
        result=mod.audit(db,full_object_resolver,
                             lambda url,kind:'NEW_KEY')
        output=json.dumps(result)
        for secret in ('SECRET_PASS','SECRET_SERIES','SECRET_SOURCE','OLD_ASSET_KEY'):
            self.assertNotIn(secret,output)
        self.assertEqual(result['counts'],{'PROVIDER_IDENTITY_CHANGED':1})
        self.assertEqual(result['database_changes'],0)
        self.assertEqual(db.execute('SELECT status FROM skip_records').fetchone()[0],'pending')


if __name__=='__main__':
    unittest.main()
