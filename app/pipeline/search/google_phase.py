"""The Google stage: the combined actor call and its follow-up searches."""
from __future__ import annotations

from urllib.parse import urlsplit
from ..errors import SearchCancelled
from ..text import dig
from ..geo import CITIES, COUNTRIES
from ..apify import _DEEP_CRAWL_MEMORY_MBYTES
from ..sources_norm import normalize_google_search_result
from ..google import crawl_newly_learned_sites, learn_missing_job_patterns, GOOGLE_SEARCH_ACTOR, _GOOGLE_QUERY_LOCATION_PATTERN, _deepen_google_results, _google_query_stage, _is_excluded_job_board, _warn_zero_result_google_sites, build_google_job_queries
from ..preflight import _run_pre_google_check

from .direct_site import (_run_direct_site_searches)
from .direct_api import (_run_direct_api_searches)
from .browser_sites import (_run_browser_site_search)


def _location_from_search_term(term: str) -> tuple[str | None, str | None]:
    """Returns (loc_type, loc_value) -- ('city', 'Oslo') or ('country', 'Norway') or
    (None, None) if neither a known city nor country name appears in the query's own
    location slot.

    Real bug fixed here: this used to substring-search the WHOLE query text, which meant
    a site: clause containing a city name inside a DOMAIN name hijacked the attribution.
    Two real cases, both confirmed against the live query builder: Germany's
    startup-sites query contains `site:berlinstartupjobs.com` and was therefore read as
    a Berlin query, and the Netherlands' contains `site:startupmap.iamsterdam.com` and
    was read as Amsterdam -- so every result from those country-wide startup searches
    was written to jobs.json with the wrong `location`, silently. Restricting the match
    to the query's real location slot makes a domain name incapable of colliding with
    it. If the pattern doesn't match (a query shape this app didn't build, e.g. the
    pre-flight check's bare "test"), it falls back to the old whole-string scan rather
    than losing attribution entirely."""
    term = term or ''
    slot_match = _GOOGLE_QUERY_LOCATION_PATTERN.search(term)
    haystack = (slot_match.group(1) if slot_match else term).lower()
    # Cities before countries: a city query never also contains its country's name
    # (build_google_job_queries embeds one or the other), but checking the more
    # specific one first is a cheap safeguard either way.
    for city in CITIES:
        if city.lower() in haystack:
            return 'city', city
    for country in COUNTRIES:
        if country.lower() in haystack:
            return 'country', country
    return None, None


def _search_term_from_page(page_item: dict) -> str:
    """The Google Search actor's dataset items are one per (query, result page), and
    carry the originating query text under a `searchQuery` field -- this tries the
    couple of shapes that field is documented/observed to take, so a minor schema
    difference doesn't silently break location attribution below."""
    return (
        dig(page_item, 'searchQuery.term')
        or (page_item.get('searchQuery') if isinstance(page_item.get('searchQuery'), str) else None)
        or page_item.get('query')
        or page_item.get('term')
        or ''
    )


