"""run_search itself -- the plan, the worker threads, and the progress counter."""
from __future__ import annotations

import collections
import functools
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
import anthropic
import pandas as pd
from apify_client import ApifyClient
from ..errors import SearchCancelled
from .. import fetcher
from ..enrich import (enrich_thin_descriptions)
from ..pages import (EMPTIED_KEY, _ALREADY_HAD_KEY as ALREADY_HAD_KEY,
                     expand_listing_pages, remove_dead_postings, remove_listing_pages)
from ..posted import max_age_from_date_settings, remove_stale
from ..search_title import (clean_level, clean_title, clean_work_mode,
                            is_not_remote, title_forms)
from ..sources_norm import unmirror_markdown_row
from ..geo import COUNTRIES, COUNTRY_ISO2
from ..language import english_requirement_of
from ..rules import CATEGORY_ORDER, categorize, seniority_of
from ..language import _LANG_CACHE_KEY, _LANG_CACHE_TEXT_KEY, _detect_language_pair, is_category_uncertain
from ..sponsorship import NO_SPONSORSHIP_PROCESS_COUNTRIES
from ..apify import ActorRunFailed, DEFAULT_ACTOR_ORDER, GLASSDOOR_ACTOR, INDEED_ACTOR, LINKEDIN_ACTOR, _APIFY_CREDIT_POLL_SECONDS, _get_default_dataset_id
from ..preflight import explain_problems
from .. import actor_filters
from .. import checkpoint
from ..sources_apis import _fetch_apify_credit_label
from ..sources_norm import (LINKEDIN_DATE_TO_WINDOW, normalize_glassdoor, normalize_indeed,
                            normalize_linkedin_pro)

from .google_phase import (_run_google_phase)


# How many selected platforms (Indeed/LinkedIn/Glassdoor) run_search runs in parallel at
# once -- each platform is one long-running unit that works through its own selected
# countries/cities sequentially and gets its own header+timer line in the Log. Sina
# asked for every selected platform to run in parallel with its own visible progress
# (not one shared queue), batched 2 at a time (a 3rd/4th/5th platform starts as soon as
# a slot frees up). Kept at 2, not higher, because of a real, previously-hit failure:
# launching 3 actor calls in parallel once exceeded this Apify account's
# concurrent-memory limit ("you will exceed the memory limit of 16384MB for all your
# Actor runs and builds (currently used: 16384MB, requested: 8192MB)") -- 2 actors of
# that size fit, a 3rd doesn't. Raise only if the Apify plan's memory limit goes up.
SEARCH_MAX_CONCURRENT_PLATFORMS = 2


# What `limit_per_call` becomes when the wizard's cap is switched off. Sina's instruction --
# "هیچ Limit ای نباید در پیدا کردن آگهی باشد" -- and the German run is why he gave it:
# LinkedIn and Glassdoor each returned exactly 100 listings, the saved cap to the item, so
# both had more to give and neither said so.
#
# Not infinity, because every one of these fields has to be a number the actor accepts. High
# enough that no real country search reaches it: the largest single platform+country result
# measured anywhere in this project is a few thousand.
NO_RESULT_LIMIT = 100000

# ...except where an actor publishes a ceiling of its own, and two of the three do. Read from
# their own input schemas rather than guessed:
#
#   valig/indeed-jobs-scraper      limit  maximum 1000
#   valig/glassdoor-jobs-scraper   limit  maximum 1000
#   apimaestro/linkedin-jobs-scraper-api  limit     maximum 100 PER PAGE -- not a total, so it
#                                         is not in the table below; _run_linkedin_pages walks pages
#
# Sending more is not trimmed to the maximum by the actor, it is refused: "Field input.limit
# must be <= 1000", and the entire leg is lost before it starts. Asking for no limit at all
# is what broke Glassdoor, so the instruction and the actor are reconciled here -- the same
# way DATE_RANGES gives each platform its own furthest reach instead of a value it rejects.
_ACTOR_RESULT_CEILING = {'indeed': 1000, 'glassdoor': 1000}


def _actor_limit(platform: str, requested: int) -> int:
    """What to ask this actor for: what Sina chose, or the actor's own maximum."""
    ceiling = _ACTOR_RESULT_CEILING.get(platform)
    return min(requested, ceiling) if ceiling else requested


# =========================================================================================
# THE FIELD: ONE TITLE, TYPED BY SINA
# =========================================================================================
#
# The field used to be written out here by hand -- data science first, then DevOps and
# MLOps, eighteen terms in the broad query and eighteen more for entry level. Moving between
# the two took a day. Sina asked for the field to be one name he types, and for everything
# else to be built from it; see search_title.py for the name and its forms.
#
# WHAT IS KEPT FROM BEFORE is the measurement that shapes every query below: across 17,544
# real European titles, a job title in this field is never translated. "DevOps" appeared 273
# times and every local form tried appeared zero times; "Data Engineer" appeared 821 times in
# German adverts against 1 "Dateningenieur". A German employer writes the English title and
# German around it. So the title is sent in English everywhere, and what the local passes add
# is the local word for a beginner and for an internship -- the half that IS translated.


# The vocabulary moved to queries.py -- see its docstring. Imported here rather than
# referenced through the module, so every call site below reads exactly as it did when these
# were defined in this file, and so a test that patches one still patches what run_search
# calls.
from .queries import (
    SEARCH_PASSES,
    _PRECISE_REPLACES_BROAD,
    country_of_location,
    keywords_for,
    terms_for_pass,
)


# The kinds whose own module decides Remote, so the actor is never asked for remote-only.
_KINDS_WITH_THEIR_OWN_REMOTE_RULE = ('thesis', 'internship')
# The actor parameter that carries "remote or not" on each platform. Indeed has none.
_WORKPLACE_PARAMETER = {'linkedin': ('remote',), 'glassdoor': ('remoteWorkType',)}

DEFAULT_SEARCH_PASSES = ('job',)
DEFAULT_SEARCH_LANGUAGES = ('en',)

# What the wizard sends: once in English, once in the country's own language.
ALL_SEARCH_LANGUAGES = ('en', 'local')


class _SearchProgress:
    """The done/total counter for one search, together with the lock that guards it.

    Several platform threads advance this at once. It used to be a plain int mutated
    through `nonlocal` plus a separately-declared `done_lock` -- correct, but it meant
    run_search's helpers could only ever be nested functions (nothing else can reach a
    `nonlocal`), so none of them could be tested on their own. Keeping the counter and
    its lock in one object fixes both: the pairing is now structural, and the helpers
    can take this as an ordinary argument.

    Only ever read to report progress -- nothing in the search decides anything from it.
    """

    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self._lock = threading.Lock()

    def advance(self, n: int = 1) -> int:
        with self._lock:
            self.done += n
            return self.done


# The three helpers below used to be nested inside run_search. They were only nested
# because run_search's progress counter was a `nonlocal` int, which nothing outside a
# closure can reach; now that it is a _SearchProgress object they take it as an ordinary
# argument. Being module-level makes them individually testable, which is the whole point
# -- a wrong actor call or a mis-sorted platform result can now be reproduced without
# standing up an entire search.


def _poll_apify_credit_impl(client, progress_cb, _credit_poll_stop):
    while not _credit_poll_stop.wait(_APIFY_CREDIT_POLL_SECONDS):
        if progress_cb:
            progress_cb(f"TOKEN_CHECK_ITEM:{_fetch_apify_credit_label(client)}|OK", 0, 1)


# A pay-per-event actor reports NOTHING at the moment its run ends: usageTotalUsd is 0 and even
# chargedEventCounts is 0, and the real figure arrives about twelve seconds later. Measured on
# apimaestro/linkedin-jobs-scraper-api -- a 10-row run read 0, 0, 0, 0, 0, 0 at 2-second
# intervals and then $0.05. The app read the run once, at the moment it ended, so the Log
# printed "$0.00" for every LinkedIn call while the account was being charged $0.005 a row.
# That is the O-2 fault (the Log must say what happened) and it is also how the price of this
# actor was first misreported to Sina: the same field, read at the same wrong moment.
_USAGE_SETTLE_SECONDS = 45
_USAGE_POLL_SECONDS = 3


