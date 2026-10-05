# -*- coding: utf-8 -*-
"""The Internship module's own Claude pass. Its own prompt, its own schema, its own plumbing.

The user's instruction: all three modules get a prompt of their own -- [owner's note: each of the three modules must have its own separate Claude prompt]. So nothing here is imported from
claude_screen/, which belongs to the Job module and is working; that file is not touched and
not read. The repetition between the three is the point.

WHY THIS PASS IS NEEDED AT ALL

The keyword rules in finder.py let a listing through when it says nothing about where the
work happens -- they have to, because 38% of these adverts never raise the subject. But that
leniency is what let a real Austrian run end with, side by side:

    Internship - Speech Recognition for Robotics    Infineon, Villach
    Video Editor Intern                             Cityfurnish, Gurugram
    Marketing Intern (Social Media)                 Cityfurnish, Gurugram

Both kinds are silent about remote work. No keyword separates them. What separates them is
what the internship IS -- its field, and whether it can be done from a desk in Turin -- and
that needs reading, which is what this pass does.

The Job module's prompt demands a quotable sentence before it drops anything, because there
silence already means drop and Claude never has to infer. Here silence survives the keyword
stage, so this prompt is explicitly allowed to judge an unstated arrangement from the work
itself. That difference between the two prompts is deliberate.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

# The job title the user is searching for -- the one thing all three modules agree on. Not a
# rule and not vocabulary; see search_title.py.
from ..prompt_any import any_workplace_prompt
from ..search_title import ROW_KEY as TITLE_ROW_KEY, clean_title, is_any_workplace, is_not_remote
from .prompt_not_remote import INTERNSHIP_SYSTEM_PROMPT_NOT_REMOTE


# This module's own model choice. Haiku is a classifier here, and it still accepts
# temperature -- worth having when the same advert should get the same verdict every run.
CLAUDE_MODEL = 'claude-haiku-4-5-20251001'


INTERNSHIP_SYSTEM_PROMPT = """# Internship screening for the user

Every posting below offers an internship, a working-student role or a traineeship. That part
is already decided -- do not re-litigate it. Your job is to say whether **this** one is worth
The user applying to. If it conflicts with anything below, **DROP**. Otherwise **KEEP**.

## Who it is for

The user. **Everything about him comes from his résumé**, given in full after these
instructions under "His résumé". Where he lives, which languages he speaks and how well, his
citizenship and residence status, the university he is enrolled at, his experience and his
skills — read them there, and nowhere else.

If a rule needs a fact his résumé does not give, do not guess it, and do not DROP for it.

## What he wants

A **paid internship in the work named on the Field line of the posting, that he can do from
his desk at home, in the city his résumé says he lives in** — for a company in any country.

Nothing he has done has to carry that title already. An internship is where someone starts
in a field, so this is never a reason to drop.

## DROP if any of these is true

1. **He would have to be present somewhere.** Office days per week, an
   attendance policy, "based in", relocation, hybrid as the working model — or a remote role
   restricted to a country he is not in ("remote within the US", "must be based in India",
   "within commuting distance of Amsterdam").

   Most of these adverts never mention the arrangement at all. **Silence is not evidence
   either way — so judge the work and the setting.**

   Work through these in order and stop at the first that applies. Say which one in
   `location_basis`, and make the verdict agree with it.

   1a. The posting says **this role** can be done remotely → KEEP, whatever the work.
   1b. The posting **requires the holder to be somewhere** → DROP. This means a sentence
       about the person: "Location: Amsterdam, 16-20 hours per week", "we are looking for a
       student in the greater area of Graz", "three days a week in our office", a workplace
       type of Hybrid, relocation, or a remote role restricted to a country he is not in
       ("remote within the US", "must be based in India").
   1c. **Home office appears only in a list of benefits** — "we offer home office, flexible
       hours, meal vouchers" → a perk for staff who already live there, not a remote role.
       DROP, and say so.
   1d. The work itself is **lab, hardware, manufacturing, retail, warehouse, clinical,
       studio or on-floor** work, and the posting says so → DROP.
   1e. Otherwise → **KEEP**.

   **Quote before you drop.** For 1b, 1c and 1d there must be words in the posting you could
   point at. If you cannot quote a sentence, you are at 1e, and 1e is a KEEP.

   Four things are NOT a reason to drop under this rule, and getting these wrong is the most
   common way this screening goes wrong:

   - **The Location and Company lines in the block above.** They say where the employer is.
     A company in Austria can supervise work done from his home. "Austria" on its own is
     never a reason.
   - **The absence of a remote statement.** Most of these adverts never raise the subject at
     all. Silence is 1e, and 1e is a KEEP.
   - **A field that *could* involve a site.** 1d needs the posting to say so. Do not infer a
     lab or a factory floor that the text does not describe.
   - **Anything you would describe as "implied".** If the word you reach for is "implied",
     "presumably", "likely" or "typically", you are inferring a requirement the posting does
     not make. That is 1e.

   If your reason for a DROP would be the country, the absence of a remote statement, or
   something the posting only implies, the answer is KEEP.
