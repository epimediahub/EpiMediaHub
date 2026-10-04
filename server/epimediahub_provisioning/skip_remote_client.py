"""Pi-side cancellable computation client over the dedicated WireGuard link.

An optional private provider relay performs no local decoding or comparisons.
Every operation requires the exact same analysis source on both machines.
"""
from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from skip_remote_protocol import (MAX_BODY, PORT, PROTOCOL, SERVER_IP, TASK_SECONDS,
                                  number, versions, window_payload, words)

_local = contextvars.ContextVar('skip_local_execution', default=False)


class RemoteDeferred(ValueError):
    def __init__(self, reason='Analyse auf Hetzner derzeit nicht erreichbar; Auftrag bleibt in der Warteschlange'):
        super().__init__('analysis_deferred')
        self.reason = reason


@contextlib.contextmanager
def local_execution():
    token = _local.set(True)
    try:
        yield
    finally:
        _local.reset(token)


def configured():
    return not _local.get() and (bool(os.environ.get('SKIP_ANALYSIS_REMOTE_URL')) or role_path().exists())


def role_path():
    return Path(__file__).with_name('skip_remote_role.json')


def read_role():
    try:
        text = role_path().read_text()
        if len(text) > 2048:
            raise ValueError()
        role = json.loads(text)
        if role.get('protocol') != PROTOCOL or not isinstance(role.get('url'), str):
            raise ValueError()
        if role.get('provider_path', 'direct') not in ('direct', 'raspberry'):
            raise ValueError()
        return role
    except (OSError, ValueError, AttributeError):
        raise RemoteDeferred('Dauerhafte Hetzner-Konfiguration ist nicht lesbar; lokale Audioanalyse bleibt ausgeschaltet') from None


def endpoint_value():
    return os.environ.get('SKIP_ANALYSIS_REMOTE_URL') or read_role()['url']


def provider_path():
    value = os.environ.get('SKIP_ANALYSIS_PROVIDER_PATH')
    if value is None:
        value = read_role().get('provider_path', 'direct') if role_path().exists() else 'direct'
    if value not in ('direct', 'raspberry'):
        raise RemoteDeferred('Privater Anbieterabruf ist nicht korrekt eingerichtet')
    return value


@dataclasses.dataclass(repr=False)
class RemoteSource:
    url: str
    busy: object
    via_pi: bool = False

    def __repr__(self):
        return '<private remote audio source>'


def endpoint():
    try:
        uri = urllib.parse.urlsplit(endpoint_value())
        valid = (uri.scheme == 'http' and uri.hostname in (SERVER_IP, '127.0.0.1', '::1')
                 and not uri.username and not uri.password and not uri.query and not uri.fragment
                 and uri.path in ('', '/') and uri.port and 1 <= uri.port <= 65535)
    except ValueError:
        valid = False
    if not valid:
        raise RemoteDeferred('Private Hetzner-Verbindung ist nicht korrekt eingerichtet')
    return urllib.parse.urlunsplit((uri.scheme, uri.netloc, '', '', ''))


def request(path, payload=None, *, method=None, timeout=4):
    raw = None if payload is None else json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
    if raw is not None and len(raw) > MAX_BODY:
        raise RemoteDeferred('Audio-Fingerprints überschreiten das Übertragungslimit')
    req = urllib.request.Request(endpoint() + path, data=raw,
        headers={'Content-Type': 'application/json'}, method=method)
    try:
        # The private link must never be routed through an environment HTTP proxy.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
            body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise RemoteDeferred()
        value = json.loads(body)
        if not isinstance(value, dict) or value.get('protocol') != PROTOCOL:
            raise RemoteDeferred('Hetzner-Worker verwendet eine andere Protokollversion')
        return value
    except RemoteDeferred:
        raise
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        if code == 409:
            raise RemoteDeferred('Hetzner führt noch einen Auftrag aus; erneuter Versuch im nächsten Lauf') from None
        if code == 412:
            raise RemoteDeferred('Analysecode auf Raspberry und Hetzner stimmt nicht überein; Update prüfen') from None
        raise RemoteDeferred() from None
    except (OSError, ValueError, urllib.error.URLError):
        raise RemoteDeferred() from None


def health():
    value = request('/health')
    if value.get('versions') != versions() or value.get('status') != 'ok':
        raise RemoteDeferred('Analysecode auf Raspberry und Hetzner stimmt nicht überein; Update prüfen')
    return value


