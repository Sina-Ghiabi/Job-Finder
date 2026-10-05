# -*- coding: utf-8 -*-
"""Is this listing the wrong level for the Mid profile?

Mid: the working middle of a career, about 3 to 5 years.

A copy of the Junior profile's rules.is_too_senior, line for line, as the user asked: [owner's note: exactly the same template, with only a few small things changed]. Every step it takes is the
step is_too_senior takes, in the same order and for the reasons written there:

    1. LinkedIn's own seniority field
    2. a level word in the TITLE
    3. a level word in the description, but only where it names THIS role
       ("As a Senior Data Engineer you will...", "Senior Data Engineer gesucht")
    4. a number of years of experience, framed as a requirement and not waived

Only three things differ from Junior, and they are the constants at the top of this file:
which field values, which words, and how many years are the wrong level for Mid.
"""
from __future__ import annotations

import re

# 1. LinkedIn's own seniority field. Junior: {'director', 'executive', 'mid-senior level'}.
WRONG_LEVEL_FIELD_VALUES = {'entry level', 'internship', 'executive', 'director'}

# 2 and 3. The English words that put a listing at the wrong level for Mid. Junior's are
# rules.SENIOR_KEYWORDS. The words in the other 12 languages are this profile's
# `wrong_level` section in words.py, applied by the Filter's word check.
WRONG_LEVEL_KEYWORDS = ['senior', 'sr.', 'principal', 'manager', 'director', 'head of', 'chief', 'vp',
 'vice president', 'president', 'team lead', 'supervisor', 'department head',
 'leadership', 'lead', 'staff', 'junior', 'jr.', 'entry level', 'entry-level',
 'graduate', 'new grad', 'early career']

# 4. Years of experience that are the wrong level for Mid. Junior drops 3 and more.
#    TOO_MANY_YEARS  a requirement of this many years or more is the wrong level
#    TOO_FEW_YEARS   a requirement capped at this many years or fewer is the wrong level
TOO_MANY_YEARS = 6
TOO_FEW_YEARS = None


# ---- everything below is is_too_senior's machinery, unchanged ---------------------------

# Two of Junior's words start an ordinary word that has nothing to do with seniority, so each
# gets a guard on its tail: "vp" opens "VPN", "director" opens "Active Directory".
#
# "lead" and "staff" need the same, and measured: without it "Data Engineer, Leading Bank"
# was dropped for the word "Leading" -- which describes the employer, not the role -- and
# "staffing" would go the same way. Only the exact words count, which is how a title writes
# them: "Lead Data Engineer", "Staff Data Engineer".
_KEYWORD_TAIL_GUARDS = {
    'vp': r'(?![a-z])',
    'director': r'(?!y\b|ies\b)',
    'lead': r'(?![a-z])',
    'staff': r'(?![a-z])',
}


def _keyword_alternatives():
    for keyword in sorted(WRONG_LEVEL_KEYWORDS, key=len, reverse=True):
        yield re.escape(keyword) + _KEYWORD_TAIL_GUARDS.get(keyword, '')


_TITLE_PATTERN = re.compile(r'\b(?:%s)' % '|'.join(_keyword_alternatives()), re.I)

_ROLE_DEFINING_PATTERN = re.compile(
    r'(?:(?<!well )(?<!such )\bas\s+(?:an?\s+)?'
    r"|\bwe(?:'re| are)\s+(?:looking|searching|hiring)\s+for\s+(?:an?\s+)?"
    r'|\bwir\s+suchen\s+(?:eine[nr]?\s+)?'
    r'|\bthis\s+is\s+(?:an?\s+)?'
    r'|\bthe\s+role\s+is\s+(?:that\s+of\s+)?(?:an?\s+)?'
    r'|(?<!sowie )\bals\s+(?:eine[nr]?\s+)?'
    r'|\bstellenbezeichnung\s*:?\s*)'
    r'(?:(?!well\b|such\b)[a-zäöüß/&+.\-]+\s+){0,2}?'
    r'(?:%s)\b' % '|'.join(_keyword_alternatives()), re.I)

_WANTED_PATTERN = re.compile(
    r'\b(?:%s)[^.!?\n]{0,50}?\b(?:wanted|sought|gesucht|gesuchte[nr]?)\b'
    % '|'.join(_keyword_alternatives()), re.I)

