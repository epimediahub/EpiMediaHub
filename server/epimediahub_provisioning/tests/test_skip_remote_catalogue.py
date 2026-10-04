"""Real catalogue HTTP and worker batches with persistent/remote audio roles."""
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.parse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import skip_analysis as audio
import skip_automation as auto
import skip_remote_client as remote
from skip_analysis_worker import process_batch
from skip_remote_protocol import PROTOCOL
from skip_remote_worker import Server
from test_skip_remote_analysis import RpcFixture
import test_skip_analysis_catalogue as catalogue_tests
import test_skip_analysis_online_errors as metadata_tests


class RemoteMetadataTests(metadata_tests.JSONProxyTests):
    def setUp(self):
        super().setUp()
        self.rpc=Server(('127.0.0.1',0),peers=('127.0.0.1',))
        self.rpc_thread=threading.Thread(target=self.rpc.serve_forever,kwargs={'poll_interval':.02},daemon=True)
        self.rpc_thread.start();self.addCleanup(self.close_rpc)
        self.endpoint='http://127.0.0.1:'+str(self.rpc.server_port)
        patch=mock.patch.dict(os.environ,SKIP_ANALYSIS_REMOTE_URL=self.endpoint,SKIP_ANALYSIS_PROVIDER_PATH='raspberry')
        patch.start();self.addCleanup(patch.stop)

    def close_rpc(self):
        self.rpc.tasks.stopping.set()
        self.rpc.shutdown();self.rpc.server_close();self.rpc_thread.join(timeout=2)

    def test_metadata_size_and_invalid_json_restore_remote_audio_after_failure(self):
        self.status=200
        for body,limit,error in ((b'{"type":"tv"}',4,ValueError),(b'{',100,json.JSONDecodeError)):
            with self.subTest(body=body):
                self.body=body
                with self.assertRaises(error): auto.fetch_json(self.url,limit=limit)
                self.assertTrue(remote.configured())
                self.assertEqual(self.rpc.tasks.items,{})

    def test_persistent_role_fetches_metadata_locally_then_offloads_audio_matching(self):
        self.status,self.body=200,b'{"type":"tv"}'
        rng=random.Random(28)
        words=[rng.getrandbits(32) for _ in range(100)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'role.json'
            path.write_text(json.dumps(dict(protocol=PROTOCOL,url=self.endpoint,provider_path='raspberry')))
            with mock.patch.dict(os.environ,SKIP_ANALYSIS_REMOTE_URL=''),mock.patch.object(remote,'role_path',return_value=path):
                self.assertTrue(remote.configured())
                self.assertEqual(auto.fetch_json(self.url),{'type':'tv'})
                self.assertEqual(self.rpc.tasks.items,{})
                self.assertTrue(remote.configured())
                self.assertEqual(audio.matching_offset(words,words,125),(0,1.0))
                self.assertEqual(remote.health()['completed'],1)


class RemoteCatalogueWorkerTests(catalogue_tests.CatalogueFixture,RpcFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.start_server()
        self.config['xtream_server']='http://provider.example'
        with self.db() as con:
            con.execute('UPDATE customer_playlists SET config_json=?',(json.dumps(self.config),))
        self.actions=[]
        self.events=[]
        fixture=self
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self):
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                action=query['action'][0]
                fixture.actions.append(action)
                if action=='get_series_info': fixture.events.append(('inventory',query['series_id'][0]))
                body=(fixture.listing if action=='get_series' else [] if action=='get_series_categories'
                      else fixture.infos[query['series_id'][0]])
                data=json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Length',str(len(data)))
                self.end_headers();self.wfile.write(data)
        self.provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        self.provider_thread=threading.Thread(target=self.provider.serve_forever,daemon=True)
        self.provider_thread.start();self.addCleanup(self.close_provider)
        def pin(cls,host,address,**kwargs):
            self.assertEqual(address,'93.184.216.34')
            return http.client.HTTPConnection('127.0.0.1',self.provider.server_port,**kwargs)
        for patch in (mock.patch.object(audio,'public_address',return_value=('provider.example','93.184.216.34')),
                      mock.patch.object(audio,'pinned_connection',side_effect=pin)):
            patch.start();self.addCleanup(patch.stop)

    def close_provider(self):
        self.provider.shutdown();self.provider.server_close();self.provider_thread.join(timeout=2)

    def worker_batch(self):
        rng=random.Random(29)
        words=[rng.getrandbits(32) for _ in range(100)]
        def analyze(*_,**kwargs):
            self.assertTrue(remote.configured(),'Metadata fetch must restore audio offload')
            self.assertEqual(audio.matching_offset(words,words,125),(0,1.0))
            return 'no_match','Remote comparison completed'
        # The actual inventory/JSON/proxy/HTTP/queue/budget path remains intact.
        # Substitute only the episode's audio contents with a real remote match.
        with mock.patch('skip_analysis_worker.analyze',side_effect=analyze):
            self.assertEqual(process_batch(self.db,max_jobs=3,max_seconds=60),['no_match']*3)
        self.assertIn('get_series',self.actions)
        self.assertIn('get_series_info',self.actions)
        self.assertEqual(remote.health()['completed'],3)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_assets').fetchone()[0],4)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='no_match' AND attempts=1").fetchone()[0],3)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],3)
            self.assertEqual(con.execute('SELECT full_done FROM skip_catalogue_runs').fetchone()[0],0)
            self.assertEqual(self.actions.count('get_series_info'),1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],0)

    def test_real_catalogue_and_three_jobs_run_with_direct_remote_audio(self):
        with mock.patch.dict(os.environ,SKIP_ANALYSIS_PROVIDER_PATH='direct'): self.worker_batch()

    def test_real_catalogue_and_three_jobs_run_with_private_media_relay(self):
        with mock.patch.dict(os.environ,SKIP_ANALYSIS_PROVIDER_PATH='raspberry'): self.worker_batch()

    def test_real_catalogue_and_jobs_run_with_only_the_persisted_role(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'role.json'
            path.write_text(json.dumps(dict(protocol=PROTOCOL,url=self.endpoint,provider_path='raspberry')))
            with mock.patch.dict(os.environ,SKIP_ANALYSIS_REMOTE_URL='',SKIP_ANALYSIS_PROVIDER_PATH=''), \
                 mock.patch.object(remote,'role_path',return_value=path):
                os.environ.pop('SKIP_ANALYSIS_PROVIDER_PATH')
                self.worker_batch()

    def test_series_finishes_over_real_rpc_before_next_series_inventory(self):
        rng=random.Random(29);words=[rng.getrandbits(32) for _ in range(100)]
        def analyze(db,job,**kwargs):
            with db() as con:
                asset=con.execute('SELECT stream_id FROM skip_assets WHERE asset_key=?',(job['asset_key'],)).fetchone()
            self.assertEqual(audio.matching_offset(words,words,125),(0,1.0))
            self.events.append(('audio',asset['stream_id']))
            return 'no_match','Remote comparison completed'
        with mock.patch.dict(os.environ,SKIP_ANALYSIS_PROVIDER_PATH='raspberry'), \
             mock.patch('skip_analysis_worker.analyze',side_effect=analyze):
            self.assertEqual(process_batch(self.db,max_jobs=8,max_seconds=60),['no_match']*5+['idle'])
        self.assertEqual(self.events,[('inventory','501'),('audio','101'),('audio','102'),
                                      ('audio','103'),('audio','110'),('inventory','502'),('audio','201')])
        self.assertEqual(remote.health()['completed'],5)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT full_done FROM skip_catalogue_runs').fetchone()[0],1)


if __name__=='__main__': unittest.main()
