#!/usr/bin/env python3
"""Isolated regression for EpiScene one-step installer safety and rollback."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install_playlist_only as installer

class FakePatcher:
    def __init__(self,original):
        self.BASELINE={'skip_schedule.py':hashlib.sha256(original).hexdigest()}
    def patch_known_files(self,root,verify_sha=True):
        if verify_sha:
            assert hashlib.sha256((root/'skip_schedule.py').read_bytes()).hexdigest()==self.BASELINE['skip_schedule.py']
        return {'skip_schedule.py':b'def scheduler():\n    return 2\n'}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.app=self.root/'provisioning';self.app.mkdir()
        self.data=self.root/'state';self.data.mkdir()
        self.db=self.data/'provisioning.db'
        self.learning=self.root/'learning';self.learning.mkdir()
        self.peer=self.learning/'safe_release_rollout_v2.py'
        self.old_peer=b'def requeue():\n    return 1\n'
        self.new_peer=b'def requeue():\n    return 2\n'
        self.peer.write_bytes(self.old_peer)
        self.original=b'def scheduler():\n    return 0\n'
        (self.app/'skip_schedule.py').write_bytes(self.original)
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE skip_presence(playlist_id INTEGER,expires_at INTEGER)')
            db.execute('CREATE TABLE skip_jobs(status TEXT)')
        (self.data/'skip-analysis.lock').write_bytes(b'')
        self.state={}
        self.state.update({unit:True for unit in (installer.ANALYSIS_TIMER,installer.WEB,
                           installer.COMPUTE,'episcene-visual-peer-reload.timer')})
        self.state[installer.ANALYSIS]=False
        self.state[installer.SHADOW]=False
        self.state[installer.OTHER_TIMERS[0]]=True
        self.state[installer.OTHER_TIMERS[1]]=False
        self.state[installer.OTHER_TIMERS[2]]=True
        self.events=[]
        def act(unit):return self.state.get(unit,False)
        def run(*args,**kwargs):
            unit=args[-1]
            if args[0]=='curl':
                Path(unit).write_bytes(self.new_peer)
                return ''
            self.events.append((args[1],unit))
            if args[1]=='stop':self.state[unit]=False
            elif args[1] in ('start','restart'):self.state[unit]=True
            return ''
        patches=[
            mock.patch.object(installer,'APP',self.app),
            mock.patch.object(installer,'LEARNING',self.learning),
            mock.patch.object(installer,'LEARN_FILE',self.peer),
            mock.patch.object(installer,'OLD_LEARN_SHA',hashlib.sha256(self.old_peer).hexdigest()),
            mock.patch.object(installer,'DATA',self.data),
            mock.patch.object(installer,'DB',self.db),
            mock.patch.object(installer,'WORKER_LOCK',self.data/'skip-analysis.lock'),
            mock.patch.object(installer,'INSTALL_LOCK',self.data/'installer.lock'),
            mock.patch.object(installer,'PENDING',self.data/'pending'),
            mock.patch.object(installer,'BACKUPS',self.data/'backups'),
            mock.patch.object(installer,'active',side_effect=act),
            mock.patch.object(installer,'command',side_effect=run),
            mock.patch.object(installer,'download_patcher',return_value=FakePatcher(self.original)),
            mock.patch.object(installer.os,'geteuid',return_value=0),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_check_only_never_touches_live_sources_or_timers(self):
        installer.install(dry_run=True)
        self.assertEqual((self.app/'skip_schedule.py').read_bytes(),self.original)
        self.assertEqual(self.peer.read_bytes(),self.old_peer)
        self.assertEqual(self.events,[])
        self.assertFalse((self.data/'backups').exists())

    def test_mixed_4k_apply_is_blocked_before_any_change(self):
        with self.assertRaisesRegex(RuntimeError,'German-only dispatch gate'):
            installer.install(dry_run=False)
        self.assertEqual((self.app/'skip_schedule.py').read_bytes(),self.original)
        self.assertEqual(self.peer.read_bytes(),self.old_peer)
        self.assertEqual(self.events,[])
        self.assertFalse((self.data/'backups').exists())
        self.assertTrue(self.state[installer.ANALYSIS_TIMER])


if __name__=='__main__':
    unittest.main()
