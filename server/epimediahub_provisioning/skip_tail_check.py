"""Approve a short trailing gap only after complete black/silent decoding.

A strong sequence consensus remains mandatory. Scene content, logos, sound,
unknown duration and larger post-credit gaps all keep a marker in review.
"""
import copy
from functools import wraps
import math
import numpy as np

POLICY = 'black_silent_tail_v1'
OPERATION = 'episcene_tail_check'


def strong(value, kind, target):
    matches = value.get('matches', [])
    trusted = any(m.get('trusted_range') for m in matches)
    return bool(matches and not value.get('ambiguous') and value.get('boundaries_confirmed')
                and value.get('boundary_spread_ms', 99999) <= 1000
                and (trusted or value.get('support',0)>=3)
                and all(m.get('boundaries_confirmed') and m.get('quality',0)>=.955
                        and m.get('ratio',0)>=.94 and (trusted or m.get('structural_diversity')) for m in matches)
                and kind=='outro' and value.get('start_ms',0)>=target.duration_ms*.65)


def valid_proof(proof, target, decision):
    return bool(isinstance(proof,dict) and proof.get('policy')==POLICY and proof.get('empty') is True
                and proof.get('asset_key')==target.episode_id and proof.get('duration_ms')==target.duration_ms
                and proof.get('start_ms')==decision.get('end_ms') and proof.get('end_ms')==target.duration_ms
                and type(proof.get('video_max')) in (int,float) and 0<=proof['video_max']<=6
                and type(proof.get('audio_peak')) in (int,float) and 0<=proof['audio_peak']<=.00056
                and type(proof.get('video_samples')) is int and proof['video_samples']>=math.floor((proof['end_ms']-proof['start_ms'])/100)
                and type(proof.get('audio_samples')) is int and proof['audio_samples']>=math.floor((proof['end_ms']-proof['start_ms']-50)*16)
                and isinstance(proof.get('source_version'),str) and len(proof['source_version'])==64
                and 1000<target.duration_ms-decision.get('end_ms',0)<=5000)


def install_visual(visual):
    if getattr(visual, '_tail_check',False):
        return
    visual._tail_check=True
    original=visual.validate_result
    @wraps(original)
    def validate(value,target,partners,kind):
        if not isinstance(value,dict) or 'tail_check' not in value:
            return original(value,target,partners,kind)
        base={k:v for k,v in value.items() if k!='tail_check'}
        if value.get('status')!='AUTO_CONFIRMED' or not strong(value,kind,target) or not valid_proof(value['tail_check'],target,value):
            raise ValueError('invalid_visual_result')
        # Existing validation rechecks all partners, distinct episode numbers,
        # trusted ranges and score/boundary calculations. Only the original
        # one-second tail condition is replaced by the measured empty tail.
        original(dict(base,status='REVIEW'),target,partners,kind)
        return value
    visual.validate_result=validate


