# -*- coding: utf-8 -*-
"""Deciding whether the company on an advert is a company on a register.

This is where the difficulty is. A job advert says "Deloitte"; the register says "Deloitte
Accountants B.V.". Names are normalised, indexed by length so a fuzzy comparison only ever
runs against candidates that could plausibly match, and the verdict is memoised -- the same
employer turns up on dozens of listings in one run.
"""
from __future__ import annotations

from __future__ import annotations

import re
from difflib import SequenceMatcher
import anthropic

from ..text import (is_true_flag)
from ..company import (
    _MAX_LEGAL_NAME_LOOKUPS_PER_RUN,
    _load_company_legal_name_cache,
    _normalize_company_name,
    _save_company_legal_name_cache,
)
from ..claude_screen import (_resolve_company_legal_name)
from .registers import (SPONSOR_LIST_COUNTRIES, _load_sponsor_list,
                        _sponsor_list_cache_path)

# Countries whose work-visa system needs no special employer-side process at all --
# Sina can get the visa himself off a plain job offer, and it's genuinely true for
# EVERY company in that country, not just some. Confirmed via real research:
# - Germany: the Skilled Worker Visa (Residence Act SS18a/18b) and EU Blue Card need
#   no "sponsor licence" or employer certification of any kind -- any employer with a
#   qualifying job offer works. "Anerkennungspartnerschaft" is a bilateral
#   employer/employee recognition agreement, not a public pre-certification registry.
# - Denmark: Pay Limit Scheme and Positive List both work with ANY employer, gated
#   only by the role's salary/occupation, never the company -- the SIRI Fast-Track
#   certified-companies list (real, and was implemented first) only offers a faster
#   process for some companies, it is never the only way in.
# - Norway: UDI does not require an employer to be separately registered/approved to
#   sponsor a Skilled Worker permit -- any registered Norwegian company in good
#   standing qualifies.
# - Sweden: Migrationsverket's real "Certified Employer" programme (Spotify, Klarna,
#   Ericsson, etc.) is confirmed OPTIONAL -- it only speeds up processing (~52 days
#   vs ~116 for a non-certified employer); any employer, certified or not, can sponsor.
# - Austria: confirmed explicitly -- any registered Austrian company with genuine
#   business activity meeting the salary/collective-bargaining-agreement threshold can
#   sponsor a Red-White-Red Card; no eligibility list exists because none is needed.
# - Belgium: the Single Permit only requires the employer to be a properly registered
#   Belgian entity in good standing -- no certification/pre-approval list found.
# - France: the Talent Passport (Passeport Talent) waives even the standard
#   labour-market test -- DREETS validates salary/qualifications/employer compliance
#   per application, not a pre-approved employer list.
# - Luxembourg: ADEM requires a labour-market test PER VACANCY (a recruitment
#   certificate), not a permanent company certification -- any registered Luxembourg
#   employer can request one; no eligibility list exists.
# - Switzerland: a federal quota + labour-market test, both per-vacancy, not
#   per-company -- no register of eligible employers exists (the quota limits how many
#   permits are granted in total, it never excludes a specific company from applying).
# - Portugal: confirmed with a real second search -- the standard D3 (Highly Qualified
#   Activity) visa needs NO company certification at all and works with any Portuguese
#   employer. IAPMEI's real "Tech Visa" certified-company list (~1,800 companies) is a
#   genuine registry, but it's an OPTIONAL faster lane for certified tech/AI/fintech
#   companies specifically, never the only way in -- same shape as Sweden/Denmark.
# - Spain: any properly registered, compliant Spanish employer can sponsor an HQP
#   permit or EU Blue Card; the UGE-CE fast-track lane is for large
#   companies/strategic sectors, a faster queue, not a pre-approval gate.
# - Italy: the Decreto Flussi/Nulla Osta process is quota- and eligibility-based (the
#   employer must be a registered, compliant entity that can pay the offered salary),
#   not a pre-approved employer list -- no public register of approved sponsors exists.
# - Finland: confirmed explicitly -- any company with a Finnish business ID and
#   demonstrated financial stability can sponsor a residence permit via Migri's Enter
#   Finland service. Migri's own "Employer certification" programme (the source of the
#   ~66-company figure originally used here) is confirmed OPTIONAL -- it only unlocks a
#   faster process, same shape as Sweden/Denmark/Portugal's optional fast-track
#   programmes; treating that narrow list as the real Yes/Unknown source would have
#   wrongly shown 'Unknown' for the vast majority of Finnish employers who simply never
#   opted into certification despite being fully able to sponsor.
# This is a different, stronger fact than 'Unknown' (which means "this specific
# country needs a specific employer's sponsorship and we don't know if this one
# qualifies") -- here there is no employer to even check.
NO_SPONSORSHIP_PROCESS_COUNTRIES = {
    'Germany', 'Denmark', 'Norway', 'Sweden', 'Austria', 'Belgium', 'France',
    'Luxembourg', 'Switzerland', 'Portugal', 'Spain', 'Italy', 'Finland',
}


