"""The job profiles: Entry, Junior, Mid and Senior -- which vocabulary, level rule and Claude
prompt each Level uses.

Junior is the Job module as it always was: app/pipeline/country_rules.py for its words,
rules.is_too_senior for its level rule, claude_screen/prompt.py for its prompt. Those files
are what Sina called complete, and nothing here changes them.

Entry, Mid and Senior are copies of Junior in their own packages, made the way Sina asked --
"دقیقا همون قالب ... فقط یه سری چیز های کوچیک باید داخلشون تغییر کنه". Each has:

    words.py    Junior's full 13-language vocabulary, with `senior` replaced by `wrong_level`
    level.py    Junior's is_too_senior, with the field values, words and years changed
    prompt.py   Junior's Claude prompt, with the level paragraph and rule 4 changed

Nothing is shared between the profiles except the engine that matches words against text,
which holds no words of its own.

Thesis and Internship are not here. They are Levels too, but they were always their own
modules (app/pipeline/thesis, app/pipeline/internship) and stay that way.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..search_title import JOB_LEVELS, clean_level


@dataclass(frozen=True)
class JobProfile:
    key: str
    label: str
    # The words module whose sections the Filter's word check reads. None is Junior's, which
    # is rules.py's own default, so passing it changes nothing about how Junior behaves.
    vocabulary: Any
    # The section that holds this profile's wrong-level words, and what the Log calls it.
    level_section: str
    level_label: str
    is_wrong_level: Callable[[dict], bool]
    system_prompt: str
    prompt_version: str
    # The same prompt for a Not Remote search: rule 1 and "what he is looking for" turned the
    # other way, everything else identical. See claude_screen/prompt_not_remote.py.
    system_prompt_not_remote: str = ''
    prompt_version_not_remote: str = ''
    # And for an Any search, derived from the Not Remote text (prompt_any.py).
    system_prompt_any: str = ''
    prompt_version_any: str = ''

    def prompt_for(self, not_remote: bool, anywhere: bool = False) -> str:
        if anywhere:
            return self.system_prompt_any
        return self.system_prompt_not_remote if not_remote else self.system_prompt

    def version_for(self, not_remote: bool, anywhere: bool = False) -> str:
        if anywhere:
            return self.prompt_version_any
        return self.prompt_version_not_remote if not_remote else self.prompt_version


def _build(key: str) -> JobProfile:
    import hashlib
    import json
    from ..claude_screen.prompt import _SCREEN_OUTPUT_SCHEMA
    if key == 'junior':
        from ..rules import is_too_senior
        from ..claude_screen.prompt import (CLAUDE_SCREEN_SYSTEM_PROMPT,
                                            _CLAUDE_SCREEN_PROMPT_VERSION)
        from ..claude_screen.prompt_not_remote import CLAUDE_SCREEN_SYSTEM_PROMPT_NOT_REMOTE
        # The same recipe as _CLAUDE_SCREEN_PROMPT_VERSION, over the Not Remote text.
        version_not_remote = hashlib.sha256(
            (CLAUDE_SCREEN_SYSTEM_PROMPT_NOT_REMOTE + '\n'
             + json.dumps(_SCREEN_OUTPUT_SCHEMA, sort_keys=True)).encode('utf-8')
        ).hexdigest()[:12]
        from ..prompt_any import any_workplace_prompt
        prompt_any = any_workplace_prompt(CLAUDE_SCREEN_SYSTEM_PROMPT_NOT_REMOTE, 'job')
        version_any = hashlib.sha256(
            (prompt_any + '\n' + json.dumps(_SCREEN_OUTPUT_SCHEMA, sort_keys=True)
             ).encode('utf-8')).hexdigest()[:12]
        return JobProfile('junior', 'Junior', None, 'senior', 'Too senior', is_too_senior,
                          CLAUDE_SCREEN_SYSTEM_PROMPT, _CLAUDE_SCREEN_PROMPT_VERSION,
                          CLAUDE_SCREEN_SYSTEM_PROMPT_NOT_REMOTE, version_not_remote,
                          prompt_any, version_any)
    from importlib import import_module
    words = import_module('%s.%s.words' % (__name__, key))
    level = import_module('%s.%s.level' % (__name__, key))
    prompt = import_module('%s.%s.prompt' % (__name__, key))
    label = key.title()
    from ..prompt_any import any_workplace_prompt
    prompt_any = any_workplace_prompt(prompt.SYSTEM_PROMPT_NOT_REMOTE, 'job')
    version_any = hashlib.sha256(
        (prompt_any + '\n' + json.dumps(_SCREEN_OUTPUT_SCHEMA, sort_keys=True)
         ).encode('utf-8')).hexdigest()[:12]
    return JobProfile(key, label, words, 'wrong_level', 'Wrong level for %s' % label,
                      level.is_wrong_level, prompt.SYSTEM_PROMPT,
                      prompt.prompt_version(_SCREEN_OUTPUT_SCHEMA),
                      prompt.SYSTEM_PROMPT_NOT_REMOTE,
                      prompt.prompt_version(_SCREEN_OUTPUT_SCHEMA, not_remote=True),
                      prompt_any, version_any)


_CACHE: dict = {}


def job_profile(level) -> JobProfile:
    """The profile for a Level. Anything that is not one of the four job levels -- Thesis,
    Internship, nothing at all -- is Junior, the profile the Job module has always been."""
    key = clean_level(level)
    if key not in JOB_LEVELS:
        key = 'junior'
    if key not in _CACHE:
        _CACHE[key] = _build(key)
    return _CACHE[key]