def measure(source,start_ms,end_ms,busy):
    from skip_analysis import run,input_options
    if type(start_ms) is not int or type(end_ms) is not int or not 0<=start_ms<end_ms<=86400000 or not 1000<end_ms-start_ms<=5000:
        raise ValueError('invalid_request')
    seconds=(end_ms-start_ms)/1000
    args=['ffmpeg','-nostdin','-v','error','-threads','2',*input_options(source),'-ss',str(start_ms/1000),'-i',source,'-t',str(seconds)]
    count=math.ceil(seconds*10)+2
    raw=run([*args,'-map','0:v:0','-an','-sn','-dn','-vf','fps=10:round=near,scale=32:32:flags=area,format=gray',
             '-frames:v',str(count),'-f','rawvideo','-pix_fmt','gray','pipe:1'],max_bytes=count*1024,timeout=30,busy=busy)
    audio=run([*args,'-map','0:a:0','-vn','-sn','-dn','-ac','1','-ar','16000','-f','f32le','pipe:1'],
              max_bytes=math.ceil(seconds*16000+1600)*4,timeout=30,busy=busy)
    if not raw or len(raw)%1024 or len(raw)//1024<math.floor(seconds*10) or not audio or len(audio)%4:
        raise ValueError('tail_incomplete')
    samples=np.frombuffer(audio,dtype='<f4')
    if len(samples)<math.floor((seconds-.05)*16000) or not np.isfinite(samples).all():
        raise ValueError('tail_incomplete')
    maximum=int(np.frombuffer(raw,dtype=np.uint8).max())
    peak=float(np.abs(samples).max())
    return dict(policy=POLICY,empty=maximum<=6 and peak<=.00056,start_ms=start_ms,end_ms=end_ms,
                video_max=maximum,audio_peak=peak,video_samples=len(raw)//1024,audio_samples=len(samples))


def install_compute(worker):
    if getattr(worker,'_tail_check',False):
        return
    worker._tail_check=True
    from skip_remote_protocol import number,relay_url,RelayInput
    original_validate,original_execute=worker.validate,worker.execute
    @wraps(original_validate)
    def validate(operation,payload):
        if operation!=OPERATION:
            return original_validate(operation,payload)
        if (not isinstance(payload,dict) or set(payload)!={'url','via_pi','start_ms','end_ms'}
                or not isinstance(payload['url'],str) or not 1<=len(payload['url'])<=8192
                or type(payload['via_pi']) is not bool or payload['via_pi'] and not relay_url(payload['url'])
                or type(payload['start_ms']) is not int or type(payload['end_ms']) is not int):
            raise ValueError('invalid_request')
        number(payload['start_ms'],0,86400000)
        number(payload['end_ms']-payload['start_ms'],1001,5000)
    @wraps(original_execute)
    def execute(operation,payload,busy):
        if operation!=OPERATION:
            return original_execute(operation,payload,busy)
        from contextlib import nullcontext
        from skip_remote_client import local_execution
        from skip_analysis import provider_proxy
        with local_execution():
            source_context=(nullcontext(RelayInput(payload['url'])) if payload['via_pi'] else provider_proxy(payload['url'],busy))
            with source_context as source:
                return measure(source,payload['start_ms'],payload['end_ms'],busy)
    worker.validate,worker.execute=validate,execute
    # Tasks captures execute as a default argument at class definition time.
    # Update that binding as well as the module attribute before daemon start.
    if worker.Tasks.__init__.__defaults__ == (original_execute,):
        worker.Tasks.__init__.__defaults__ = (execute,)
    import skip_visual
    install_visual(skip_visual)


def confirm_tail(db,asset,value,target,partners,kind,busy):
    if value.get('status')!='REVIEW' or not strong(value,kind,target) or not 1000<target.duration_ms-value['end_ms']<=5000:
        return value
    from skip_scene_reliability import reserve,asset_version,event,error_code,CONTEXT,analysis_playlist
    from skip_analysis import provider_proxy,source_url
    from skip_remote_client import call,_busy
    with db() as con:
        playlist=analysis_playlist(con,asset['playlist_id'])
    try:
        reserve(65,'Abspannrest prüfen')
        with provider_proxy(source_url(playlist,asset),busy) as source:
            proof=call(OPERATION,dict(url=source.url,via_pi=source.via_pi,start_ms=value['end_ms'],end_ms=target.duration_ms),_busy(source,busy))
        proof=dict(proof,asset_key=target.episode_id,duration_ms=target.duration_ms,source_version=asset_version(asset))
        if proof.get('empty') is False:
            # Validate complete measurement shape before caching a real
            # content-bearing tail. Failed/incomplete measurements stay open.
            hypothetical=dict(value,status='AUTO_CONFIRMED',tail_check=dict(proof,empty=True,video_max=0,audio_peak=0))
            if not valid_proof(hypothetical['tail_check'],target,hypothetical):
                raise ValueError('tail_incomplete')
            if CONTEXT.get() is not None:
                CONTEXT.get()['tail_outcome']='not_empty'
            with db() as con:
                event(con,'tail_check',asset['asset_key'],empty=False,reason='tail_contains_content')
            return value
        decision=dict(copy.deepcopy(value),status='AUTO_CONFIRMED',tail_check=proof)
        import skip_visual
        skip_visual.validate_result(decision,target,partners,kind)
        if CONTEXT.get() is not None:
            CONTEXT.get()['tail_outcome']='empty'
        with db() as con:
            event(con,'tail_check',asset['asset_key'],empty=True,length_ms=target.duration_ms-value['end_ms'])
        return decision
    except ValueError as error:
        # Optional approval evidence may wait without discarding the complete
        # underlying candidate. A playback pause still propagates normally.
        if busy():
            raise
        with db() as con:
            event(con,'tail_check',asset['asset_key'],empty=False,reason=error_code(error))
        return value
