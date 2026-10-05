# -*- coding: utf-8 -*-
"""The one job title the user types, and the forms it is searched and recognised in.

Until this existed, a field was 522 hand-written items in ten places -- the English query,
the entry-level phrases, a role word in twelve languages, internship phrases, the direct
sites, Google, the title filter, the dropdown and two Claude prompts. Moving from data
science to DevOps took a day and produced eight faults (Test-Campaign-Bugs.md, L). The user's
answer: [owner's note: one job title is typed and searched for - only one name].

So the field is now ONE string. Everything that used to be written by hand per field is
built from it; the words that do not depend on the field -- Werkstudent, Praktikum, Junior,
Berufseinsteiger, Neolaureato -- stay where they are and never change.

WHY THIS ONE FILE IS SHARED, when the three modules share nothing

The user's rule is that the Job, Internship and Thesis modules share no vocabulary, so that
tuning one cannot move another. The title is not vocabulary. It is the single thing all of
them must agree on exactly: the search asks for it, each filter keeps it, Claude is told it.
Three copies of the default could disagree -- the search asking for "Data Engineering" while
a filter still knew "DevOps" -- and that would be a fault, not independence. So the name and
its forms are defined once, here. What each module DOES with them, deciding whether a title
belongs, is still written separately inside each module.
"""
from __future__ import annotations

import re

# What the box holds until the user types something else.
DEFAULT_SEARCH_TITLE = 'Data Engineering'

# Where each row carries the title it is being judged against. Written by the Filter step,
# not by the search, and that choice is the point: Filter must use the title in the box NOW.
# A listing saved last week by a DevOps search, filtered today after the box was changed to
# Data Engineering, has to be judged as Data Engineering.
#
# It is also what makes Claude's cache safe. Both modules hash the exact text they send, and
# this title is part of that text -- so a verdict reached for one title can never be reused
# for another. No version number to remember to bump.
ROW_KEY = '_search_title'

# The Level, the other thing the user chooses in Search -- exactly one at a time. It replaced the
# Job / Internship / Thesis checkboxes: Thesis and Internship are their own modules, and the
# four job levels are profiles of the Job module, each with its own complete vocabulary,
# level rule and Claude prompt (app/pipeline/profiles/).
# 'any' is what Search offers now in place of the four job levels: it searches for every kind of
# posting it can find -- jobs, internships and theses -- and puts no seniority word in any query.
# The four job levels stay valid values (old settings hold them, the Filter's profiles are keyed
# by them, and tests call with them); Search simply no longer offers them. See Document T-19.
LEVELS = ('any', 'thesis', 'internship', 'entry', 'junior', 'mid', 'senior')
JOB_LEVELS = ('entry', 'junior', 'mid', 'senior')
# What the Search window and the Filter window offer, in the order they offer it.
SEARCH_TYPES = ('any', 'thesis', 'internship')
# Junior, because it is the profile the Job module has always been.
DEFAULT_SEARCH_LEVEL = 'junior'
# Written onto each row by the Filter step beside ROW_KEY, for the same reason: Filter judges
# by the level chosen NOW, and Claude's cache key picks it up without being told.
LEVEL_ROW_KEY = '_search_level'


def clean_level(level) -> str:
    """One of LEVELS, or the default for anything else."""
    text = str(level or '').strip().lower()
    return text if text in LEVELS else DEFAULT_SEARCH_LEVEL


def clean_search_type(value) -> str:
    """'any', 'thesis' or 'internship' -- what Search is looking for.

    A saved value from before this existed (junior, mid, senior, entry, or nothing) is read as
    'any': those meant "a job", and Any includes jobs. That is what makes opening the Search
    window on an old settings.json show a real choice instead of a blank one.
    """
    text = str(value or '').strip().lower()
    return text if text in ('thesis', 'internship') else 'any'


