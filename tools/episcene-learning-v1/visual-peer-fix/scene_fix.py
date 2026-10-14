#!/usr/bin/env python3
"""Strictly scoped EpiScene analysis-playlist + late-outro visual window patch.

Never modifies approval confidence thresholds. Existing customer account
authorization for app submissions is left completely untouched.
"""
from __future__ import annotations
import ast

OLD_JOIN=("JOIN customer_playlists p ON p.id=a.playlist_id "
          "JOIN customers c ON c.id=p.customer_id AND c.enabled=1")
NEW_JOIN=("JOIN skip_analysis_playlists p ON p.id=a.playlist_id "
          "AND p.archived=0")
OLD_PLAYLIST="SELECT * FROM customer_playlists WHERE id=?"
NEW_PLAYLIST="SELECT * FROM skip_analysis_playlists WHERE id=?"
OLD_WINDOW="        begin, end = audio[0]['start_ms'] - 6000, audio[0]['end_ms'] + 6000"
NEW_WINDOW="""        # Human postprocessing found that some actual end credits begin
        # significantly before a high-confidence audio repetition. Expand
        # the *visual inspection* window only; do not shift or approve a marker.
        begin, end = audio[0]['start_ms'] - 6000, audio[0]['end_ms'] + 6000
        if kind == 'outro':
            begin -= 55000"""


def patch(source):
    # The expanded window contains the original assignment as a substring:
    # check the fully-patched state BEFORE looking for legacy anchors.
    if (source.count(NEW_JOIN)==2 and source.count(NEW_PLAYLIST)==1
            and source.count(NEW_WINDOW)==1
            and OLD_JOIN not in source and OLD_PLAYLIST not in source):
        ast.parse(source)
        return source,False
    if (source.count(OLD_JOIN)!=2 or source.count(OLD_PLAYLIST)!=1
            or source.count(OLD_WINDOW)!=1 or source.count('    if audio:\n')!=1 or NEW_WINDOW in source
            or NEW_JOIN in source or NEW_PLAYLIST in source):
        raise ValueError('Unexpected live scene revision; no modification')
    result=(source.replace(OLD_JOIN,NEW_JOIN)
                  .replace(OLD_PLAYLIST,NEW_PLAYLIST)
                  .replace(OLD_WINDOW,NEW_WINDOW))
    if (result.count(NEW_JOIN)!=2 or result.count(NEW_PLAYLIST)!=1
            or result.count(NEW_WINDOW)!=1):
        raise ValueError('Incomplete EpiScene visual patch')
    ast.parse(result)
    return result,True
