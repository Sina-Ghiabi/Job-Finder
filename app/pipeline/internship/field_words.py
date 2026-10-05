# -*- coding: utf-8 -*-
"""Does this internship's title name the job the user is searching for? — the Internship module's
own copy.

A copy, on purpose, and the whole point of the copy is that it is a copy. The user's rule for
these three modules has been the same from the first day: *owner's note: no shared dictionary, nothing shared at all* — no
shared dictionary, nothing shared at all, three modules that happen to run over one list. A
change tuned here for internships cannot silently change what the Job or Thesis module keeps.
The only thing the three agree on is the title itself (app/pipeline/search_title.py).

WHY THIS EXISTS AT ALL

Until the Internship search existed nothing asked whether a listing was on-topic: the job
search sends role titles, so everything it found was on-topic by construction. That ended
the moment a search asked for a KIND of position. Measured on the real German internship
run, 5,231 listings recognised as internships, 2,914 of them with no data, AI or software
word in the title: "Werkstudent Corporate HR - Rewards & Labour Law", "Praktikum Video News
bei BurdaForward", "Werkstudent Creative Content Production". Every one would have reached
Claude and been paid for.

THE TITLE SINA TYPES IS THE FIELD

This file used to hold about 150 field words in thirteen languages. The user replaced them with
one name: [owner's note: one typed title must take the place of all of these]. An internship
is in the field when its title names that job -- every word of it, in any order, each at the
start of a word. For "Data Engineering" (and its twin "Data Engineer"):

    Praktikum Data Engineer im Bereich Advanced Analytics   kept
    Praktikant AI & Data Engineering (m/w/d)                kept
    Werkstudent Data Engineering & Data Science             kept
    Intern Deployment Engineer - Data & AI                  kept     any order
    Werkstudent Data Science (w/m/x)                        dropped  a different job

Measured on the real German internship run, whose search asked for no field at all: of 6,476
internships, "Data Engineering" keeps 151 and "Data Science" 158. The old field words kept
3,565. From now on the search itself asks for the title ("Werkstudent Data Engineer"), so far
more of what arrives names it.

A word of three letters or fewer has to END a word as well as start one: "AI" must not find
"Airflow". The word list is kept out of the public repository.

THE TITLE, AND ONLY THE TITLE

Measured when the field words were written: reading the body as well kept 95% of everything,
because almost every German advert mentions Künstliche Intelligenz or Daten somewhere in its
company blurb. A title says what the internship IS; a body sells the company.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..search_title import ROW_KEY as TITLE_ROW_KEY, clean_title, title_forms

# Where the untranslated title is kept, when there is one. This module names the key itself
# so it keeps working whatever the Job module renames.
ORIGINAL_TITLE_KEY = '_original_title'

# Where the other names for the job are kept on a row, stamped by find() beside the title and
# the Level. This module names the key itself, like the others, so it shares nothing.
ALSO_ROW_KEY = '_title_also'

# What separates the words of a title. A hyphen only between two letters; `+`, `#` and `.`
# are left alone because they are part of names -- C++, C#, .NET.
_WORD_SPLIT = re.compile(r'[\s/&,;:|()\[\]]+|(?<=[^\W_])-(?=[^\W_])')


def _word_pattern(word: str):
    """One word of the title, found at the start of a word in the internship's title."""
    starts_with_letter = re.match(r'[^\W_]', word) is not None
    ends_with_letter = re.search(r'[^\W_]$', word) is not None
    letters = re.sub(r'[\W_]', '', word)
    lead = r'(?<![^\W_])' if starts_with_letter else ''
    trail = r'(?![^\W_])' if ends_with_letter and len(letters) <= 3 else ''
    return re.compile(lead + re.escape(word) + trail, re.IGNORECASE)


@lru_cache(maxsize=64)
def _form_patterns(search_title: str, also: tuple = ()) -> tuple:
    """For each form of the title -- and of every other name for the same work -- the patterns for
    all of its words. `also` is what title_equivalents found for the title ("Machine Learning
    Engineer" for "Data Science"); without it this is the typed title and its twin, as it was."""
    forms = []
    seen = set()
    for name in (search_title,) + tuple(also):
        for form in title_forms(name):
            if form.lower() in seen:
                continue
            seen.add(form.lower())
            words = [word for word in _WORD_SPLIT.split(form) if re.search(r'[^\W_]', word)]
            forms.append(tuple(_word_pattern(word) for word in words))
    return tuple(forms)


def title_is_in_field(title, search_title=None, also=None) -> bool:
    """Does this title name the job being searched for -- or another name for it?

    A missing title is True, not False: a row with nothing to read is not evidence of
    anything, and this app never deletes on an absence.
    """
    text = ' '.join(str(title or '').split())
    if not text:
        return True
    return any(all(pattern.search(text) for pattern in form)
               for form in _form_patterns(clean_title(search_title), tuple(also or ())))


def row_is_in_field(row, search_title=None, also=None) -> bool:
    """The same question for a whole row: its title as posted, or as it was before
    translation. With no title at all it is kept."""
    wanted = search_title if search_title is not None else row.get(TITLE_ROW_KEY)
    also = also if also is not None else row.get(ALSO_ROW_KEY)
    titles = [title for title in (row.get('title'), row.get(ORIGINAL_TITLE_KEY))
              if str(title or '').strip()]
    if not titles:
        return True
    return any(title_is_in_field(title, wanted, also) for title in titles)


def remove_off_field(rows: list, search_title=None, also=None) -> tuple:
    """Drop the internships whose titles name some other job. Returns (kept, removed)."""
    kept: list = []
    removed: list = []
    for row in rows:
        (kept if row_is_in_field(row, search_title, also) else removed).append(row)
    return kept, removed