# Remote or Not Remote, the third thing the user chooses in Search. His words: [owner's note: Remote already works as well as it can; reuse it, and with Not Remote bring everything else]. Remote is every rule exactly as it was. Not Remote asks the same
# question and keeps the other answer: a role that says it is remote is dropped, and one that
# is on-site, hybrid or silent is kept.
# 'any' is the third: no Work Location rule at all, remote, hybrid, on-site and silent all
# kept. The Search and Filter windows offer Remote and Any; 'not_remote' is still understood
# (settings saved before Any existed carry it) and is what the windows open as Any.
WORK_MODES = ('remote', 'not_remote', 'any')
DEFAULT_WORK_MODE = 'remote'
# Written onto each row by the Filter step, like the title and the Level, so the keyword rules
# and Claude read the choice made NOW, and a verdict reached for one is never reused for the
# other.
WORK_MODE_ROW_KEY = '_search_work_mode'


def clean_work_mode(mode) -> str:
    """'remote', 'not_remote' or 'any'; anything else is the default, Remote."""
    text = str(mode or '').strip().lower().replace(' ', '_').replace('-', '_')
    return text if text in WORK_MODES else DEFAULT_WORK_MODE


def is_not_remote(row_or_mode) -> bool:
    """True when this row -- or this mode -- is being judged for Not Remote."""
    mode = (row_or_mode.get(WORK_MODE_ROW_KEY) if isinstance(row_or_mode, dict)
            else row_or_mode)
    return clean_work_mode(mode) == 'not_remote'


def is_any_workplace(row_or_mode) -> bool:
    """True when this row -- or this mode -- is judged with no regard to where the work is done."""
    mode = (row_or_mode.get(WORK_MODE_ROW_KEY) if isinstance(row_or_mode, dict)
            else row_or_mode)
    return clean_work_mode(mode) == 'any'


# A job title and the name of its field are the same thing said two ways, and a search needs
# both. "Junior Data Engineering" is not a title anyone posts; "Junior Data Engineer" is. But
# "Werkstudent Data Engineering (m/w/d)" and "Data Engineering Intern" are both real. So a
# title ending in one of these gets its twin, whichever of the two the user typed.
#
# Only these three pairs, because each is exact in both directions. A word list that tried to
# guess more ("Analytics" -> "Analyst"?) would be guessing, and guessing is what made the
# first date filter wrong.
_TWINS = (('Engineering', 'Engineer'), ('Development', 'Developer'), ('Science', 'Scientist'))


def clean_title(title) -> str:
    """The title with its spacing tidied, or the default if nothing usable was given."""
    text = ' '.join(str(title or '').replace('"', ' ').split())
    return text or DEFAULT_SEARCH_TITLE


def _swap_ending(text: str, have: str, make: str):
    """`text` with its final word `have` replaced by `make`, in the same letter case -- or
    None if it does not end that way. "data engineering" gives "data engineer", not
    "data Engineer"."""
    found = re.search(r'\b(%s)$' % have, text, re.I)
    if not found:
        return None
    written = found.group(1)
    if written.isupper():
        make = make.upper()
    elif written.islower():
        make = make.lower()
    return text[:found.start(1)] + make


def title_forms(title) -> list:
    """Every form of the title to search for and to recognise: as typed, then its twin.

    >>> title_forms('Data Engineering')
    ['Data Engineering', 'Data Engineer']
    >>> title_forms('DevOps')
    ['DevOps']
    """
    text = clean_title(title)
    for field, role in _TWINS:
        for have, make in ((field, role), (role, field)):
            twin = _swap_ending(text, have, make)
            if twin is not None:
                return [text, twin]
    return [text]


def role_form(title) -> str:
    """The form a job advert uses for one person doing the work -- what "Junior" attaches to.

    "Data Engineering" -> "Data Engineer". A title with no twin is its own role form.
    """
    text = clean_title(title)
    for field, role in _TWINS:
        swapped = _swap_ending(text, field, role)
        if swapped is not None:
            return swapped
    return text


def field_form(title) -> str:
    """The form that names the subject rather than the person -- what a thesis is about.

    "Data Engineer" -> "Data Engineering": a German thesis advert reads "Masterarbeit Data
    Engineering", never "Masterarbeit Data Engineer". A title with no twin is its own field
    form.
    """
    text = clean_title(title)
    for field, role in _TWINS:
        swapped = _swap_ending(text, role, field)
        if swapped is not None:
            return swapped
    return text


def quoted(forms) -> list:
    """Each form as an exact phrase, the way every actor and search engine reads one."""
    return ['"%s"' % form for form in forms]
