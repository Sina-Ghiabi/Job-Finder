# -*- coding: utf-8 -*-
"""Everything the Google search does, split by subject.

    sites      Which sites are searched, and the URL shape of a posting on each.
    queries    Building the query that gets sent.
    deepen     Following a result page into the postings behind it.
    learn      Working out the URL shape of a site never seen before.
    report     Naming the sites that returned nothing.

This was one 1,165-line module. It re-exports every name it used to hold, so
`from .google import anything` still works exactly as it did -- which is how the split was
proved faithful: no caller and no test had to change.
"""
from __future__ import annotations

from .sites import (  # noqa: F401
    GOOGLE_SEARCH_ACTOR,
    GOOGLE_QUERY_ROLE_TERMS,
    GOOGLE_EXCLUDED_JOB_BOARDS,
    GOOGLE_EXCLUDED_TLD_HINTS,
    GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS,
    GOOGLE_GLOBAL_EXTRA_SITES,
    GOOGLE_GLOBAL_SITES_PER_GROUP,
    GLOBAL_STARTUP_SITES,
    COUNTRY_STARTUP_SITES,
    _GOOGLE_QUERY_LOCATION_PATTERN,
    GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT,
    _PATTERN_CRAWL_BATCH_SIZE,
    _DEEP_CRAWL_BATCH_SIZE,
    _MAX_PATTERN_DISCOVERIES_PER_RUN,
)
from .queries import (  # noqa: F401
    _is_excluded_job_board,
    _known_sites_clause,
    _startup_sites_clause,
    _global_extra_sites_clauses,
    build_google_job_queries,
    _google_query_stage,
)
from .deepen import (  # noqa: F401
    _crawl_domain,
    all_job_url_patterns,
    _known_pattern_domain,
    _deep_crawl_plan,
    _deep_crawl_run_input,
    _absorb_deep_crawl_items,
    _deepen_google_results,
)
from .learn import (  # noqa: F401
    learn_missing_job_patterns,
    crawl_newly_learned_sites,
)
from .report import (  # noqa: F401
    _warn_zero_result_google_sites,
)

# What this package is for. pyflakes reads __all__, not `# noqa`, and without
# it every re-export below looks like an import nobody uses.
__all__ = [
    'COUNTRY_STARTUP_SITES',
    'GLOBAL_STARTUP_SITES',
    'GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT',
    'GOOGLE_EXCLUDED_JOB_BOARDS',
    'GOOGLE_EXCLUDED_TLD_HINTS',
    'GOOGLE_GLOBAL_EXTRA_SITES',
    'GOOGLE_GLOBAL_SITES_PER_GROUP',
    'GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS',
    'GOOGLE_QUERY_ROLE_TERMS',
    'GOOGLE_SEARCH_ACTOR',
    '_DEEP_CRAWL_BATCH_SIZE',
    '_GOOGLE_QUERY_LOCATION_PATTERN',
    '_MAX_PATTERN_DISCOVERIES_PER_RUN',
    '_PATTERN_CRAWL_BATCH_SIZE',
    '_absorb_deep_crawl_items',
    '_crawl_domain',
    '_deep_crawl_plan',
    '_deep_crawl_run_input',
    '_deepen_google_results',
    '_global_extra_sites_clauses',
    '_google_query_stage',
    '_is_excluded_job_board',
    '_known_pattern_domain',
    '_known_sites_clause',
    '_startup_sites_clause',
    '_warn_zero_result_google_sites',
    'all_job_url_patterns',
    'annotations',
    'build_google_job_queries',
    'crawl_newly_learned_sites',
    'learn_missing_job_patterns',
]
