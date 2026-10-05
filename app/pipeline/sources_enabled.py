# -*- coding: utf-8 -*-
"""Which sources a search is allowed to use -- one table, read by the window and the search.

WHY

"میخوام در داخل Search برای هر Actor یک Checkbox بذاری که ما انتخاب کنیم که میخوایم از کدوم
Actor ها استفاده کنیم / چون Deep Crawl واقعا خیلی خیلی وقت میبره / میخوام برای همه از Indeed
تا API ها Check-box بذاری"

Until now only the four Apify platforms could be switched off. Everything else -- the Google
sub-stages and the thirteen direct sources -- ran whenever a search ran, with no way to say
no. Deep Crawl is the one that prompted this: it fetches up to fifteen pages per known-job-
board result through apify/website-content-crawler, and on a real Netherlands run it crawled
208 pages across 7 sites. It cost only $0.20, but it took longer than every other stage put
together, and time is the thing he cannot get back.

So this is a switch per source, and the same table drives the Search window's checkboxes and
the search's own decisions -- the pattern that actor_filters.py already uses for the filters,
and for the same reason: a box that does not reach the search is decoration, and a source
that cannot be switched off is a box that was never offered.

WHAT IS NOT HERE

The four Apify platforms -- indeed, glassdoor, linkedin, google. They have had their own
drag-to-reorder checklist in the Search window since long before this, saved as
`actor_order`, and run_search already honours it. Putting them here as well would give two
controls for one decision.
"""
from __future__ import annotations

SETTINGS_KEY = 'sources_enabled'

# Costs money (an Apify actor) rather than being a free JSON API. Shown in the window so a
# choice about time is also a choice about money, where it is one.
PAID = 'paid'
FREE = 'free'


class Source:
    """One switchable source: its key, how it reads in the window, and when it applies."""

    def __init__(self, key, label, group, scope, cost=FREE, default=True, hint=''):
        self.key = key
        self.label = label
        self.group = group
        # Which countries it can contribute to at all, for the window's own note. 'any'
        # means it is not tied to a country.
        self.scope = scope
        self.cost = cost
        self.default = default
        self.hint = hint


# THE GOOGLE STAGES ARE DELIBERATELY NOT HERE.
#
# Deep Crawl is the slow stage -- 208 pages across 7 sites on a real Netherlands run, longer
# than every other stage put together -- and the first version of this file gave it, and the
# two stages beside it, a switch each. Sina asked for one switch for Google instead: "نه پس
# برای Deep Crawl نمیخواد بذاری برای Google بذار".
#
# And Google already has that switch. It is one of the four platforms in the Search window's
# own drag-to-reorder checklist, saved as `actor_order`, and `run_google = 'google' in
# actor_order` gates the WHOLE phase -- the Google query, the known and startup sites, Deep
# Crawl and the URL-pattern discovery are all inside that one `if`. So unticking Google
# already stops Deep Crawl, and a second control here would have been two switches for one
# decision.

# ONE SWITCH FOR THE WHOLE DIRECT-API STAGE.
#
# This arrived at its shape by being narrowed twice. First it had a box per stage and per
# source -- nineteen of them. Then: a switch for the actors only. Then, finally: "برای اینایی
# که گفتی چک باکس نمیخوام فقط برای Google Indeed Glassdoor LinkedIn API ها" -- five switches
# in total, and the fifth is the APIs as one thing.
#
# So the four platforms keep the drag-to-reorder checklist they have always had, and this is
# the fifth box. Every direct source lives behind it: the eleven free JSON APIs, and the two
# that need an Apify actor because they have no public API and block outside traffic --
# werk.nl and workatastartup.com, which between them took $0.82 and about ten minutes of the
# 94-minute Netherlands run.
#
# The per-source gates stay in direct_api.py. is_enabled() answers True for any key this
# table does not carry, so they are harmless now and a single line here is all it would take
# to expose one of them later.
DIRECT_SOURCES = [
    Source('direct_apis', 'The direct APIs', 'direct', 'all countries', PAID,
           hint='EURES, Jooble, remotive.com, remoteok.com, arbeitnow.com, '
                'arbeitsagentur.de, arbetsformedlingen.se, reed.co.uk, '
                'francetravail.fr, swissdevjobs.ch, jobs.ch — all free — plus werk.nl '
                'and workatastartup.com, which need an Apify actor and so cost money '
                'and time. Measured on the Netherlands run: $0.82 and about ten '
                'minutes, almost all of it those two.'),
]

SOURCES = list(DIRECT_SOURCES)
BY_KEY = {source.key: source for source in SOURCES}

GROUP_LABELS = {
    'direct': 'Sources that run an Apify actor of their own',
}


def sources_in(group):
    return [source for source in SOURCES if source.group == group]


def defaults():
    """Everything on. A source switched off is a decision he makes, not one he inherits."""
    return {source.key: source.default for source in SOURCES}


def is_enabled(settings, key) -> bool:
    """May this source run?

    Defaults to TRUE for an unknown key and for a settings file that has never been
    through the new window. That direction matters: a search that silently stopped using
    half its sources after an update would look like the sources had broken, and this
    project has already lost weeks to a filter that removed more than anyone realised.
    """
    source = BY_KEY.get(key)
    saved = (settings or {}).get(SETTINGS_KEY)
    if not isinstance(saved, dict):
        return True if source is None else bool(source.default)
    if key not in saved:
        return True if source is None else bool(source.default)
    return bool(saved[key])


def disabled_names(settings) -> list:
    """The labels of everything switched off, for one honest line in the Log."""
    return [source.label for source in SOURCES if not is_enabled(settings, source.key)]
