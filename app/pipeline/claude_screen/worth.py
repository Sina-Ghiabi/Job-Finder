# -*- coding: utf-8 -*-
"""Part two: how well does each listing that survived match the user's résumé?

The user's design, in his words: Claude [owner's note: one part finds listings by the profile, and the next says what percentage of the remaining ones match the uploaded résumé]. So Claude
works in two parts:

    part one   the Level's profile decides KEEP or DROP     (screen.py, and the Thesis and
                                                              Internship modules' own)
    part two   this file: a match percentage against the     every Level, one Match column
               résumé he uploaded, for what part one kept

Until now this file held a hard-coded paragraph about the user -- "entry or junior level, in
data, ML or AI" -- written before the field became a title he types and never updated when
it did, so a Data Engineering search was still being judged against data science. The
résumé replaces it entirely.

It sees only what survived, a dozen or a few dozen, so it can afford one request per
listing, and a listing whose text, Level, title and résumé are all unchanged since its last
answer is not asked again.
"""
from __future__ import annotations

import hashlib
import json

from .prompt import CLAUDE_MODEL, _CLAUDE_SCREEN_DESCRIPTION_MAX_CHARS
from .batch import (_await_batch)
from . import spend
from ..drop_note import listing_text_without_note
from ..search_title import LEVEL_ROW_KEY, ROW_KEY as TITLE_ROW_KEY, clean_level, clean_title


# Where the answer is kept on a row. The score goes in `claude_match` for every Level, which
# is the key the Match column reads first, so one column means the same thing for a thesis
# and a senior job alike.
MATCH_KEY = 'claude_match'
APPLY_VERDICT_KEY = 'apply_verdict'
APPLY_NOTE_KEY = 'apply_note'
STRENGTHS_KEY = 'resume_strengths'
GAPS_KEY = 'resume_gaps'
CACHE_KEY = 'resume_match_cache_key'

# Below this a listing is flagged like any other Claude drop: it still appears in the review
# dialog and can be kept by hand. Moved here from the first part with the score itself. The
# history of the number: a cybersecurity delivery architect passed every rule and scored 35
# against a data-engineering profile while every genuine match in the same run scored 65 to
# 85, and the user asked for everything under 35% to be cut -- so the line sits just above it.
MATCH_MINIMUM = 36

_LEVEL_NAMES = {'any': 'Any', 'thesis': 'Thesis', 'internship': 'Internship',
                'entry': 'Entry', 'junior': 'Junior', 'mid': 'Mid', 'senior': 'Senior'}

_APPLY_SYSTEM_PROMPT = """# Résumé match for the user

Every listing below has already been screened and kept. It is in the work named on its Field
line — the job title the user is searching for — at the level on its Level line (a Level of Any
means he did not choose one), and nothing in
it rules him out. Your job is the second question: **how well does this listing match his
résumé?**

His résumé is given in full after these instructions, under "His résumé". It is the only
source of facts about him. Do not assume a skill, a tool, a degree or a year of experience
the résumé does not show, and do not overlook one it does.

## How to judge

Read what the listing actually asks for — its must-haves first, then its nice-to-haves —
and hold each one against the résumé.

Judge by the Level line, because what "a fit" means depends on it:

- **Thesis** and **Internship** — the subject, and the skills to start on it. Years of
  experience are not expected and their absence is not a gap.
- **Entry** and **Junior** — the right foundations and the first practical experience. A
  missing tool he could learn in weeks is a small gap; a missing core skill is a big one.
- **Mid** and **Senior** — depth. The years, the scale and the ownership the listing asks
  for, shown in the résumé's own experience.

## Your answer

- **strengths** — what in his résumé meets the listing, named specifically ("Airflow and
  dbt in production for two years — asked for"). Empty only if nothing does.
- **gaps** — what the listing wants that his résumé does not show, most important first.
  Empty if nothing.
- **match** — one number, 0 to 100:
  - 80–100 he meets essentially every must-have, and most nice-to-haves;
  - 60–79 he meets the must-haves, with gaps he could close quickly;
  - 40–59 a real part fits, but at least one must-have is missing or thin;
  - 0–39 the core of the job is something his résumé does not show.
  Never inflate it.
- **verdict**:
  - **apply** — it fits and the posting says enough to be sure. He should spend the time.
  - **check** — it could fit, but the posting does not say enough to be sure: a description
    of a few hundred characters, requirements not stated. Worth opening the link first.
  - **skip** — the posting itself shows it is not for him, and he would find that out after
    an hour. Say which words do it.
- **note** — one sentence, at most about fifteen words, in plain English, leading with the
  reason and quoting the posting where you can. It is read next to the listing in a table:

    "Asks for Spark and Kafka at scale; résumé shows neither."
    "Airflow, dbt and Python all asked for and all on the résumé."
    "Description is 262 characters -- open the link to see the real requirements."

Never invent a requirement the posting does not contain. If nothing in the text settles it,
that is exactly what **check** is for."""

