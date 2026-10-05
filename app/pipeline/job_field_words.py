# -*- coding: utf-8 -*-
"""Does this listing's title name the job the user is searching for? — the Job module's own copy.

A copy, on purpose, and kept beside the Job module's own rules. The user's rule for the three
modules is that they share nothing, and that rule is what this file obeys: the Internship and
Thesis modules each carry their own copy of this check, and tuning one cannot move another.
The only thing the three agree on is the title itself (app/pipeline/search_title.py).

THE TITLE SINA TYPES IS THE FIELD

Until the job title box existed, this file was a hand-written list of about 150 field words
in thirteen languages -- DevOps, platform, infrastructure, data, software, Informatik,
données. The user replaced it with one name: [owner's note: one typed title must take the place of all of these]. So a listing is in the field when its title names that job, and only then.
The word list is kept out of the public repository.

HOW A TITLE "NAMES" THE JOB

Every word of the title, in any order, each at the start of a word. For "Data Engineering"
(and its twin "Data Engineer"):

    Data Engineer (m/w/d)                    kept
    Senior Data Engineer - Microsoft Fabric  kept
    Software Engineer - Data (All Genders)   kept     any order
    Data (Platform) Engineer im Databricks   kept     words in between
    Data Scientist (m/w/d)                   dropped  a different job
    Data Architect (w/m/d)                   dropped

Measured on the real German job run (8,801 listings): "Data Engineering" keeps 1,262, and
the listings sharing the word "data" that it drops are Data Scientist, Data Analyst and Data
Architect. The old field words kept 7,649 of the same 8,801, nearly all of them for Claude
to read and pay for.

Each word only has to START a word, so "Engineer" also finds "Engineers" and "Engineering".
A word of three letters or fewer has to END one too: "AI" must not find "Airflow", nor "ML"
"MLOps".

The title alone, never the description -- measured at every turn in this project: a title
says what the job IS, a description sells the company, and almost every one mentions data.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .search_title import ROW_KEY as TITLE_ROW_KEY, clean_title, title_forms

# Where the untranslated title is kept, when there is one. Either title naming the job is
# enough: they are the same heading in two languages.
ORIGINAL_TITLE_KEY = '_original_title'

# What separates the words of a title. A hyphen only between two letters, so "Data-Engineer"
# is two words while a leading "-" is nothing. `+`, `#` and `.` are left alone, because they
# are part of names -- C++, C#, .NET.
_WORD_SPLIT = re.compile(r'[\s/&,;:|()\[\]]+|(?<=[^\W_])-(?=[^\W_])')


def _word_pattern(word: str):
    """One word of the title, found at the start of a word in the listing's title."""
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


def title_is_in_field(title, search_title=None, also=None) -> bool:
    """Does this title name the job being searched for?

    A missing title is True, not False: a row with nothing to read is not evidence of
    anything, and this app never deletes on an absence.

    `also` is the other names employers give the same work -- see title_equivalents. Without
    it this is exactly the rule it has always been: every word of the typed title, and
    nothing else counts.
    """
    text = ' '.join(str(title or '').split())
    if not text:
        return True
    for name in [clean_title(search_title)] + [n for n in (also or []) if str(n).strip()]:
        if any(all(pattern.search(text) for pattern in form)
               for form in _form_patterns(name)):
            return True
    return False


def row_is_in_field(row, search_title=None, also=None) -> bool:
    """The same question for a whole row: its title as posted, or as it was before
    translation. With no title at all it is kept."""
    wanted = search_title if search_title is not None else row.get(TITLE_ROW_KEY)
    titles = [title for title in (row.get('title'), row.get(ORIGINAL_TITLE_KEY))
              if str(title or '').strip()]
    if not titles:
        return True
    return any(title_is_in_field(title, wanted, also) for title in titles)


FIELD_MATCHED_AS_KEY = 'field_matched_as'
FIELD_SIMILARITY_KEY = 'field_similarity'


def matched_title(row, search_title=None, also=None):
    """Which of the searched titles this listing's own title names, or None.

    The typed title is tried first, so a listing that names it is credited to it rather than
    to whichever equivalent also happens to fit. That ordering is what makes the Similarity
    column readable: the number beside a row is the closest title that found it, not an
    accident of list order.
    """
    wanted = search_title if search_title is not None else row.get(TITLE_ROW_KEY)
    titles = [title for title in (row.get('title'), row.get(ORIGINAL_TITLE_KEY))
              if str(title or '').strip()]
    if not titles:
        return None
    for name in [clean_title(wanted)] + [n for n in (also or []) if str(n).strip()]:
        if any(title_is_in_field(title, name) for title in titles):
            return name
    return None


def stamp_field_match(rows: list, search_title=None, also=None, scores=None) -> None:
    """Write onto every row which searched title found it, and how similar that title is.

    Two columns in the Jobs table read these, and one of them decides the order the user sees:
    [owner's note: whatever is shown must be ordered by highest similarity]. The typed title scores 100
    -- it is what he asked for -- and each equivalent carries the score Claude gave it.

    A row whose title says nothing is credited to the typed title at 100 rather than left
    blank. It was kept because silence is not evidence, and a blank Similarity would sort it
    to the bottom as though it had been judged and found wanting.
    """
    typed = clean_title(search_title)
    by_title = {str(k).lower(): v for k, v in (scores or {}).items()}
    for row in rows:
        found = matched_title(row, typed, also)
        row[FIELD_MATCHED_AS_KEY] = found or typed
        row[FIELD_SIMILARITY_KEY] = (100 if not found or found.lower() == typed.lower()
                                     else int(by_title.get(found.lower(), 100)))


def remove_off_field(rows: list, search_title=None, also=None) -> tuple:
    """Drop the listings whose titles name some other job. Returns (kept, removed).

    `search_title` is the title in the Search box; without it each row's own stamped title
    is used, and without that the default.

    `also` widens what counts as the field, and it is the fix for the worst measurement in
    this project: asked literally, this rule removed 7,737 of 8,768 real listings, and 56% of
    a sample of those removals were genuine data-science jobs whose titles said "AI Engineer"
    or "Machine Learning Engineer" instead. Because this step runs before everything, those
    listings never reached Claude and the mistake could not be undone later.
    """
    kept: list = []
    removed: list = []
    for row in rows:
        (kept if row_is_in_field(row, search_title, also) else removed).append(row)
    return kept, removed
