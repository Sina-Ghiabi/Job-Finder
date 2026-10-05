"""Direct API search -- job boards with a usable public API, no crawler."""
from __future__ import annotations

from ..text import _JOOBLE_WARN_THRESHOLD, _run_direct_api_source
from ..geo import CITY_COUNTRY, COUNTRY_ISO2, JOOBLE_API_COUNTRIES, _EURES_COUNTRIES
from ..sponsorship import _fetch_arbeitnow_sponsorship
from ..sources_urls import _DIRECT_ROLE_TERM, _fetch_every_role_term
from ..sources_apis import _fetch_arbeitsagentur_de, _fetch_arbetsformedlingen_se, _fetch_eures, _fetch_francetravail, _fetch_jobcloud, _fetch_jooble, _fetch_reed_uk, _fetch_remoteok, _fetch_remotive, _fetch_swissdevjobs, _fetch_werk_nl, _fetch_workatastartup, _read_jooble_usage, _record_jooble_usage
from ..preflight import _JOOBLE_LIFETIME_LIMIT
from .. import sources_enabled


def _run_jooble_searches(rows: list[dict], countries: list[str], cities: list[str],
                         jooble_api_keys: dict, progress_cb=None) -> int:
    """Every configured Jooble country/city, subject to the key's lifetime budget.

    Returns how many rows were added. Split out of _run_direct_api_searches because
    Jooble is the only source with a hard, PERMANENT cap -- 500 requests per key, ever,
    with no way to buy more -- so the budget arithmetic here is the one place in the
    search path where a bug is unrecoverable rather than merely annoying. It is worth
    being able to read it, and test it, on its own.
    """
    # Jooble is the ONE direct source that still searches a single role term while every
    # other one now searches all four (see _fetch_every_role_term). That is deliberate:
    # four terms means four times the requests, and Jooble's free key allows 500 requests
    # for its entire lifetime with no way to buy more. Every other source here is either
    # free or billed per run, so spending four calls on them costs nothing that matters;
    # spending four on Jooble spends a quarter of the budget it will ever have.
    #
    # The cost of that choice is real and worth naming: measured on arbeitsagentur.de, one
    # term finds about a quarter of what four find. Jooble therefore contributes a quarter
    # of what it could, and the way to change that is a paid Jooble key, not a code change.
    added = 0
    for domain_code, (jooble_country, jooble_city) in JOOBLE_API_COUNTRIES.items():
        api_key = jooble_api_keys.get(domain_code)
        if not api_key:
            continue
        locations: list[str | None] = []
        if jooble_country in countries:
            locations.append(None)  # None == country-wide, no `location` filter
        if jooble_city and jooble_city in cities:
            locations.append(jooble_city)
        if not locations:
            continue

        domain = f'{domain_code}.jooble.org'
        for city in locations:
            location_label = city or jooble_country
            used_so_far = _read_jooble_usage().get(domain_code, 0)
            remaining = _JOOBLE_LIFETIME_LIMIT - used_so_far
            if remaining <= 0:
                if progress_cb:
                    progress_cb(
                        f"GLOG:direct_api|error|Skipped {domain} for {location_label} -- the free API key's "
                        f"lifetime limit ({_JOOBLE_LIFETIME_LIMIT} requests) is used up. To help:\n"
                        f"    1 - Ask Jooble (via https://{domain}/api/about) to raise the limit "
                        f"on this key, or request a new one\n"
                        f"    2 - Update jooble_{domain_code}_api_key in settings.json once you have it",
                        0, 1,
                    )
                continue
            if progress_cb:
                low_budget_note = f" (only {remaining} of {_JOOBLE_LIFETIME_LIMIT} lifetime requests left!)" if remaining <= _JOOBLE_WARN_THRESHOLD else ""
                progress_cb(f"GLOG:direct_api|info|Checking {domain} for {location_label} (direct API call){low_budget_note}", 0, 1)
            used = used_so_far  # updated by the on_request_sent callback below
            try:
                def _count_it(code=domain_code):
                    nonlocal used
                    used = _record_jooble_usage(code)

                new_rows = _fetch_jooble(domain_code, jooble_country, _DIRECT_ROLE_TERM, api_key,
                                          location=city, on_request_sent=_count_it)
                rows.extend(new_rows)
                added += len(new_rows)
                if progress_cb:
                    remaining_after = _JOOBLE_LIFETIME_LIMIT - used
                    budget_note = f" ({remaining_after} of {_JOOBLE_LIFETIME_LIMIT} lifetime requests left.)" if remaining_after > _JOOBLE_WARN_THRESHOLD else f" -- WARNING: only {remaining_after} of {_JOOBLE_LIFETIME_LIMIT} lifetime requests left!"
                    progress_cb(f"GLOG:direct_api|success|{domain} for {location_label}: {len(new_rows)} individual job posting(s) found.{budget_note}", 0, 1)
                    if remaining_after <= 0:
                        progress_cb(
                            f"GLOG:direct_api|error|{domain}'s free API key just used its last lifetime request. "
                            f"Ask Jooble (https://{domain}/api/about) for a higher limit or a new key "
                            "before the next search.",
                            0, 1,
                        )
            except Exception as e:
                if progress_cb:
                    progress_cb(
                        f"GLOG:direct_api|error|{domain} API call failed for {location_label} ({e}) -- please check manually:\n"
                        f"    1 - Open https://{domain} and search \"Data Scientist\"\n"
                        f"    2 - If it works fine there, the API key or endpoint may have changed\n"
                        f"    3 - Send back what you find so it can be fixed",
                        0, 1,
                    )
    return added