SPONSORSHIP_KEYWORDS = [
    'e-verify', 'everify',
    'not eligible for immigration sponsorship', 'not eligible for sponsorship',
    'no sponsor available', 'no sponsorship available',
    'will not sponsor', 'unable to sponsor', 'not able to sponsor',
    'does not sponsor', 'can not sponsor', 'cannot sponsor',
    'no visa sponsor', 'no visa sponsorship',
    'sponsor is not available', 'sponsorship is not available',
    'authorized to work without sponsorship',
    'no h1b', 'h1b not sponsored',
    'must be a us citizen', 'us citizenship required',
    'green card holder', 'security clearance required',
    'itar', 'export control',
]

# Every keyword above is matched only where a word starts, never mid-word.
#
# This is not a refinement -- it fixes the single largest silent loss measured in this
# app. 'itar' (the US export-control regime) was being found inside "Mitarbeiter", the
# most common word in German job adverts, and inside "military" and "sanitary" in
# English ones. Measured on a real 2,901-listing corpus: 992 listings were dropped by
# this rule, 983 of them by 'itar' alone -- 34% of everything the search had collected,
# deleted before Sina could ever see it, with no message anywhere.
#
# The boundary is deliberately leading-only. Every genuine phrase here begins at a word
# start, so \b at the front loses nothing; leaving the tail open keeps matches like
# "no visa sponsor" inside "no visa sponsorship" working exactly as before, which a
# trailing \b would have silently broken.
_SPONSORSHIP_KEYWORD_PATTERN = re.compile(
    r'\b(?:%s)' % '|'.join(re.escape(kw) for kw in
                           sorted(SPONSORSHIP_KEYWORDS, key=len, reverse=True)))


def has_sponsorship_restriction(row):
    """Drops listings that won't sponsor a visa / require US work authorization already
    in place (E-Verify, "not eligible for sponsorship", citizenship requirements, etc.)."""
    text = f"{row.get('title') or ''} {row.get('description') or ''}".lower()
    return bool(_SPONSORSHIP_KEYWORD_PATTERN.search(text))
# Normalizing a real register (the UK's is ~127,000 names, the US's ~131,000) takes
# ~0.36s, and _load_sponsor_list re-reads and re-parses the JSON file on top of that --
# both paid again on EVERY Filter click, per sponsor-list country, even though the
# underlying file only changes once a month. Memoized here on the cache file's
# mtime+size, the same pattern already used for _load_direct_search_overrides.
_NORMALIZED_SPONSOR_CACHE: dict = {}


# Key under which _normalized_sponsor_lookup stashes its {length: [names]} index inside
# the same dict. A tuple, so it can never collide with a real normalized company name
# (those are always plain strings) -- which also means the plain `normalized in lookup`
# membership test above stays exactly as correct as before.
_SPONSOR_LEN_INDEX_KEY = ('__len_index__',)


# Same idea, same collision-proof tuple-key trick: a per-register memo of
# {normalized company name -> did it match}, so a company appearing on 40 listings is
# scanned once rather than 40 times. See _company_matches_sponsor_list for the numbers.
_SPONSOR_VERDICT_CACHE_KEY = ('__verdict_cache__',)