# "5+ years", "+5 years"
_PLUS_YEARS_PATTERN = re.compile(r'\b(\d{1,2})\s*\+\s*years?\b|\+\s*(\d{1,2})\s*years?\b')

# "3-4 years", "5/7 years", "5 to 7 years"
_RANGE_YEARS_PATTERN = re.compile(r'\b(\d{1,2})\s*(?:[-/|]|\bto\b)\s*(\d{1,2})\s*years?\b')

# "8 years of experience" -- a bare minimum, with the lookbehind that keeps it off the "3" in
# "1-3 years", and a gap that cannot cross a sentence. See rules.SENIOR_MIN_YEARS_PATTERN.
_BARE_YEARS_PATTERN = re.compile(
    r'(?<![-/|\d])\b(\d{1,2})\s*\+?\s*years?'
    r"(?:\s+(?:of|in|'?s|professional|relevant|hands-on|industry|practical|commercial|work|working))*"
    r'\s+experience\b'
)

_REQUIREMENT_WORDS = (
    'required', 'require', 'requires', 'requirement', 'minimum', 'min.', 'at least',
    'must have', 'need', 'needs', 'looking for', 'seeking', 'proven', 'demonstrated',
    'experience:', 'expected', 'ideally', 'preferably', 'preferred', 'qualification',
)

_REQUIREMENT_WAIVERS = (
    'no prior experience', 'no experience', 'without experience', 'gain', 'you will gain',
    'not required', 'no previous experience',
)


_EXPERIENCE_WORD = re.compile(r'experience|\bexp\b|erfahrung')


def _sentence_around(text, match):
    start = text.rfind('.', 0, match.start()) + 1
    end = text.find('.', match.end())
    return text[start:end if end != -1 else len(text)]


def _is_requirement(text, match):
    sentence = _sentence_around(text, match)
    return (not any(waiver in sentence for waiver in _REQUIREMENT_WAIVERS)
            and any(word in sentence for word in _REQUIREMENT_WORDS))


def _years_are_wrong(text):
    if TOO_MANY_YEARS is not None:
        for match in _PLUS_YEARS_PATTERN.finditer(text):
            if int(match.group(1) or match.group(2)) >= TOO_MANY_YEARS:
                return True
        for low, high in _RANGE_YEARS_PATTERN.findall(text):
            if int(high) >= int(low) >= TOO_MANY_YEARS:
                return True
        for match in _BARE_YEARS_PATTERN.finditer(text):
            if int(match.group(1)) >= TOO_MANY_YEARS and _is_requirement(text, match):
                return True
    if TOO_FEW_YEARS is not None:
        # The one place this file is NOT is_too_senior word for word, because this direction
        # does not exist there. Junior only ever drops a LARGE range, and a large range is
        # almost never about anything but experience. A SMALL one often is not: measured,
        # "the product roadmap for the next 1-2 years" is a real advert. So here a range
        # counts only when its own sentence is about experience -- "experience", the "exp"
        # that structured boards abbreviate it to ("|5 years of exp|"), or German "Erfahrung".
        for match in _RANGE_YEARS_PATTERN.finditer(text):
            low, high = int(match.group(1)), int(match.group(2))
            if (low <= high <= TOO_FEW_YEARS
                    and _EXPERIENCE_WORD.search(_sentence_around(text, match))):
                return True
        for match in _BARE_YEARS_PATTERN.finditer(text):
            if int(match.group(1)) <= TOO_FEW_YEARS and _is_requirement(text, match):
                return True
    return False


def is_wrong_level(row) -> bool:
    """True when this listing is aimed at a level other than Mid. The Mid profile's
    is_too_senior."""
    seniority_level = str(row.get('seniority_level') or '').strip().lower()
    if seniority_level in WRONG_LEVEL_FIELD_VALUES:
        return True

    if _TITLE_PATTERN.search(str(row.get('title') or '')):
        return True
    description = str(row.get('description') or '')
    if _ROLE_DEFINING_PATTERN.search(description) or _WANTED_PATTERN.search(description):
        return True

    combined_text = f"{row.get('title') or ''} {row.get('description') or ''}".lower()
    # Every years pattern needs the literal "year"; checking that first is the same saving
    # is_too_senior makes.
    if 'year' not in combined_text:
        return False
    return _years_are_wrong(combined_text)
