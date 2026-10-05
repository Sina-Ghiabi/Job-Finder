# -*- coding: utf-8 -*-
"""The Internship module -- one of the three parallel tracks a Filter run drives.

    app/pipeline/filters.py + rules.py + country_rules.py    the Job module
    app/pipeline/thesis/                                     the second
    app/pipeline/internship/                                 this one

They share no vocabulary, no rules and no helpers, by the user's instruction, and each is handed
its own copy of the listings so none can see another's edits. Merging any two of them back
together to save duplication is the failure this arrangement exists to prevent.
"""
from .finder import (  # noqa: F401
    find,
    is_internship,
    passes_location_rule,
    remove_duplicates,
    survives,
)
from . import claude  # noqa: F401
from . import words  # noqa: F401

__all__ = [
    'find',
    'is_internship',
    'passes_location_rule',
    'remove_duplicates',
    'survives',
    'claude',
    'words',
]
