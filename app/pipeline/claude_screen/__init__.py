# -*- coding: utf-8 -*-
"""The Claude passes, split by subject.

    prompt   the eight questions and the shape of the answer
    batch    waiting for a queued batch
    screen   asking the eight questions
    worth    asking whether a survivor is worth an evening
    company  resolving an employer's legal name

This was one 914-line module. Every name it held is re-exported here, so
`from .claude_screen import anything` still works -- which is how the split was proved
faithful: no caller and no test had to change.
"""
from __future__ import annotations

from .prompt import (  # noqa: F401
    CLAUDE_MODEL,
    CLAUDE_SCREEN_SYSTEM_PROMPT,
    _CLAUDE_SCREEN_DESCRIPTION_MAX_CHARS,
    _claude_screen_prompt,
    _MATCH_LINE_PATTERN,
    _KEEP_DROP_LINE_PATTERN,
    _SCREEN_OUTPUT_SCHEMA,
    _CLAUDE_SCREEN_PROMPT_VERSION,
    _claude_screen_cache_key,
    _NOT_AN_EMPLOYER,
    FILTER_CLAUDE_STEP_CHECKLIST,
)
from .batch import (  # noqa: F401
    _BATCH_POLL_SECONDS,
    _BATCH_MAX_WAIT_SECONDS,
    _await_batch,
)
from .screen import (  # noqa: F401
    _TRANSIENT_ERROR_NAMES,
    _TRANSIENT_ERROR_TEXT,
    _is_transient,
    _SCREEN_RETRY_ATTEMPTS,
    _SCREEN_RETRY_BASE_SECONDS,
    claude_screen_one,
    _REJECTS_SCHEMA_TEXT,
    _rejects_structured_output,
    _SCREEN_MAX_TOKENS,
    _SCREEN_MAX_TOKENS_RETRY,
    _SCREEN_INCOMPLETE_ERROR,
    _STRUCTURED_OUTPUT_SUPPORTED,
    _read_structured_answer,
    _screen_once,
    _evidence_fits_rule,
    _evidence_is_real,
    _BATCH_GROUP_SIZE,
    _BATCH_TOKENS_PER_LISTING,
    _GROUP_ITEM_PROPERTIES,
    _GROUP_ITEM_SCHEMA,
    _GROUP_OUTPUT_SCHEMA,
    _group_request_params,
    claude_screen_batch,
)
from .worth import (  # noqa: F401
    APPLY_VERDICT_KEY,
    APPLY_NOTE_KEY,
    MATCH_KEY as RESUME_MATCH_KEY,
    MATCH_MINIMUM as RESUME_MATCH_MINIMUM,
    STRENGTHS_KEY as RESUME_STRENGTHS_KEY,
    GAPS_KEY as RESUME_GAPS_KEY,
    CACHE_KEY as RESUME_MATCH_CACHE_KEY,
    _APPLY_SYSTEM_PROMPT,
    _APPLY_OUTPUT_SCHEMA,
    _apply_prompt,
    claude_resume_match,
    resume_match_cache_key,
)
from .company import (  # noqa: F401
    _resolve_company_legal_name,
)


# pyflakes reads __all__, not `# noqa`: without it every re-export above looks
# like an import nobody uses.
__all__ = [
    'APPLY_NOTE_KEY',
    'APPLY_VERDICT_KEY',
    'CLAUDE_MODEL',
    'CLAUDE_SCREEN_SYSTEM_PROMPT',
    'FILTER_CLAUDE_STEP_CHECKLIST',
    'RESUME_GAPS_KEY',
    'RESUME_MATCH_CACHE_KEY',
    'RESUME_MATCH_KEY',
    'RESUME_MATCH_MINIMUM',
    'RESUME_STRENGTHS_KEY',
    '_APPLY_OUTPUT_SCHEMA',
    '_APPLY_SYSTEM_PROMPT',
    '_BATCH_GROUP_SIZE',
    '_BATCH_MAX_WAIT_SECONDS',
    '_BATCH_POLL_SECONDS',
    '_BATCH_TOKENS_PER_LISTING',
    '_CLAUDE_SCREEN_DESCRIPTION_MAX_CHARS',
    '_CLAUDE_SCREEN_PROMPT_VERSION',
    '_GROUP_ITEM_PROPERTIES',
    '_GROUP_ITEM_SCHEMA',
    '_GROUP_OUTPUT_SCHEMA',
    '_KEEP_DROP_LINE_PATTERN',
    '_MATCH_LINE_PATTERN',
    '_NOT_AN_EMPLOYER',
    '_REJECTS_SCHEMA_TEXT',
    '_SCREEN_INCOMPLETE_ERROR',
    '_SCREEN_MAX_TOKENS',
    '_SCREEN_MAX_TOKENS_RETRY',
    '_SCREEN_OUTPUT_SCHEMA',
    '_SCREEN_RETRY_ATTEMPTS',
    '_SCREEN_RETRY_BASE_SECONDS',
    '_STRUCTURED_OUTPUT_SUPPORTED',
    '_TRANSIENT_ERROR_NAMES',
    '_TRANSIENT_ERROR_TEXT',
    '_apply_prompt',
    '_await_batch',
    '_claude_screen_cache_key',
    '_claude_screen_prompt',
    '_evidence_fits_rule',
    '_evidence_is_real',
    '_group_request_params',
    '_is_transient',
    '_read_structured_answer',
    '_rejects_structured_output',
    '_resolve_company_legal_name',
    '_screen_once',
    'claude_resume_match',
    'claude_screen_batch',
    'claude_screen_one',
    'resume_match_cache_key',
]