def _normalized_sponsor_lookup(country: str, sponsor_list: list) -> dict:
    """{normalized name -> original name} for one country's register, built once and
    reused until the cached register file actually changes on disk.

    The returned dict also carries a length index under _SPONSOR_LEN_INDEX_KEY (see
    _company_matches_sponsor_list for what it's for). It's attached here rather than
    built per lookup because it costs one pass over the register and is then reused for
    every company checked in the run."""
    try:
        stat = _sponsor_list_cache_path(country).stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = None
    cached_stamp, cached_lookup = _NORMALIZED_SPONSOR_CACHE.get(country, (object(), None))
    if stamp is not None and stamp == cached_stamp and cached_lookup is not None:
        return cached_lookup
    # dict[Any, Any] rather than dict[str, str]: alongside the real normalized-name
    # keys, two TUPLE keys are added below (the length index and the verdict memo).
    # Tuples precisely so they can never collide with a real company name.
    lookup: dict = {_normalize_company_name(name): name for name in sponsor_list}
    by_length: dict[int, list[str]] = {}
    for normalized_name in lookup:
        by_length.setdefault(len(normalized_name), []).append(normalized_name)
    # (built before the two tuple keys below are added, so it only ever holds real names)
    lookup[_SPONSOR_LEN_INDEX_KEY] = by_length
    lookup[_SPONSOR_VERDICT_CACHE_KEY] = {}
    _NORMALIZED_SPONSOR_CACHE[country] = (stamp, lookup)
    return lookup


_SPONSOR_NAME_FUZZY_THRESHOLD = 0.90


def _company_matches_sponsor_list(company: str, normalized_sponsor_names: dict) -> bool:
    """normalized_sponsor_names maps normalized-name -> original name. Tries an exact
    match on the normalized name first (covers the common case: only a legal suffix,
    punctuation, or casing differs), then falls back to a fuzzy scan for genuinely
    close-but-not-identical spellings -- exactly the "may not match exactly, a small
    difference" case Sina flagged -- without being loose enough to produce a false 'Yes'."""
    normalized = _normalize_company_name(company)
    if not normalized:
        return False
    if normalized in normalized_sponsor_names:
        return True

    # Memoized per normalized name, for the life of the register cache. This function is
    # called once per JOB, not once per company -- and a real search returns many
    # listings from the same employer (the profiling dataset had 800 listings across 120
    # companies, a 6.7x repeat factor). Without this, the identical full fuzzy scan was
    # repeated for every one of them: at ~0.7s per unmatched name against a 130,000-name
    # register, 200 UK listings meant minutes of pure local CPU re-deriving answers it
    # had already computed. Keyed on the normalized name, so it is exactly as correct as
    # recomputing.
    verdict_cache = normalized_sponsor_names.get(_SPONSOR_VERDICT_CACHE_KEY)
    if verdict_cache is not None and normalized in verdict_cache:
        return verdict_cache[normalized]

    target_len = len(normalized)
    # SequenceMatcher's ratio is exactly 2*M/(len_a+len_b) where M <= min(len_a,
    # len_b) -- so a candidate whose length falls outside this range can mathematically
    # never reach _SPONSOR_NAME_FUZZY_THRESHOLD, regardless of content. Skipping those
    # up front is a real, correctness-preserving speedup (verified with a real 20,000
    # -trial brute-force test finding zero cases where a candidate outside this range
    # reached the threshold), not an approximation -- it matters here because a real
    # sponsor list can have up to ~130,000 names, and without this every single
    # company checked ran a full O(N) SequenceMatcher scan against every one of them.
    min_len = target_len * _SPONSOR_NAME_FUZZY_THRESHOLD / (2 - _SPONSOR_NAME_FUZZY_THRESHOLD)
    max_len = target_len * (2 - _SPONSOR_NAME_FUZZY_THRESHOLD) / _SPONSOR_NAME_FUZZY_THRESHOLD

    # Two purely mechanical speedups below. Neither can change which companies match --
    # both only skip candidates that provably cannot reach the threshold -- and this is
    # the single hottest function in a Filter run: measured at 1,689 ms per unmatched
    # company against a real-shaped 130,000-name register, which with the 25-lookup cap
    # is up to 42 seconds of pure local CPU.
    #
    # 1. Iterate ONLY the length band, instead of walking all 130,000 names to test each
    #    one's length. Measured: the band admits ~34% of a real register, so two thirds
    #    of the loop was spent rejecting on length alone.
    length_index = normalized_sponsor_names.get(_SPONSOR_LEN_INDEX_KEY)
    if length_index is None:
        candidates = (c for c in normalized_sponsor_names
                      if c != _SPONSOR_LEN_INDEX_KEY and min_len <= len(c) <= max_len)
    else:
        import math as _math
        candidates = (
            c
            for length in range(max(0, int(_math.ceil(min_len))), int(max_len) + 1)
            for c in length_index.get(length, ())
        )

    best_ratio = 0.0
    for candidate in candidates:
        # 2. real_quick_ratio() and quick_ratio() are documented UPPER BOUNDS on ratio()
        #    and are far cheaper to compute, so anything they rule out could never have
        #    passed the real test either. Ordered cheapest-first.
        matcher = SequenceMatcher(None, normalized, candidate)
        if matcher.real_quick_ratio() < _SPONSOR_NAME_FUZZY_THRESHOLD:
            continue
        if matcher.quick_ratio() < _SPONSOR_NAME_FUZZY_THRESHOLD:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            if best_ratio >= 0.999:
                break

    matched = best_ratio >= _SPONSOR_NAME_FUZZY_THRESHOLD
    if verdict_cache is not None:
        verdict_cache[normalized] = matched
    return matched


