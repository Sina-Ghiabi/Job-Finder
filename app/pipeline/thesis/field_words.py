# -*- coding: utf-8 -*-
"""Is this thesis about the job Sina is searching for? — the Thesis module's own copy.

A copy, on purpose. Sina's rule for these three modules has been the same from the first
day: *"نه دیکشنری مشترک نه هیچی"* — no shared dictionary, nothing shared at all. A change
tuned for the way internship titles are written must not be able to change what this module
keeps, and the only way to guarantee that is for this file to be its own. The only thing the
three agree on is the title itself (app/pipeline/search_title.py).

WHY THIS EXISTS AT ALL

A thesis is a thesis whatever its subject, and this module's own rules cannot tell a
machine-learning Masterarbeit from a marketing one. On the real German internship run, 260
listings were recognised as theses and 36 of them were about something else entirely.

THE TITLE SINA TYPES IS THE FIELD

This file used to hold about 150 field words in thirteen languages. Sina replaced them with
one name, and for Thesis too: "Masterarbeit Data Engineering". A thesis is in the field when
it names that job -- every word of it, in any order, each at the start of a word.

AND HERE, THE TITLE IS NOT ENOUGH ON ITS OWN

This is the one place the three copies differ, and it was measured, not chosen. A job advert
and an internship advert name a job in their title. A thesis advert names a TOPIC:

    Masterarbeit Deep Learning auf multivariaten Zeitreihendaten im Motorradbereich
    Thesis - Optimization of Graph Neural Networks for Product related data
    Abschlussarbeit Entwicklung eines ML-Modells zur Anomalieerkennung

On the real German corpus, 334 theses, the title alone kept NONE of them for "Data Science"
and one for "Data Engineering" -- the check would have deleted every thesis Sina could want.
Reading the description as well, where the advert says who it is looking for ("Studium der
Informatik, Data Science oder vergleichbar"):

    Data Science       keeps 160 of 334   (136 of the 245 the old field words called data work)
    Data Engineering   keeps  84
    DevOps             keeps  11

So here the title OR the description may name the job. What that lets through that should
not be -- 24 of the 89 off-subject theses for "Data Science", a BMW product audit among them
-- is read by Claude, which is told the title and drops a thesis about something else.

A word of three letters or fewer has to END a word as well as start one: "AI" must not find
"Airflow". The word list is kept out of the public repository.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..search_title import ROW_KEY as TITLE_ROW_KEY, clean_title, title_forms

# Where the untranslated text is kept, when there is one. This module names the keys itself
# so it keeps working whatever the Job module renames.
ORIGINAL_TITLE_KEY = '_original_title'
ORIGINAL_DESCRIPTION_KEY = '_original_description'

# What separates the words of a title. A hyphen only between two letters; `+`, `#` and `.`
# are left alone because they are part of names -- C++, C#, .NET.
_WORD_SPLIT = re.compile(r'[\s/&,;:|()\[\]]+|(?<=[^\W_])-(?=[^\W_])')


def _word_pattern(word: str):
    """One word of the title, found at the start of a word in the thesis advert."""
    starts_with_letter = re.match(r'[^\W_]', word) is not None
    ends_with_letter = re.search(r'[^\W_]$', word) is not None
    letters = re.sub(r'[\W_]', '', word)
    lead = r'(?<![^\W_])' if starts_with_letter else ''
    trail = r'(?![^\W_])' if ends_with_letter and len(letters) <= 3 else ''
    return re.compile(lead + re.escape(word) + trail, re.IGNORECASE)


@lru_cache(maxsize=32)
def _form_patterns(search_title: str) -> tuple:
    """For each form of the title, the patterns for all of its words."""
    forms = []
    for form in title_forms(search_title):
        words = [word for word in _WORD_SPLIT.split(form) if re.search(r'[^\W_]', word)]
        forms.append(tuple(_word_pattern(word) for word in words))
    return tuple(forms)


def text_names_job(text, search_title=None) -> bool:
    """Does this piece of text name the job being searched for? Empty text does not."""
    text = ' '.join(str(text or '').split())
    if not text:
        return False
    return any(all(pattern.search(text) for pattern in form)
               for form in _form_patterns(clean_title(search_title)))


def title_is_in_field(title, search_title=None) -> bool:
    """Does this title alone name the job? A missing title is True: a row with nothing to
    read is not evidence of anything, and this app never deletes on an absence."""
    if not str(title or '').strip():
        return True
    return text_names_job(title, search_title)


def row_is_in_field(row, search_title=None) -> bool:
    """Does the thesis advert name the job -- in its title or in its description, as posted
    or as it was before translation? With nothing to read at all it is kept."""
    wanted = search_title if search_title is not None else row.get(TITLE_ROW_KEY)
    texts = [text for text in (row.get('title'), row.get(ORIGINAL_TITLE_KEY),
                               row.get('description'), row.get(ORIGINAL_DESCRIPTION_KEY))
             if str(text or '').strip()]
    if not texts:
        return True
    return any(text_names_job(text, wanted) for text in texts)


def remove_off_field(rows: list, search_title=None) -> tuple:
    """Drop the theses that never name the job. Returns (kept, removed)."""
    kept: list = []
    removed: list = []
    for row in rows:
        (kept if row_is_in_field(row, search_title) else removed).append(row)
    return kept, removed
