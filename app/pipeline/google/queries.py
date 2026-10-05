# -*- coding: utf-8 -*-
"""Building the Google query a search actually sends.

One query per country and per city, naming the job boards worth asking about and
excluding the three the app already searches directly. Google caps a query at about
thirty-two words, which is why the site lists here are grouped rather than listed
whole -- every word spent on a domain is a word not spent on a role term.
"""

from __future__ import annotations

from ..geo import (CITY_COUNTRY, COUNTRY_JOB_SITES)
from .sites import (GOOGLE_QUERY_ROLE_TERMS, GOOGLE_EXCLUDED_JOB_BOARDS, GOOGLE_EXCLUDED_TLD_HINTS, GOOGLE_GLOBAL_EXTRA_SITES, GOOGLE_GLOBAL_SITES_PER_GROUP, GLOBAL_STARTUP_SITES, COUNTRY_STARTUP_SITES)

def _is_excluded_job_board(url: str) -> bool:
    url_lower = (url or '').lower()
    return any(brand in url_lower for brand in GOOGLE_EXCLUDED_JOB_BOARDS)


def _known_sites_clause(country: str | None) -> str | None:
    sites = COUNTRY_JOB_SITES.get(country) if country else None
    if not sites:
        return None
    return '(' + ' OR '.join(f'site:{s}' for s in sites) + ')'


def _startup_sites_clause(country: str | None) -> str | None:
    sites = list(GLOBAL_STARTUP_SITES)
    if country:
        sites += COUNTRY_STARTUP_SITES.get(country) or []
    if not sites:
        return None
    return '(' + ' OR '.join(f'site:{s}' for s in sites) + ')'


def _global_extra_sites_clauses() -> list[str]:
    groups = [
        GOOGLE_GLOBAL_EXTRA_SITES[i:i + GOOGLE_GLOBAL_SITES_PER_GROUP]
        for i in range(0, len(GOOGLE_GLOBAL_EXTRA_SITES), GOOGLE_GLOBAL_SITES_PER_GROUP)
    ]
    return ['(' + ' OR '.join(f'site:{s}' for s in group) + ')' for group in groups]


def build_google_job_queries(countries: list[str], cities: list[str],
                            role_terms: list | None = None) -> str:
    """2/3 + N + 1 queries per selected location (country or city), newline-separated --
    the Google Search actor's `queries` input runs one search per line, order preserved:

    1. Known-sites stage: role terms + location, restricted to that country's major
       local job boards (COUNTRY_JOB_SITES) via `site:` OR-clauses -- run first, so the
       most reliable local sources are checked before anything else.
    2. Startup-sites stage: same role terms + location, restricted to that country's
       dedicated startup/scaleup job boards (COUNTRY_STARTUP_SITES) -- only present for
       a country with a researched entry (16 of the 18 today; Belgium and Luxembourg
       have none), skipped entirely otherwise. Kept as its own stage (not merged into known-sites) so it gets its
       own "Startup Websites Search" section in the Log and its own google_stage tag.
    3. Global-extra-sites stage: same role terms + location, restricted to
       GOOGLE_GLOBAL_EXTRA_SITES (not country-specific -- searched for every location).
       One query line *per group* of GOOGLE_GLOBAL_SITES_PER_GROUP sites (currently a
       single line, since the list holds exactly GOOGLE_GLOBAL_SITES_PER_GROUP = 8
       domains) rather than one line for the whole list, so this list can keep growing
       without ever risking Google's ~32-word query limit on a single line.
    4. Open-web stage: same role terms + location, no site restriction beyond excluding
       LinkedIn/Indeed/Glassdoor (GOOGLE_EXCLUDED_TLD_HINTS) -- catches company career
       pages and any other job board not covered by stages 1-3.

    A country with no COUNTRY_JOB_SITES/COUNTRY_STARTUP_SITES entry just skips that
    stage for that country (the others still always run). A city always uses its parent
    country's site lists (via CITY_COUNTRY) but with the city name as the actual search
    location, so all stages stay scoped to that city specifically, not the whole country.

    Countries are processed before cities; within each, stage 1 before 2 before 3 (in
    group order) before 4. Kept well under Google's ~32-word query limit by using the
    curated role-term list above instead of the much longer KEYWORDS OR-list."""
    # `role_terms` is what the Internship and Thesis passes send: the same query shape
    # with their own words in it. None means the job pass, which uses the curated four
    # exactly as it always has -- so the Job path is unchanged by this.
    role_clause = '(' + ' OR '.join(role_terms or GOOGLE_QUERY_ROLE_TERMS) + ')'
    exclude_clause = ' '.join(f'-site:{domain}' for domain in GOOGLE_EXCLUDED_TLD_HINTS)
    global_clauses = _global_extra_sites_clauses()
    lines = []

    def add_location(location: str, known_sites_country: str | None):
        known_clause = _known_sites_clause(known_sites_country)
        if known_clause:
            lines.append(f'{role_clause} jobs {location} {known_clause}')
        startup_clause = _startup_sites_clause(known_sites_country)
        if startup_clause:
            lines.append(f'{role_clause} jobs {location} {startup_clause}')
        for global_clause in global_clauses:
            lines.append(f'{role_clause} jobs {location} {global_clause}')
        lines.append(f'{role_clause} jobs {location} {exclude_clause}')

    for country in countries:
        add_location(country, country)
    for city in cities:
        add_location(city, CITY_COUNTRY.get(city))

    return '\n'.join(lines)


def _google_query_stage(term: str) -> str:
    """Distinguishes which of the 4 query stages (build_google_job_queries) a result
    page's query text came from: 'known' (country-specific job sites), 'startup'
    (COUNTRY_STARTUP_SITES, only for a country with a researched entry), 'global'
    (GOOGLE_GLOBAL_EXTRA_SITES, present in every location's query), or 'open' (no site
    restriction). The open-web stage's clause is exclusively `-site:` exclusions, so a
    literal `-site:` substring reliably identifies it; the global and startup stages are
    identified by containing one of their own site lists verbatim (COUNTRY_JOB_SITES,
    COUNTRY_STARTUP_SITES, and GOOGLE_GLOBAL_EXTRA_SITES are all pairwise disjoint, by
    design -- see COUNTRY_STARTUP_SITES' own comment on why wellfound.com specifically
    was kept out of it)."""
    term = term or ''
    if '-site:' in term:
        return 'open'
    if any(site in term for site in GOOGLE_GLOBAL_EXTRA_SITES):
        return 'global'
    if any(site in term for site in GLOBAL_STARTUP_SITES):
        return 'startup'
    for sites in COUNTRY_STARTUP_SITES.values():
        if any(site in term for site in sites):
            return 'startup'
    return 'known'