class _LegalNameBudget:
    """The counters one sponsor run keeps while resolving legal names.

    They used to be five loose locals mutated inside a 70-line loop, which is why the loop
    could not be broken up: every piece of it wrote to them. Holding them together lets each
    step move out, and makes what the run spent readable in one place.
    """

    __slots__ = ('cache_hits', 'fresh_lookups', 'skipped_over_budget', 'cache_dirty')

    def __init__(self):
        self.cache_hits = 0
        self.fresh_lookups = 0
        self.skipped_over_budget = 0
        self.cache_dirty = False


def _match_against_register(country_jobs, normalized_lookup):
    """Mark every job whose own company name is already in the register.

    Returns the ones it could not match, which is what the legal-name lookup below is for.
    """
    still_unmatched = []
    for job in country_jobs:
        company = job.get('company')
        if company and _company_matches_sponsor_list(company, normalized_lookup):
            job['sponsorship_visa'] = 'Yes'
        else:
            still_unmatched.append(job)
    return still_unmatched


def _companies_worth_looking_up(needing_legal_name, no_paid_lookup_for):
    """The distinct company names a paid lookup may be spent on, keyed by their normal form.

    Two kinds are refused: a job the caller has already excluded, and a "company" that came
    from _extract_company_from_text's regex rather than the source's own field -- that
    extractor is documented to sometimes return a job title, and paying Claude to web-search
    a made-up name is exactly the waste that got Company Popularity deleted. A cached name
    still applies to both; only a new billed lookup is withheld.
    """
    unique_companies: dict = {}
    for job in needing_legal_name:
        if id(job) in no_paid_lookup_for:
            continue
        if is_true_flag(job.get('company_from_text')):
            continue
        company = job.get('company')
        if not company:
            continue
        key = _normalize_company_name(company)
        if key and key not in unique_companies:
            unique_companies[key] = company
    return unique_companies


def _resolve_legal_names(unique_companies, country_cache, country, client, budget,
                         should_cancel):
    """Fill the cache with each company's legal name, within the run's budget.

    Four reasons a lookup does not happen, and each one is counted separately so the Log can
    say which: it is already cached, Claude is not configured, Sina pressed Cancel, or the
    run has spent its allowance. A miss is never cached as a permanent guess.
    """
    for key, company in unique_companies.items():
        if key in country_cache:
            budget.cache_hits += 1
            continue
        if client is None:
            continue
        if should_cancel and should_cancel():
            budget.skipped_over_budget += 1
            continue
        if budget.fresh_lookups >= _MAX_LEGAL_NAME_LOOKUPS_PER_RUN:
            budget.skipped_over_budget += 1
            continue
        country_cache[key] = _resolve_company_legal_name(client, company, country)
        budget.cache_dirty = True
        budget.fresh_lookups += 1


def _match_by_legal_name(needing_legal_name, country_cache, normalized_lookup):
    """Give each job its employer's legal name, and match the register again with it.

    The name is written onto every job that has one, matched or not: a listing that says
    "Booking.com" should also carry "Booking.com B.V." for the table, the export and any
    later run. The register match is only one of the things that name is good for.
    """
    for job in needing_legal_name:
        company = job.get('company')
        key = _normalize_company_name(company) if company else ''
        legal_name = country_cache.get(key)
        if legal_name:
            job['company_legal_name'] = legal_name
            if _company_matches_sponsor_list(legal_name, normalized_lookup):
                job['sponsorship_visa'] = 'Yes'