def _settled_usage(client, run_id, run_info, usage_usd, bought_rows, should_cancel=None):
    """The cost of a finished run, waiting for it to settle when the actor bills per event.

    A run that already reports a cost is returned as it is. A pay-per-event run is recognised by
    carrying `chargedEventCounts` at all (the older per-compute actors do not), and is only
    waited on when it actually returned rows -- a run that bought nothing really cost nothing.

    If the figure has not settled in _USAGE_SETTLE_SECONDS the answer is None, which the Log
    prints as blank. UNKNOWN, never 0: a false $0.00 is exactly the error being fixed.
    """
    if usage_usd:
        return usage_usd
    charged = run_info.get('chargedEventCounts') if isinstance(run_info, dict) else None
    if charged is None or not bought_rows:
        return usage_usd
    deadline = time.time() + _USAGE_SETTLE_SECONDS
    while time.time() < deadline:
        if should_cancel and should_cancel():
            return None
        time.sleep(_USAGE_POLL_SECONDS)
        info = client.run(run_id).get()
        value = (info.get('usageTotalUsd') if isinstance(info, dict)
                 else getattr(info, 'usage_total_usd', None))
        if value:
            return value
    return None


def _run_actor_and_fetch(client, limit_per_call, should_cancel,
                         actor_id, run_input, log_prefix, memory_mbytes=None, item_limit=None):
    # item_limit defaults to limit_per_call (the wizard's "result limit per search"),
    # which is right for Indeed/LinkedIn/Glassdoor, where one dataset item IS one
    # job. It is explicitly overridden for the Google Search actor, where one dataset
    # item is a whole PAGE of results: a real full search builds 90 query lines x
    # maxPagesPerQuery 3 = 270 page items, so a limit of e.g. 100 silently discarded
    # 170 of them -- and since the queries are ordered country by country, that meant
    # dropping the LAST locations entirely rather than trimming each one evenly.
    effective_limit = limit_per_call if item_limit is None else item_limit
    # memory_mbytes is only ever passed for the main Google Search actor call
    # below -- never for Indeed/LinkedIn/Glassdoor, which can run two at a time via
    # SEARCH_MAX_CONCURRENT_PLATFORMS and would each try to claim the full account
    # memory cap at once if this were unconditional, which the account doesn't
    # have room for. Google's own call is always the ONLY actor running at that
    # point (executor.shutdown(wait=True) above already waited for every other
    # platform to finish first), so it's safe to hand it the same full-cap boost
    # _deepen_google_results/_run_direct_site_searches already use.
    kwargs = {'memory_mbytes': memory_mbytes} if memory_mbytes else {}
    run = client.actor(actor_id).start(run_input=run_input, **kwargs)
    run_id = run.get('id') if isinstance(run, dict) else getattr(run, 'id', None)
    if not run_id:
        raise RuntimeError(f"could not start actor run: {run!r}")

    poll_interval = 4
    run_info = run
    while True:
        run_info = client.run(run_id).get()
        status = run_info.get('status') if isinstance(run_info, dict) else getattr(run_info, 'status', None)
        if status in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT', 'TIMED_OUT'):
            break
        if should_cancel and should_cancel():
            try:
                client.run(run_id).abort()
            except Exception:
                pass
            raise SearchCancelled()
        time.sleep(poll_interval)

    # Real cost Apify actually billed for this run, confirmed via Apify's own API
    # docs (present once the run reaches a terminal state, even a failed one --
    # Apify still bills for compute already spent) -- never estimated/guessed.
    usage_usd = run_info.get('usageTotalUsd') if isinstance(run_info, dict) else getattr(run_info, 'usage_total_usd', None)

    if status != 'SUCCEEDED':
        status_message = run_info.get('statusMessage') if isinstance(run_info, dict) else getattr(run_info, 'status_message', None)
        raise ActorRunFailed(
            f"run ended with status {status}" + (f": {status_message}" if status_message else ""),
            usage_usd=usage_usd,
        )

    dataset_id = _get_default_dataset_id(run_info)
    if not dataset_id:
        raise ActorRunFailed(f"could not find dataset id on run object: {run_info!r}", usage_usd=usage_usd)
    items = list(client.dataset(dataset_id).iterate_items(limit=effective_limit))
    usage_usd = _settled_usage(client, run_id, run_info, usage_usd, bool(items), should_cancel)
    return items[:effective_limit], usage_usd


# The actor rewrites a boolean search into a semantic one unless told not to, and its own
# default is to do it. Measured on 300 real Netherlands rows, same query, everything else
# held still: with the rewrite on, 17% of titles contained one of the phrases the query
# asked for; with it off, 25%. The two result sets overlapped by only 59%, so this is a
# genuinely different search rather than a reordering.
#
# Sent as a constant and deliberately NOT offered in the Search window: Sina's instruction
# when the measurement came in -- "اگر واقعا کار میکنه فعالش کن و اصلا نذارش داخل Search
# Field". A boolean query is what the rest of this module builds, phrase by phrase, so
# having it honoured is not a preference.
_LINKEDIN_KEEP_THE_QUERY_LITERAL = False


def _linkedin_request(keywords, loc_type, location, row_country, limit_per_call,
                      date_settings, not_remote=False):
    """What LinkedIn is asked, for one location -- one shape, and a real remote filter.

    THIS USED TO BE TWO SHAPES AND NEITHER FILTERED ANYTHING. The old actor took either a
    search URL carrying f_WT=2 or plain keywords, and f_WT was measured IGNORED: the same URL
    without it returned the identical 300 jobs. So the premise of every Remote search -- that
    Sina works from home in Turin -- never reached LinkedIn, and every office job in the
    country was bought at $0.002 a row and then guessed at from prose. (The replacement
    charges $0.005 a row -- more per row, but only Remote rows come back.)

    apimaestro/linkedin-jobs-scraper-api has `remote`, and it is honoured: measured, 100 of
    100 rows tagged Remote with it, and only 43 ids in common with the unfiltered run, so it
    searches deeper for remote jobs rather than trimming the same list. It also returns each
    row's own workplace tag (`work_type`), which is what the Work Location rule reads first.

    WITHOUT A WINDOW, REMOTE FOLLOWS THE WORK MODE. With the Search window's settings in hand
    (which is every real run) _actor_request throws this value away and sends the window's
    "Workplace Type" exactly as it was chosen -- see there. This default is what a request built
    with no settings has always been, and it is what every test written before the window had a
    say still reads. It is a recall setting, not a decision: the actor shows only ~200 rows per
    query, and unfiltered they are mostly Hybrid and On-site -- measured, 42 Remote in 180 rows
    against 45 when asked for Remote alone. Nothing is deleted at the actor and every row
    carries its own tag.

    It is sent in a Remote search outside Italy and nowhere else. `remote` takes ONE value, so
    a Not Remote search cannot ask for "everything but remote"; and Italy holds Turin and
    Milan, where he can reach an office and where a filter that is honoured would hide
    exactly the on-site jobs he wants (the old actor's f_WT did that for city searches too,
    invisibly, because it did nothing).

    The posted-time window and the boolean query are both honoured: OR/quotes are parsed
    (100 of 100 titles contained a phrase from a three-phrase OR query, against 5 of 15 when
    the same words were joined by spaces), and `date_posted` was measured at day / week /
    month. `limit` is a PAGE size here, 100 at most, and _run_linkedin_pages walks the pages.
    """
    linkedin_location = (
        location if loc_type == 'country'
        else f"{location}, {row_country}" if row_country else location
    )
    run_input = {
        "keywords": keywords,
        "location": linkedin_location,
        "limit": _LINKEDIN_PAGE_SIZE,
    }
    window = LINKEDIN_DATE_TO_WINDOW.get(date_settings.get('linkedin') or '', '')
    if window:
        run_input["date_posted"] = window
    if not not_remote:
        run_input["remote"] = "remote"
    return run_input


# One call returns at most 100 rows -- the actor's own `limit` maximum -- and a second call
# with page_number=2 returns the next. Measured on one real query with the remote filter on:
# page 1 gave 100, page 2 gave 55, page 3 gave 0. A page shorter than the page size is the
# last page, which is how _run_linkedin_pages knows when to stop, and the ceiling below is a
# guard against a runaway loop rather than a limit anyone should reach: 30 pages is 3,000
# rows, and LinkedIn itself stops showing results well before that.
_LINKEDIN_PAGE_SIZE = 100
_LINKEDIN_MAX_PAGES = 30


def _run_linkedin_pages(run_actor_and_fetch, actor, run_input, log_prefix, note=None):
    """Every page of one LinkedIn search, de-duplicated, as (rows, total cost in USD).

    There is no cap parameter here any more. The window's "Results limit" is the actor's own
    `limit`: under 100 it asks for that many in ONE call and a page shorter than the page size
    is the last page, so the walk stops by itself; "Max" sends nothing and every page is walked.

    The first page failing is an ordinary failure and propagates, exactly as a single-call
    actor does. A LATER page failing keeps what was already fetched and paid for, and says so
    through `note` -- losing 100 paid rows to a hiccup on page 2 would be a bill with nothing
    to show for it, and swallowing the reason would be the O-2 fault in another costume.
    """
    run_input = dict(run_input)
    rows: list = []
    seen: set = set()
    spent = 0.0
    for page in range(1, _LINKEDIN_MAX_PAGES + 1):
        try:
            items, usage = run_actor_and_fetch(
                actor, dict(run_input, page_number=page), log_prefix)
        except SearchCancelled:
            raise
        except Exception as exc:
            if page == 1:
                raise
            if note:
                note(f"ERROR: {log_prefix} page {page} failed ({exc}) — kept the "
                     f"{len(rows)} rows already fetched")
            break
        spent += usage or 0.0
        fresh = [item for item in items if item.get('job_id') not in seen]
        seen |= {item.get('job_id') for item in items}
        rows += fresh
        if len(items) < _LINKEDIN_PAGE_SIZE:
            break
    return rows, (spent or None)


