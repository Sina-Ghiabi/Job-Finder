# -*- coding: utf-8 -*-
"""The filters Sina picks in the Filter window, applied to the pool.

These are different in kind from everything else in `filters.py`, and keeping them apart is
the point. Those rules read a posting and judge it -- is this remote, is it the right level,
does it demand a language he lacks. These ask a much simpler question: **did he ask for this
one?** A country he did not tick, a kind of role he did not want, a posting older than the
window he chose. No judgement, no reading, no cost.

WHY THIS MODULE EXISTS AT ALL

The Filter window offered ten choices and only three of them reached the pipeline. Level,
work mode and title were passed through; countries, cities, date range, résumé-match floor,
category and sponsorship were collected, hashed into the run's signature, and then silently
dropped. Sina picked Junior · Remote · Netherlands · Part-Time · Internship and got back
German full-time listings, because four of those five were never applied and the fifth --
the country -- was only ever consulted by the Not Remote place rule, which does nothing in a
Remote search.

That is L-2 again: code that exists, is correct, and is never called. The cure is the same
one -- put the call where it cannot be forgotten, and test that each choice changes the
answer.

"SILENCE SURVIVES", AND THE TWO PLACES IT DOES NOT

The standing rule is that a listing which does not say when it was posted, or what its visa
position is, is KEPT -- not knowing something is never evidence against a listing. The date
and sponsorship filters below follow it exactly.

Two do not, and both exceptions are deliberate and written down where they live:

  * **the country** (`filter_by_place`) -- Sina overruled it in as many words: "اگر نوشتم
    Netherlands یعنی فقط Netherlands میخوام". Name a chosen country or be removed.
  * **the kind of role** (`filter_by_category`) -- `categorize` has no "unknown"; a quiet
    listing is labelled Full-Time, and the filter agrees with the Type column rather than
    contradicting what Sina is looking at.
"""
from __future__ import annotations

from .geo import CITY_COUNTRY
from .posted import parse_posted_date
from .text import text_of

def _wanted_places(countries, cities) -> set:
    """The countries this run asked for, including the ones its chosen cities are in.

    A city selection stores no country -- Sina's Amsterdam run was cities=['Amsterdam'],
    countries=[] -- so the city's own country counts as asked for. Without this, picking a
    city and nothing else would remove every listing the search just paid for.
    """
    wanted = {str(c).strip().lower() for c in (countries or []) if str(c).strip()}
    for city in (cities or []):
        country = CITY_COUNTRY.get(str(city).strip())
        if country:
            wanted.add(country.lower())
    return wanted


def filter_by_place(jobs: list, countries=None, cities=None) -> tuple:
    """Keep the listings in a country Sina asked for. Returns (kept, removed).

    Unlike the Not Remote place rule in `filters.py`, this runs in **both** work modes,
    because it answers a different question. That rule asks "could he physically do this
    job"; this one asks "did he ask to see this country". A Remote search still has a
    country selection, and ignoring it is what made a Netherlands Remote filter return German
    listings.

    THIS IS THE ONE STRICT FILTER IN THE APP, AND SINA ASKED FOR IT IN THOSE WORDS

    "اگر نوشتم Netherlands یعنی فقط Netherlands میخوام". The first version of this had three
    escape hatches -- an empty country, a country field naming several places, and a board's
    "Worldwide"/"Europe" -- all of them kept on the usual "silence survives" reasoning. He
    overruled that, and counting the Bank showed the hatches were worth 309 rows out of the
    13,967 a Netherlands filter was keeping: they were not protecting much, and every one of
    them was a row he had not asked to see.

    So the rule is now: **name a country he asked for, or be removed.** A field listing
    several countries is read properly rather than waved through -- "Germany, Netherlands"
    names the Netherlands and stays; "USA, Canada, Mexico" does not and goes. A row that
    says nothing goes too, which is the one place this module departs from the rule the rest
    of it follows, and it departs on instruction.

    This applies only when he has actually chosen somewhere. No country and no city ticked
    means the whole pool passes through untouched.
    """
    wanted = _wanted_places(countries, cities)
    if not wanted:
        return jobs, 0
    kept = []
    for job in jobs:
        # A field naming several places is split and each one considered, so "Germany,
        # Netherlands" is judged on the Netherlands rather than on the comma.
        named = {part.strip().lower() for part in
                 str(job.get('country') or '').split(',') if part.strip()}
        if named & wanted:
            kept.append(job)
    return kept, len(jobs) - len(kept)


