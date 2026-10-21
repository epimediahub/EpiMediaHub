#!/usr/bin/env python3
"""Playlist-specific language eligibility. Independent from priority/ranking.

4K ANALYSE is a mixed-language trial provider feed, so only explicit German
language evidence or an explicitly approved German provider category can pass.
THE BEST is curated to Italian by its provider; no language ranking is applied.

This module is a pure policy for integration with every primary and auxiliary
producer. It intentionally does not mutate jobs, database rows or playlists.
"""
from __future__ import annotations
import json
import re

GERMAN_CODES=frozenset({'de','deu','ger','de-de','de_at','de-at','de_ch','de-ch'})
GERMAN_LABEL=re.compile(r'(?i)(?:^|[\s|:\[\]()/\\_-])(?:de|deutsch|deutsche|german)(?=$|[\s|:\[\]()/\\_-])')


def normalized_codes(codes):
    if isinstance(codes,str):
        try:
            parsed=json.loads(codes)
        except (ValueError,TypeError):
            return frozenset()
    else:
        parsed=codes
    if isinstance(parsed,str):
        parsed=[parsed]
    if not isinstance(parsed,(tuple,list,set,frozenset)):
        return frozenset()
    return frozenset(s.strip().lower().replace('_','-') for s in parsed if isinstance(s,str))


def german_evidence(*,codes=(),category_id=None,approved_category_ids=(),category_label=''):
    language=normalized_codes(codes)
    if language & GERMAN_CODES:
        return 'explicit_language_code'
    # Category names can be suggestive but are not trusted automatically.
    # A configured provider category ID is required to allow by category alone.
    if (category_id is not None and str(category_id) in {str(c) for c in approved_category_ids}
            and isinstance(category_label,str) and GERMAN_LABEL.search(category_label)):
        return 'approved_german_category'
    return None


def eligible(playlist_id,*,codes=(),category_id=None,approved_category_ids=(),category_label=''):
    if playlist_id==10:
        return True,'curated_italian_playlist'
    if playlist_id==8:
        evidence=german_evidence(codes=codes,category_id=category_id,
                                 approved_category_ids=approved_category_ids,
                                 category_label=category_label)
        return (bool(evidence),evidence or 'german_source_not_verified')
    return False,'not_an_independent_analysis_playlist'
