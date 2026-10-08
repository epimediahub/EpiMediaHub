"""Small, non-fatal hooks for existing phase timers and fingerprint caches."""
from contextlib import contextmanager
from functools import wraps
import logging
import resource
import sqlite3
import sys
from pathlib import Path
import time


def install(db):
    import skip_automation as audio
    import skip_scene as visual
    import skip_markers as markers
    from skip_daily_reports import encode
    if getattr(audio.analysis_phase, '_episcene_report', False):
        audio.analysis_phase._report_db[0] = db
        return
    original = audio.analysis_phase
    source_db = [db]

    @contextmanager
    def phase(name):
        started, cpu = time.perf_counter(), time.process_time()
        asset_key = ''
        try:
            with source_db[0]() as con:
                row = con.execute("SELECT asset_key FROM skip_jobs WHERE status='running' ORDER BY id LIMIT 1").fetchone()
                asset_key = row[0] if row else ''
        except sqlite3.Error:
            logging.warning('EpiScene phase attribution unavailable')
        error = None
        try:
            with original(name):
                yield
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            payload = dict(phase=name,elapsed_seconds=round(time.perf_counter()-started,6),
                controller_cpu_seconds=round(time.process_time()-cpu,6),
                controller_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,error_type=error)
            try:
                with source_db[0]() as con:
                    con.execute("INSERT INTO episcene_report_events(at,kind,asset_key,payload) VALUES(?,'phase',?,?)",
                        (time.time(),asset_key,encode(payload)))
            except sqlite3.Error:
                logging.warning('EpiScene phase telemetry could not be saved')
    phase._episcene_report = True
    phase._report_db = source_db
    audio.analysis_phase = phase

    def cache_hook(original, label):
        @wraps(original)
        def cached(con, asset, *args, **kwargs):
            result = original(con, asset, *args, **kwargs)
            try:
                con.execute("INSERT INTO episcene_report_events(at,kind,asset_key,payload) VALUES(?,'cache',?,?)",
                    (time.time(),asset['asset_key'],encode(dict(cache=label,hit=result is not None))))
            except sqlite3.Error:
                logging.warning('EpiScene cache telemetry could not be saved')
            return result
        return cached
    audio.cached_window = cache_hook(audio.cached_window,'audio')
    visual._cache = cache_hook(visual._cache,'visual')
    original_review = markers.review_record
    @wraps(original_review)
    def review(con, row, decision, start, end, disabled, *args, **kwargs):
        result = original_review(con,row,decision,start,end,disabled,*args,**kwargs)
        # Device/manual markers may have no skip_auto_evidence row. Record the
        # explicit review action instead of inferring an actor from confidence.
        con.execute("INSERT INTO episcene_report_events(at,kind,asset_key,record_id,payload) VALUES(?,'review',?,?,?)",
            (time.time(),row['asset_key'],row['id'],encode(dict(human_review=1,review_decision=decision))))
        return result
    markers.review_record = review
    # The CLI defines process_one in __main__; imports use the named module.
    # Instrument both so idle/budget/priority waits are visible even with no jobs.
    import skip_analysis_worker as worker
    modules = [worker]
    main = sys.modules.get('__main__')
    if main is not worker and Path(getattr(main,'__file__','')).name=='skip_analysis_worker.py':
        modules.append(main)
    def worker_hook(original):
        @wraps(original)
        def process(db, *args, **kwargs):
            started = time.perf_counter()
            result = original(db,*args,**kwargs)
            try:
                with db() as con:
                    con.execute("INSERT INTO episcene_report_events(at,kind,payload) VALUES(?,'worker',?)",
                        (time.time(),encode(dict(status=result,elapsed_seconds=round(time.perf_counter()-started,6)))))
            except sqlite3.Error:
                logging.warning('EpiScene worker status could not be saved')
            return result
        return process
    for module in modules:
        module.process_one = worker_hook(module.process_one)