def filter_by_category(jobs: list, categories=None) -> tuple:
    """Keep only the kinds of role asked for -- Full-Time, Internship, Thesis and so on.

    The category is **computed here**, not read off the row, and that is the fix for a real
    fault: `reapply_filters` writes `Category` in its keyword step, which runs after this
    one, so reading the stored value meant reading whatever the Bank happened to hold from a
    previous run. Filtering for Part-Time and Internship returned Thesis and Full-Time rows,
    because the value being matched was replaced a moment later.

    Computing it makes this filter independent of where it sits in the pipeline, which is
    the property that stops the fault coming back if the steps are ever reordered.

    Nothing ticked means every kind, which is what the window says.

    **This is the one filter here that does not keep a silent listing**, and the exception
    is deliberate. `categorize` has no "unknown": a posting that says nothing about its kind
    comes back 'Full-Time', because that is the honest default and it is what the Jobs page
    already prints in the Type column. So the filter agrees with the column Sina is looking
    at -- ticking Part-Time removes the rows whose Type reads Full-Time, including the quiet
    ones. Keeping them instead would mean the window and the table disagreed about the same
    row, which is worse than either answer on its own.
    """
    wanted = {str(c).strip().lower() for c in (categories or []) if str(c).strip()}
    if not wanted:
        return jobs, 0
    from .rules import categorize
    kept = []
    for job in jobs:
        try:
            value = str(categorize(job) or '').strip().lower()
        except Exception:
            # A row categorize cannot read is not evidence against the row.
            value = text_of(job.get('Category')).strip().lower()
        if not value or value in wanted:
            kept.append(job)
    return kept, len(jobs) - len(kept)


def filter_by_sponsorship(jobs: list, sponsorship=None) -> tuple:
    """Keep listings whose sponsorship verdict is the one asked for.

    Only ever used with an explicit choice; the window's default is "Any", which returns
    everything untouched.
    """
    wanted = str(sponsorship or '').strip().lower()
    if not wanted:
        return jobs, 0
    kept = [job for job in jobs
            if not text_of(job.get('sponsorship_visa')).strip()
            or text_of(job.get('sponsorship_visa')).strip().lower() == wanted]
    return kept, len(jobs) - len(kept)


# How many days back each window reaches. The keys are the wizard's own option values, so
# the Filter window and the Search wizard cannot drift apart on what "pastWeek" means.
# 'anyTime' is deliberately absent: it is the window's default and means no date filter.
_DAYS_BACK = {'past24Hours': 1, 'pastWeek': 7, 'pastMonth': 30}


def is_a_date_window(date_range) -> bool:
    """Whether this date choice actually restricts anything.

    Asked by the Log, which must not announce a step for a choice of 'Any time'. Kept here
    rather than re-listing the keys at the call site, so there is one place that knows.
    """
    return str(date_range or '').strip() in _DAYS_BACK


def filter_by_date(jobs: list, date_range=None) -> tuple:
    """Keep listings posted inside the chosen window.

    A listing with no date is kept. That is not laziness: measured across the corpora, a
    large share of rows carry no date at all, and **not knowing when something was posted is
    not evidence that it is old.** The same rule already governs the date filter inside
    run_search.
    """
    days = _DAYS_BACK.get(str(date_range or '').strip())
    if not days:
        return jobs, 0
    from datetime import datetime, timedelta, timezone

    # parse_posted_date works in UTC and returns an aware datetime, but not every shape it
    # parses carries a zone -- a bare "2026-04-17" comes back naive. Comparing the two raises
    # TypeError, so a naive answer is read as UTC, which is the zone the rest of this already
    # assumes. Getting this wrong would not have been a wrong answer; it would have been a
    # crash in the middle of a Filter run.
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for job in jobs:
        when = parse_posted_date(job.get('posted_date'))
        if when is not None and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when is None or when >= cutoff:
            kept.append(job)
    return kept, len(jobs) - len(kept)


def filter_by_match(jobs: list, minimum=0) -> tuple:
    """Keep listings whose résumé match reaches the floor.

    Runs after Claude's second pass, since that is what produces the score. A listing with no
    score -- one Claude never reached, or a run with Claude switched off -- is kept: an
    absent number is not a low one.
    """
    try:
        floor = int(str(minimum or 0).strip() or 0)
    except ValueError:
        floor = 0
    if floor <= 0:
        return jobs, 0
    kept = []
    for job in jobs:
        score = job.get('claude_match')
        if not isinstance(score, int) or isinstance(score, bool) or score >= floor:
            kept.append(job)
    return kept, len(jobs) - len(kept)