2. **It calls itself a working-student role and does not say the role is remote.**

   This rule fires only when the posting **uses one of these words**: "Werkstudent",
   "working student", "student worker", "studentische Hilfskraft", "studiejob",
   "studentmedarbetare", "student assistant", "Studentenjob", "praktikant naast je studie".
   If none of them appears, rule 2 does not apply — do not infer a working-student
   arrangement from the fact that a role is an internship, is part-time, or is aimed at
   students. An "Intern" or a "Traineeship" is not one of these.

   Where it does apply: these are not ordinary internships. They are a standing part-time
   job of 16–20 hours a week alongside study at a university in that same city, and the
   arrangement only exists for someone already living there. The user lives and studies where
   his résumé says, so he cannot hold one in another city however remote-friendly the work
   sounds.

   So a named working-student role is a DROP **unless the posting states plainly that this
   role is performed remotely**. A home-office benefit is not that statement. Silence is not
   that statement.
3. **It is not the work named on the Field line.** That line is the job title the user is
   searching for. The same work under any other name an employer gives it counts. A
   different job that only mentions it, or works alongside it, does not — however junior.
4. **It is unpaid** — voluntary, expenses-only, for credit alone, or self-funded. An
   internship that says nothing at all about pay is not a DROP under this rule.
5. **It requires a language he does not speak INSTEAD of English** — a language his résumé
   does not list, or one wanted fluent where his résumé gives a basic level, with English
   never named beside it.

   **A posting that wants English together with another language is a KEEP.** "Fluency in
   Dutch and English", "Deutsch und Englisch", "Nederlands en Engels", "English and at
   least one more language" — all KEEP. The posting has said the work can be done in a
   language he has, and whether the second one is a wall is a judgement about his own CV
   that he makes himself, looking at the advert. Taking it here takes it away from him.
   A bonus or nice-to-have is fine too, as it always was.

   So the only DROP under this rule is a posting that demands a language he lacks and never
   offers English anywhere near the demand.
6. **It requires enrolment at a university in a country other than the one his résumé says
   he studies in**, or a placement agreement his university cannot provide. Wanting an
   enrolled student is fine.

   Read the requirement against where he actually studies. If his university is in the EU,
   then "an EU university" or "a European university" is a requirement he ALREADY MEETS —
   never drop for that. Do not confuse this with rule 8: studying in a country is not the
   same as being its citizen.
7. **It is not a real vacancy** — a search-results or index page listing many positions, a
   course sold as an internship, a scheme charging a fee, one role posted across dozens
   of cities, or a page written ABOUT the work rather than offering any: a careers
   article, a guide, a role profile explaining what the role involves, an organisation
   describing itself. A real posting names one employer with one opening and says how to
   apply for it; if no single employer is taking anyone on here, it is not a vacancy.
8. **It requires a citizenship, residency, work permit or security clearance his résumé shows
   he does not have.** One his résumé shows he has is fine.
9. **It is a graduate scheme that requires having already graduated**, or it wants more than
   3 years of experience, or it is a senior role wearing an internship label.

## Never DROP for

- **A degree requirement.** Being a student is normal for an internship.
- **A city, country or company address on its own.** That says where the company is. Decide
  rule 1 by reading the work, not the address.
- **Silence about pay, duration or start date.** Not mentioning something is not a statement.
- **A short duration, or a start date far in the future.** A six-month internship starting
  next October is still worth seeing.