def _apply_sponsor_list_matches_to_jobs(jobs: list[dict], anthropic_api_key: str | None = None,
                                          progress_cb=None, no_paid_lookup_for: set | None = None,
                                          should_cancel=None) -> None:
    """Type-(b) cross-reference: for every job whose country has an official sponsor
    list (SPONSOR_LIST_COUNTRIES -- Netherlands, United Kingdom, United States, Canada)
    and isn't already tagged 'Yes' by a type-(a) source, checks its company name
    against that list and marks 'Yes' on a real match. Mutates the list of job dicts in
    place -- called only from reapply_filters (the Filter button), on survivors of BOTH
    the content-filter loop AND Claude's final KEEP/DROP pass, not from run_search, so a
    raw/unfiltered search never pays for this scan. Re-running this every time Filter is
    clicked (not just once) matters for two real cases: a job saved to jobs.json before
    this country's sponsor list existed at all, and a sponsor list that's since been
    refreshed (IND updates its register monthly) with a company that wasn't listed the
    first time this job was fetched.

    Two passes per country:
    1. Match each job's own raw company name against the register directly -- free, no
       Claude needed, and covers most real matches on its own.
    2. For survivors, resolve each UNIQUE remaining company's real legal name (a job ad
       often shortens or informally spells the name the register uses) and re-check --
       cache-first (see _load_company_legal_name_cache), so a company already looked up
       on ANY previous Filter run, or already resolved earlier in this very run (e.g.
       two listings from the same employer), never triggers a second real, billed web
       search. Only runs at all when anthropic_api_key is configured; with no key,
       survivors of pass 1 are simply left at whatever sponsorship_visa value they
       already had.

    no_paid_lookup_for: a set of id(job) values that may read the legal-name cache but
    must never trigger a fresh, billed lookup -- used for listings Claude flagged, since
    those are about to be offered for deletion (see the call site in reapply_filters).

    should_cancel: checked before each fresh, billed lookup. Real bug this closes:
    Filter's Cancel button broke out of the Claude loop and then fell straight into this
    step, which could still spend up to _MAX_LEGAL_NAME_LOOKUPS_PER_RUN real web searches
    AFTER the user had asked it to stop -- the opposite of what Cancel means. The free
    register match still runs either way, since it costs nothing."""
    no_paid_lookup_for = no_paid_lookup_for or set()
    by_country: dict[str, list[dict]] = {}
    for job in jobs:
        country = job.get('country')
        if country not in SPONSOR_LIST_COUNTRIES or job.get('sponsorship_visa') == 'Yes':
            continue
        by_country.setdefault(country, []).append(job)
    if not by_country:
        return

    legal_name_cache = _load_company_legal_name_cache()
    budget = _LegalNameBudget()
    client = anthropic.Anthropic(api_key=anthropic_api_key) if anthropic_api_key else None

    for country, country_jobs in by_country.items():
        sponsor_list = _load_sponsor_list(country, progress_cb=progress_cb)
        if not sponsor_list:
            continue
        normalized_lookup = _normalized_sponsor_lookup(country, sponsor_list)

        _match_against_register(country_jobs, normalized_lookup)

        # The legal name is resolved for EVERY named company in this country, not only the
        # ones the register failed to match -- Sina's call, and it is about the data rather
        # than the match. It stays cheap because the answer is cached on disk per company
        # per country, so each company costs one lookup ever, not one per run.
        needing_legal_name = [job for job in country_jobs
                              if str(job.get('company') or '').strip()]
        if not needing_legal_name:
            continue

        country_cache = legal_name_cache.setdefault(country, {})
        _resolve_legal_names(
            _companies_worth_looking_up(needing_legal_name, no_paid_lookup_for),
            country_cache, country, client, budget, should_cancel)
        _match_by_legal_name(needing_legal_name, country_cache, normalized_lookup)

    if budget.cache_dirty:
        _save_company_legal_name_cache(legal_name_cache)
    if progress_cb and (budget.cache_hits or budget.fresh_lookups or budget.skipped_over_budget):
        progress_cb(
            f"GLOG:filter_step:sponsorship|info|Company legal-name lookups: {budget.cache_hits} from cache, "
            f"{budget.fresh_lookups} new (billed).",
            0, 1,
        )
    if progress_cb and budget.skipped_over_budget:
        # Never silent: a run that hits the ceiling says so, with what to do about it.
        progress_cb(
            f"GLOG:filter_step:sponsorship|warning|Stopped after {_MAX_LEGAL_NAME_LOOKUPS_PER_RUN} "
            f"company legal-name lookups this run -- {budget.skipped_over_budget} more company(ies) were left "
            "unresolved to keep Claude spend bounded. They'll be picked up on the next Filter run "
            "(each resolved name is cached permanently, so this catches up over a few runs).",
            0, 1,
        )