def _indeed_request(keywords, loc_type, location, row_country, limit_per_call,
                    date_settings, not_remote=False):
    """What Indeed is asked: an ISO2 country, plus a free-text location for a city.

    The actor's schema allows lower case only. All 18 entries in COUNTRY_ISO2 are already
    lower case, so `.lower()` changes nothing today -- it is here so that adding a
    nineteenth country as 'GB' cannot silently lose the whole Indeed leg.
    """
    run_input = {
        "country": COUNTRY_ISO2.get(row_country or '', '').lower(),
        "title": keywords,
        "limit": _actor_limit('indeed', limit_per_call),
        "datePosted": date_settings['indeed'],
    }
    if loc_type == 'city':
        run_input["location"] = location
    return run_input


def _glassdoor_request(keywords, loc_type, location, row_country, limit_per_call,
                       date_settings, not_remote=False):
    """What Glassdoor is asked. Its location field takes a city, state or country name
    directly, so no separate country field is needed either way.

    remoteWorkType IS A REAL FILTER, and it is the only one in this app that is. Measured on
    the same Netherlands query, everything else held still: without it, 300 rows, 84% of the
    titles in his field; with it, 15 rows, 100% in his field. LinkedIn's f_WT was tested the
    same way and returned the identical 300 jobs with and without, so nothing filters for
    remote work at LinkedIn's end -- this is where the premise of the whole search can
    actually be enforced.

    That matters for the bill as well as the results. Glassdoor charged $0.0000 for those
    300 rows; LinkedIn charges $0.002 each, $2.00 for a thousand. So the one source that can
    refuse office work before counting it is also the cheap one, and the expensive one is
    being paid to return jobs the Work Location rule then deletes.

    Not sent in the two cases that have always been exceptions, for the same reason the
    LinkedIn URL has them: a Not Remote search wants the opposite, and Italy holds Turin and
    Milan, where he can reach an office.
    """
    run_input = {
        "keywords": keywords,
        "location": location,
        "limit": _actor_limit('glassdoor', limit_per_call),
        "daysOld": date_settings['glassdoor'],
    }
    if not not_remote:
        run_input["remoteWorkType"] = True
    return run_input


# One entry per paid platform: how to ask it, and how to read what comes back. Adding a
# fourth actor is a line here and a function above, rather than another branch inside the
# function that runs them -- which is what this table replaced.
_PLATFORM_REQUESTS = {
    'linkedin': (LINKEDIN_ACTOR, _linkedin_request, normalize_linkedin_pro),
    'indeed': (INDEED_ACTOR, _indeed_request, normalize_indeed),
    'glassdoor': (GLASSDOOR_ACTOR, _glassdoor_request, normalize_glassdoor),
}


def _actor_request(platform, keywords, loc_type, location, row_country, limit_per_call,
                   date_settings, not_remote=False, settings=None, skip_remote=False):
    """(actor id, run input, normaliser) for one platform and one location.

    `not_remote` is the work mode Sina chose. Only Glassdoor's request really acts on it --
    it has the one working remote filter of the three -- but every builder takes it so the
    table can call them all the same way.

    `settings` carries the per-actor filters he picked in the Search window. They are
    applied LAST and only ever add or replace a key, so a call without them produces exactly
    what this function produced before they existed -- which is what keeps every test
    written against these builders correct.
    """
    actor, build, normalize = _PLATFORM_REQUESTS.get(
        platform, _PLATFORM_REQUESTS['glassdoor'])
    run_input = build(keywords, loc_type, location, row_country, limit_per_call,
                      date_settings, not_remote or skip_remote)
    built_place = run_input.get('location')   # Indeed: the city, which "remote" replaces
    if settings:
        # THE WINDOW'S VALUE IS THE VALUE SENT. The builders derive a remote filter from the work
        # mode, which is right for a request built with no window and wrong the moment there is
        # one: a dropdown that says Hybrid must send hybrid, and one that says Any must send
        # nothing. Sina: "بعد هر انتخابی که کردم اونجا مستقیما در مقدار پارامتر مربوطه به اون
        # Actor قرار داده بشه". So what the builder derived is discarded and the dropdown's own
        # value goes in, through apply_to_request, exactly as chosen.
        for derived in _WORKPLACE_PARAMETER.get(platform, ()):
            run_input.pop(derived, None)
        actor_filters.apply_to_request(run_input, settings, platform)
    # THE ONE EXCEPTION, stated rather than hidden: the thesis and internship passes. They are
    # almost never remote and have their own modules with a Remote rule that lets silence
    # through; asked for remote-only first, LinkedIn and Glassdoor returned nothing for either
    # (Document T-19). `skip_remote` is how the caller says so. There is no exception for any
    # place: Remote means Remote in Italy, Turin and Milan as everywhere else.
    # Everywhere else the dropdown's value is the value sent.
    if skip_remote:
        for derived in _WORKPLACE_PARAMETER.get(platform, ()):
            run_input.pop(derived, None)
        if platform == 'indeed' and run_input.get('location') == 'remote':
            # Indeed's remote switch IS its location: put the searched place back, or drop it.
            if built_place is None:
                run_input.pop('location', None)
            else:
                run_input['location'] = built_place
    return actor, run_input, normalize


def _process_plan_item(run_actor_and_fetch, progress, date_settings, limit_per_call,
                       progress_cb, should_cancel, title, level, kind, language, shape,
                       platform, loc_type, location, not_remote=False, also=None,
                       settings=None):
    if should_cancel and should_cancel():
        # Guards against a queued (not-yet-started) item that a worker thread picks
        # up right as cancellation is requested -- without this, it would still
        # start (and pay for) a brand-new Apify actor run before its own polling
        # loop inside run_actor_and_fetch got a chance to notice should_cancel().
        raise SearchCancelled()

    # For a city, the row's 'country' field is still the real country (for the
    # country column, Excel export, etc.) -- only the search itself targets the city.
    row_country = country_of_location(loc_type, location)
    # Built here rather than passed in, because a local-language query depends on the
    # country this item is for: Germany asks in German, Sweden in Swedish. None means this
    # country has nothing to ask in this language -- an English-speaking country has no
    # local pass -- and the item is skipped rather than sent an empty query.
    # A precise pass on a platform that ignores quoted phrases would be a second full-price
    # call for the same 1,000 rows, so on those platforms the precise query REPLACES the
    # broad one instead of joining it -- see _PRECISE_REPLACES_BROAD.
    # An Any search has no seniority, and the precise job query is nothing BUT seniority words
    # ("Junior Data Scientist" OR "Entry Level …"), so there is nothing left of it to ask. The
    # broad query still runs, and so do the internship and thesis passes in full. Measured on
    # 20 rows per platform: that precise query returned 1-3 rows, and none for Mid.
    if kind == 'job' and level == 'any' and shape == 'precise':
        progress.advance()
        return []
    if platform in _PRECISE_REPLACES_BROAD and kind != 'job':
        if shape == 'broad':
            progress.advance()
            return []
        shape = 'precise'
    keywords = keywords_for(kind, row_country, language, shape, title=title, level=level,
                            also=also)
    if not keywords:
        progress.advance()
        return []

    if progress_cb:
        progress_cb(f"LOCATION_START:{platform.capitalize()}|{location}", progress.done, progress.total)

    log_prefix = f"{platform.capitalize()}/{location}"
    usage_usd = None
    try:
        # A thesis or an internship is never asked for remote-only at the actor. They are almost
        # never remote, and their own modules decide Remote with a rule that lets silence
        # through; a filter applied first removes what those modules would have kept. Measured:
        # with it, LinkedIn and Glassdoor returned 0 rows for both kinds; LinkedIn without it
        # returned 9 internships for the same query. `not_remote` is how the request builders
        # are told to send no remote filter, so it is reused rather than a second switch added.
        actor, run_input, normalize = _actor_request(
            platform, keywords, loc_type, location, row_country, limit_per_call,
            date_settings, not_remote, settings,
            skip_remote=kind in _KINDS_WITH_THEIR_OWN_REMOTE_RULE)
        if platform == 'linkedin':
            # One search is several pages here, because the actor returns at most 100 rows a call.
            items, usage_usd = _run_linkedin_pages(
                run_actor_and_fetch, actor, run_input, log_prefix,
                note=(lambda message: progress_cb(message, progress.done, progress.total))
                if progress_cb else None)
        else:
            items, usage_usd = run_actor_and_fetch(actor, run_input, log_prefix)
        if progress_cb:
            cost = f"{usage_usd:.2f}" if usage_usd is not None else ''
            progress_cb(f"LOCATION_DONE:{platform.capitalize()}|{location}|SUCCESS|{cost}", progress.done, progress.total)
    except SearchCancelled:
        raise
    except Exception as e:
        usage_usd = getattr(e, 'usage_usd', None)
        if progress_cb:
            cost = f"{usage_usd:.2f}" if usage_usd is not None else ''
            progress_cb(f"LOCATION_DONE:{platform.capitalize()}|{location}|FAILED|{cost}", progress.done, progress.total)
            # The reason, as an ERROR line rather than an indented aside.
            #
            # It used to go out as "  ! Indeed/Germany failed: …", which reaches the Log as
            # an ordinary grey line among hundreds of progress ticks, and twice that was
            # enough to hide a real fault for hours. The actor's own complaint is always
            # specific and always actionable -- "Field input.limit must be <= 1000", "Field
            # input.datePosted must be equal to one of the allowed values" -- and it names
            # the field, the value and the alternatives. Losing that costs a whole platform
            # for a whole run, silently: a German search finished with no Indeed and no
            # Glassdoor results and said nothing about why.
            progress_cb(f"ERROR: {platform.capitalize()} found nothing for {location} — "
                        f"{e}", progress.done, progress.total)
        items = []
        normalize = None

    item_rows = []
    if normalize:
        for item in items:
            normalized = normalize(item)
            normalized['platform'] = platform
            normalized['country'] = row_country
            item_rows.append(normalized)
    return item_rows