def call(operation, payload, busy=lambda: False):
    if busy():
        raise ValueError('analysis_deferred')
    task = None
    completed = False
    started = time.monotonic()
    try:
        submitted = request('/v1/tasks', dict(protocol=PROTOCOL, versions=versions(),
                                             operation=operation, payload=payload))
        task = submitted.get('id')
        if not isinstance(task, str) or not re.fullmatch(r'[a-f0-9]{32}', task):
            raise RemoteDeferred()
        while True:
            if busy():
                raise ValueError('analysis_deferred')
            if time.monotonic() - started >= TASK_SECONDS:
                raise RemoteDeferred('Zeitlimit der ausgelagerten Analyse erreicht; Auftrag wird erneut versucht')
            value = request('/v1/tasks/' + task)
            state = value.get('state')
            if state == 'done':
                completed = True
                return value.get('result')
            if state == 'failed':
                completed = True
                code = value.get('error')
                if code == 'analysis_deferred':
                    raise RemoteDeferred('Hetzner-Auftrag wurde unterbrochen; erneuter Versuch im nächsten Lauf')
                if not isinstance(code, str) or not re.fullmatch(r'[a-z_]+(?:_[1-5][0-9]{2})?', code):
                    raise RemoteDeferred()
                raise ValueError(code)
            if state != 'running':
                raise RemoteDeferred()
            time.sleep(.4)
    finally:
        if task is not None and not completed:
            try:
                request('/v1/tasks/' + task, method='DELETE', timeout=2)
            except RemoteDeferred:
                pass


def _busy(source, busy):
    if not isinstance(source, RemoteSource):
        raise RemoteDeferred('Lokale Audioanalyse ist abgeschaltet; private Hetzner-Quelle fehlt')
    return lambda: source.busy() or busy()


def probe(source, busy):
    check = _busy(source, busy)
    value = call('probe', {'url': source.url, 'via_pi': source.via_pi}, check)
    try:
        duration = number(value['duration_ms'], 5000, 86_400_000)
        chapters = value['chapters']
        if type(duration) is not int or not isinstance(chapters, list) or len(chapters) > 500:
            raise ValueError()
        return duration, chapters
    except (KeyError, TypeError, ValueError):
        raise RemoteDeferred('Hetzner hat ungültige Laufzeitdaten geliefert') from None


def fingerprint(source, start_ms, length_ms, busy, *, require_complete=False, with_coverage=False):
    check = _busy(source, busy)
    value = call('fingerprint', dict(url=source.url, start_ms=start_ms, length_ms=length_ms,
                                   require_complete=require_complete, via_pi=source.via_pi), check)
    try:
        result = words(value['words']), number(value['step_ms'], .001, 1000)
        coverage = number(value['coverage_ms'], 0, length_ms + 250)
        if require_complete and coverage < length_ms - 250:
            raise ValueError()
        return (*result, coverage) if with_coverage else result
    except (KeyError, TypeError, ValueError):
        raise RemoteDeferred('Hetzner hat unvollständige Audio-Fingerprints geliefert') from None


def match(reference, target, step_ms):
    value = call('match', dict(reference=[int(w) & 0xffffffff for w in reference],
                             target=[int(w) & 0xffffffff for w in target], step_ms=step_ms))
    if value is None:
        return None
    try:
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError()
        return number(value[0], 0, len(target) * step_ms), number(value[1], 0, 1)
    except (ValueError, TypeError):
        raise RemoteDeferred('Hetzner hat einen ungültigen Audiovergleich geliefert') from None


def boundaries(reference, target, step_ms, offset):
    value = call('boundaries', dict(reference=[int(w) & 0xffffffff for w in reference],
                                  target=[int(w) & 0xffffffff for w in target],
                                  step_ms=step_ms, offset=offset))
    if type(value) is not bool:
        raise RemoteDeferred('Hetzner hat ungültige Abschnittsgrenzen geliefert')
    return value


def detect(target, partners, kind, config, busy=lambda: False):
    from skip_detector_v3 import AUTO, REVIEW, REJECTED, Detection
    value = call('detect', dict(target=window_payload(target), partners=[window_payload(p) for p in partners],
                                kind=kind, config=dataclasses.asdict(config)), busy)
    try:
        result = Detection(**value)
        if result.kind != kind or result.status not in (AUTO, REVIEW, REJECTED):
            raise ValueError()
        number(result.confidence, 0, 1)
        if (type(result.partners_used) is not int or not 0 <= result.partners_used <= 4
                or type(result.partners_supporting) is not int
                or not 0 <= result.partners_supporting <= result.partners_used
                or not isinstance(result.details, dict)):
            raise ValueError()
        for point in (result.start_sec, result.end_sec):
            if point is not None:
                number(point, 0, target.duration_sec or 86_400)
        if result.found and (result.end_sec is None or result.end_sec <= result.start_sec):
            raise ValueError()
        return result
    except (TypeError, ValueError, KeyError):
        raise RemoteDeferred('Hetzner hat ungültige Detektor-Daten geliefert') from None