# Reasoning first, then the number, then the verdict. JSON fields are generated in schema
# order, so a score placed before its reasons would be committed to before any were written
# -- the Job screen measured exactly that failure with its own verdict field.
_APPLY_OUTPUT_SCHEMA: dict = {
    'type': 'object',
    'properties': {
        'strengths': {'type': 'string',
                      'description': 'What in his résumé meets the listing, specifically.'},
        'gaps': {'type': 'string',
                 'description': 'What the listing wants that his résumé does not show.'},
        'match': {'type': 'integer',
                  'description': 'Match percentage 0-100 against his résumé.'},
        'verdict': {'type': 'string', 'enum': ['apply', 'check', 'skip']},
        'note': {'type': 'string',
                 'description': 'One sentence, about fifteen words, saying why.'},
    },
    'required': ['strengths', 'gaps', 'match', 'verdict', 'note'],
    'additionalProperties': False,
}

# A hash of the prompt and the schema, so an edit to either invalidates every stored answer.
_APPLY_PROMPT_VERSION = hashlib.sha256(
    (_APPLY_SYSTEM_PROMPT + '\n'
     + json.dumps(_APPLY_OUTPUT_SCHEMA, sort_keys=True)).encode('utf-8')).hexdigest()[:12]


def _apply_prompt(job: dict) -> str:
    """One listing as part two sees it: the title searched for, the Level, and the posting."""
    return (
        f"Field: {clean_title(job.get(TITLE_ROW_KEY))}\n"
        f"Level: {_LEVEL_NAMES[clean_level(job.get(LEVEL_ROW_KEY))]}\n"
        f"Title: {job.get('title') or ''}\n"
        f"Company: {job.get('company') or ''}\n"
        f"Location: {job.get('location') or ''} ({job.get('country') or ''})\n"
        # Without our own note on the end -- see drop_note. This part can read a listing
        # that part one flagged (a flagged row still reaches the review dialog), so the note
        # really can be there, and it must not be matched against the résumé as if the
        # employer had written it.
        f"Description:\n{listing_text_without_note(job.get('description'))[:_CLAUDE_SCREEN_DESCRIPTION_MAX_CHARS]}"
    )


def _resume_section(text) -> str:
    return ('# His résumé\n\n'
            'the user uploaded this himself. It is the only source of facts about him.\n\n'
            '<resume>\n%s\n</resume>\n' % str(text or '').strip())


def _system_text(resume_text) -> str:
    """The instructions, then the résumé, as one plain string. No cache mark: every request
    here goes out in one batch and runs in parallel, where each writes the cache rather than
    reading another's -- measured on the screen's own batch path to cost more than it saved."""
    return _APPLY_SYSTEM_PROMPT + '\n\n' + _resume_section(resume_text)


def resume_match_cache_key(job: dict, resume_text) -> str:
    """Everything part two's answer depends on: the prompt, the résumé and the listing as
    sent -- title searched for and Level included."""
    from app.resume import fingerprint
    return hashlib.sha256(
        (_APPLY_PROMPT_VERSION + '\n' + fingerprint(resume_text) + '\n'
         + _apply_prompt(job)).encode('utf-8')).hexdigest()