def _run_direct_api_searches(rows: list[dict], countries: list[str], cities: list[str], progress_cb=None,
                              jooble_api_keys: dict | None = None, reed_uk_api_key: str | None = None,
                              francetravail_credentials: tuple | None = None,
                              apify_client=None, role_terms=None, settings=None) -> None:
    """Additive, same principle as _run_direct_site_searches -- runs alongside every
    other stage, only ever adds rows. Covers the sites whose real location mechanism
    is a JSON API RoleHound can call directly (no Apify actor at all needed for these):
    arbetsformedlingen.se (Sweden, country-wide), arbeitsagentur.de (Germany,
    country-wide or Berlin-specific), and -- for each domain in JOOBLE_API_COUNTRIES
    Sina has supplied his own key for (jooble_api_keys: {'de': '...', 'nl': '...'}) --
    that Jooble country domain's real REST API, country-wide or city-specific. This is a
    completely different, unblocked mechanism from jooble.org's Cloudflare-walled
    browser path, see MANUAL_ASSIST_GLOBAL_SITES's removed entry above for why that one
    doesn't work. francetravail.fr's API also exists but needs registered credentials
    RoleHound doesn't have -- not attempted here."""
    # EVERY SOURCE BELOW IS NOW SWITCHABLE.
    #
    # Until this, the thirteen sources in this function ran whenever a search ran, and only
    # the four Apify platforms could be turned off. Sina asked for a box per source: "میخوام
    # برای همه از Indeed تا API ها Check-box بذاری که خودمون بتونیم انتخاب کنیم".
    #
    # `on` folds that choice into the condition each source already had, so a source still
    # only runs when it applies to a chosen country AND has its key AND he has left it
    # ticked. Unknown keys and a settings file that predates the window both read as ON --
    # see sources_enabled.is_enabled for why that direction is the safe one.
    def on(key):
        return sources_enabled.is_enabled(settings, key)

    # The one switch the Search window offers for this whole stage. Checked here, before any
    # source is considered, because that is what the box means: the APIs as one thing, off or
    # on. The per-source gates below stay for the day one of them earns a box of its own --
    # is_enabled answers True for a key the table does not carry, so they cost nothing now.
    if not on('direct_apis'):
        if progress_cb:
            progress_cb('GLOG:direct_api|info|Direct APIs skipped — switched off in '
                        'Search.', 0, 1)
        return

    want_sweden = 'Sweden' in countries and on('arbetsformedlingen')
    # Country and city are independent, non-propagating selections everywhere else in
    # this app (see COUNTRY_JOB_SITES/CITIES comment) -- matched here too: selecting
    # both Germany and Berlin runs both a country-wide and a Berlin-specific API call,
    # not just one or the other.
    germany_locations: list[str | None] = []
    if 'Germany' in countries and on('arbeitsagentur'):
        germany_locations.append(None)  # None == country-wide, no `wo=` filter
    if 'Berlin' in cities:
        germany_locations.append('Berlin')
    jooble_api_keys = jooble_api_keys or {}
    want_reed = bool(reed_uk_api_key) and 'United Kingdom' in countries and on('reed')
    want_francetravail = (bool(francetravail_credentials) and 'France' in countries
                          and on('francetravail'))
    # EURES needs no key at all -- runs for whichever of its 14 supported countries are
    # actually selected, in one combined call (see _fetch_eures).
    eures_iso2_codes = ([COUNTRY_ISO2[c] for c in _EURES_COUNTRIES if c in countries]
                        if on('eures') else [])
    want_switzerland_apis = 'Switzerland' in countries and on('swissdevjobs')
    # remotive.com needs no key/signup and isn't tied to any one country -- it always
    # runs whenever this function runs at all (run_search only calls it when a search is
    # actually happening), same as it already does via GOOGLE_GLOBAL_EXTRA_SITES.
    #
    # There is no early return here any more. It used to read
    # `if not (want_sweden or ... or want_remotive): return` -- unreachable, since the
    # remotive term was a literal True, and its condition ALSO omitted eures_iso2_codes
    # and want_switzerland_apis. So it was dead code hiding two missing terms: the day
    # anyone made remotive conditional, EURES and the Swiss APIs would have silently
    # stopped running. The unconditional sources below (remotive, remoteok, arbeitnow)
    # mean this function always has real work to do anyway. The two variables that fed
    # that vanished guard -- want_jooble and want_remotive -- are gone with it; both had
    # no remaining reader, and a variable that reads like a decision but controls
    # nothing costs the next debugger real time to rule out.

    added = 0
    if progress_cb:
        progress_cb("DIRECT_API_START", 0, 1)

    if want_sweden:
        added += _run_direct_api_source(
            rows, 'arbetsformedlingen.se for Sweden',
            lambda: _fetch_every_role_term(_fetch_arbetsformedlingen_se, role_terms),
            'Open https://arbetsformedlingen.se/platsbanken and search "Data Scientist"',
            progress_cb,
        )

    for city in germany_locations:
        location_label = city or 'Germany'
        added += _run_direct_api_source(
            rows, f'arbeitsagentur.de for {location_label}',
            lambda c=city: _fetch_every_role_term(lambda t: _fetch_arbeitsagentur_de(t, city=c), role_terms),
            'Open https://www.arbeitsagentur.de/jobsuche and search "Data Scientist"',
            progress_cb,
        )

    # The Netherlands' national board. Country and city are independent selections here
    # exactly as they are for Germany above, so picking both Netherlands and Amsterdam
    # runs a country-wide search and an Amsterdam one rather than only the narrower.
    #
    # Needs the Apify client because werk.nl has no public API and blocks non-Dutch
    # traffic at the network edge -- see _fetch_werk_nl for what was tried first. Without
    # a client this simply does not run, which is the same behaviour as an unconfigured
    # key elsewhere in this function.
    if apify_client is not None and on('werk_nl'):
        netherlands_locations: list[str | None] = []
        if 'Netherlands' in countries:
            netherlands_locations.append(None)
        for city in cities:
            if CITY_COUNTRY.get(city) == 'Netherlands':
                netherlands_locations.append(city)
        for city in netherlands_locations:
            location_label = city or 'Netherlands'
            added += _run_direct_api_source(
                rows, f'werk.nl for {location_label}',
                lambda c=city: _fetch_every_role_term(lambda t: _fetch_werk_nl(apify_client, t, city=c), role_terms),
                'Open https://www.werk.nl/werkzoekenden/vacatures and search "Data Scientist"',
                progress_cb,
            )

    # Y Combinator's board -- global, so it runs whenever a search runs at all, like
    # remotive and remoteok below. It is already a known site for the Google phase, but
    # every link on its listing page is a category rather than a posting, so Google alone
    # never turned it into rows: a real Netherlands search got zero from it.
    if apify_client is not None and on('workatastartup'):
        added += _run_direct_api_source(
            rows, 'workatastartup.com',
            lambda: _fetch_every_role_term(lambda t: _fetch_workatastartup(apify_client, t), role_terms),
            'Open https://www.workatastartup.com/jobs and search "Data Scientist"',
            progress_cb,
        )

    if on('jooble'):
        added += _run_jooble_searches(rows, countries, cities, jooble_api_keys,
                                     progress_cb)
    if want_reed and reed_uk_api_key:
        added += _run_direct_api_source(
            rows, 'reed.co.uk for United Kingdom',
            lambda: _fetch_every_role_term(lambda t: _fetch_reed_uk(t, reed_uk_api_key), role_terms),
            'Open https://www.reed.co.uk and search "Data Scientist"',
            progress_cb,
        )

    if want_francetravail and francetravail_credentials:
        client_id, client_secret = francetravail_credentials
        added += _run_direct_api_source(
            rows, 'francetravail.fr for France',
            lambda: _fetch_every_role_term(lambda t: _fetch_francetravail(t, client_id, client_secret), role_terms),
            'Open https://candidat.francetravail.fr and search "Data Scientist"',
            progress_cb,
        )

    # One call per country, not one shared call for all of them -- a real test with 3
    # countries in a single call returned 49 Austria rows and just 1 Denmark row (one
    # shared 50-result page, sorted by most-recent, dominated by whichever country
    # happens to have the most recent postings). Calling per-country costs nothing extra
    # here (no key, no quota) and gets each selected country its own real 50-result page.
    for iso2_code in eures_iso2_codes:
        country_name = next(c for c in _EURES_COUNTRIES if COUNTRY_ISO2[c] == iso2_code)
        added += _run_direct_api_source(
            rows, f'europa.eu (EURES) for {country_name}',
            lambda iso=iso2_code: _fetch_every_role_term(lambda t: _fetch_eures(t, [iso]), role_terms),
            'Open https://europa.eu/eures/portal and search "Data Scientist"',
            progress_cb,
        )

    if on('remotive'):
        added += _run_direct_api_source(
            rows, 'remotive.com',
            lambda: _fetch_every_role_term(_fetch_remotive, role_terms),
            'Open https://remotive.com/remote-jobs and search "Data Scientist"',
            progress_cb,
        )
    if on('remoteok'):
        added += _run_direct_api_source(
            rows, 'remoteok.com',
            lambda: _fetch_every_role_term(_fetch_remoteok, role_terms),
            'Open https://remoteok.com and search "Data Scientist"', progress_cb,
        )
    if on('arbeitnow'):
        added += _run_direct_api_source(
            rows, 'arbeitnow.com',
            lambda: _fetch_every_role_term(_fetch_arbeitnow_sponsorship, role_terms),
            'Open https://www.arbeitnow.com/visa-sponsorship-jobs', progress_cb,
        )

    if want_switzerland_apis:
        added += _run_direct_api_source(
            rows, 'swissdevjobs.ch', lambda: _fetch_every_role_term(_fetch_swissdevjobs, role_terms),
            'Open https://swissdevjobs.ch and search "Data Scientist"', progress_cb,
        )
    if 'Switzerland' in countries and on('jobcloud'):
        for jobcloud_domain in ('jobs.ch', 'jobup.ch'):
            added += _run_direct_api_source(
                rows, jobcloud_domain, lambda d=jobcloud_domain: _fetch_every_role_term(lambda t: _fetch_jobcloud(d, t), role_terms),
                f'Open https://www.{jobcloud_domain} and search "Data Scientist"', progress_cb,
            )

    if progress_cb:
        progress_cb(f"GLOG:direct_api|info|Direct API search done: {added} row(s) added.", 0, 1)
        progress_cb("DIRECT_API_END", 0, 1)