- **The job board's own furniture** — filter menus, "similar jobs", cookie notices, the site
  name in the page title.

## One trap

**A perk is not a working arrangement.** "Work from anywhere for one month a year", a
home-office allowance, flexible hours — none of these makes an internship remote. Look at
what the posting says about doing *this* work.
"""


# The whole description goes to Claude. The decisive sentence in an internship advert is
# routinely the last one -- eligibility and arrangements come after the sales pitch -- so
# truncating is exactly the wrong economy. The cap is a guard against a scraper returning a
# whole site in one field, nothing more.
_DESCRIPTION_MAX_CHARS = 60000


def _listing_prompt(row: dict) -> str:
    """One internship, as Claude sees it: every field together, judged as a unit.

    The location line is labelled the way it is because of what happened when it was not.
    It used to read "Location: (Netherlands)" -- the job board's country field, with an empty
    city -- and three real postings that contain no sentence about place or remote work
    anywhere in 1,900 characters were dropped with the reasons "Location: Netherlands, not
    Turin or Milan", "Netherlands-based role" and "Amsterdam office required". None of that
    was in the posting. The prompt already said the address is not a reason, twice, and said
    it again after being strengthened; Claude kept reading a field labelled "Location" as
    where the work happens, which is a fair reading of that word.

    So the label now says what the field actually is. Arguing with a misleading label is
    weaker than not writing one.

    The Field line is the job title in the Search box, which rule 3 judges against. Because
    it is part of this text, it is part of the cache key: a verdict reached for one title is
    never reused for another.
    """
    return (
        f"Field: {clean_title(row.get(TITLE_ROW_KEY))}\n"
        f"Title: {row.get('title') or ''}\n"
        f"Company: {row.get('company') or ''}\n"
        f"Where the employer is — job-board metadata, NOT a requirement on the candidate: "
        f"{row.get('location') or '—'} ({row.get('country') or '—'})\n"
        f"Source: {row.get('platform') or ''}\n"
        f"Employment type (as reported by the source): {row.get('employment_type') or ''}\n"
        # NOT "the only text that can support a DROP". That wording was tried and measured
        # in the Job module, where it turned a correct rule-5 drop into a KEEP: a listings
        # page announces itself in its TITLE, and saying only the description counts took
        # that evidence away.
        f"Description:\n"
        f"{(row.get('description') or '')[:_DESCRIPTION_MAX_CHARS]}"
    )


# `checked` first, and that ordering is the design rather than a detail: JSON fields are
# generated in schema order, so a verdict placed first would have to be named before the
# model has written anything. `location_basis` sits before the verdict for the same reason --
# it forces the question this pass exists to answer to be settled in words first.
#
# `minimum`/`maximum` are deliberately absent: the API rejects them on integer fields, so
# `match` is clamped in code below instead.
_OUTPUT_SCHEMA: dict = {
    'type': 'object',
    'properties': {
        'checked': {
            'type': 'string',
            'description': 'Your brief pass through rules 1-9, in order. One short clause '
                           'per rule that mattered.',
        },
        'field': {
            'type': 'string',
            'description': 'What kind of work this internship actually is, in three words '
                           'or fewer -- "machine learning", "social media", "lab testing".',
        },
        # The reporting values matter as much as the verdict. An earlier version offered
        # only "silent" and "says on-site", so a posting opening with "Location: Amsterdam"
        # and one that genuinely said nothing came back with the same label -- the verdict
        # was right and the Log was wrong, which is the kind of thing nobody catches.
        'location_basis': {
            'type': 'string',
            'enum': ['says this role is remote',
                     'says on-site or hybrid',
                     'names a place the holder must be',
                     'home office listed only as a benefit',
                     'working-student role, inherently local',
                     'silent - work needs a site',
                     'silent - work is data or code'],
            'description': 'How you settled rules 1 and 2. Pick the one that decided it.',
        },
        'verdict': {'type': 'string', 'enum': ['KEEP', 'DROP']},
        'rule': {'type': 'integer',
                 'description': 'Which rule (1-9) forced a DROP, or 0 for a KEEP.'},
        'reason': {'type': 'string',
                   'description': 'Twelve words or fewer, naming the rule. Empty for a KEEP.'},
    },
    # No `match`: scoring an internship against the user is the second part's job now, read
    # against his uploaded résumé (claude_screen/worth.py). This part only decides. The
    # field was last, after the verdict, so taking it out cannot move a verdict.
    'required': ['checked', 'field', 'location_basis', 'verdict', 'rule', 'reason'],
    'additionalProperties': False,
}


# A hash of this module's prompt AND its schema, so any edit to either invalidates every
# cached verdict automatically -- there is no number to forget to bump. The schema is hashed
# in because it changes the decisions and not merely their shape.
_PROMPT_VERSION = hashlib.sha256(
    (INTERNSHIP_SYSTEM_PROMPT + '\n'
     + json.dumps(_OUTPUT_SCHEMA, sort_keys=True)).encode('utf-8')).hexdigest()[:12]

CACHE_KEY = 'internship_claude_cache_key'
VERDICT_KEY = 'internship_claude_verdict'
REASON_KEY = 'internship_claude_reason'
MATCH_KEY = 'internship_claude_match'
BASIS_KEY = 'internship_claude_location_basis'
FIELD_KEY = 'internship_claude_field'


def resume_text() -> str:
    """The résumé uploaded in Search, as read when it was accepted. '' when there is none."""
    from app.resume import load_resume_text
    return load_resume_text()


def resume_section(text) -> str:
    """This module's own copy of the "His résumé" block, which the rules point to for every
    fact about the user. After the rules, so the two are cached together across a run."""
    return ('# His résumé\n\n'
            'the user uploaded this himself. It is the only source of facts about him.\n\n'
            '<resume>\n%s\n</resume>\n' % str(text or '').strip())


# The same rules for a Not Remote search, written out in full in their own file: rule 1 and
# the working-student rule turned the other way, the home-city exception gone.
_PROMPT_VERSION_NOT_REMOTE = hashlib.sha256(
    (INTERNSHIP_SYSTEM_PROMPT_NOT_REMOTE + '\n'
     + json.dumps(_OUTPUT_SCHEMA, sort_keys=True)).encode('utf-8')).hexdigest()[:12]


_PROMPT_ANY = any_workplace_prompt(INTERNSHIP_SYSTEM_PROMPT_NOT_REMOTE, 'internship')
_PROMPT_VERSION_ANY = hashlib.sha256(
    (_PROMPT_ANY + '\n' + json.dumps(_OUTPUT_SCHEMA, sort_keys=True)).encode('utf-8')).hexdigest()[:12]


def system_prompt_for(row) -> str:
    """This module's rules for the Remote, Not Remote or Any choice the row is filtered at."""
    if is_any_workplace(row or {}):
        return _PROMPT_ANY
    return INTERNSHIP_SYSTEM_PROMPT_NOT_REMOTE if is_not_remote(row or {}) \
        else INTERNSHIP_SYSTEM_PROMPT