def _build_search_plan(actor_order, countries, cities):
    """Every (platform, location_type, location) the dedicated actors should run.

    Returns (plan, run_google, total). Pure, and deliberately so: this is where the
    location-scoping rules live, including the cities-only case that the suite guards --
    selecting only a city must produce ONE call for that city, not one per country.

    Google is excluded from `plan` on purpose: it is one combined call for the whole
    run, not one per location, so it is counted separately in `total`.
    """
    plan = []
    for platform in actor_order:
        if platform == 'google':
            continue  # handled separately below -- one call total, not one per city
        for country in countries:
            plan.append((platform, 'country', country))
            # LinkedIn also gets that country's best cities, one search each.
            #
            # Its country-wide search stops at exactly 1,000 jobs -- LinkedIn's own
            # ceiling, per search, documented in the actor's `splitByLocation` field
            # ("bypass LinkedIn's 1000 job limit per search URL by creating separate
            # searches for each city"). Measured for 24 cents before this was written: the
            # same search restricted to Berlin returned 120 jobs of which 48 were not in
            # the 1,000 the country-wide run had already produced. 40% new, from one city.
            #
            # A city Sina did not choose is never added to the plan. LinkedIn used to get
            # each selected country's strongest city asked separately as well, because it
            # caps one query at 1,000 results and a Berlin-only search once returned 48 jobs
            # the Germany-wide one had not -- a real gain, measured. Sina's rule outranks it:
            # "من میخوام فقط جا هایی که انتخاب کردم رو ببینم ولا غیر / به هیچ عنوان نباید
            # شهر های دیگه ای که خودت به نظرت خوب اومده رو اضافه کنی". A search asks for the
            # places he picked, and for nothing else; if he wants Berlin, he picks Berlin,
            # and then Berlin is searched exactly once.
        for city in cities:
            plan.append((platform, 'city', city))

    # Google now searches selected countries too, not just cities -- same as the three
    # dedicated actors above, so it runs whenever 'google' is enabled and at least one
    # country or city is selected.
    run_google = 'google' in actor_order and bool(cities or countries)
    total = len(plan) + (1 if run_google else 0)
    return plan, run_google, total


def _run_platform_locations(process_plan_item, progress, progress_cb, should_cancel,
                            platform, items):
    """Runs every (loc_type, location) selected for ONE platform, sequentially, in
    order, bookended by PLATFORM_START/PLATFORM_END log markers -- this whole
    function is one unit of work submitted to the executor below, so every
    selected platform gets its own independently-ticking header line in the Log,
    running in parallel with its sibling platforms (up to
    SEARCH_MAX_CONCURRENT_PLATFORMS at once), while each platform's own countries
    are always searched one at a time, never interleaved with each other.

    Deliberately never RAISES SearchCancelled -- it returns whatever it already
    fetched instead. A real bug this fixes: it used to raise straight out of the
    loop, which discarded `platform_rows` entirely, so cancelling lost every
    country that platform had already finished. The README's promise ("cancelling
    shows whatever was already fetched") only held for run_search's outer handler;
    the rows never reached it. The caller re-checks should_cancel() itself after
    draining every future, so cancellation still stops the run."""
    if progress_cb:
        progress_cb(f"PLATFORM_START:{platform.capitalize()}", progress.done, progress.total)
    platform_rows = []
    completed = 0
    for loc_type, location in items:
        if should_cancel and should_cancel():
            break
        try:
            platform_rows.extend(process_plan_item(platform, loc_type, location))
        except SearchCancelled:
            break  # keep everything this platform already collected
        completed += 1
        progress.advance()
    # Account for the locations this platform will now never run, so the progress
    # bar resolves instead of freezing partway. Round one's break-on-cancel fixed
    # real data loss but left `done` short of `total`, which reads as "the app hung"
    # rather than "the search stopped".
    skipped = len(items) - completed
    if skipped:
        progress.advance(skipped)
    if progress_cb:
        progress_cb(f"PLATFORM_END:{platform.capitalize()}", progress.done, progress.total)
    return platform_rows


def _check_tokens(client, anthropic_api_key, progress_cb):
    """Prove the keys work before anything is fetched. Raises if Apify's does not.

    The Apify token is a hard gate: without it every later step fails one at a time, each
    with its own confusing error, after the run has already started. The Claude key is not --
    a search without Claude still collects listings, and the Filter is where it would be
    missed -- so a bad one is reported and the search carries on.
    """
    if progress_cb:
        progress_cb("TOKEN_CHECK_START", 0, 1)
    try:
        client.user().get()
        apify_label = _fetch_apify_credit_label(client)
        if progress_cb:
            progress_cb(f"TOKEN_CHECK_ITEM:{apify_label}|OK", 0, 1)
    except Exception as e:
        if progress_cb:
            progress_cb("TOKEN_CHECK_ITEM:Apify Token|FAILED", 0, 1)
        raise RuntimeError(f"Could not verify Apify token — check it's correct and has credits: {e}")

    if anthropic_api_key:
        try:
            anthropic.Anthropic(api_key=anthropic_api_key).models.list(limit=1)
            if progress_cb:
                progress_cb("TOKEN_CHECK_ITEM:Claude Token|OK", 0, 1)
        except Exception:
            if progress_cb:
                progress_cb("TOKEN_CHECK_ITEM:Claude Token|FAILED", 0, 1)
    elif progress_cb:
        progress_cb("TOKEN_CHECK_ITEM:Claude Token|SKIPPED", 0, 1)


def _resolve_passes(search_level, search_for, search_title, progress_cb):
    """What this run is looking for: the passes, the title, and the job Level.

    The Level chosen in Search decides which one search runs -- Thesis, Internship, or the
    job search asked at Entry, Junior, Mid or Senior. Job and Internship are never one run.
    Without a Level, `search_for` decides as it always did. Returns
    (passes, title, job_level, level).
    """
    level = clean_level(search_level) if search_level else None
    if level in ('thesis', 'internship'):
        search_for = (level,)
    elif level == 'any':
        # Everything it can find: jobs, internships and theses, in the order the passes are
        # declared. Each is its own pass with its own words in English and in the country's own
        # language, so Any is not a fourth kind of query -- it is the other three, run in turn.
        search_for = ('job', 'internship', 'thesis')
    elif level:
        search_for = ('job',)

    # The passes this run will make, in the order they are declared -- Job, then Internship,
    # then Thesis. An unknown key is ignored rather than guessed at, and an empty selection
    # falls back to the job pass, so nothing can accidentally search for nothing.
    wanted = tuple(search_for or DEFAULT_SEARCH_PASSES)
    passes = [entry for entry in SEARCH_PASSES if entry['key'] in wanted]
    if not passes:
        passes = [entry for entry in SEARCH_PASSES if entry['key'] == 'job']

    # The one job title every Job and Internship query in this run is built from. Resolved
    # once, here, so that no two parts of one search can ever ask about different titles.
    title = clean_title(search_title)
    # The job Level the job pass asks for; Junior when none was chosen, as it always was.
    # Any asks for no seniority at all, and says so with the word rather than a default: a
    # missing level falls back to Junior inside keywords_for, which would put "Junior Data
    # Scientist" into a search that was supposed to have no level in it.
    job_level = (level if level in ('entry', 'junior', 'mid', 'senior', 'any') else 'junior')
    if progress_cb:
        progress_cb('GLOG:pass|info|Job title: %s.'
                    % ', '.join('"%s"' % form for form in title_forms(title)), 0, 1)
        if level:
            progress_cb('GLOG:pass|info|Level: %s.' % level.title(), 0, 1)
    return passes, title, job_level, level


