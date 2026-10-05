"""The Search button's pipeline.

Split by stage, lowest first -- each may only import from the ones above it:

    direct_site    Per-site direct search -- crawling each job board's own search URL.
    direct_api     Direct API search -- job boards with a usable public API, no crawler.
    browser_sites  Sites that need a real browser -- opened by one, automatically.
    google_phase   The Google stage: the combined actor call and its follow-up searches.
    runner         run_search itself -- the plan, the worker threads, and the progress counter.

Re-exports every name the rest of the package used to import from search.py, so
`from .search import run_search` and friends keep working unchanged.
"""
from __future__ import annotations

from .direct_site import (  # noqa: F401
    _absorb_direct_site_items,
    _direct_site_run_input,
    _direct_site_tasks,
    _report_direct_site_outcomes,
    _run_direct_site_searches,
)

from .direct_api import (  # noqa: F401
    _run_direct_api_searches,
    _run_jooble_searches,
)

from .browser_sites import (  # noqa: F401
    _run_browser_site_search,
    _search_one_site,
)

from .google_phase import (  # noqa: F401
    _absorb_google_pages,
    _location_from_search_term,
    _run_google_followups,
    _run_google_phase,
    _search_term_from_page,
)

from .queries import KEYWORDS  # noqa: F401

from .runner import (  # noqa: F401
    SEARCH_PASSES,
    DEFAULT_SEARCH_PASSES,
    ALL_SEARCH_LANGUAGES,
    SEARCH_MAX_CONCURRENT_PLATFORMS,
    NO_RESULT_LIMIT,
    _SearchProgress,
    _build_search_plan,
    _finish_run_search_df,
    _poll_apify_credit_impl,
    _process_plan_item,
    _run_actor_and_fetch,
    _run_platform_locations,
    run_search,
)


__all__ = [
    'KEYWORDS',
    'SEARCH_PASSES',
    'DEFAULT_SEARCH_PASSES',
    'ALL_SEARCH_LANGUAGES',
    'SEARCH_MAX_CONCURRENT_PLATFORMS',
    'NO_RESULT_LIMIT',
    '_SearchProgress',
    '_absorb_direct_site_items',
    '_absorb_google_pages',
    '_build_search_plan',
    '_direct_site_run_input',
    '_direct_site_tasks',
    '_finish_run_search_df',
    '_location_from_search_term',
    '_poll_apify_credit_impl',
    '_process_plan_item',
    '_report_direct_site_outcomes',
    '_run_actor_and_fetch',
    '_run_direct_api_searches',
    '_run_direct_site_searches',
    '_run_google_followups',
    '_run_google_phase',
    '_run_jooble_searches',
    '_run_browser_site_search',
    '_search_one_site',
    '_run_platform_locations',
    '_search_term_from_page',
    'run_search',
]
