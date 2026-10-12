"""Transfer a confirmed marker only after independent episode/edit validation.

Repeated intros never prove episode identity. Three widely separated story
anchors and both marker boundaries must support one affine time mapping.
"""
import copy
import json
import math
import time
import unicodedata
import numpy as np

POLICY='verified_language_variant_v1'
STEP=500


def title_key(title):
    from skip_automation import clean_title
    title=clean_title(title)
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in unicodedata.normalize('NFKC',title).casefold()).split())


def identity(con,asset):
    asset=dict(asset)
    external=con.execute('SELECT imdb_id,tmdb_id FROM skip_auto_identities WHERE source_key=?',(asset['source_key'],)).fetchone()
    if external and external['imdb_id']:
        return ('imdb',external['imdb_id'],asset['season'],asset['episode'])
    if external and external['tmdb_id']:
        return ('tmdb',external['tmdb_id'],asset['season'],asset['episode'])
    return ('candidate_title_year',title_key(asset['title']),str(asset['year']),asset['season'],asset['episode'])


def same_candidate(con,source,target):
    if source['season']!=target['season'] or source['episode']!=target['episode']:
        return False
    left,right=identity(con,source),identity(con,target)
    if left[0]==right[0] and left[0]!='candidate_title_year':
        return left==right
    # An explicit conflicting external ID cannot be rescued by a title.
    if left[0]!='candidate_title_year' and right[0]!='candidate_title_year':
        return False
    return bool(title_key(source['title']) and title_key(source['title'])==title_key(target['title'])
                and source['year'] and target['year'] and str(source['year'])==str(target['year']))


def match_anchor(source,target,source_start,target_start,scale_hint=1.):
    """Return a unique changing sequence and its measured target position."""
    s,t=np.asarray(source,dtype=np.uint64),np.asarray(target,dtype=np.uint64)
    if len(s)<10 or len(t)<len(s) or s.ndim!=2 or t.ndim!=2:
        raise ValueError('variant_anchor_missing')
    from skip_visual import _diverse,_distinct_structure
    if not _diverse(s) or not _distinct_structure(s):
        raise ValueError('variant_anchor_uninformative')
    hits=[]
    scales=sorted({1.,round(scale_hint,5),.96,.98,1.02,1.04})
    for scale in scales:
        indices=np.rint(np.arange(len(s))*scale).astype(int)
        for start in range(max(0,len(t)-int(indices[-1]))):
            segment=t[start+indices]
            informative=(s[:,2]>=10)&(segment[:,2]>=10)&(s[:,3]>=8)&(s[:,3]<=247)&(segment[:,3]>=8)&(segment[:,3]<=247)
            distances=np.array([(int(a)^int(b)).bit_count()+(int(c)^int(d)).bit_count()
                                for a,b,c,d in zip(s[:,0],segment[:,0],s[:,1],segment[:,1])])
            good=(distances<=8)&informative
            if good.mean()>=.94 and distances[good].mean()<=4:
                hits.append((float(distances[good].mean()),target_start+start*STEP,scale,float(good.mean())))
    if not hits:
        raise ValueError('variant_anchor_mismatch')
    hits.sort()
    best=hits[0]
    if any(abs(h[1]-best[1])>1000 and h[0]<=best[0]+1 for h in hits):
        raise ValueError('variant_anchor_ambiguous')
    return dict(source_ms=source_start,target_ms=best[1],quality=round(1-best[0]/127,6),ratio=best[3])


def fit_map(anchors,duration_ms):
    if len(anchors)<3:
        raise ValueError('variant_identity_insufficient')
    x=np.array([a['source_ms'] for a in anchors],dtype=float)
    y=np.array([a['target_ms'] for a in anchors],dtype=float)
    if x.max()-x.min()<duration_ms*.3:
        raise ValueError('variant_identity_insufficient')
    scale,offset=np.polyfit(x,y,1)
    residual=float(np.abs(y-(scale*x+offset)).max())
    if not .96<=scale<=1.04 or abs(offset)>120000 or residual>750:
        raise ValueError('variant_edit_mismatch')
    return dict(scale=float(scale),offset_ms=float(offset),residual_ms=residual)


