# -*- coding: utf-8 -*-
"""What makes one Filter run the same as another.

The user's rule: re-filtering with the same choices must show the previous answer instead of
paying for it again, and changing **any one** of them must redo the work from the start.

So the question this module answers is narrow and exact: would a Filter run right now
produce the same listings as the one whose signature is stored? It is answered by hashing
everything a verdict depends on, and nothing else.

WHAT IS IN THE SIGNATURE, AND WHY EACH PART HAS TO BE

    the choices        level, work mode, title, countries, cities, and every option the
                       dialog offers -- these are what the user picked, and the whole point
    the pool           bank.json's own fingerprint. A new search means new listings; an
                       answer computed over a different pool is not the same answer
    the resume         its fingerprint. Every fact about the user comes from it, so a new
                       resume is new verdicts -- the same reason claude_screen hashes it
    the prompt         the rules Claude was given. Editing a rule must invalidate the
                       stored answer, and hashing the prompt's own text means nobody has
                       to remember to bump a counter

WHAT IS DELIBERATELY NOT IN IT

    the time it ran    a stale answer over the same pool with the same rules is still the
                       right answer; expiring it would spend money to prove that
    the listing order  a set of survivors is the same set however it is sorted

This mirrors `_claude_screen_cache_key`, which does the same job for one listing. That one
saves an API call; this one saves a whole run -- and the two compose: even when the
signature differs and everything is re-filtered, the per-listing cache means only the
listings whose own inputs changed are actually paid for again.
"""
from __future__ import annotations

import hashlib
import json


# Every choice the Filter dialog offers, in a fixed order so two equal selections always
# hash alike. A new option added to the dialog belongs here too -- and if it is forgotten,
# changing it will silently reuse the previous answer, which is the one failure this module
# can have. Section 3.signature has a test that counts these against the dialog's own list.
FILTER_CHOICE_KEYS = (
    'search_title',
    'search_level',
    'search_work_mode',
    'countries',
    'cities',
    'date_range',
    'min_match_percent',
    'categories',
    'sponsorship',
    # Which of the job titles found in the pool are worth reading. The costly choice in the
    # window: everything left out is removed before Claude sees it, so unticking "AI Engineer"
    # takes 512 listings out of a run rather than hiding them afterwards. In the signature
    # because a different set of fields is a different answer -- and because re-ticking one
    # must make the Filter run again rather than show a result that never included it.
    'fields',
    'use_claude',
)


def _stable(value):
    """A value in a form that hashes the same whenever it means the same.

    Lists of choices are sets to the user -- ticking Germany then Austria is the same selection
    as ticking Austria then Germany -- so they are sorted. Everything else is compared as
    the text it displays as, which is what he actually chose.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, bool):
        return value
    return str(value).strip()


def choices_from(settings: dict) -> dict:
    """The filter choices, read out of a settings-shaped dict and normalised."""
    return {key: _stable((settings or {}).get(key)) for key in FILTER_CHOICE_KEYS}


def filter_signature(choices: dict, pool_fingerprint: str, resume_fingerprint: str,
                     prompt_version: str) -> str:
    """One hex string standing for "this Filter, over this pool, under these rules"."""
    payload = {
        'choices': {key: _stable((choices or {}).get(key)) for key in FILTER_CHOICE_KEYS},
        'pool': str(pool_fingerprint or ''),
        'resume': str(resume_fingerprint or ''),
        'prompt': str(prompt_version or ''),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def pool_fingerprint(rows: list) -> str:
    """A fingerprint of the pool a Filter would read.

    The URLs, sorted, plus the count. Not the whole rows: a listing whose description was
    re-fetched between runs is the same listing, and the per-listing Claude cache already
    decides whether its own text changed. What must invalidate a stored answer is the pool
    gaining or losing listings, which is exactly what a new search does.
    """
    urls = sorted({str((row or {}).get('url') or '') for row in (rows or [])})
    digest = hashlib.sha256(('\n'.join(urls)).encode('utf-8')).hexdigest()
    return '%d:%s' % (len(urls), digest[:32])


def describe(choices: dict) -> str:
    """The choices as one readable line, for the Log.

    The user reads this to know what he is looking at, so it names the things that change what
    he sees and stays quiet about the ones left at their default.
    """
    picked = {key: _stable((choices or {}).get(key)) for key in FILTER_CHOICE_KEYS}
    parts = []
    if picked.get('search_title'):
        parts.append(str(picked['search_title']))
    if picked.get('search_level'):
        parts.append(str(picked['search_level']).title())
    mode = picked.get('search_work_mode')
    if mode:
        parts.append({'not_remote': 'Not Remote', 'any': 'Any'}.get(str(mode), 'Remote'))
    for key, label in (('countries', ''), ('cities', '')):
        values = picked.get(key)
        if values:
            parts.append(label + ', '.join(values[:4])
                         + (' +%d' % (len(values) - 4) if len(values) > 4 else ''))
    if picked.get('date_range'):
        parts.append(str(picked['date_range']))
    # A floor of zero is no floor. `_stable` turns it into the string '0', which is truthy,
    # so the number has to be read as a number here -- otherwise every default run says
    # "match 0%+" and the line stops meaning anything.
    try:
        floor = int(str(picked.get('min_match_percent') or 0).strip() or 0)
    except ValueError:
        floor = 0
    if floor > 0:
        parts.append('match %d%%+' % floor)
    if picked.get('categories'):
        parts.append('/'.join(picked['categories']))
    if picked.get('sponsorship'):
        parts.append('visa: %s' % picked['sponsorship'])
    if picked.get('use_claude') is False:
        parts.append('no Claude')
    return ' · '.join(parts) if parts else 'everything'
