"""Real videos -> private RPC -> EpiScene, with different sound/encoding."""
import contextlib
import copy
import dataclasses
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
import skip_analysis as audio
import skip_remote_client as remote
import skip_visual as visual
from skip_remote_protocol import PROTOCOL, versions
from skip_remote_worker import validate
from test_skip_remote_analysis import RpcFixture
from test_skip_analysis_episcene import sequence


class VisualRpcTests(RpcFixture, unittest.TestCase):
    def setUp(self):
        self.start_server()

    def test_real_rpc_returns_identical_decision_and_reuses_bounded_visual_cache(self):
        target, refs = sequence(13), [sequence(i,20+i) for i in (10,11,12)]
        expected = visual.detect(target, refs, 'intro')
        self.assertEqual(remote.visual_detect(target,refs,'intro'),expected)
        before = remote.health()['episcene']['cache']['hits']
        self.assertEqual(remote.visual_detect(target,refs,'intro'),expected)
        after = remote.health()['episcene']['cache']
        self.assertGreaterEqual(after['hits'] - before,3)
        self.assertLessEqual(after['pairs'],after['capacity'])

    def test_worker_rejects_unbounded_windows_booleans_and_wrong_private_relay(self):
        base = dict(url='https://provider.example/video',via_pi=False,start_ms=0,length_ms=60000,step_ms=500)
        for patch in (dict(length_ms=60001),dict(step_ms=True),dict(start_ms=1.5),dict(via_pi=True)):
            with self.assertRaises(ValueError):
                validate('visual_fingerprint',base | patch)
        window=sequence(13).payload()
        for patch in (dict(frames=window['frames']*20),dict(step_ms=25),dict(trusted_ranges=[[-1,60000]])):
            with self.assertRaises(ValueError):
                validate('visual_detect',dict(policy=visual.POLICY,kind='intro',target=window | patch,partners=[]))

    def test_no_local_video_decoder_fallback_when_remote_role_is_missing(self):
        with mock.patch.object(remote,'configured',return_value=False),mock.patch.object(audio,'run') as decoder:
            with self.assertRaises(remote.RemoteDeferred):
                remote.visual_fingerprint(remote.RemoteSource('private',lambda:False),0,15000)
            decoder.assert_not_called()

    def test_private_provider_relay_is_used_for_visual_extraction(self):
        source=remote.RemoteSource('http://10.87.26.2:8791/'+'a'*32,lambda:False,True)
        frames=sequence(12).frames[:40]
        with (mock.patch.object(audio,'provider_proxy',side_effect=AssertionError('No direct provider')),
              mock.patch.object(visual,'extract',return_value=frames) as decoder):
            result=remote.visual_fingerprint(source,0,20000)
        self.assertEqual(result,frames)
        self.assertEqual(str(decoder.call_args.args[0]),source.url)

    def test_lease_cancellation_stops_visual_work(self):
        observed=[]
        def execute(operation,payload,busy):
            while not busy():
                time.sleep(.01)
            observed.append(operation)
            raise ValueError('analysis_deferred')
        self.server.tasks.executor=execute
        target,ref=sequence(13),sequence(12)
        polls=[0]
        def busy():
            polls[0]+=1
            return polls[0]>2
        with self.assertRaisesRegex(ValueError,'analysis_deferred'):
            remote.visual_detect(target,[ref],'intro',busy)
        deadline=time.monotonic()+2
        while not observed and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertEqual(observed,['visual_detect'])


@unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg unavailable')
class ActualVideoTests(RpcFixture,unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.start_server()

    def video(self,episode,prefix,brightness=0,quality=23,frequency=440):
        rng=np.random.default_rng(700+episode)
        common=np.random.default_rng(4817).integers(30,220,(48,8,12,3),dtype=np.uint8)
        before=rng.integers(30,220,(prefix*2,8,12,3),dtype=np.uint8)
        after=rng.integers(30,220,(16,8,12,3),dtype=np.uint8)
        small=np.concatenate([before,common,after])
        pixels=np.repeat(np.repeat(small,12,axis=1),12,axis=2)
        pixels=np.clip(pixels.astype(int)+brightness,0,255).astype(np.uint8)
        pixels[:,-12:,:,:]=0  # A changing subtitle/footer outside the central crop.
        pixels=np.repeat(pixels,4,axis=0)
        path=self.root/f'episode-{episode}.mp4'
        command=['ffmpeg','-nostdin','-v','error','-threads','2','-filter_threads','1',
            '-f','rawvideo','-pix_fmt','rgb24','-s','144x96','-r','8','-i','pipe:0',
        ]
        if frequency is not None:
            command+=['-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=11025','-shortest']
        command+=['-c:v','libx264','-preset','ultrafast','-crf',str(quality),'-pix_fmt','yuv420p']
        command+=['-c:a','aac'] if frequency is not None else ['-an']
        command+=['-movflags','+faststart',str(path)]
        result=subprocess.run(command,
            input=pixels.tobytes(),capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode()[:300])
        return path,(prefix+24+8)*1000

    def window(self,path,duration,episode,trusted=False,prefix=0):
        source=remote.RemoteSource('private-test-video',lambda:False)
        with mock.patch.object(audio,'provider_proxy',side_effect=lambda *_:contextlib.nullcontext(str(path))):
            frames=remote.visual_fingerprint(source,0,duration,500)
        return visual.VisualWindow(frames,0,500,duration,duration,str(episode),episode,
                                   [[prefix*1000,(prefix+24)*1000]] if trusted else [])

    def test_actual_video_different_sound_brightness_and_compression_preserve_intro_boundaries(self):
        reference,ref_duration=self.video(1,8,frequency=440)
        target,target_duration=self.video(2,13,brightness=10,quality=30,frequency=880)
        ref=self.window(reference,ref_duration,1,True,8)
        own=self.window(target,target_duration,2)
        result=remote.visual_detect(own,[ref],'intro')
        self.assertEqual(result['status'],'AUTO_CONFIRMED',result)
        self.assertEqual(result['start_ms'],13000)
        self.assertEqual(result['end_ms'],36750)
        self.assertGreaterEqual(result['confidence'],.955)

    def test_actual_video_without_audio_can_build_independent_episode_consensus(self):
        windows=[]
        for episode,prefix in ((1,6),(2,8),(3,10),(4,12)):
            path,duration=self.video(episode,prefix,quality=18+episode*3,frequency=None)
            windows.append(self.window(path,duration,episode))
        result=remote.visual_detect(windows[-1],windows[:-1],'intro')
        self.assertEqual(result['status'],'AUTO_CONFIRMED',result)
        self.assertEqual(result['support'],3)
        self.assertEqual(result['start_ms'],12000)
        self.assertLessEqual(35000,result['end_ms'])
        self.assertLess(result['end_ms'],36000)


if __name__=='__main__':unittest.main()