def _run_platform_passes(plan, pass_plan, rows, progress, run_platform_locations_for,
                         progress_cb, should_cancel):
    """Every paid actor call of the search: pass by pass, platform by platform.

    Split out of run_search, which held this loop, the Google loop and everything around
    them in one 465-line function. This one answers a single question -- who is asked what,
    in which order, and what happens when one of them fails or Sina presses cancel -- and it
    is the question that spends the money.

    `rows` is extended in place, and holds whatever was collected even when the run is
    cancelled: a cancelled search keeps what it has already paid for. Raises SearchCancelled
    upwards so the caller can report it once.
    """
    platforms_in_plan = []
    seen_platforms = set()
    for platform, _loc_type, _location in plan:
        if platform not in seen_platforms:
            seen_platforms.add(platform)
            platforms_in_plan.append(platform)
    platform_locations = {
        platform: [(loc_type, location) for pf, loc_type, location in plan if pf == platform]
        for platform in platforms_in_plan
    }

    # ONE PASS PER KIND, in order, each finished before the next begins. Sina's
    # instruction exactly: "آگهی های شغلی پیدا بشه و پرونده اش بسته بشه، بعد
    # Internship، بعد Thesis" -- and they all land in the same `rows`, which the
    # existing filters then separate as they already do.
    #
    # Sequential rather than parallel on purpose. Two actor runs at a time is this
    # Apify account's memory ceiling (see SEARCH_MAX_CONCURRENT_PLATFORMS), and three
    # passes running at once would be three times that. It also means that if credit
    # runs out part-way, the Job pass -- the one that matters most -- is already done.
    for pass_number, (search_pass, language, shape) in enumerate(pass_plan, start=1):
      run_platform_locations = run_platform_locations_for(
          str(search_pass['key']), language, shape)
      if progress_cb:
        progress_cb('GLOG:pass|info|Search %d of %d — %s, in %s, asked %s.'
                    % (pass_number, len(pass_plan), str(search_pass['label']).lower(),
                       'English' if language == 'en' else "each country's own language",
                       'broadly' if shape == 'broad' else 'as exact phrases'),
                    progress.done, progress.total)
      executor = ThreadPoolExecutor(max_workers=SEARCH_MAX_CONCURRENT_PLATFORMS)
      try:
        futures = {
            executor.submit(run_platform_locations, platform, platform_locations[platform]): platform
            for platform in platforms_in_plan
        }
        # Real bug fixed here: this loop used to check should_cancel() at the TOP
        # of each iteration and raise immediately -- BEFORE draining the future
        # whose completion triggered that very iteration. So a cancel arriving
        # after a platform had already finished all its work threw that platform's
        # rows away, exactly the opposite of the documented cancel behaviour
        # (verified with a faithful simulation: 0 rows kept, though two platforms
        # had finished). Now every completed future is always drained first;
        # cancellation only stops platforms that haven't started yet, and the raise
        # happens once, after the loop.
        cancelled_mid_run = False
        for future in as_completed(futures):
            platform = futures[future]
            if should_cancel and should_cancel() and not cancelled_mid_run:
                cancelled_mid_run = True
                # Python 3.8 has no Executor.shutdown(cancel_futures=...) --
                # Future.cancel() is the 3.8-compatible equivalent, and only
                # succeeds on a future that hasn't started running yet, which is
                # exactly what's wanted: don't start any *new* platform once
                # cancelled, but let already-running ones finish (they self-abort
                # within a few seconds via their own should_cancel() poll inside
                # run_platform_locations/run_actor_and_fetch, then return whatever
                # they already collected).
                for f in futures:
                    f.cancel()
            try:
                rows.extend(future.result())
            except CancelledError:
                pass  # never started -- nothing of its own to keep
            except Exception as e:
                if progress_cb:
                    progress_cb(f"  ! {platform.capitalize()} failed: {e}", progress.done, progress.total)
        if should_cancel and should_cancel():
            raise SearchCancelled()
      finally:
        executor.shutdown(wait=True)
      # Written down before the next pass starts. A crash after this point costs the
      # pass that was running, not the ones already finished -- see checkpoint.py.
      checkpoint.save('search pass %d of %d' % (pass_number, len(pass_plan)), rows)
      if progress_cb:
        progress_cb('GLOG:pass|success|Search %d of %d done — %s collected so far.'
                    % (pass_number, len(pass_plan), format(len(rows), ',')),
                    progress.done, progress.total)

def _run_google_passes(rows, client, countries, cities, actor_order, passes, title,
                       run_actor_and_fetch, progress, *, jooble_api_keys, reed_uk_api_key,
                       francetravail_credentials, anthropic_api_key, progress_cb,
                       should_cancel, preflight_problems_cb, late_problems,
                       settings=None):
    """The Google phase, once per pass -- and the budget rule that has to hold with it.

    The direct-API sources and the pre-flight check live inside this phase and are
    keyword-independent, so they would repeat pointlessly on passes 2 and 3. They run on the
    first pass only; the later passes ask Google alone. That is also what keeps Jooble's
    500-request lifetime budget from being spent three times over for one search -- see
    7.12, which fails if it ever reaches a second pass.
    """
    # Once per pass, with that pass's own role terms. The job pass sends None and
    # therefore builds exactly the query it always has -- see build_google_job_queries.
    #
    # The direct-API sources and the pre-flight check live inside this phase and are
    # keyword-independent, so they would repeat pointlessly on passes 2 and 3. They
    # run on the first pass only; the later passes ask Google alone.
    for pass_number, search_pass in enumerate(passes, start=1):
        if should_cancel and should_cancel():
            raise SearchCancelled()
        if progress_cb and len(passes) > 1:
            progress_cb('GLOG:pass|info|Google, search %d of %d — %s.'
                        % (pass_number, len(passes),
                           str(search_pass['label']).lower()),
                        progress.done, progress.total)
        _run_google_phase(
            rows, client, countries, cities, actor_order,
            run_actor_and_fetch=run_actor_and_fetch,
            jooble_api_keys=jooble_api_keys if pass_number == 1 else None,
            reed_uk_api_key=reed_uk_api_key if pass_number == 1 else None,
            francetravail_credentials=(francetravail_credentials
                                       if pass_number == 1 else None),
            anthropic_api_key=anthropic_api_key,
            progress_cb=progress_cb,
            should_cancel=should_cancel,
            preflight_problems_cb=preflight_problems_cb if pass_number == 1 else None,
            problems=late_problems,
            done=progress.done, total=progress.total,
            role_terms=terms_for_pass(str(search_pass['key']), title)[0],
            direct_api_terms=terms_for_pass(str(search_pass['key']), title)[1],
            settings=settings,
        )
    progress.advance()
    checkpoint.save('google', rows)

def _drop_stale(rows, date_settings, progress, progress_cb):
    """The date range, applied to every source equally.

    It reaches the three paid actors and nothing else: Google results never see it, and
    neither do the two direct APIs that between them supply most of a German search. EURES
    and arbeitsagentur.de hand back whatever they hold, which in one real search included an
    advert 1,990 days old -- five and a half years.

    Only a listing whose own date says it is too old is dropped. One that gives no date is
    kept: not knowing when something was posted is not evidence that it is old.
    """
    try:
        max_age = max_age_from_date_settings(date_settings)
        if max_age:
            rows[:], stale = remove_stale(rows, max_age)
            if stale and progress_cb:
                progress_cb('GLOG:date|info|%d listing(s) posted more than %d days ago '
                            'removed; %d kept.' % (len(stale), max_age, len(rows)),
                            progress.done, progress.total)
    except Exception as e:
        # Additive, like every step around it: if the dates cannot be read the search keeps
        # everything it found, which is how the app behaved before this existed.
        if progress_cb:
            progress_cb(f"GLOG:date|error|Could not apply the date range ({e}) -- "
                        "every listing is kept.", progress.done, progress.total)



