"""Native media relay: no Pi decoder, private peer guard, range seeks and persistent role."""
import contextlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import skip_analysis as audio
import skip_remote_client as remote
import skip_remote_protocol as protocol
from skip_remote_worker import validate, execute
from test_skip_remote_analysis import RpcFixture


class RelayTests(RpcFixture, unittest.TestCase):
    def setUp(self):
        self.start_server()

    def test_native_decoder_receives_relayed_media_and_seeks_without_provider_credentials(self):
        rate = 11025
        t = np.arange(rate * 42) / rate
        pcm = (11000*np.sin(2*np.pi*(190+30*(np.floor(t/3)%7))*t)).astype('<i2')
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as writer:
            writer.setparams((1,2,rate,0,'NONE','not compressed'))
            writer.writeframes(pcm.tobytes())
        data = stream.getvalue()
        ranges = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_HEAD(self): self.relay(False)
            def do_GET(self): self.relay(True)
            def relay(self, body):
                header = self.headers.get('Range')
                ranges.append(header)
                start,end = 0,len(data)-1
                if header:
                    match = re.fullmatch(r'bytes=(\d+)-(\d*)',header)
                    if not match:
                        self.send_error(400); return
                    start=int(match[1]); end=min(int(match[2]) if match[2] else end,end)
                self.send_response(206 if header else 200)
                self.send_header('Content-Type','audio/wav')
                self.send_header('Accept-Ranges','bytes')
                self.send_header('Content-Length',str(end-start+1))
                if header: self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}')
                self.end_headers()
                if body:
                    try: self.wfile.write(data[start:end+1])
                    except (BrokenPipeError,ConnectionResetError): pass
        provider = ThreadingHTTPServer(('127.0.0.1',0),Provider)
        provider.daemon_threads=True
        thread = threading.Thread(target=provider.serve_forever,daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                file = Path(directory)/'episode.wav'; file.write_bytes(data)
                with remote.local_execution():
                    expected = [audio.fingerprint(str(file),start,20_000,with_coverage=True,
                                                  require_complete=True) for start in (0,15_000)]
            parent = threading.get_ident()
            decoding = []
            payloads = []
            worker_ids = set()
            original = audio.run
            def run(*args,**kwargs):
                self.assertNotEqual(threading.get_ident(),parent,'Pi must not decode')
                self.assertIn(threading.get_ident(),worker_ids)
                decoding.append(args[0][0])
                return original(*args,**kwargs)
            def compute(operation,payload,busy):
                identity = threading.get_ident()
                worker_ids.add(identity)
                payloads.append(dict(payload))
                try:
                    return execute(operation,payload,busy)
                finally:
                    worker_ids.remove(identity)
            def address(url,host):
                self.assertEqual(host,'media.fixture')
                self.assertNotIn(threading.get_ident(),worker_ids,'Compute host must not resolve provider')
                return urllib.parse.urlsplit(url),('127.0.0.1',)
            self.server.tasks.executor=compute
            upstream=f'http://media.fixture:{provider.server_port}/series/private-user/private-password/42.wav'
            with mock.patch.dict('os.environ',SKIP_ANALYSIS_PROVIDER_PATH='raspberry'), \
                 mock.patch.object(protocol,'CLIENT_IP','127.0.0.1'), \
                 mock.patch.object(protocol,'SERVER_IP','127.0.0.1'), \
                 mock.patch.object(audio,'public_address',side_effect=address), \
                 mock.patch.object(audio,'run',side_effect=run):
                with audio.provider_proxy(upstream) as source:
                    self.assertTrue(source.via_pi)
                    self.assertNotIn('private-password',repr(source))
                    self.assertEqual(audio.probe(source),(42000,[]))
                    for start,wanted in zip((0,15_000),expected):
                        self.assertEqual(audio.fingerprint(source,start,20_000,with_coverage=True,
                            require_complete=True),wanted)
                    url=source.url
                with self.assertRaises(urllib.error.URLError):
                    urllib.request.urlopen(url,timeout=.5)
            self.assertEqual(decoding,['ffprobe','ffmpeg','ffmpeg'])
            self.assertTrue(any(value and not value.startswith('bytes=0-') for value in ranges),ranges)
            self.assertTrue(all(item['via_pi'] for item in payloads))
            self.assertTrue(all('private-user' not in item['url'] and 'private-password' not in item['url']
                                for item in payloads))
        finally:
            provider.shutdown();provider.server_close();thread.join(timeout=2)

    def test_provider_http_error_retains_pi_side_category_after_remote_decoder_failure(self):
        class Denied(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self): self.send_error(403)
        provider=ThreadingHTTPServer(('127.0.0.1',0),Denied)
        thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
        upstream=f'http://media.fixture:{provider.server_port}/series/user/password/1.mp4'
        try:
            with mock.patch.dict('os.environ',SKIP_ANALYSIS_PROVIDER_PATH='raspberry'), \
                 mock.patch.object(protocol,'CLIENT_IP','127.0.0.1'), \
                 mock.patch.object(protocol,'SERVER_IP','127.0.0.1'), \
                 mock.patch.object(audio,'public_address',return_value=(urllib.parse.urlsplit(upstream),('127.0.0.1',))):
                with self.assertRaisesRegex(ValueError,'^provider_http_403$'):
                    with audio.provider_proxy(upstream) as source:
                        audio.probe(source)
        finally:
            provider.shutdown();provider.server_close();thread.join(timeout=2)


class RelayGuardTests(unittest.TestCase):
    def test_parallel_seek_waits_for_the_provider_and_playback_closes_the_relay(self):
        entered=threading.Event();release=threading.Event();playback=threading.Event()
        requests=[];responses=[]
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self):
                requests.append(self.headers.get('Range'))
                self.send_response(206)
                self.send_header('Content-Length','65536')
                self.send_header('Content-Range','bytes 0-65535/131072')
                self.end_headers()
                entered.set()
                release.wait(timeout=3)
                try: self.wfile.write(b'a'*65536)
                except (BrokenPipeError,ConnectionResetError): pass
        provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        provider.daemon_threads=True
        thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
        upstream=f'http://media.fixture:{provider.server_port}/series/user/password/1.mp4'
        def request(source,start):
            try:
                value=urllib.request.Request(source,headers={'Range':f'bytes={start}-'})
                with urllib.request.urlopen(value,timeout=3) as response:
                    responses.append(response.read())
            except (urllib.error.URLError,OSError):
                responses.append(None)
            except Exception as error:
                # Early provider release intentionally truncates Content-Length.
                import http.client
                if not isinstance(error,http.client.IncompleteRead): raise
                responses.append(error.partial)
        try:
            with mock.patch.object(audio,'public_address',return_value=(urllib.parse.urlsplit(upstream),('127.0.0.1',))):
                with audio._provider_proxy_local(upstream,playback.is_set) as source:
                    first=threading.Thread(target=request,args=(source,0));first.start()
                    self.assertTrue(entered.wait(timeout=2))
                    second=threading.Thread(target=request,args=(source,65536));second.start()
                    time.sleep(.15)
                    self.assertEqual(requests,['bytes=0-'],'Seek must wait for the first provider connection')
                    playback.set()
                    second.join(timeout=1)
                    self.assertFalse(second.is_alive(),'Playback must cancel the waiting seek')
                    release.set()
                    first.join(timeout=2)
                    self.assertFalse(first.is_alive())
                    self.assertEqual(requests,['bytes=0-'])
                    self.assertEqual(responses,[None,b''])
                with self.assertRaises(urllib.error.URLError): urllib.request.urlopen(source,timeout=.5)
        finally:
            release.set()
            provider.shutdown();provider.server_close();thread.join(timeout=2)

    def test_only_fixed_peer_port_and_ephemeral_token_can_be_a_relay_input(self):
        valid='http://10.87.26.2:8791/'+'a'*32
        validate('probe',dict(url=valid,via_pi=True))
        self.assertEqual(audio.input_options(protocol.RelayInput(valid))[1],'http,tcp')
        self.assertEqual(audio.input_options(valid)[1],'file')
        invalid=[valid+'?source=elsewhere',valid+'/extra',valid.replace(':8791',':22'),
                 valid.replace('10.87.26.2','127.0.0.1'),valid.replace('http:','https:'),
                 valid.replace('10.87.26.2','user:password@10.87.26.2'),valid[:-1]]
        for url in invalid:
            with self.subTest(url=url),self.assertRaises(ValueError):
                validate('probe',dict(url=url,via_pi=True))
        for mode in ('true',1,None):
            with self.assertRaisesRegex(ValueError,'invalid_request'):
                validate('probe',dict(url=valid,via_pi=mode))

    def test_unsigned_private_source_is_not_an_allowed_provider(self):
        with mock.patch.object(audio,'run',side_effect=AssertionError('Decoder must not start')):
            with self.assertRaisesRegex(ValueError,'unsafe_source'):
                execute('probe',dict(url='http://10.87.26.2:8791/'+'a'*32),lambda:False)

    def test_wrong_peer_and_wrong_token_open_no_upstream_connection(self):
        url='https://media.fixture/series/user/password/1.mp4'
        with mock.patch.object(audio,'public_address',return_value=(urllib.parse.urlsplit(url),('1.1.1.1',))), \
             mock.patch.object(audio,'pinned_connection',side_effect=AssertionError('Provider must stay closed')) as connect:
            with audio._provider_proxy_local(url,lambda:False,peer='10.87.26.1') as source:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(source,timeout=2)
                self.assertEqual(error.exception.code,403);error.exception.close()
            with audio._provider_proxy_local(url,lambda:False,peer='127.0.0.1') as source:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(source+'wrong',timeout=2)
                self.assertEqual(error.exception.code,503);error.exception.close()
            connect.assert_not_called()

    def test_persistent_gateway_role_works_without_systemd_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'role.json'
            file.write_text(json.dumps(dict(protocol=1,url='http://10.87.26.1:8790',provider_path='raspberry')))
            with mock.patch.dict('os.environ',clear=True),mock.patch.object(remote,'role_path',return_value=file):
                self.assertTrue(remote.configured())
                self.assertEqual(remote.provider_path(),'raspberry')
                file.write_text(json.dumps(dict(protocol=1,url='http://10.87.26.1:8790',provider_path='unexpected')))
                with self.assertRaises(remote.RemoteDeferred): remote.provider_path()


if __name__=='__main__': unittest.main()