def mapped(mapping,point):
    return int(round(mapping['scale']*point+mapping['offset_ms']))


def sample(db,asset,kind,start,length,busy):
    from skip_scene import capture,_window,_snapshot
    row=capture(db,asset,kind,start,start+length,busy)
    window=_window(row,asset)
    from skip_scene_reliability import asset_version
    window.reuse_snapshot=dict(_snapshot(row,asset),source_version=asset_version(asset))
    return window


def anchor_evidence(left,right,hint):
    return dict(match_anchor(left.frames,right.frames,left.offset_ms,right.offset_ms,hint),
                source_window=left.reuse_snapshot,target_window=right.reuse_snapshot)


def marker_signature(marker):
    from skip_scene_reliability import digest
    return digest({k:dict(marker).get(k) for k in ('id','asset_key','source_key','season','episode',
                  'duration_ms','segment_type','start_ms','end_ms','reviewed_at','status','disabled','evidence_json')})


def verify(db,source,target,marker,busy,excluded_ranges=()):
    from skip_scene_reliability import asset_version,reserve
    if not source['duration_ms'] or not target['duration_ms']:
        raise ValueError('variant_runtime_unknown')
    ratio=target['duration_ms']/source['duration_ms']
    if not .94<=ratio<=1.06:
        raise ValueError('variant_runtime_mismatch')
    anchors=[]
    # Story anchors are outside every approved intro/outro in the source.
    for fraction in (.25,.5,.75):
        start=int(source['duration_ms']*fraction)//STEP*STEP
        length=10000
        if any(start<end+5000 and start+length>begin-5000 for begin,end in excluded_ranges):
            raise ValueError('variant_story_anchor_in_marker')
        reserve(40,'Sprachfassung prüfen')
        left=sample(db,source,'variant_story',start,length,busy)
        guess=round(start*ratio)
        right_start=max(0,(guess-30000)//STEP*STEP)
        right_length=min(60000,target['duration_ms']-right_start)
        right=sample(db,target,'variant_story',right_start,right_length,busy)
        anchors.append(anchor_evidence(left,right,ratio))
    mapping=fit_map(anchors,source['duration_ms'])
    boundary_evidence=[]
    for name in ('start_ms','end_ms'):
        boundary=marker[name]
        start=max(0,(boundary-5000)//STEP*STEP)
        length=min(15000,source['duration_ms']-start)
        if length<5000:
            raise ValueError('variant_boundary_missing')
        left=sample(db,source,'variant_boundary',start,length,busy)
        predicted=mapped(mapping,start)
        right_start=max(0,(predicted-3000)//STEP*STEP)
        right_length=min(math.ceil(length*mapping['scale']/STEP)*STEP+6000,target['duration_ms']-right_start)
        right=sample(db,target,'variant_boundary',right_start,right_length,busy)
        evidence=anchor_evidence(left,right,mapping['scale'])
        if abs(evidence['target_ms']-mapped(mapping,evidence['source_ms']))>750:
            raise ValueError('variant_boundary_mismatch')
        boundary_evidence.append(dict(evidence,boundary=name))
    start,end=mapped(mapping,marker['start_ms']),mapped(mapping,marker['end_ms'])
    from skip_markers import valid_range
    if not valid_range(marker['segment_type'],start,end,target['duration_ms']):
        raise ValueError('variant_boundaries_invalid')
    return dict(policy=POLICY,method='verified_variant_reuse',episcene_required=True,
                source_marker_id=marker['id'],source_marker_signature=marker_signature(marker),
                source_asset=source['asset_key'],source_version=asset_version(source),
                target_asset=target['asset_key'],target_version=asset_version(target),
                season=target['season'],episode=target['episode'],time_map=mapping,
                story_anchors=anchors,boundary_anchors=boundary_evidence,
                start_ms=start,end_ms=end,checked_at=time.time(),independent_episode_votes=0)


def release_ready(con,row,evidence):
    from skip_scene_reliability import asset_version
    from skip_scene import CACHE_SECONDS
    try:
        source=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',(evidence['source_asset'],)).fetchone()
        target=con.execute('SELECT * FROM skip_assets WHERE asset_key=?',(row['asset_key'],)).fetchone()
        marker=con.execute('SELECT r.*,e.evidence_json FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id WHERE r.id=?',(evidence['source_marker_id'],)).fetchone()
        if (not source or not target or not marker or marker['status']!='approved' or marker['disabled']
                or evidence.get('policy')!=POLICY or evidence.get('target_asset')!=row['asset_key']
                or marker['asset_key']!=source['asset_key'] or marker['segment_type']!=row['segment_type']
                or marker['source_key']!=source['source_key'] or marker['season']!=source['season'] or marker['episode']!=source['episode']
                or abs(marker['duration_ms']-source['duration_ms'])>500
                or evidence['source_version']!=asset_version(source) or evidence['target_version']!=asset_version(target)
                or evidence['source_marker_signature']!=marker_signature(marker) or not same_candidate(con,source,target)
                or not 0<=time.time()-evidence['checked_at']<=CACHE_SECONDS):
            return False
        anchors=evidence['story_anchors']
        mapping=fit_map(anchors,source['duration_ms'])
        if any(abs(mapping[k]-evidence['time_map'][k])>1e-6 for k in mapping):
            return False
        boundaries=evidence['boundary_anchors']
        if (len(boundaries)!=2 or {a['boundary'] for a in boundaries}!={'start_ms','end_ms'}
                or any(a['quality']<.968 or a['ratio']<.94 or abs(a['target_ms']-mapped(mapping,a['source_ms']))>750 for a in anchors+boundaries)
                or row['start_ms']!=mapped(mapping,marker['start_ms']) or row['end_ms']!=mapped(mapping,marker['end_ms'])):
            return False
        # Recheck content-bound snapshots, not just claimed scores. Failure,
        # eviction, changed pixels or a changed source revision requires a new
        # validation. Cached evidence never advances from a failed read.
        from skip_scene import _snapshot,_window
        for anchor in anchors+boundaries:
            windows=[]
            for field,asset in [('source_window',source),('target_window',target)]:
                snap=anchor[field]
                cached=con.execute('SELECT * FROM skip_scene_windows WHERE id=?',(snap['id'],)).fetchone()
                if (not cached or cached['created_at']<time.time()-CACHE_SECONDS
                        or dict(_snapshot(cached,asset),source_version=asset_version(asset))!=snap):
                    return False
                windows.append(_window(cached,asset))
            verified=match_anchor(windows[0].frames,windows[1].frames,windows[0].offset_ms,windows[1].offset_ms,mapping['scale'])
            if any(verified[k]!=anchor[k] for k in verified):
                return False
        # The original source marker must still pass its own policy. A prior
        # transfer is excluded so provenance cannot become a circular chain.
        source_evidence=json.loads(marker['evidence_json'] or '{}')
        if source_evidence.get('method')=='verified_variant_reuse':
            return False
        from skip_release import scene_release_ready,current_reference,reviewed_release_ready,detector_release_ready
        return (scene_release_ready(con,marker) and current_reference(con,marker)
                and reviewed_release_ready(marker) and detector_release_ready(con,marker))
    except (KeyError,TypeError,ValueError,OverflowError):
        return False


def try_reuse(db,target,busy_factory,required):
    from skip_scene_reliability import event,error_code,CONTEXT,analysis_playlist
    from skip_automation import protected,store_proposal
    from skip_release import accept_pending,scene_release_ready,current_reference,reviewed_release_ready,detector_release_ready
    from skip_scene import enabled
    with db() as con:
        if not enabled(con) or not required:
            return []
        candidates=con.execute('''SELECT a.* FROM skip_assets a JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          WHERE a.asset_key<>? AND a.season=? AND a.episode=? AND a.media_type='episode'
          AND EXISTS(SELECT 1 FROM skip_records r WHERE r.asset_key=a.asset_key AND r.status='approved' AND r.disabled=0)
          ORDER BY a.updated_at DESC LIMIT 16''',(target['asset_key'],target['season'],target['episode'])).fetchall()
        candidates=[dict(a) for a in candidates if same_candidate(con,a,target)]
        target_playlist=analysis_playlist(con,target['playlist_id'])
    reused=[]
    if candidates:
        # New catalogue assets often have no measured runtime yet. Probe only
        # when a usable source candidate exists, before transferring anything.
        from skip_analysis import provider_proxy,source_url,probe
        busy=busy_factory(db,[target_playlist])
        with provider_proxy(source_url(target_playlist,target),busy) as media:
            duration,_=probe(media,busy)
        if target['duration_ms'] and abs(duration-target['duration_ms'])>2000:
            return []
        with db() as con:
            con.execute('UPDATE skip_assets SET duration_ms=? WHERE asset_key=? AND duration_ms=?',(duration,target['asset_key'],target['duration_ms']))
        target['duration_ms']=duration
    for source in candidates[:2]:
        with db() as con:
            source_playlist=analysis_playlist(con,source['playlist_id'])
            markers=con.execute('SELECT r.*,e.evidence_json FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id WHERE r.asset_key=? AND r.status=\'approved\' AND r.disabled=0',(source['asset_key'],)).fetchall()
            valid=[]
            for marker in markers:
                e=json.loads(marker['evidence_json'] or '{}')
                if (marker['segment_type'] in required and e.get('method')!='verified_variant_reuse'
                    and scene_release_ready(con,marker) and current_reference(con,marker)
                    and reviewed_release_ready(marker) and detector_release_ready(con,marker)):
                    valid.append(dict(marker))
        busy=busy_factory(db,[target_playlist,source_playlist])
        for marker in valid:
            kind=marker['segment_type']
            if kind in reused:
                continue
            try:
                evidence=verify(db,source,target,marker,busy,[(m['start_ms'],m['end_ms']) for m in markers])
                with db() as con:
                    if protected(con,target,kind):
                        continue
                    # Validate current source, revision and human decisions in
                    # the same publication transaction as the marker insert.
                    proposed=dict(target,segment_type=kind,start_ms=evidence['start_ms'],end_ms=evidence['end_ms'])
                    if not release_ready(con,proposed,evidence):
                        continue
                    saved=store_proposal(con,target,kind,evidence['start_ms'],evidence['end_ms'],'episcene',.99,evidence)
                    accepted=accept_pending(con,asset_key=target['asset_key']) if saved else 0
                    approved=con.execute("SELECT status FROM skip_records WHERE id=?",(saved['id'],)).fetchone() if saved else None
                    if approved and approved[0]=='approved':
                        reused.append(kind)
                        from skip_scene_reliability import state
                        # The surrounding connection owns publication. Avoid
                        # opening a second writer until it commits below.
                    event(con,'variant_reuse',target['asset_key'],status='verified' if kind in reused else 'review',
                          source_asset=source['asset_key'],segment_type=kind,playlist_id=target['playlist_id'],time_map=evidence['time_map'])
                if kind in reused:
                    state(db,target,kind,'reused_verified')
            except ValueError as error:
                if str(error)=='analysis_deferred':
                    raise
                with db() as con:
                    event(con,'variant_reuse',target['asset_key'],status='fallback',reason=error_code(error),segment_type=kind)
    return reused