def _absorb_google_pages(pages, rows: list[dict]):
    """Turn the Google actor's result PAGES into listing rows.

    Returns (known_site_counts, startup_site_counts, excluded_job_board_count) -- the
    two dicts drive the per-site breakdown in the Log. Appends to `rows`; otherwise pure,
    so the exclusion rule below can be tested without an actor.

    One Google dataset item is a PAGE of results, not one job, which is why this loops
    twice.
    """
    known_site_counts: dict[str, int] = {}
    startup_site_counts: dict[str, int] = {}
    excluded_job_board_count = 0
    for page_item in pages:
        term = _search_term_from_page(page_item)
        loc_type, loc_value = _location_from_search_term(term)
        google_stage = _google_query_stage(term)
        for result in (page_item.get('organicResults') or []):
            # Real gap fixed here: this app-side exclusion used to be
            # skipped entirely in this loop, relying only on Filter's
            # own dedup (_remove_duplicates_list) to collapse a Google
            # copy of a LinkedIn/Indeed/Glassdoor listing against that
            # platform's own dedicated-actor row. That relies on either
            # an EXACT URL match or a company+title fuzzy match -- but a
            # Google-scraped LinkedIn/Indeed/Glassdoor row very often has
            # no extractable `company` at all (Google never returns one,
            # and _extract_company_from_text's deliberately conservative
            # regex frequently can't recover it from these sites' own
            # title formats), which disqualifies it from the fuzzy match
            # entirely -- leaving ONLY an exact-URL match as a safety
            # net, which isn't guaranteed if Google indexed a
            # differently-formatted URL (tracking params, a different
            # path) than the dedicated actor's own output. A real
            # duplicate could silently survive Filter as an extra,
            # lower-quality row. _is_excluded_job_board (substring-based,
            # catches any TLD/subdomain -- e.g. glassdoor.ca -- unlike an
            # exact-domain check) is restored here as the real, app-side
            # guarantee it always was meant to be; GOOGLE_EXCLUDED_TLD_HINTS
            # above still does its job at the query level first (fewer
            # of these ever get scraped/billed for in the first place).
            url = result.get('url')
            if _is_excluded_job_board(url):
                excluded_job_board_count += 1
                continue
            normalized = normalize_google_search_result(result, loc_type, loc_value)
            normalized['platform'] = 'google'
            normalized['google_stage'] = google_stage
            rows.append(normalized)
            if google_stage == 'known' and normalized.get('url'):
                domain = urlsplit(normalized['url']).netloc.lower()
                known_site_counts[domain] = known_site_counts.get(domain, 0) + 1
            elif google_stage == 'startup' and normalized.get('url'):
                domain = urlsplit(normalized['url']).netloc.lower()
                startup_site_counts[domain] = startup_site_counts.get(domain, 0) + 1
    return known_site_counts, startup_site_counts, excluded_job_board_count


def _run_google_followups(rows: list[dict], client, countries, cities, *,
                          anthropic_api_key, progress_cb, should_cancel,
                          jooble_api_keys, reed_uk_api_key, francetravail_credentials,
                          problems=None, direct_api_terms=None, settings=None):
    """The four additive searches that hang off the Google results.

    Every one of them only ever ADDS rows -- none replaces or filters what Google already
    found. Grouped here because they always run together, in this order, and because the
    reason each is additive is worth stating once rather than four times.

    `problems` collects whatever could not be reached, for the pre-flight window to report
    with an explanation of how to fix it.
    """
    # Deep-crawl every result above one level, any domain, to reach the
    # real job pages a listing/aggregator page might only link to.
    _, _, _, no_pattern_domains = _deepen_google_results(
        rows, client, progress_cb=progress_cb, should_cancel=should_cancel,
        anthropic_api_key=anthropic_api_key,
    )
    # Additive: for domains with a confirmed real location-search mechanism
    # of their own, search that directly too -- doesn't replace anything
    # above, just adds more (and more precisely city-scoped) coverage.
    # The pass's own phrases, exactly as the direct APIs get them. Without this every pass
    # asked stepstone.de and xing.com for "Data Scientist" -- so the Internship and Thesis
    # searches quietly re-ran the Job search against a dozen of the best German boards.
    _run_direct_site_searches(
        rows, client, countries, cities, progress_cb=progress_cb, should_cancel=should_cancel,
        role_terms=direct_api_terms,
    )
    # Now that every source has contributed its rows, work out how to read the sites
    # RoleHound could not. Runs here rather than inside the deep crawl because the crawl
    # only sees its own eligible subset -- doing it there examined one domain out of
    # nineteen. What is learned is permanent and takes effect from the next search.
    try:
        learned_sites = learn_missing_job_patterns(
            rows, anthropic_api_key=anthropic_api_key,
            progress_cb=progress_cb, should_cancel=should_cancel)
        # Act on it now. Saving a pattern and waiting for the next search leaves this
        # run's jobs behind the listing page that taught us the pattern.
        if learned_sites:
            crawl_newly_learned_sites(rows, client, learned_sites,
                                      progress_cb=progress_cb, should_cancel=should_cancel)
    except SearchCancelled:
        raise
    except Exception as e:
        if progress_cb:
            progress_cb('GLOG:pattern|error|Could not learn new sites this run (%s) -- '
                        'nothing else is affected.' % e, 0, 1)

    # Also additive: Sweden/Germany's real location mechanism is a JSON
    # API, not an HTML page -- calls it directly (no Apify actor at all).
    # The pass's own phrases go here too. These sources take one plain phrase rather than a
    # boolean query, and they are free -- arbeitsagentur.de and EURES between them are where
    # German theses actually live, so asking them for "Masterarbeit Data Science" is the
    # single highest-value part of the thesis pass.
    _run_direct_api_searches(rows, countries, cities, progress_cb=progress_cb,
                              jooble_api_keys=jooble_api_keys, reed_uk_api_key=reed_uk_api_key,
                              francetravail_credentials=francetravail_credentials,
                              apify_client=client, role_terms=direct_api_terms,
                              settings=settings)
    # Also additive: sites Apify's crawler cannot read, opened by the fetch ladder --
    # which now does automatically what this stage used to need a person for.
    _run_browser_site_search(rows, countries, cities=cities, progress_cb=progress_cb,
                            should_cancel=should_cancel, problems=problems)
    # Blanket safety net: any COUNTRY_JOB_SITES/GOOGLE_GLOBAL_EXTRA_SITES
    # domain that produced zero results this run is reported, regardless of whether it has
    # a confirmed deep-crawl pattern.
    _warn_zero_result_google_sites(
        rows, countries, cities, progress_cb=progress_cb,
        extra_broken_domains=no_pattern_domains, problems=problems,
    )


