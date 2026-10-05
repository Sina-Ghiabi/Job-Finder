# -*- coding: utf-8 -*-
"""Visa sponsorship: the registers, and matching an employer against them.

    registers  downloading and caching the government lists
    matching   deciding whether a company on an advert is a company on a list

This was one 733-line module. Every name it held is re-exported here, so
`from .sponsorship import anything` still works.
"""
from __future__ import annotations

from .registers import (  # noqa: F401
    SPONSOR_LIST_COUNTRIES,
    _SPONSOR_LIST_CACHE_MAX_AGE_DAYS,
    _ARBEITNOW_API_URL,
    _fetch_arbeitnow_sponsorship,
    _IND_NL_REGISTER_URL,
    _fetch_ind_nl_sponsor_list,
    _UK_SPONSOR_REGISTER_PAGE_URL,
    _UK_SPONSOR_CSV_URL_PATTERN,
    _fetch_uk_sponsor_list,
    _curl_get,
    _USCIS_H1B_CSV_URL,
    _USCIS_H1B_YEARS,
    _fetch_uscis_h1b_sponsor_list,
    _CANADA_LMIA_API_URL,
    _CANADA_LMIA_DATASET_ID,
    _CANADA_LMIA_QUARTERS,
    _CANADA_LMIA_BROWSER_HEADERS,
    _fetch_canada_lmia_sponsor_list,
    _SPONSOR_LIST_FETCHERS,
    _sponsor_list_cache_path,
    _load_sponsor_list,
)
from .matching import (  # noqa: F401
    NO_SPONSORSHIP_PROCESS_COUNTRIES,
    SPONSORSHIP_KEYWORDS,
    _SPONSORSHIP_KEYWORD_PATTERN,
    has_sponsorship_restriction,
    _NORMALIZED_SPONSOR_CACHE,
    _SPONSOR_LEN_INDEX_KEY,
    _SPONSOR_VERDICT_CACHE_KEY,
    _normalized_sponsor_lookup,
    _SPONSOR_NAME_FUZZY_THRESHOLD,
    _company_matches_sponsor_list,
    _apply_sponsor_list_matches_to_jobs,
)


# pyflakes reads __all__, not `# noqa`: without it every re-export above reads
# as an import nobody uses, and the static-analysis suite fails.
__all__ = [
    'NO_SPONSORSHIP_PROCESS_COUNTRIES',
    'SPONSORSHIP_KEYWORDS',
    'SPONSOR_LIST_COUNTRIES',
    '_ARBEITNOW_API_URL',
    '_CANADA_LMIA_API_URL',
    '_CANADA_LMIA_BROWSER_HEADERS',
    '_CANADA_LMIA_DATASET_ID',
    '_CANADA_LMIA_QUARTERS',
    '_IND_NL_REGISTER_URL',
    '_NORMALIZED_SPONSOR_CACHE',
    '_SPONSORSHIP_KEYWORD_PATTERN',
    '_SPONSOR_LEN_INDEX_KEY',
    '_SPONSOR_LIST_CACHE_MAX_AGE_DAYS',
    '_SPONSOR_LIST_FETCHERS',
    '_SPONSOR_NAME_FUZZY_THRESHOLD',
    '_SPONSOR_VERDICT_CACHE_KEY',
    '_UK_SPONSOR_CSV_URL_PATTERN',
    '_UK_SPONSOR_REGISTER_PAGE_URL',
    '_USCIS_H1B_CSV_URL',
    '_USCIS_H1B_YEARS',
    '_apply_sponsor_list_matches_to_jobs',
    '_company_matches_sponsor_list',
    '_curl_get',
    '_fetch_arbeitnow_sponsorship',
    '_fetch_canada_lmia_sponsor_list',
    '_fetch_ind_nl_sponsor_list',
    '_fetch_uk_sponsor_list',
    '_fetch_uscis_h1b_sponsor_list',
    '_load_sponsor_list',
    '_normalized_sponsor_lookup',
    '_sponsor_list_cache_path',
    'has_sponsorship_restriction',
]
