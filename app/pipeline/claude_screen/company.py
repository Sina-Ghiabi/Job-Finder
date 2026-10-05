# -*- coding: utf-8 -*-
"""Resolving an employer's registered legal name.

The name on a job advert and the name in a government visa-sponsor register are
often not the same string. This asks Claude for the legal one, once per employer.
"""
from __future__ import annotations


from ..company import (_COMPANY_LEGAL_NAME_ANSWER_PATTERN,
                       _COMPANY_LEGAL_NAME_SYSTEM_PROMPT)
from .prompt import CLAUDE_MODEL
from . import spend


def _resolve_company_legal_name(client, company: str, country: str) -> str | None:
    """One real, separately-billed, web-search-backed Claude call resolving a single
    company's exact registered legal name in `country` (e.g. 'Booking.com' ->
    'Booking.com B.V.', confirmed with a real test call, citing real KVK/LEI registry
    sources) -- the name that actually appears in a government sponsor register, which
    a plain fuzzy-match on the ad's own company text can otherwise miss. Returns None
    on failure or an unconfident/UNKNOWN answer -- the caller caches the None result
    too, since a repeat query for the same company rarely succeeds where the first one
    didn't, and this real API call must never run twice for the same company."""
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            temperature=0,
            system=_COMPANY_LEGAL_NAME_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Company: {company}\nCountry: {country}"}],
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        )
        # The third and last place Claude costs money. It searches the web, so it is the
        # dearest call per listing of the three -- leaving it out of the ledger would make
        # the Health Check understate a run with sponsor lookups in it.
        spend.record(CLAUDE_MODEL, getattr(response, 'usage', None), listings=1)

        text_parts = [block.text for block in response.content if getattr(block, 'type', None) == 'text']
        answer = '\n'.join(text_parts).strip()
        name_matches = _COMPANY_LEGAL_NAME_ANSWER_PATTERN.findall(answer)
        if not name_matches:
            return None
        # Claude sometimes wraps its answer in markdown emphasis (a real, observed
        # case: "** UNKNOWN" instead of plain "UNKNOWN") despite being told to answer
        # with plain text -- strip that formatting before the UNKNOWN check, or a
        # wrapped "UNKNOWN" silently becomes a fake, garbage "legal name" that then
        # fails every real match.
        candidate = name_matches[-1].strip().strip('*`_ ').rstrip('.').strip()
        if candidate and candidate.upper() != 'UNKNOWN':
            return candidate
        return None
    except Exception:
        return None
