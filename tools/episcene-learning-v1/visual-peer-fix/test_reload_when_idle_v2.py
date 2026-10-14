#!/usr/bin/env python3
"""Regression tests for draining a continuous analyzer without killing jobs."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import reload_when_idle_v2 as reload


def db_file(path, *, leases=0, running=0):
    con=sqlite3.connect(path)
    con.execute('CREATE TABLE skip_presence(expires_at INTEGER)')
    con.execute('CREATE TABLE skip_jobs(status TEXT)')
    if leases:
        con.execute('INSERT INTO skip_presence VALUES(4102444800)')
    for _ in range(running):
        con.execute("INSERT INTO skip_jobs VALUES('running')")
    con.commit()
    con.close()


class FakeSystemctl:
    def __init__(self):
        self.states={
            reload.ANALYSIS_TIMER:True,
            reload.ANALYSIS:True,
            reload.COMPUTE:True,
            reload.WEB:True,
            reload.SHADOW:False,
        }
        self.actions=[]
        self.fail=None

    def __call__(self,*args,timeout=30,check=False):
        self.actions.append(args)
        unit=args[-1]
        if args[:3]==('systemctl','is-active','--quiet'):
            return SimpleNamespace(returncode=0 if self.states[unit] else 3,stdout='')
        if args[:3]==('systemctl','show',unit):
            return SimpleNamespace(returncode=0,stdout='active\n' if self.states[unit] else 'inactive\n')
        if args[:2]==('systemctl','stop'):
            if self.fail==('stop',unit):
                raise RuntimeError('simulated_stop_error')
            self.states[unit]=False
            return SimpleNamespace(returncode=0,stdout='')
        if args[:2]==('systemctl','start'):
            if self.fail==('start',unit):
                raise RuntimeError('simulated_start_error')
            self.states[unit]=True
            return SimpleNamespace(returncode=0,stdout='')
        if args[:2]==('systemctl','restart'):
            if self.fail==('restart',unit):
                raise RuntimeError('simulated_restart_error')
            self.states[unit]=True
            return SimpleNamespace(returncode=0,stdout='')
        raise AssertionError(args)

    def action(self,verb,unit):
        return ('systemctl',verb,unit) in self.actions


class DrainTests(unittest.TestCase):
    def exercise(self, leases=0, running=0):
        temp=tempfile.TemporaryDirectory()
        root=Path(temp.name)
        path=root/'provisioning.db'
        db_file(path,leases=leases,running=running)
        patchers=[
            patch.object(reload,'DATA',root),
            patch.object(reload,'DB',path),
            patch.object(reload,'PENDING',root/'episcene-visual-peer-reload-pending'),
            patch.object(reload,'PAUSED',root/'episcene-visual-peer-analysis-timer-paused'),
            patch.object(reload,'MUTEX',root/'.episcene-visual-peer-reload.lock'),
            patch.object(reload,'WORKER_LOCK',root/'skip-analysis.lock')
        ]
        for p in patchers:p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(patchers)])
        self.addCleanup(temp.cleanup)
        reload.PENDING.write_text('')
        reload.WORKER_LOCK.write_bytes(b'')
        fake=FakeSystemctl()
        context=patch.object(reload,'call',side_effect=fake)
        context.start()
        self.addCleanup(context.stop)
        return root,fake

    def test_pause_new_jobs_then_reload_only_after_active_batch_exits(self):
        root,ctl=self.exercise(running=3)
        with patch('builtins.print'):
            reload.finish()
        self.assertTrue(reload.PAUSED.exists())
        self.assertTrue(reload.PENDING.exists())
        self.assertFalse(ctl.states[reload.ANALYSIS_TIMER])
        self.assertFalse(ctl.action('restart',reload.COMPUTE))
        ctl.states[reload.ANALYSIS]=False
        with patch('builtins.print'):
            reload.finish()
        self.assertFalse(reload.PAUSED.exists())
        self.assertFalse(reload.PENDING.exists())
        self.assertTrue(ctl.states[reload.ANALYSIS_TIMER])
        self.assertTrue(ctl.action('restart',reload.COMPUTE))
        self.assertTrue(ctl.action('restart',reload.WEB))
        # A stale SQLite running row must not block a restart forever.
        with sqlite3.connect(reload.DB) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='running'").fetchone()[0],3)

    def test_new_playback_restores_timer_after_it_was_paused(self):
        _,ctl=self.exercise()
        with patch('builtins.print'):
            reload.finish()
        self.assertTrue(reload.PAUSED.exists())
        with sqlite3.connect(reload.DB) as db:
            db.execute('INSERT INTO skip_presence VALUES(4102444800)')
        with patch('builtins.print'):
            reload.finish()
        self.assertFalse(reload.PAUSED.exists())
        self.assertTrue(ctl.states[reload.ANALYSIS_TIMER])
        self.assertTrue(reload.PENDING.exists())

    def test_missing_worker_lock_fails_closed_without_root_owned_creation(self):
        _,ctl=self.exercise()
        ctl.states[reload.ANALYSIS]=False
        reload.WORKER_LOCK.unlink()
        with patch('builtins.print'):
            reload.finish()
        self.assertTrue(reload.PENDING.exists())
        self.assertFalse(reload.WORKER_LOCK.exists())
        self.assertFalse(ctl.action('restart',reload.COMPUTE))

    def test_playback_does_not_pause_analyzer_or_restart_anything(self):
        _,ctl=self.exercise(leases=1)
        with patch('builtins.print'):
            reload.finish()
        self.assertTrue(ctl.states[reload.ANALYSIS_TIMER])
        self.assertFalse(reload.PAUSED.exists())
        self.assertTrue(reload.PENDING.exists())
        self.assertFalse(ctl.action('restart',reload.COMPUTE))

    def test_capture_in_progress_waits_for_safe_window(self):
        _,ctl=self.exercise()
        ctl.states[reload.ANALYSIS]=False
        ctl.states[reload.SHADOW]=True
        with patch('builtins.print'):
            reload.finish()
        self.assertTrue(reload.PENDING.exists())
        self.assertFalse(ctl.action('restart',reload.COMPUTE))
        ctl.states[reload.SHADOW]=False
        with patch('builtins.print'):
            reload.finish()
        self.assertFalse(reload.PENDING.exists())

    def test_restart_failure_keeps_flag_and_timer_paused(self):
        _,ctl=self.exercise()
        ctl.states[reload.ANALYSIS]=False
        ctl.fail=('restart',reload.COMPUTE)
        with patch('builtins.print'),self.assertRaisesRegex(RuntimeError,'simulated_restart_error'):
            reload.finish()
        self.assertTrue(reload.PENDING.exists())
        self.assertTrue(reload.PAUSED.exists())
        self.assertFalse(ctl.states[reload.ANALYSIS_TIMER])
        ctl.fail=None
        with patch('builtins.print'):
            reload.finish()
        self.assertFalse(reload.PENDING.exists())
        self.assertTrue(ctl.states[reload.ANALYSIS_TIMER])

    def test_preexisting_inactive_timer_stays_inactive(self):
        _,ctl=self.exercise()
        ctl.states[reload.ANALYSIS]=False
        ctl.states[reload.ANALYSIS_TIMER]=False
        with patch('builtins.print'):
            reload.finish()
        self.assertFalse(ctl.states[reload.ANALYSIS_TIMER])
        self.assertFalse(reload.PAUSED.exists())
        self.assertFalse(reload.PENDING.exists())


if __name__=='__main__':
    unittest.main(verbosity=2)