def cache_key(row: dict) -> str:
    """Everything that influences the verdict for this internship: its exact prompt text,
    the version of the prompt it was judged by (Remote or Not Remote) and the résumé it was
    judged against. Stored on the row so a later Filter run can skip the billed call when
    none of them has changed."""
    from app.resume import fingerprint
    version = (_PROMPT_VERSION_ANY if is_any_workplace(row)
               else _PROMPT_VERSION_NOT_REMOTE if is_not_remote(row) else _PROMPT_VERSION)
    return hashlib.sha256(
        (version + '\n' + fingerprint(resume_text()) + '\n'
         + _listing_prompt(row)).encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------------------
# Talking to the API
# ---------------------------------------------------------------------------------------

_MAX_TOKENS = 600
_MAX_TOKENS_RETRY = 1400
_RETRY_ATTEMPTS = 3
_RETRY_BASE_SECONDS = 1.5

_TRANSIENT_NAMES = ('RateLimitError', 'InternalServerError', 'APIConnectionError',
                    'APITimeoutError', 'ServiceUnavailableError', 'OverloadedError')
_TRANSIENT_TEXT = re.compile(
    r'overloaded|rate.?limit|too many requests|timeout|timed out|temporarily|'
    r'connection (reset|aborted|error)|502|503|504', re.I)


def _is_transient(exc: Exception) -> bool:
    """Worth sending again, or the same answer every time?"""
    status = getattr(exc, 'status_code', None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    if type(exc).__name__ in _TRANSIENT_NAMES:
        return True
    return bool(_TRANSIENT_TEXT.search(str(exc)))


def _read_answer(answer: str) -> tuple:
    """Read one schema-constrained JSON verdict.

    Returns (drop, reason, match, basis, field, error, retry). `match` is always None now --
    the score comes from the résumé match in the second part -- and is kept in the tuple so
    everything that reads one stays unchanged.
    """
    try:
        data = json.loads(answer)
    except Exception:
        # The grammar makes this all but impossible, which is why it is not trusted blindly:
        # if it ever happens it is retried, never read as a silent KEEP.
        return False, None, None, None, None, 'Claude returned an unparseable answer', True

    drop = str(data.get('verdict', '')).upper() == 'DROP'
    reason = None
    if drop:
        rule = data.get('rule')
        text = str(data.get('reason') or '').strip() or 'unspecified reason'
        reason = f'Rule {rule} - {text}' if isinstance(rule, int) and rule else text

    match = data.get('match')
    if isinstance(match, bool) or not isinstance(match, int):
        match = None
    else:
        match = max(0, min(100, match))

    return (drop, reason, match,
            str(data.get('location_basis') or '') or None,
            str(data.get('field') or '') or None, None, False)


_GROUP_ITEM_SCHEMA: dict = {
    'type': 'object',
    'properties': dict(
        {'listing': {'type': 'integer',
                     'description': 'The number of the internship this answer is about.'}},
        **_OUTPUT_SCHEMA['properties']),
    'required': ['listing'] + list(_OUTPUT_SCHEMA['required']),
    'additionalProperties': False,
}
_GROUP_SCHEMA: dict = {
    'type': 'object',
    'properties': {'answers': {'type': 'array', 'items': _GROUP_ITEM_SCHEMA}},
    'required': ['answers'],
    'additionalProperties': False,
}


def _request_params(rows: list) -> dict:
    """One request carrying several internships, each judged on its own.

    Sharing a request is what makes this affordable -- the prompt is identical for every
    listing, so sent one at a time it is paid for once per internship. Three at a time is
    this module's own choice: the Job module measured that crowding a request makes Claude
    less willing to say no, and rules 1 and 2 here both ask for a judgement rather than a
    lookup.
    """
    body = '\n\n'.join('===== INTERNSHIP %d =====\n%s' % (i + 1, _listing_prompt(row))
                       for i, row in enumerate(rows))
    params = dict(
        model=CLAUDE_MODEL,
        max_tokens=_MAX_TOKENS * len(rows),
        # One Filter run stamps one Remote or Not Remote choice on every row. A plain string,
        # as this module always sent: no cache mark on requests that run in parallel.
        system=(system_prompt_for(rows[0] if rows else None) + '\n\n'
                + resume_section(resume_text())),
        messages=[{'role': 'user', 'content':
                   'Below are %d separate internship postings, numbered 1 to %d. Judge each '
                   'on its own, exactly as you would if it were the only one in front of '
                   'you. Nothing in one posting tells you anything about another. Answer '
                   'every one, in order, and put its number in each answer.\n\n%s'
                   % (len(rows), len(rows), body)}],
    )
    # temperature was removed from the API on the 4.6+ models and is a 400 there. Haiku 4.5
    # still takes it, and determinism is worth having on a classifier.
    if 'haiku' in CLAUDE_MODEL or 'claude-3' in CLAUDE_MODEL:
        params['temperature'] = 0
    params['output_config'] = {'format': {'type': 'json_schema', 'schema': _GROUP_SCHEMA}}
    return params


# One listing per request. The Job module shares a request between three because it screens
# hundreds and the prompt would otherwise be paid for once per listing; this module screens
# between fifteen and eighty, so it can afford the accurate answer.
#
# And it is the accurate one. Measured on the Job module's 93-listing corpus, same prompt,
# all sizes in one batch so nothing else could differ: one-at-a-time kept 3, three kept 6,
# ten kept 9 -- and every disagreement at the larger sizes was a listing wrongly KEPT.
# Crowding a request does not make Claude reason worse about the advert in front of it so
# much as make it less willing to say no.
#
# Sharing also makes the answer depend on WHICH listings happen to share the request, and
# that showed up here as results that moved between runs: a QuantumBlack internship scored
# 85% in one run and was dropped in the next, because the pool had shrunk from 45 to 15 and
# its neighbours changed. At one per request there are no neighbours.
#
# The cost of this on a real Austrian run is about thirteen cents.
_GROUP_SIZE = 1

# Below this many internships, a queued batch is not worth the wait -- a batch is half price
# but is answered on Anthropic's own schedule, usually within the hour and occasionally 24.
# A real run screens dozens here, so unlike the Thesis module this one will normally batch.
_BATCH_WORTH_IT = 15

_BATCH_POLL_SECONDS = 30
_BATCH_MAX_WAIT_SECONDS = 24 * 60 * 60


def _await_batch(client, batch_id, total, progress_cb=None, should_cancel=None) -> bool:
    """Wait for this module's batch. True when it ended, False if cancelled or timed out.

    A failed retrieve is slept through rather than treated as an ending: the batch is still
    running on Anthropic's side, and giving up over one bad HTTP response would abandon work
    already paid for.
    """
    started = time.time()
    while True:
        if should_cancel and should_cancel():
            try:
                client.messages.batches.cancel(batch_id)
            except Exception:
                pass
            if progress_cb:
                progress_cb('GLOG:filter_step:internship|warning|Internship batch cancelled.',
                            0, 1)
            return False
        try:
            current = client.messages.batches.retrieve(batch_id)
        except Exception:
            time.sleep(_BATCH_POLL_SECONDS)
            continue
        if current.processing_status == 'ended':
            return True
        if time.time() - started > _BATCH_MAX_WAIT_SECONDS:
            if progress_cb:
                progress_cb('GLOG:filter_step:internship|error|The Internship batch did not '
                            'finish within 24 hours.', 0, 1)
            return False
        if progress_cb:
            counts = getattr(current, 'request_counts', None)
            done = (getattr(counts, 'succeeded', 0) or 0) if counts else 0
            progress_cb("  Waiting for the Internship batch… (%d of %d answered, %.0f minutes)"
                        % (done, total, (time.time() - started) / 60), done, total)
        time.sleep(_BATCH_POLL_SECONDS)


def _read_group(text: str, rows: list) -> dict:
    """Match answers back to internships by their number, never by position.

    An answer whose number is missing or out of range is discarded rather than applied to
    the neighbouring listing: applying one verdict to the wrong internship is the single
    failure here that would never show up in a log.
    """
    out: dict = {}
    try:
        answers = list(json.loads(text).get('answers') or [])
    except Exception:
        return out
    for item in answers:
        if not isinstance(item, dict):
            continue
        number = item.get('listing')
        if isinstance(number, bool) or not isinstance(number, int):
            continue
        if not 1 <= number <= len(rows):
            continue
        drop, reason, match, basis, field, error, _retry = _read_answer(json.dumps(item))
        if not error:
            out[id(rows[number - 1])] = (drop, reason, match, basis, field)
    return out


def _direct_params(rows: list) -> dict:
    """_request_params, reshaped for an immediate call rather than a batch.

    The difference is not cosmetic. A batch request's params are serialised to JSON and sent
    as data, so `output_config` sits in them quite happily. An immediate call goes through
    the SDK's typed signature, and the installed SDK (0.72.0) predates that parameter -- it
    raises TypeError on an unexpected keyword. `extra_body` is the documented way past that,
    and the API itself accepts the field.

    This cost a whole live run to find, because the retry loop below used to swallow the
    exception and return no answers at all -- which looked exactly like Claude declining to
    answer. Hence the error reporting in screen().
    """
    params = _request_params(rows)
    output_config = params.pop('output_config', None)
    if output_config is not None:
        params['extra_body'] = {'output_config': output_config}
    return params


def _screen_group_now(client, rows: list) -> tuple:
    """One immediate request for a group.

    Returns ({id(row): (drop, reason, match, basis, field)}, error). The error is returned
    rather than swallowed so a misconfigured request cannot look like a quiet "no answer".
    """
    params = _direct_params(rows)
    last_error = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            response = client.messages.create(**params)
        except Exception as exc:
            last_error = '%s: %s' % (type(exc).__name__, str(exc)[:160])
            if _is_transient(exc) and attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_BASE_SECONDS * (2 ** attempt))
                continue
            return {}, last_error
        # Checked before anything is read: a cut-off answer is unfinished reasoning, and
        # reading a verdict out of unfinished reasoning is how a real internship gets deleted
        # for a sentence Claude was still in the middle of writing.
        if getattr(response, 'stop_reason', None) == 'max_tokens':
            params['max_tokens'] = _MAX_TOKENS_RETRY * len(rows)
            last_error = 'Claude did not finish its answer'
            continue
        text = '\n'.join(b.text for b in response.content
                         if getattr(b, 'type', None) == 'text')
        return _read_group(text, rows), None
    return {}, last_error


def _screen_now(client, groups: list, progress_cb=None, should_cancel=None) -> dict:
    """Ask about every group immediately, reporting any error rather than hiding it.

    The reporting is the point. An earlier version returned an empty dict on failure, which
    is indistinguishable from Claude having nothing to say -- and a real run spent its whole
    length looking like the latter when it was the former.
    """
    answers: dict = {}
    errors: dict = {}
    for group in groups:
        if should_cancel and should_cancel():
            break
        got, error = _screen_group_now(client, group)
        answers.update(got)
        if error:
            errors[error] = errors.get(error, 0) + 1
    if errors and progress_cb:
        for error, count in sorted(errors.items(), key=lambda kv: -kv[1]):
            progress_cb('GLOG:filter_step:internship|error|Claude could not answer %d '
                        'Internship request(s): %s. Those listings are kept unjudged.'
                        % (count, error), 0, 1)
    return answers


def screen(client, rows: list, progress_cb=None, should_cancel=None) -> dict:
    """Ask Claude about every internship. Returns {id(row): (drop, reason, match, basis,
    field)}.

    Anything missing from the returned dict was not answered -- a failed request, an answer
    with a bad number, a group cut short. The caller keeps those rather than guessing, so a
    hiccup can never silently delete an internship.
    """
    if not rows:
        return {}

    groups = [rows[i:i + _GROUP_SIZE] for i in range(0, len(rows), _GROUP_SIZE)]

    if len(rows) < _BATCH_WORTH_IT:
        if progress_cb:
            progress_cb('GLOG:filter_step:internship|info|%d internship listing(s) sent to '
                        'Claude now, in %d request(s). Too few to be worth a queued batch.'
                        % (len(rows), len(groups)), 0, len(rows))
        return _screen_now(client, groups, progress_cb, should_cancel)

    requests = []
    by_id = {}
    for index, group in enumerate(groups):
        custom_id = 'internship-%d' % index
        by_id[custom_id] = group
        requests.append({'custom_id': custom_id, 'params': _request_params(group)})

    try:
        batch = client.messages.batches.create(requests=requests)
    except Exception as exc:
        if progress_cb:
            progress_cb('GLOG:filter_step:internship|warning|Could not send the Internship '
                        'batch (%s) — asking now instead.' % str(exc)[:80], 0, 1)
        return _screen_now(client, groups, progress_cb, should_cancel)

    if progress_cb:
        progress_cb('GLOG:filter_step:internship|info|%d internship listing(s) sent to '
                    'Claude as a batch, in %d request(s) of up to %d. Batches are half price '
                    'and are queued rather than answered immediately.'
                    % (len(rows), len(groups), _GROUP_SIZE), 0, len(rows))

    if not _await_batch(client, batch.id, len(rows), progress_cb, should_cancel):
        return {}

    answers = {}
    try:
        for result in client.messages.batches.results(batch.id):
            # A name of its own: `group` above is a list, and reusing it for a lookup that
            # can come back with nothing muddles the two.
            answered = by_id.get(result.custom_id)
            if not answered or result.result.type != 'succeeded':
                continue
            text = '\n'.join(b.text for b in result.result.message.content
                             if getattr(b, 'type', None) == 'text')
            answers.update(_read_group(text, answered))
    except Exception as exc:
        if progress_cb:
            progress_cb('GLOG:filter_step:internship|warning|Could not read the Internship '
                        'batch results (%s).' % str(exc)[:80], 0, 1)
    return answers
