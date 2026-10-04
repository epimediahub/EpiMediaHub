#!/usr/bin/env python3
"""Bounded compute daemon, reachable only through the dedicated WireGuard peer.

One active operation; no database and no persisted source URLs. The Raspberry
renews each operation's short lease while checking provider playback locally.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import signal
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from skip_remote_client import local_execution
from skip_remote_protocol import (CLIENT_IP, LEASE_SECONDS, MAX_BODY, PORT, PROTOCOL,
                                  SERVER_IP, TASK_SECONDS, number, versions, words)


def parse_window(value):
    import numpy as np
    from skip_detector_v3 import FpWindow
    if not isinstance(value, dict) or set(value) != {
            'fp', 'start_sec', 'item_sec', 'delay_sec', 'time_offset_sec',
            'episode_id', 'duration_sec', 'trusted'}:
        raise ValueError('invalid_request')
    words(value['fp'])
    number(value['start_sec'], 0, 86_400)
    number(value['item_sec'], .001, 1)
    number(value['delay_sec'], 0, 10)
    number(value['time_offset_sec'], -10, 10)
    if value['duration_sec'] is not None:
        number(value['duration_sec'], 5, 86_400)
    if (type(value['trusted']) is not bool or not isinstance(value['episode_id'], str)
            or len(value['episode_id']) > 128):
        raise ValueError('invalid_request')
    return FpWindow(**(value | {'fp': np.array(value['fp'], dtype=np.uint32)}))


def validate(operation, payload):
    from skip_detector_v3 import Config
    if not isinstance(payload, dict):
        raise ValueError('invalid_request')
    if operation in ('probe', 'fingerprint'):
        if not isinstance(payload.get('url'), str) or not 1 <= len(payload['url']) <= 8192:
            raise ValueError('invalid_request')
        if operation == 'fingerprint':
            number(payload.get('start_ms'), 0, 86_400_000)
            number(payload.get('length_ms'), 15_000, 720_000)
            if type(payload.get('require_complete')) is not bool:
                raise ValueError('invalid_request')
    elif operation in ('match', 'boundaries'):
        words(payload.get('reference')); words(payload.get('target'))
        number(payload.get('step_ms'), .001, 1000)
        if operation == 'boundaries':
            number(payload.get('offset'), 0, 86_400_000)
    elif operation == 'detect':
        if payload.get('kind') not in ('intro', 'outro') or payload.get('config') != dataclasses.asdict(Config()):
            raise ValueError('invalid_request')
        parse_window(payload.get('target'))
        if not isinstance(payload.get('partners'), list) or not 0 <= len(payload['partners']) <= 4:
            raise ValueError('invalid_request')
        for item in payload['partners']:
            parse_window(item)
    else:
        raise ValueError('invalid_request')


def execute(operation, payload, busy):
    # Explicit execution role also prevents accidental recursion in a combined
    # integration test or in an inherited client environment on the server.
    with local_execution():
        from skip_analysis import provider_proxy, probe, fingerprint, matching_offset
        if operation in ('probe', 'fingerprint'):
            with provider_proxy(payload['url'], busy) as source:
                if operation == 'probe':
                    duration, chapters = probe(source, busy)
                    return dict(duration_ms=duration, chapters=chapters)
                fp, step, coverage = fingerprint(source, payload['start_ms'], payload['length_ms'], busy,
                    require_complete=payload['require_complete'], with_coverage=True)
                return dict(words=fp, step_ms=step, coverage_ms=coverage)
        if operation == 'match':
            return matching_offset(payload['reference'], payload['target'], payload['step_ms'])
        if operation == 'boundaries':
            from skip_automation import matching_boundaries
            return matching_boundaries(payload['reference'], payload['target'], payload['step_ms'], payload['offset'])
        from skip_detector_v3 import Config, PairCache, detect
        return dataclasses.asdict(detect(parse_window(payload['target']),
            [parse_window(item) for item in payload['partners']], payload['kind'], Config(), PairCache()))


class Busy(Exception):
    pass


class Tasks:
    def __init__(self, executor=execute):
        self.executor, self.lock = executor, threading.Lock()
        self.active, self.items = None, {}
        self.stopping = threading.Event()

    def submit(self, operation, payload):
        validate(operation, payload)
        with self.lock:
            if self.active is not None:
                raise Busy()
            timestamp = time.monotonic()
            self.items = {key: item for key, item in self.items.items()
                          if timestamp - item['updated'] < 300}
            if len(self.items) >= 32:
                oldest = min(self.items, key=lambda key: self.items[key]['updated'])
                del self.items[oldest]
            identity = uuid.uuid4().hex
            item = dict(id=identity, state='running', started=timestamp, renewed=timestamp,
                        updated=timestamp, cancel=threading.Event(), operation=operation)
            self.items[identity] = item
            self.active = identity
        threading.Thread(target=self._run, args=(item, payload), daemon=True).start()
        return identity

    def _run(self, item, payload):
        def busy():
            return (self.stopping.is_set() or item['cancel'].is_set()
                    or time.monotonic() - item['renewed'] > LEASE_SECONDS
                    or time.monotonic() - item['started'] > TASK_SECONDS)
        try:
            if busy():
                raise ValueError('analysis_deferred')
            result = self.executor(item['operation'], payload, busy)
            if busy():
                raise ValueError('analysis_deferred')
            # Check serializability here; no credentials in error messages.
            json.dumps(result, allow_nan=False)
            output = dict(state='done', result=result)
        except ValueError as error:
            code = str(error)
            if not re.fullmatch(r'[a-z_]+(?:_[1-5][0-9]{2})?', code):
                code = 'analysis_failed'
            output = dict(state='failed', error=code)
        except Exception:
            output = dict(state='failed', error='analysis_failed')
        finally:
            payload.clear()
        with self.lock:
            item.update(output, updated=time.monotonic())
            self.active = None

    def get(self, identity, cancel=False):
        with self.lock:
            item = self.items.get(identity)
            if item is None:
                return None
            if cancel:
                item['cancel'].set()
            elif item['state'] == 'running':
                item['renewed'] = time.monotonic()
            return {key: item[key] for key in ('id', 'state', 'result', 'error') if key in item}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, *, peers=(CLIENT_IP,), tasks=None):
        self.peers = frozenset(peers)
        self.health_peers = self.peers | {'127.0.0.1', SERVER_IP}
        self.tasks = tasks or Tasks()
        self.component_versions = versions()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, code, **value):
        data = json.dumps(dict(protocol=PROTOCOL, **value), allow_nan=False, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health' and self.client_address[0] in self.server.health_peers:
            with self.server.tasks.lock:
                active = self.server.tasks.active is not None
                completed = sum(item['state'] == 'done' for item in self.server.tasks.items.values())
            self.reply(200, status='ok', versions=self.server.component_versions,
                       active=active, completed=completed)
            return
        self.task_status()

    def do_DELETE(self):
        self.task_status(cancel=True)

    def task_status(self, cancel=False):
        if self.client_address[0] not in self.server.peers:
            self.reply(403, error='forbidden'); return
        match = re.fullmatch(r'/v1/tasks/([a-f0-9]{32})', self.path)
        if not match:
            self.reply(404, error='not_found'); return
        item = self.server.tasks.get(match.group(1), cancel=cancel)
        if item is None:
            self.reply(404, error='not_found'); return
        self.reply(200, **item)

    def do_POST(self):
        if self.client_address[0] not in self.server.peers:
            self.reply(403, error='forbidden'); return
        if self.path != '/v1/tasks':
            self.reply(404, error='not_found'); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                self.reply(413, error='input_limit'); return
            value = json.loads(self.rfile.read(length))
            if (not isinstance(value, dict) or value.get('protocol') != PROTOCOL
                    or value.get('versions') != self.server.component_versions):
                self.reply(412, error='version_mismatch'); return
            identity = self.server.tasks.submit(value.get('operation'), value.get('payload'))
            self.reply(202, id=identity, state='running')
        except Busy:
            self.reply(409, error='busy')
        except (ValueError, KeyError, TypeError, OverflowError):
            self.reply(400, error='invalid_request')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default=SERVER_IP, choices=(SERVER_IP, '127.0.0.1'))
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--peer', default=CLIENT_IP, choices=(CLIENT_IP, '127.0.0.1'))
    args = parser.parse_args()
    server = Server((args.bind, args.port), peers=(args.peer,))
    def stop(*_):
        server.tasks.stopping.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.tasks.stopping.set()
        server.server_close()


if __name__ == '__main__':
    main()