def _open_listing_pages(rows, progress, progress_cb, should_cancel):
    """Some of what a search collects is a page of jobs rather than a job.

    "Software Jobs | aktuell 1.500+ offen", "Remote Jobs in Austria". Before they are judged
    as vacancies and found wanting, they are opened, because the vacancies are inside them.
    Measured on a real Austrian search: nine such pages held 43 postings the search had
    never seen. Runs before enrichment, so whatever comes out goes through every step below
    exactly as if the search had found it directly.
    """

    # Some of what a search collects is a page of jobs rather than a job -- "Software Jobs |
    # aktuell 1.500+ offen", "Remote Jobs in Austria". Before they are judged as vacancies
    # and found wanting, they are opened, because the vacancies are inside them. Measured on
    # a real Austrian search: nine such pages held 43 postings the search had never seen.
    #
    # Placed here, before enrichment, so whatever comes out goes through every step below
    # exactly as if the search had found it directly. Additive: a failure returns nothing
    # and the search carries on with what it had.
    try:
        recovered = expand_listing_pages(rows, progress_cb=progress_cb,
                                         should_cancel=should_cancel)
        rows.extend(recovered)
        # Only now, and only the ones that actually gave up their contents. A page that
        # could not be emptied keeps its place in the search -- see remove_listing_pages
        # for the 32 Austrian pages that would otherwise have been discarded with whatever
        # they listed still inside them.
        rows[:], spent = remove_listing_pages(rows)
        if spent and progress_cb:
            emptied = [page for page in spent if page.get(EMPTIED_KEY)]
            # Only the ones nothing could be read from. A page whose postings the
            # search already had is not a site with a problem, and naming it here
            # sends Sina to fix something that works -- see _ALREADY_HAD_KEY.
            barren = [page for page in spent
                      if not page.get(EMPTIED_KEY) and not page.get(ALREADY_HAD_KEY)]
            progress_cb('GLOG:expand|info|%d page(s) dropped now that the postings inside '
                        'them have been collected.' % len(emptied), progress.done,
                        progress.total)
            if barren:
                # Naming the sites rather than only counting them. A page of jobs whose
                # postings cannot be recognised is a gap in the URL patterns, and the host
                # is the whole of what is needed to close it -- where a bare count is
                # something nobody can act on.
                hosts: collections.Counter = collections.Counter()
                for page in barren:
                    url = str(page.get('url') or '')
                    hosts[url.split('/')[2] if url.count('/') > 2 else '?'] += 1
                named = ', '.join('%s (%d)' % (host, count)
                                  for host, count in hosts.most_common(6))
                progress_cb(
                    'GLOG:expand|warning|%d page(s) list jobs but none of their postings '
                    'could be recognised, so they are dropped rather than sent on as '
                    'adverts: %s. These sites need a posting URL pattern before their jobs '
                    'can be collected.' % (len(barren), named),
                    progress.done, progress.total)
    except SearchCancelled:
        raise
    except Exception as e:
        if progress_cb:
            progress_cb(f"GLOG:expand|error|Could not open the listing pages ({e}) -- "
                        "the search continues without what was inside them.",
                        progress.done, progress.total)



def _fill_in_and_prune(rows, progress, progress_cb, should_cancel):
    """The last two: read the pages that arrived as stubs, then drop what is already gone."""

    # Before anything reads the descriptions. Four sources return only a
    # "<title> at <company>" stub, and every step below -- the Remote rule, seniority,
    # language detection, and Claude's own scoring -- judges a listing by its
    # description. Fetching the real page costs no Apify credit; see enrich.py.
    try:
        enrich_thin_descriptions(rows, progress_cb=progress_cb, should_cancel=should_cancel)
    except SearchCancelled:
        raise
    except Exception as e:
        # Enrichment is additive: if it fails entirely, every listing simply keeps the
        # stub it already had, which is how the app behaved before this step existed.
        if progress_cb:
            progress_cb(f"GLOG:enrich|error|Description enrichment failed ({e}) -- "
                        "listings keep their original text.", progress.done, progress.total)

    # Postings that have already been taken down. After enrichment, not before, and that
    # order is the point: many rows only receive their page text during enrichment, and a
    # "Job Not Found" notice cannot be read off a page that has not been fetched yet.
    #
    # Removed at the pool, like index pages two steps above, so Job, Internship and Thesis
    # all see the same clean pool -- a vanished internship is as vanished as a vanished job.
    # Measured on 34,693 listings: 27 say they are gone, and all 27 were read and all 27 are.
    try:
        rows[:], gone = remove_dead_postings(rows)
        if gone and progress_cb:
            progress_cb('GLOG:enrich|info|%d posting(s) removed because the page now says the '
                        'vacancy has been taken down.' % len(gone),
                        progress.done, progress.total)
    except Exception as e:
        if progress_cb:
            progress_cb(f"GLOG:enrich|error|Could not check for taken-down postings ({e}) -- "
                        "they are kept.", progress.done, progress.total)

    # Everything that failed on the way, in one window, with Claude's plain-language fix
    # advice attached. Deliberately at the end and not mid-search: these are things to act
    # on afterwards, and interrupting a running search to say a site was quiet would be
    # exactly the kind of popup this replaced.


def _clean_up_collected(rows, date_settings, progress, progress_cb, should_cancel):
    """Everything done to what the search fetched, before it becomes a table.

    Three steps, in this order and for a reason each: the date range first, so nothing is
    fetched for a listing about to be dropped; then listing pages opened, because the
    vacancies are inside them; then the stubs filled in and the dead postings dropped.

    Each step owns its own try and its own checkpoint, so one failing step never costs the
    others, and a crash after any of them costs only the step that was running.
    """
    _drop_stale(rows, date_settings, progress, progress_cb)
    checkpoint.save('collected', rows)
    _open_listing_pages(rows, progress, progress_cb, should_cancel)
    checkpoint.save('expanded', rows)
    _fill_in_and_prune(rows, progress, progress_cb, should_cancel)

def _start_credit_poller(client, progress_cb):
    """Keep the "Apify Token - $X.XX credit" line current while the search runs.

    Sina asked for it because a long search keeps spending the whole time it runs, and the
    balance from the first second stops being true within minutes. Its own daemon thread, so
    it never blocks the search, and it hands back the stop flag because whoever starts it
    owns stopping it -- run_search does that in a `finally`, on every path out.
    """
    stop = threading.Event()
    thread = threading.Thread(
        target=functools.partial(_poll_apify_credit_impl, client, progress_cb, stop),
        daemon=True)
    thread.start()
    return stop, thread


def _report_late_problems(late_problems, preflight_problems_cb, anthropic_api_key,
                          progress, progress_cb):
    """What went quiet on the way, shown once at the end rather than scrolling past.

    The pre-flight check runs before the search and can only report what is knowable up
    front. These are found during it -- a site that stayed shut, a domain Google returned
    nothing from -- so they are collected as the search goes and put in one window here.

    Never fatal: a report that cannot be shown must not cost a search that has already been
    paid for.
    """
    if not (late_problems and preflight_problems_cb):
        return
    try:
        explain_problems(late_problems, anthropic_api_key=anthropic_api_key,
                         progress_cb=progress_cb)
        preflight_problems_cb(late_problems)
    except Exception as e:
        if progress_cb:
            progress_cb(f"GLOG:preflight|error|Could not show the problem report ({e}).",
                        progress.done, progress.total)