def _run_google_phase(rows, client, countries, cities, actor_order, *,
                      run_actor_and_fetch, jooble_api_keys, reed_uk_api_key,
                      francetravail_credentials, anthropic_api_key, progress_cb,
                      should_cancel, preflight_problems_cb, done, total,
                      problems=None, role_terms=None, direct_api_terms=None,
                      settings=None):
    """The whole Google stage of a search: pre-check, the one combined Google actor call,
    and the four additive follow-up searches that hang off its results.

    Lifted out of run_search, which was 610 lines and impossible to read in one sitting.
    This phase is genuinely separable: it appends to `rows` and reads `done`/`total` only
    to report progress, so the only thing it needed from run_search's body was the nested
    `run_actor_and_fetch` closure -- now passed in explicitly.

    Raises SearchCancelled if the user cancels; run_search's own handler still catches it
    and returns whatever was already fetched.
    """
    if should_cancel and should_cancel():
        raise SearchCancelled()

    # Started here, before the pre-Google check, so Sina sees ONE continuous
    # "Google" timer covering the whole phase (pre-check included), not just
    # the actor call itself.
    if progress_cb:
        progress_cb("PLATFORM_START:Google", done, total)

    # Everything this checks only matters right here, right before Google
    # actually starts -- see _run_pre_google_check's docstring. If Indeed/
    # LinkedIn/Glassdoor were also selected, this naturally only runs after
    # they're all fully done (the executor block above has already returned by
    # this point); if none of them were selected, `plan` was empty and this
    # runs immediately.
    google_ok = True
    try:
        jooble_api_keys, reed_uk_api_key, francetravail_credentials = _run_pre_google_check(
            client, countries, cities, actor_order, jooble_api_keys, reed_uk_api_key,
            francetravail_credentials, progress_cb=progress_cb, problems_cb=preflight_problems_cb,
            should_cancel=should_cancel,
        )
    except SearchCancelled:
        if progress_cb:
            progress_cb("Google search cancelled by you during the pre-Google check.", done, total)
        google_ok = False

    if google_ok:
        google_locations = list(countries) + list(cities)
        log_prefix = f"Google — {', '.join(google_locations)}"
        try:
            google_queries = build_google_job_queries(countries, cities, role_terms)
            google_pages_per_query = 3
            run_input = {
                "queries": google_queries,
                "maxPagesPerQuery": google_pages_per_query,
                "websiteContentScraper": {"enable": True},
            }
            # One Google dataset item is a PAGE of results, not one job -- so the
            # wizard's per-job limit must not be applied here (see
            # run_actor_and_fetch's item_limit). The real ceiling is however many
            # pages this run's own queries can produce.
            google_item_limit = len(google_queries.splitlines()) * google_pages_per_query
            # Started right before the one combined actor call that produces
            # the known-site results (it can genuinely take a minute or more) --
            # a real, live-ticking timer so Sina can see this stage actually
            # started instead of the Log going quiet with no sign anything is
            # happening. Stopped right below once real results are in.
            if progress_cb:
                progress_cb("KNOWN_SITES_START", done, total)
                # Same one combined actor call also covers the startup-sites
                # stage (when the country has a COUNTRY_STARTUP_SITES entry) --
                # its own Running timer starts here too, stopped alongside
                # Known Websites' once the same call returns.
                progress_cb("STARTUP_SITES_START", done, total)
            pages, _google_usage_usd = run_actor_and_fetch(
                GOOGLE_SEARCH_ACTOR, run_input, log_prefix, memory_mbytes=_DEEP_CRAWL_MEMORY_MBYTES,
                item_limit=google_item_limit,
            )
            known_site_counts, startup_site_counts, excluded_job_board_count = \
                _absorb_google_pages(pages, rows)
            if progress_cb and excluded_job_board_count:
                progress_cb(
                    f"GLOG:platform:Google|info|Skipped {excluded_job_board_count} "
                    "result(s) from LinkedIn/Indeed/Glassdoor (already covered by their own actors).",
                    done, total,
                )
            # "Known Websites" breakdown -- no live per-site progress is
            # possible (every known site for a location shares ONE combined
            # site: OR-clause query, all sent in a single Google Actor call,
            # so there's no way to know mid-call which specific site a result
            # is about to come from), and no per-site cost either (the whole
            # call's usageTotalUsd covers known+global+open-web together, not
            # split by site) -- only the final per-site job COUNT, once the
            # whole call is done, is a real number. Only sites that actually
            # returned something get their own line, per Sina's own ask -- but
            # the Running timer above is always stopped here regardless, even
            # with zero known-site results, so it never ticks forever.
            if progress_cb:
                # One summary cost line for the WHOLE section (the real
                # usageTotalUsd from the one combined Google Search actor call
                # that produced every known-site result this run), followed by
                # each site's own final job count -- per Sina's approved format.
                progress_cb(f"KNOWN_SITES_HEADER:{_google_usage_usd}", done, total)
                for domain, count in sorted(known_site_counts.items()):
                    progress_cb(f"KNOWN_SITE_RESULT:{domain}|{count}", done, total)
                # Same cost note applies here -- one combined call, no per-site
                # split possible. Always stops the Running timer, even with
                # zero startup-site results (e.g. a country with no
                # COUNTRY_STARTUP_SITES entry yet).
                progress_cb(f"STARTUP_SITES_HEADER:{_google_usage_usd}", done, total)
                for domain, count in sorted(startup_site_counts.items()):
                    progress_cb(f"STARTUP_SITE_RESULT:{domain}|{count}", done, total)
            _run_google_followups(
                rows, client, countries, cities,
                anthropic_api_key=anthropic_api_key, progress_cb=progress_cb,
                should_cancel=should_cancel, problems=problems,
                jooble_api_keys=jooble_api_keys,
                reed_uk_api_key=reed_uk_api_key,
                francetravail_credentials=francetravail_credentials,
                direct_api_terms=direct_api_terms,
                settings=settings,
            )
        except SearchCancelled:
            raise
        except Exception as e:
            if progress_cb:
                # Stops every sub-timer this stage can start but that never
                # reached its own normal stop line, since whatever failed
                # happened somewhere inside this try block -- without this, a
                # timer started right before the failure ticks forever.
                progress_cb("GOOGLE_STAGE_FAILED", done, total)
                progress_cb(f"  ! {log_prefix} failed: {e}", done, total)
        finally:
            # Real bug fixed here: PLATFORM_END:Google used to sit at the end of
            # the `try` body, so it only ever fired on the fully-successful
            # path. Any failure inside the Google stage (and the
            # pre-check-cancelled path below) left the outer "Google" header
            # ticking forever, since GOOGLE_STAGE_FAILED only stops the four
            # INNER timers, not the header itself. A `finally` guarantees the
            # header always closes, however this stage ends.
            if progress_cb:
                progress_cb("PLATFORM_END:Google", done, total)
    elif progress_cb:
        # Pre-check cancelled -- the header was already started above, so it has
        # to be closed here too or it ticks forever exactly the same way.
        progress_cb("GOOGLE_STAGE_FAILED", done, total)
        progress_cb("PLATFORM_END:Google", done, total)