def _read_answer(text: str):
    """(match, verdict, note, strengths, gaps), or None for an answer that cannot be used."""
    try:
        data = json.loads(text)
    except Exception:
        return None
    verdict = str(data.get('verdict') or '').strip().lower()
    if verdict not in ('apply', 'check', 'skip'):
        return None
    match = data.get('match')
    if isinstance(match, bool) or not isinstance(match, int):
        match = None
    else:
        match = max(0, min(100, match))
    return (match, verdict, str(data.get('note') or '').strip(),
            str(data.get('strengths') or '').strip(), str(data.get('gaps') or '').strip())


def claude_resume_match(client, jobs: list, resume_text: str, progress_cb=None,
                        should_cancel=None) -> dict:
    """{id(job): (match, verdict, note, strengths, gaps)} for every listing it could judge.

    One request per listing, all sent as one batch at half price. A listing that gets no
    answer is simply absent -- the caller leaves it as it was rather than guessing, because a
    wrong "skip" here costs the user a job he never sees.
    """
    if not jobs:
        return {}

    requests = []
    by_custom_id = {}
    for index, job in enumerate(jobs):
        custom_id = 'match-%d' % index
        by_custom_id[custom_id] = job
        params = dict(
            model=CLAUDE_MODEL,
            max_tokens=700,
            system=_system_text(resume_text),
            messages=[{'role': 'user', 'content': _apply_prompt(job)}],
            output_config={'format': {'type': 'json_schema',
                                      'schema': _APPLY_OUTPUT_SCHEMA}},
        )
        if 'haiku' in CLAUDE_MODEL or 'claude-3' in CLAUDE_MODEL:
            params['temperature'] = 0
        requests.append({'custom_id': custom_id, 'params': params})

    try:
        batch = client.messages.batches.create(requests=requests)
    except Exception as exc:
        if progress_cb:
            progress_cb('GLOG:filter_step:worth|warning|Could not ask Claude to match the '
                        'listings against your résumé (%s). They are all shown, unscored.'
                        % str(exc)[:90], 0, 1)
        return {}

    if progress_cb:
        progress_cb('GLOG:filter_step:worth|info|Matching the %d surviving listing(s) against '
                    'your résumé, one at a time.' % len(jobs), 0, len(jobs))

    if not _await_batch(client, batch.id, len(jobs), 'worth', progress_cb, should_cancel):
        return {}

    answers: dict = {}
    try:
        for result in client.messages.batches.results(batch.id):
            job = by_custom_id.get(result.custom_id)
            if job is None or result.result.type != 'succeeded':
                continue
            # Part two costs money too. Counted here as well as in the screening half, or
            # the Health Check reports a run at a fraction of what it really cost: the
            # first measurement of a Berlin-sized filter showed $0.0183 for screening and
            # nothing at all for the résumé match, which had read eight more listings.
            spend.record(CLAUDE_MODEL, getattr(result.result.message, 'usage', None),
                         batch=True, listings=1)
            # A cut-off answer is unfinished reasoning; reading a score out of it is how a
            # listing gets a number Claude never meant.
            if getattr(result.result.message, 'stop_reason', None) == 'max_tokens':
                continue
            text = '\n'.join(b.text for b in result.result.message.content
                             if getattr(b, 'type', None) == 'text')
            answer = _read_answer(text)
            if answer is not None:
                answers[id(job)] = answer
    except Exception:
        return answers

    if progress_cb:
        counts: dict = {}
        for _match, verdict, _note, _strengths, _gaps in answers.values():
            counts[verdict] = counts.get(verdict, 0) + 1
        progress_cb('GLOG:filter_step:worth|success|%d worth applying to, %d worth opening '
                    'first, %d not worth the time.'
                    % (counts.get('apply', 0), counts.get('check', 0),
                       counts.get('skip', 0)), 0, 1)
    return answers