def run_search(token, limit_per_call, date_settings, countries=None, actor_order=None,
                cities=None, progress_cb=None, should_cancel=None,
                jooble_api_keys=None, reed_uk_api_key=None, francetravail_credentials=None,
                preflight_problems_cb=None, anthropic_api_key=None, search_for=None,
                search_languages=None, search_title=None, search_level=None,
                search_work_mode=None, actor_filter_settings=None):
    """Runs the selected actors, in the given order, for the given countries, normalizes,
    dedups, removes fakes, categorizes and sorts. Does NOT translate anything and does NOT
    apply the content filters (remote rule, seniority, sponsorship, unpaid, language) --
    every fetched listing is returned as-is, in its original language; only the Filter
    button (reapply_filters) translates and removes anything.

    date_settings: dict with keys 'linkedin' (str), 'indeed' (str), 'glassdoor' (int) -- values
      taken from *_DATE_OPTIONS above.
    countries: subset of COUNTRIES to search -- defaults to all of them.
    actor_order: subset/ordering of ALL_PLATFORMS -- defaults to DEFAULT_ACTOR_ORDER
      (Indeed, then Glassdoor, then LinkedIn; 'google' only runs if explicitly included).
    cities: subset of CITIES to search -- searched by every platform in actor_order that
      supports it: Indeed/Glassdoor/LinkedIn search each city directly via their own
      city-capable 'location' fields (same as they search countries), and 'google' (if
      included) searches it via Google, explicitly excluding linkedin.com/indeed.com/
      glassdoor.com results since those three sites are already covered by the dedicated
      actors above -- Google is only meant to surface company career pages and other job
      boards. Unlike the other three platforms, google is called once total (not once per
      city) since its `queries` input already covers every city in one batch.
    progress_cb: callable(str message, int done, int total)
    should_cancel: callable() -> bool, checked between actor calls to allow the user to stop early.
    preflight_problems_cb: callable(problems: list[dict]) -> dict, the single place
      anything unreachable is reported. Called up to twice per search:
        - before any real search work, if the pre-flight health check finds a broken
          source, so no credits are spent on it. These problems are often fixable on the
          spot: 'fixable'/'fix_kind'/'settings_key' say which setting resolves it.
        - after the search, for whatever went quiet on the way -- a site that stayed shut,
          a domain Google returned nothing from. These carry kind='url' and are never
          fixable inline; they are told, not asked.
      Every problem dict has 'name'/'reason', and 'fix_advice' written by explain_problems.
      Should show a dialog, block, and return
      {'cancel': bool, 'resolved_keys': {settings_key: new_value}}.
      None (the default) skips both -- broken sources are just logged and skipped.
    anthropic_api_key: used for the Token Check up front, for the automatic job-URL
      pattern discovery, and to write the plain-language fix advice shown for anything
      that failed. None skips all three (Token Check logs 'Not Configured').
    Returns a pandas DataFrame with an added 'Category' column, sorted in the display order.
    If the search is interrupted partway through by an unexpected error (network outage,
    Apify credits running out mid-run, etc.), whatever was already fetched is still
    processed and returned rather than being lost.
    """
    # Real, expensive bug fixed here: this used to be `countries = countries or
    # COUNTRIES`, which reads an EMPTY list (a deliberate cities-only selection, which
    # the wizard explicitly allows -- it validates "at least one country OR city") as
    # "no preference, search everything". Picking only Amsterdam therefore ran the full
    # 18-country search on top of it: 57 paid platform actor calls instead of 3, 74
    # Google query lines instead of 4, and 16 of Jooble's non-renewable 500 lifetime
    # requests spent. `is None` distinguishes "caller didn't pass one" (use the default)
    # from "caller passed an empty one" (search no countries), which `or` cannot.
    countries = COUNTRIES if countries is None else list(countries)
    actor_order = actor_order or DEFAULT_ACTOR_ORDER
    cities = [] if cities is None else list(cities)
    client = ApifyClient(token)
    # Rung 5 of the fetch ladder needs the same token. Set here, once, before anything
    # fetches: it is the only route that opens glassdoor.com, reed.co.uk, totaljobs.com,
    # cv-library.co.uk, cwjobs.co.uk, stepstone.at, moovijob.com or tecnoempleo.com, all of
    # which answer this machine with a 403 no matter which local rung asks.
    fetcher.set_apify_token(token)
    rows: list = []
    # Anything that could not be reached DURING the search -- a site that stayed shut, a
    # domain that went quiet. The pre-flight check runs before the search and so can only
    # report what is knowable up front; these are found on the way, and are shown in the
    # same window at the end rather than scrolling past in the log.
    late_problems: list[dict] = []

    _check_tokens(client, anthropic_api_key, progress_cb)

    # Keeps the "Apify Token - $X.XX credit" line refreshed every
    # _APIFY_CREDIT_POLL_SECONDS for the rest of this search, instead of only ever
    # showing the balance from the very start of the run -- Sina asked for this since a
    # The credit line in the Log, refreshed for as long as the search runs; stopped in the
    # `finally` at the end, however run_search ends (success, cancel, or an error).
    _credit_poll_stop, _credit_poll_thread = _start_credit_poller(client, progress_cb)
    # Bound once, so every call site below reads as it did when this was a nested function,
    # and so a test that patches _run_actor_and_fetch still patches what the search calls.
    run_actor_and_fetch = functools.partial(_run_actor_and_fetch, client, limit_per_call,
                                            should_cancel)

    # The pre-flight health check used to run here, before Indeed/LinkedIn/Glassdoor
    # even started -- but everything it checks (the Google actor, and every direct-API
    # source) is only ever actually used later, inside the Google stage. It now runs
    # right before that stage starts instead (see _run_pre_google_check, called below,
    # right before `if run_google:`), so nothing gets checked before it's actually
    # about to matter.

    passes, title, job_level, level = _resolve_passes(
        search_level, search_for, search_title, progress_cb)

    # Each selected kind, in each selected language. English first, because it is the pass
    # that applies in every country -- if credit runs out part-way, the one that always
    # works has already run.
    languages = tuple(search_languages or DEFAULT_SEARCH_LANGUAGES)
    # Broad first, then precise. Broad is the backbone -- 273 of the 302 relevant listings
    # measured -- and precise is the cheap top-up that catches the 29 most on-target titles
    # the broad query's thousand cannot hold.
    #
    # The job pass now has a precise shape too, and it is the entry-level one. It used to be
    # skipped, back when the job keywords were role titles and an exact phrase could only
    # narrow them. Since the move to DevOps and MLOps that is no longer true: the broad query
    # returns the whole field, seniors included, and the junior roles Sina can actually be
    # hired into never survive LinkedIn's thousand. `keywords_for` returns None for the
    # shapes that have nothing to ask, so a pass that gains nothing still costs nothing.
    pass_plan = [(entry, language, shape)
                 for entry in passes
                 for language in languages
                 for shape in ('broad', 'precise')]

    plan, run_google, total = _build_search_plan(actor_order, countries, cities)
    # The plan is walked once per pass, so the counter has to know that up front or every
    # percentage in the Log is wrong by the number of passes.
    progress = _SearchProgress(total * len(pass_plan))

    # THE OTHER NAMES THIS JOB GOES BY, resolved once for the whole search.
    #
    # One request about the title, cached on disk per title, and no listing is sent -- see
    # title_equivalents. It does not add a single actor run: the names join the existing query
    # with OR, so the plan above is exactly the same size it was. What it changes is what each
    # of those runs asks for, which is why Sina wanted it -- a search for "Data Science" never
    # asked for "Machine Learning Engineer" and never saw those jobs at all.
    #
    # No key, no credit, a refused request: the list is empty and every query is the one it
    # was before. This can only widen.
    other_names = []
    if search_title:
        try:
            import anthropic

            from ..title_equivalents import equivalents_for
            other_names = equivalents_for(
                search_title,
                anthropic.Anthropic(api_key=anthropic_api_key) if anthropic_api_key else None,
                progress_cb)
        except Exception as exc:                                     # noqa: BLE001
            if progress_cb:
                progress_cb('GLOG:pass|warning|Could not ask for other names for "%s" (%s). '
                            'The search asks for the title exactly, as before.'
                            % (search_title, str(exc)[:70]), 0, 1)
            other_names = []
    if other_names and progress_cb:
        progress_cb('GLOG:pass|success|Searching for %s and %d other name(s) for the same '
                    'work: %s' % (search_title, len(other_names), ', '.join(other_names)),
                    0, 1)

    # Not Remote changes what LinkedIn is asked for -- see _linkedin_request. Resolved once,
    # here, so every platform in every pass asks the same question Sina selected.
    not_remote = is_not_remote(clean_work_mode(search_work_mode))

    def run_platform_locations_for(kind, language, shape):
        """The platform worker bound to one pass: one kind, one language, one query shape."""
        item = functools.partial(
            _process_plan_item, run_actor_and_fetch, progress, date_settings,
            limit_per_call, progress_cb, should_cancel, title, job_level, kind, language,
            shape, not_remote=not_remote, also=other_names,
            settings=actor_filter_settings)
        return functools.partial(_run_platform_locations, item, progress,
                                 progress_cb, should_cancel)





    try:
        # One thread per SELECTED PLATFORM (not per platform+location pair) -- each
        # thread works through its own countries/cities sequentially. Up to
        # SEARCH_MAX_CONCURRENT_PLATFORMS platforms run at once; a 3rd/4th selected
        # platform starts as soon as an earlier one finishes and frees a slot. Each
        # actor call is network/polling-bound (waiting on Apify, not local CPU), so
        # threads are the right tool here, same as translate_many above. `rows` is only
        # ever touched from this one (the run_search caller's) thread, in the
        # as_completed loop below -- never from inside a worker thread; `done` IS
        # touched from worker threads (inside run_platform_locations), guarded by
        # done_lock above.
        _run_platform_passes(plan, pass_plan, rows, progress,
                             run_platform_locations_for, progress_cb,
                             should_cancel)

        if run_google:
            _run_google_passes(
                rows, client, countries, cities, actor_order, passes, title,
                run_actor_and_fetch, progress,
                jooble_api_keys=jooble_api_keys,
                reed_uk_api_key=reed_uk_api_key,
                francetravail_credentials=francetravail_credentials,
                anthropic_api_key=anthropic_api_key,
                progress_cb=progress_cb, should_cancel=should_cancel,
                preflight_problems_cb=preflight_problems_cb,
                late_problems=late_problems,
                settings=actor_filter_settings)
    except SearchCancelled:
        # User clicked "Cancel Search" -- same principle as the unexpected-error case
        # below: don't throw away what was already fetched, just stop here and show it.
        if progress_cb:
            progress_cb(
                f"Search cancelled by you. Showing the {len(rows)} listing(s) found so far.",
                progress.done, progress.total,
            )
    except Exception as e:
        # Something unexpected blew up the whole loop (not just one actor call) --
        # don't lose what was already fetched, just stop here and process it as-is.
        if progress_cb:
            progress_cb(
                f"ERROR: Search stopped early ({e}). Showing the {len(rows)} listing(s) found so far.",
                progress.done, progress.total,
            )

    # The date range reaches the three paid actors and nothing else. Google results never
    # see it, and neither do the two direct APIs that between them supply most of a German
    # search: EURES and arbeitsagentur.de hand back whatever they hold, which in one real
    # search included an advert 1,990 days old -- five and a half years.
    #
    # So the range chosen in Search is applied here as well, to every source equally. Only a
    # listing whose own date field says it is too old is dropped; one that gives no date is
    # kept and goes on to every filter below, because not knowing when something was posted
    # is not evidence that it is old. Placed before expansion and enrichment so nothing is
    # fetched for a listing that is about to be discarded.
    _clean_up_collected(rows, date_settings, progress, progress_cb, should_cancel)

    _report_late_problems(late_problems, preflight_problems_cb, anthropic_api_key,
                          progress, progress_cb)

    if progress_cb:
        progress_cb("Preparing results…", progress.done, progress.total)

    # Wrapped in try/finally purely for robustness -- _credit_poll_stop.set() must
    # always fire so the background credit-refresh thread (started earlier in this
    # function) actually stops, however this tail exits (including if pd.DataFrame
    # itself somehow raised, which nothing below already guarded against).
    try:
        result = _finish_run_search_df(rows, progress_cb, progress.done, progress.total)
        # Only once the run has produced its result. A checkpoint left on disk is what tells
        # the next start that the last search did not finish, so it is cleared here and
        # nowhere else -- including not on the cancel path, where the rows are handed back
        # but the search genuinely did not complete.
        checkpoint.clear()
        return result
    finally:
        _credit_poll_stop.set()


def _finish_run_search_df(rows, progress_cb, done, total):
    """The post-fetch cleanup/categorize/sort tail of run_search, split out only so the
    caller can wrap it in one try/finally guaranteeing the credit-poll thread always
    stops -- see the comment at that call site."""
    # Before the DataFrame is built, so every module reading the pool -- Job, Internship and
    # Thesis alike -- sees a Markdown mirror on its real address and with its real title.
    # This corrects rows; it removes none. Sina's rule is that a raw search shows everything
    # it fetched, and cleanup waits for Filter. See unmirror_markdown_row.
    for row in rows:
        unmirror_markdown_row(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Everything below is post-processing on data that's already been successfully (and
    # expensively) fetched from Apify. If anything in here raises, we must still return
    # the raw df instead of losing every fetched listing -- the fetch already cost Apify
    # credits, and a bug in categorizing/sorting is not a reason to throw all of it away.
    # Duplicate/fake removal deliberately does NOT happen here any more -- Sina asked for
    # a raw search to show every listing exactly as fetched, with cleanup happening only
    # when Filter is clicked (see reapply_filters' _remove_duplicates_list/
    # _remove_fake_listings_list, its first step).
    try:
        df['Category'] = df.apply(categorize, axis=1)
        df['Seniority'] = df.apply(seniority_of, axis=1)
        # The third classified column, stamped here as well as in the Filter so a raw search
        # shows it too. This is the one table where 'Other only' really appears: the Filter
        # deletes those rows, a raw search keeps every listing exactly as fetched.
        df['English'] = df.apply(english_requirement_of, axis=1)

        # Sponsorship Visa column: only rows from a confirmed "type (a)" source
        # (currently arbeitnow.com's own visa_sponsorship=true tag) arrive with this
        # already set to 'Yes' -- every other row (the vast majority right now, until
        # more countries' "type (b)" company lists are researched and wired in) defaults
        # to 'Unknown' rather than a guessed 'No', since not being tagged Yes here is not
        # the same as confirmed non-sponsorship.
        if 'sponsorship_visa' not in df.columns:
            df['sponsorship_visa'] = 'Unknown'
        else:
            df['sponsorship_visa'] = df['sponsorship_visa'].fillna('Unknown')

        # Optional BOOLEAN columns get normalized here for the same reason
        # sponsorship_visa does right above: only some row builders set them, so pandas
        # fills the rest with NaN -- and NaN is truthy, which silently disabled the
        # Remote rule and the English rule for every listing in the dataset (see
        # is_true_flag's docstring for the full story). Filling them at the DataFrame
        # boundary means a real False reaches jobs.json instead of a NaN, which also
        # keeps that file valid JSON for anything other than Python's own parser.
        #
        # Only 'thin_description' is genuinely reachable today -- 'was_translated' is set
        # exclusively inside reapply_filters, which works on a plain list and never
        # touches pandas, so no fetcher can produce that column during a search. It's
        # listed anyway as cheap insurance for the day one does; is_true_flag already
        # guards every read of it regardless.
        for bool_column in ('thin_description', 'was_translated'):
            if bool_column in df.columns:
                df[bool_column] = df[bool_column].fillna(False).astype(bool)

        # Germany/Denmark (NO_SPONSORSHIP_PROCESS_COUNTRIES) aren't a Yes/Unknown
        # question -- no employer there needs any special process, so this overrides
        # even a stray 'Yes' from a type-(a) source, since it's a stronger, more useful
        # fact than a sponsorship tag that was never really meaningful there.
        if 'country' in df.columns:
            df.loc[df['country'].isin(NO_SPONSORSHIP_PROCESS_COUNTRIES), 'sponsorship_visa'] = "Employer's Discretion"

        # type (b) cross-referencing (company name against an official sponsor
        # register, e.g. the Netherlands/IND) deliberately does NOT run here -- Sina
        # asked for it to run only from the Filter button (reapply_filters), after the
        # content-filter loop, so it only ever scans survivors instead of every raw
        # listing on every single search. See _apply_sponsor_list_matches_to_jobs.

        # Deliberately UNFILTERED beyond this point -- only dedup/fake-removal/categorizing
        # happened above. Translation and the content filters (remote rule, seniority,
        # sponsorship, unpaid, language) are NOT applied here -- every fetched listing is
        # shown as-is, in its original language; only clicking the Filter button
        # (reapply_filters, below) translates and actually removes anything.

        df['_is_italy'] = df['country'] == 'Italy'
        category_ranks = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        df['_category_rank'] = df['Category'].map(category_ranks).fillna(len(CATEGORY_ORDER))
        # Detect each listing's language ONCE, into two real columns, BEFORE anything
        # below asks for it. is_category_uncertain (next line) then reads the answer via
        # detect_language's cache instead of recomputing it, and -- because these columns
        # survive df.to_dict('records') into jobs.json -- so does Filter's language step
        # on its first run. See _detect_language_pair for the measurements.
        _lang_pairs = df.apply(_detect_language_pair, axis=1, result_type='expand')
        df[_LANG_CACHE_KEY] = _lang_pairs[0]
        df[_LANG_CACHE_TEXT_KEY] = _lang_pairs[1]
        # Listings whose Type badge couldn't be confidently determined without translation
        # (see is_category_uncertain) are pushed to the very end of the raw list -- Filter
        # re-translates and re-categorizes them properly and re-sorts from scratch.
        df['_uncertain'] = df.apply(is_category_uncertain, axis=1)
        df = df.sort_values(
            by=['_uncertain', '_category_rank', '_is_italy'],
            ascending=[True, True, False],
            kind='stable',
        ).drop(columns=['_is_italy', '_category_rank', '_uncertain']).reset_index(drop=True)
    except Exception as e:
        if progress_cb:
            progress_cb(
                f"ERROR: Cleanup/categorizing failed ({e}). Showing the {len(df)} listing(s) "
                "fetched, unprocessed.",
                done, total,
            )

    return df
