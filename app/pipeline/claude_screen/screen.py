# -*- coding: utf-8 -*-
"""The eight questions, asked of every listing that survived the keyword rules.

Two ways of asking, and they answer identically: one listing per call, and three to a
request sent as a batch. The batch is what a real run uses -- half price, and the
prompt paid for once per request instead of once per listing -- and the sequential
path is the fallback for anything the batch could not answer.
"""
from __future__ import annotations

import json
import re
import time

from .prompt import (CLAUDE_MODEL,
                     _KEEP_DROP_LINE_PATTERN,
                     _MATCH_LINE_PATTERN, _NOT_AN_EMPLOYER, _SCREEN_OUTPUT_SCHEMA,
                     _claude_screen_prompt, current_resume_text, system_blocks_for,
                     system_text_for)
from .batch import (_await_batch)
from . import spend
from ..drop_note import listing_text_without_note


_TRANSIENT_ERROR_NAMES = (
    'RateLimitError', 'InternalServerError', 'APIConnectionError', 'APITimeoutError',
    'APIConnectionTimeoutError', 'ServiceUnavailableError', 'OverloadedError',
)
_TRANSIENT_ERROR_TEXT = re.compile(
    r'overloaded|rate.?limit|too many requests|timeout|timed out|temporarily|'
    r'connection (reset|aborted|error)|502|503|504', re.I)


def _is_transient(exc: Exception) -> bool:
    """Worth sending again, or the same answer every time?"""
    status = getattr(exc, 'status_code', None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    if type(exc).__name__ in _TRANSIENT_ERROR_NAMES:
        return True
    return bool(_TRANSIENT_ERROR_TEXT.search(str(exc)))


# A screen that errors is deliberately never cached, so that a hiccup is retried rather
# than frozen in as "no decision". The cost of that correct choice is that a listing which
# errors keeps costing an API call on EVERY future Filter run -- and a real live run showed
# exactly that: one row of three failed, reproducibly, when screened as part of a burst.
#
# So a transient failure is retried here, before it becomes the caller's problem. Only
# transient ones: a bad key or a malformed request will fail identically however many times
# it is sent, and retrying those just makes the user wait longer for the same error.
_SCREEN_RETRY_ATTEMPTS = 3
_SCREEN_RETRY_BASE_SECONDS = 1.5

def claude_screen_one(client, job: dict):
    """Asks Claude the eight questions about one listing, scores it against the user's profile,
    and reads the employer's name out of the posting (see CLAUDE_SCREEN_SYSTEM_PROMPT).

    Returns (drop, reason, match_percent, error, employer). Fails open (drop=False) if the
    API call itself errors out, so a network hiccup never silently deletes data -- but the
    error is returned so the caller can report it. match_percent is None if Claude's
    response didn't contain a parseable MATCH line (e.g. the call errored), and employer is
    None whenever the posting does not name one, which is the normal case.

    A transient failure is retried with a growing pause before it is reported as an error;
    see _SCREEN_RETRY_ATTEMPTS. An answer Claude did not finish is retried immediately with
    a larger token budget instead, since waiting changes nothing about running out of room."""
    last_error: str | None = None
    max_tokens = _SCREEN_MAX_TOKENS
    for attempt in range(_SCREEN_RETRY_ATTEMPTS):
        drop, reason, match_percent, error, retry, employer = _screen_once(
            client, job, max_tokens)
        if not retry:
            return drop, reason, match_percent, error, employer
        last_error = error
        if error == _SCREEN_INCOMPLETE_ERROR:
            max_tokens = _SCREEN_MAX_TOKENS_RETRY
            continue
        if attempt < _SCREEN_RETRY_ATTEMPTS - 1:
            time.sleep(_SCREEN_RETRY_BASE_SECONDS * (2 ** attempt))
    return False, None, None, last_error, None


_REJECTS_SCHEMA_TEXT = re.compile(r'output_config|output_format|json_schema|'
                                  r'unexpected keyword argument|unknown (field|parameter)', re.I)


def _rejects_structured_output(exc: Exception) -> bool:
    """Is this the API (or SDK) saying it will not take a schema, rather than a real fault?

    Deliberately narrow. A 429 or a 500 must NOT land here -- those are transient and are
    retried as themselves; treating one as "schemas are unsupported" would quietly downgrade
    every remaining listing in the run over a momentary hiccup.
    """
    status = getattr(exc, 'status_code', None)
    if isinstance(status, int) and status not in (400, 404, 422):
        return False
    return bool(_REJECTS_SCHEMA_TEXT.search(str(exc)))


# The answer is two short lines, so 100 tokens is the right budget for it -- measured over
# 240 real listings, 239 finished on end_turn using at most ~75 of them.
#
# The 240th is why the second number exists. Occasionally Claude obeys the prompt's
# "check all 9 rules as a complete, sequential pipeline" literally and writes the review
# out, rule by rule, running out of room before it ever reaches the verdict. Repeating that
# request unchanged is pointless -- temperature is 0, so the same request returns the same
# truncated answer -- which is exactly what the first version of this retry did: three
# billed calls to fail three identical times. What the answer actually needs is room to
# finish, so the retry gives it room. Confirmed on the listing that exposed this
# ("Data Scientist - AI Search & Ranking - Dusseldorf"): truncated at 100, and a clean
# "KEEP / MATCH: 62" at 600.
#
# Truncation also has to invalidate the whole answer, not just an unparseable one. A
# half-written review is prose about the rules, and prose contains sentences like
# "No DROP." and "RULE 2 -- REMOTE RULE" -- one stray line beginning "DROP:" in the middle
# of that reasoning would be read as the verdict and delete a job the user should have seen.
#
# 500, not 100, because the schema-constrained answer carries its `checked` pass over the
# nine rules: measured over 60 real listings it used 195 output tokens on average and 348 at
# the worst. The old 100 was right for the two bare lines the prose format asked for.
_SCREEN_MAX_TOKENS = 500
_SCREEN_MAX_TOKENS_RETRY = 1200
_SCREEN_INCOMPLETE_ERROR = 'Claude did not finish its answer'

# One-element list so a single rejection is remembered for the rest of the process without
# a global statement in the hot path. Starts True: the schema is what the app wants.
_STRUCTURED_OUTPUT_SUPPORTED = [True]

def _read_structured_answer(answer: str, job: dict | None = None):
    """Read the schema-constrained JSON answer.

    Returns (drop, reason, match, error, retry, employer). The employer rides along in the
    screening answer rather than in a second call of its own: 86% of the listings that
    reach Claude arrive with no company name, so a separate pass would run on nearly all of
    them and cost 23% more than asking here.
    """
    try:
        data = json.loads(answer)
    except Exception:
        # The grammar makes this all but impossible, which is exactly why it is not trusted
        # blindly: if it ever does happen, it is retried rather than read as a silent KEEP.
        return False, None, None, 'Claude returned an unparseable answer', True, None

    # Rule 4's replacement, written onto the row before anything else is decided. Claude is
    # asked what level the posting is pitched at and the listing is kept whatever the answer
    # -- so this is the one field here that is recorded for a KEEP as well as a DROP.
    #
    # Written even when the verdict is DROP: a listing removed for being on-site is still a
    # Senior listing, and the Jobs table shows the Seniority column for every row it has.
    if job is not None:
        said = str(data.get('seniority') or '').strip()
        if said in ('Intern', 'Junior', 'Mid', 'Senior', 'Lead', 'Unspecified'):
            job['claude_seniority'] = said

    drop = str(data.get('verdict', '')).upper() == 'DROP'
    reason = None
    if drop:
        rule = data.get('rule')
        text = str(data.get('reason') or '').strip() or 'unspecified reason'
        reason = f'Rule {rule} - {text}' if isinstance(rule, int) and rule else text
        # A DROP has to be able to point at words in the posting. Measured over 117 real
        # DROPs, 11 could not: "unpaid" where pay is never mentioned, "on-site" where only a
        # city is named, "2+ years implied", "no on-site requirement stated" -- each of them
        # a rule the prompt already gives ("silence is not a statement", "quote before you
        # drop") and each one still broken often enough to cost real jobs. Asking harder in
        # the prompt cut them from 17 to 11; this is the part that cannot be talked out of.
        # A listing whose quote is not in it goes back to being a KEEP, which is the safe
        # direction: The user loses nothing but a line in the review dialog.
        evidence = data.get('drop_evidence')
        if job is not None and not (_evidence_is_real(evidence, job)
                                    and _evidence_fits_rule(rule, evidence)):
            drop, reason = False, None
        elif job is not None:
            # Kept, not discarded. This is the only place the quote exists, and until it was
            # written down a removal left no trace on the listing: auditing the real Germany
            # run needed a throwaway script, and two of ninety-four drops could not be
            # explained at all. app/pipeline/drop_note.py puts it on the end of the posting.
            job['claude_screen_evidence'] = str(evidence or '').strip() or None

    match_percent = data.get('match')
    if isinstance(match_percent, bool) or not isinstance(match_percent, int):
        match_percent = None
    else:
        match_percent = max(0, min(100, match_percent))

    # The employer only survives if the quote backing it is really in the posting. This
    # name goes on to be matched against government visa-sponsor registers, and a
    # plausible invention would match something there.
    employer = str(data.get('employer') or '').strip().strip('*`_"\'').strip()
    if employer and not _NOT_AN_EMPLOYER.match(employer):
        if job is None or _evidence_is_real(data.get('employer_evidence'), job):
            pass
        else:
            employer = ''
    else:
        employer = ''

    return drop, reason, match_percent, None, False, employer or None


def _screen_once(client, job: dict, max_tokens: int = _SCREEN_MAX_TOKENS):
    """One attempt. Returns the usual 4-tuple plus whether it is worth trying again."""
    try:
        # Prompt caching: CLAUDE_SCREEN_SYSTEM_PROMPT is thousands of tokens and
        # IDENTICAL on every call in reapply_filters' sequential per-listing loop --
        # without cache_control, the full prompt was billed at full input-token price
        # on every single listing screened. Only the first call per ~5-minute cache
        # window pays full price; every later call in the same Filter run reads it at a
        # much lower rate -- a real, sizeable, easily-avoidable cost for a Filter run
        # over more than a couple of jobs.
        # The prompt is the one for the Level this row was filtered at (Junior's is
        # CLAUDE_SCREEN_SYSTEM_PROMPT), followed by the user's résumé; every row in one Filter
        # run carries the same Level and is read against the same résumé, so the cache still
        # holds across the run.
        system_blocks = system_blocks_for(job, current_resume_text())

        request = dict(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": _claude_screen_prompt(job)}],
        )
        # temperature was REMOVED from the API on Sonnet 5, Opus 5 and the whole 4.6+
        # family: sending it is a 400 on every single call, which a model comparison found
        # the hard way -- 60 of 60 Sonnet requests failed before the parameter was dropped.
        # Haiku 4.5 still accepts it and determinism is worth having on a classifier, so it
        # is sent only where it is legal.
        if 'haiku' in CLAUDE_MODEL or 'claude-3' in CLAUDE_MODEL:
            request['temperature'] = 0
        # Sent through extra_body rather than a named argument because the installed SDK
        # (0.72.0) predates the parameter; the API itself accepts it, confirmed with real
        # calls. If a future SDK adds it natively this can become output_config=... .
        structured = _STRUCTURED_OUTPUT_SUPPORTED[0]
        if structured:
            request['extra_body'] = {
                'output_config': {'format': {'type': 'json_schema',
                                             'schema': _SCREEN_OUTPUT_SCHEMA}}}

        try:
            response = client.messages.create(**request)
        except Exception as exc:
            # If this build of the API will not take the schema, screening must carry on
            # rather than stop -- the prose path below still works, it is simply the one
            # with the failure modes the schema was adopted to remove. Recorded once so the
            # rest of the run does not keep paying for the same rejection.
            if structured and _rejects_structured_output(exc):
                _STRUCTURED_OUTPUT_SUPPORTED[0] = False
                request.pop('extra_body', None)
                response = client.messages.create(**request)
            else:
                raise

        spend.record(CLAUDE_MODEL, getattr(response, 'usage', None), listings=1)

        text_parts = [block.text for block in response.content if getattr(block, 'type', None) == 'text']
        answer = '\n'.join(text_parts).strip()

        # Checked BEFORE anything is read out of the answer: a cut-off answer is unfinished
        # reasoning, and reading a verdict out of unfinished reasoning is how a job gets
        # deleted for a sentence Claude was still in the middle of writing.
        if getattr(response, 'stop_reason', None) == 'max_tokens':
            return False, None, None, _SCREEN_INCOMPLETE_ERROR, True, None

        if _STRUCTURED_OUTPUT_SUPPORTED[0]:
            return _read_structured_answer(answer, job)

        drop = False
        reason = None
        kd_match = _KEEP_DROP_LINE_PATTERN.search(answer)
        if kd_match:
            line = kd_match.group(0).strip()
            if line.upper().startswith('DROP'):
                drop = True
                reason = line.split(':', 1)[1].strip() if ':' in line else 'unspecified reason'

        match_percent = None
        match = _MATCH_LINE_PATTERN.search(answer)
        if match:
            match_percent = max(0, min(100, int(match.group(1))))

        # A complete answer that still says nothing is worth one more try too. Until now it
        # was accepted silently: the listing was kept with no reason and no Match %,
        # indistinguishable from a real KEEP. Caught by the live suite failing once on
        # "a MATCH percentage was parsed" and passing on the next run.
        if kd_match is None and match is None:
            return False, None, None, 'Claude returned an unparseable answer', True, None

        # The prose fallback has no employer field; the schema path is where names come from.
        return drop, reason, match_percent, None, False, None
    except Exception as e:
        return False, None, None, str(e), _is_transient(e), None


# What a quote has to contain to be able to carry the rule it is offered for. Only the three
# rules that were measured being stretched are listed; every other rule passes on the quote
# being real, which is all _evidence_is_real can ask.
#
# Why this exists: checking that the quoted words are in the posting stops an invented
# sentence, not an irrelevant one. A DROP reading "Rule 3 - unpaid volunteer position" on an
# internship that never mentions money passed that check by quoting some other true sentence.
# So a quote offered for rule 3 now has to contain a word about not being paid, one for
# rule 2 a language, one for rule 4 a number or a seniority word -- in any of the languages
# this app reads. A quote that cannot is treated as no quote, and the DROP becomes a KEEP.
_EVIDENCE_MUST_CONTAIN = {
    # The word for "language" is a compound in half of these languages, so the bare noun is
    # not what a posting writes: German says Sprachkenntnisse and Sprachniveau, never
    # "Sprache", and the guard could not see either. Matched on the stem for the same reason
    # muttersprach\w* already is.
    2: re.compile(
        r'\b(dutch|nederlands\w*|german|deutsch\w*|french|fran[cç]ais\w*|italian|italian[oa]|'
        r'norwegian|norsk\w*|swedish|svenska|danish|dansk|finnish|suomi\w*|spanish|espa[nñ]ol|'
        # Dutch pluralises "taal" to "talen", which no stem covers -- and a bare `talen\w*`
        # would swallow "talent", a word in half the adverts on the board. Spelled out so it
        # cannot.
        r'portuguese|portugu[eê]s|language|taal\w*|talen(?:kennis)?|'
        r'sprach\w*|langue\w*|lingu[ae]\w*|'
        r'spr[åa]k\w*|kieli\w*|idioma\w*|'
        r'fluent|vloeiend|flytende|muttersprach\w*|mother ?tongue|native speaker|'
        r'b2|c1|c2)\b', re.I),
    # Two whole languages named unpaid work in a word this did not hold: Dutch onbezoldigd
    # and Italian non retribuito. Found offline, by trying the sentences a posting would
    # really write against the pattern -- the same class of blindness as rule 4's "eight",
    # and cheaper to find, because the guard is a pure function of the words.
    3: re.compile(
        r'\b(unpaid|onbetaal\w*|onbezoldig\w*|vrijwillig\w*|volunteer|voluntary|ehrenamt\w*|'
        r'unbezahlt\w*|unverg[uü]tet\w*|ohne verg[uü]tung|ul[øo]nnet|non r[eé]mun[eé]r\w*|'
        r'b[eé]n[eé]vol\w*|non retribuit\w*|senza retribuzione|sin remunerac\w*|'
        r'no salary|geen salaris|zonder salaris|kein gehalt|'
        r'without pay|expenses only|onkostenvergoeding|for credit|study credits|'
        r'studiepunten|ects|self[- ]funded|fee|tuition)\b', re.I),
    # "a number" meant a digit here, and adverts write the number in words as often as not:
    # "at least eight years of experience, who has led a data science team of five or more"
    # carries no digit, no `experienced` (it says "experience"), and no `lead` (it says
    # "led") -- so the quote was rejected, the DROP became a KEEP, and a role wanting eight
    # years reached the user as a junior opening. Counterfactual testing found it: Claude answered
    # DROP rule 4 three times out of three, and the guard overturned all three. The same
    # sentence with "8" instead of "eight" was dropped correctly, which is what named the
    # cause.
    #
    # Rather than list the cardinals of eleven languages -- where Norwegian "to" and Swedish
    # "sex" would match ordinary English words -- the span of time is what is matched. A
    # rule 4 quote says how much experience is wanted, and to say that it must name a unit:
    # years, Jahre, jaar, ans, anni, años, år, vuotta. That covers the number written either
    # way, in every language this app reads.
    4: re.compile(
        r'(\d'
        r'|\b(years?|jahr|jahren?|jaar|ans|ann[ée]es?|anni|a[nñ]os|anos|[åa]r|vuotta|vuoden'
        r'|senior|sr|medior|mid[- ]level|lead|leads|leading|led|principal|head of|staff'
        r'|manag\w+|superviso\w+|experienc\w+|ervaren|ervaring|erfahren\w*|erfahrung\w*'
        r'|erfaren|leitend\w*|f[uü]hrung\w*|graduate|entry[- ]level|junior|trainee'
        r'|intern)\b)', re.I),
}


def _evidence_fits_rule(rule, evidence: str) -> bool:
    """Could these words support that rule at all? See _EVIDENCE_MUST_CONTAIN."""
    wanted = _EVIDENCE_MUST_CONTAIN.get(rule if isinstance(rule, int) else 0)
    return wanted is None or bool(wanted.search(str(evidence or '')))


def _evidence_is_real(evidence: str, job: dict) -> bool:
    """Is the quoted phrase actually in the listing?

    The guard against an invented answer, used for both things Claude is asked to quote:
    the words naming the employer, and the words forcing a DROP. Compared on letters and
    digits only, so a difference in punctuation, casing or collapsed whitespace between the
    posting and Claude's copy of it does not reject a genuine quote.
    """
    def squeeze(text):
        return re.sub(r'[^a-z0-9]+', '', str(text or '').lower())

    needle = squeeze(evidence)
    if len(needle) < 6:
        return False
    # The note we appended after the last removal is not part of the posting, and it repeats
    # the previous quote verbatim. Left in the haystack it would confirm a re-quote of our own
    # note as if the employer had written it -- the guard checking its own homework.
    haystack = squeeze('%s %s %s' % (job.get('title') or '', job.get('company') or '',
                                     listing_text_without_note(job.get('description'))))
    return needle in haystack


# How many listings share one request.
#
# Sharing at all is what makes this affordable: the prompt is identical for every listing,
# so sent one at a time it is paid 93 times over. But it is not free, and the price is
# accuracy. Measured on the real 93-listing corpus, same prompt, all four sizes sent in one
# batch so nothing else could differ:
#
#     group   kept   cost     agreement with one-at-a-time
#         1      3   $0.169   (the reference)
#         3      6   $0.113   96.7%
#         5      5   $0.104   95.6%
#        10      9   $0.093   93.4%
#
# Every one of the six disagreements at ten was a listing wrongly KEPT -- an Amsterdam role
# whose only remote wording was a staff perk ("work from anywhere for one month a year"),
# and a Dutch-language role in Bilthoven asking for two office days a week. Sent alone or in
# threes, Claude drops both and says exactly why. Crowding the request does not make it
# reason worse about the listing in front of it so much as make it less willing to say no.
#
# ONE. This was three, chosen to save about two cents a run, and the 3.3% it cost was paid in
# exactly the currency that matters: listings wrongly KEPT.
#
# The user reported one of them -- Simon-Kucher's "Intern/Associate Consultant Data Science",
# which says "you must be enrolled at a university and able to work from our Amsterdam office
# during the internship period" and arrived in a Remote search with a 68% match and
# apply_verdict 'apply'. The stored row read claude_screen_drop: False. Asked about that exact
# row on its own, Claude answers "Rule 1 - Must work from Amsterdam office during
# internship." It is the shape the table above already describes: an Amsterdam role whose only
# remote wording is a company perk, in this case "whether it's remotely or in the office".
#
# He had already asked for this -- [owner's note: the plan was to send them one by one until it works] -- and the
# Internship and Thesis modules were changed to _GROUP_SIZE = 1 then. This one was missed, so
# a Junior search, which is what he runs, kept bundling three. The same mistake as Rule 5
# living in ten files and being changed in one, and t0_static now checks all three agree.
#
# The price of being right, from the table: $0.169 against $0.113 for 93 listings, which is
# 0.18 cents a listing instead of 0.12. His standing instruction settles whether that matters:
# accuracy is the goal and cost is explicitly not a constraint.
_BATCH_GROUP_SIZE = 1

# Room for every answer in the group, plus a little. One answer measured ~95 tokens.
_BATCH_TOKENS_PER_LISTING = 600

# The single-listing schema with a listing number added, wrapped in an array. The number is
# what ties an answer back to a posting: order is not trusted, and an answer whose number is
# missing or out of range is discarded rather than applied to the wrong job.
#
# The `**_SCREEN_OUTPUT_SCHEMA['properties']` is the whole point of this line and was once
# missing, with consequences worth recording. `properties` held only `listing` while
# `required` named all eight real fields and `additionalProperties` was False -- so the
# grammar permitted exactly one field, demanded eight, and emitted what it was permitted:
#
#     {"answers":[{"listing":1}]}
#
# Thirteen output tokens, no verdict, no match. `_read_structured_answer` reads a missing
# verdict as "not a DROP", so every listing came back KEPT and unscored, and the whole
# batch screening pass -- the one that runs on a real search -- decided nothing at all.
# It looked like a working stage: no errors, answers for every listing, a plausible bill.
_GROUP_ITEM_PROPERTIES: dict = dict(
    {'listing': {'type': 'integer',
                 'description': 'The number of the listing this answer is about.'}},
    **_SCREEN_OUTPUT_SCHEMA['properties'])
_GROUP_ITEM_SCHEMA: dict = {
    'type': 'object',
    'properties': _GROUP_ITEM_PROPERTIES,
    'required': ['listing'] + list(_SCREEN_OUTPUT_SCHEMA['required']),
    'additionalProperties': False,
}
_GROUP_OUTPUT_SCHEMA = {
    'type': 'object',
    'properties': {'answers': {'type': 'array', 'items': _GROUP_ITEM_SCHEMA}},
    'required': ['answers'],
    'additionalProperties': False,
}


def _group_request_params(group: list) -> dict:
    """One request carrying several listings, each judged on its own."""
    body = '\n\n'.join('===== LISTING %d =====\n%s' % (index + 1, _claude_screen_prompt(job))
                         for index, job in enumerate(group))
    params = dict(
        model=CLAUDE_MODEL,
        max_tokens=_BATCH_TOKENS_PER_LISTING * len(group),
        # One Filter run stamps one Level on every row, so a group never mixes profiles.
        system=system_text_for(group[0], current_resume_text()),
        messages=[{'role': 'user', 'content':
                   'Below are %d separate job listings, numbered 1 to %d. Judge each one on '
                   'its own, exactly as you would if it were the only one in front of you. '
                   'Nothing in one listing tells you anything about another. Answer every '
                   'one, in order, and put the listing number in each answer.\n\n%s'
                   % (len(group), len(group), body)}],
    )
    if 'haiku' in CLAUDE_MODEL or 'claude-3' in CLAUDE_MODEL:
        params['temperature'] = 0
    params['output_config'] = {'format': {'type': 'json_schema',
                                          'schema': _GROUP_OUTPUT_SCHEMA}}
    return params


def claude_screen_batch(client, jobs: list, progress_cb=None, should_cancel=None) -> dict:
    """Screen every listing in one batch. Returns {id(job): (drop, reason, match, error,
    employer)}.

    Returns an empty dict if the batch cannot be created at all, so the caller can fall
    back to the sequential path rather than losing the run.
    """
    import time as _time

    if not jobs:
        return {}

    groups = [jobs[start:start + _BATCH_GROUP_SIZE]
              for start in range(0, len(jobs), _BATCH_GROUP_SIZE)]
    requests = []
    by_custom_id = {}
    for index, group in enumerate(groups):
        custom_id = 'group-%d' % index
        by_custom_id[custom_id] = group
        requests.append({'custom_id': custom_id, 'params': _group_request_params(group)})

    try:
        batch = client.messages.batches.create(requests=requests)
    except Exception as exc:
        if progress_cb:
            progress_cb("GLOG:filter_step:claude|warning|Could not send the batch (%s) -- "
                        "screening one listing at a time instead." % str(exc)[:90], 0, 1)
        return {}

    if progress_cb:
        progress_cb(
            "GLOG:filter_step:claude|info|%d listing(s) sent to Claude as a BATCH, in %d "
            "request(s) of up to %d listings each. Batches are charged at half price, and "
            "sharing a request means the instructions are paid for once per request instead "
            "of once per listing -- together about five times cheaper. Batches are queued "
            "rather than answered immediately: this usually finishes within an hour, and can "
            "take up to 24. Nothing is lost while it waits, and the Log will report the "
            "result when it arrives."
            % (len(jobs), len(groups), _BATCH_GROUP_SIZE), 0, len(jobs))

    started = _time.time()
    if not _await_batch(client, batch.id, len(jobs), 'claude', progress_cb, should_cancel):
        return {}

    # Anything missing from this dict -- a request that failed, an answer whose listing
    # number was wrong, a group the model cut short -- is simply absent, and the caller
    # screens those listings one at a time instead. Nothing is silently marked KEEP.
    answers: dict = {}
    try:
        for result in client.messages.batches.results(batch.id):
            group_jobs = by_custom_id.get(result.custom_id)
            if not group_jobs:
                continue
            if result.result.type != 'succeeded':
                continue
            # What this group cost, from the tokens the API itself reports. Batch price.
            spend.record(CLAUDE_MODEL, getattr(result.result.message, 'usage', None),
                         batch=True, listings=len(group_jobs))
            text = '\n'.join(b.text for b in result.result.message.content
                              if getattr(b, 'type', None) == 'text')
            try:
                answered = list(json.loads(text).get('answers') or [])
            except Exception:
                continue
            for item in answered:
                if not isinstance(item, dict):
                    continue
                number = item.get('listing')
                # The number is the only thing tying an answer to a posting. An answer that
                # does not carry a usable one is dropped rather than guessed at by position:
                # applying one listing's verdict to another is the one failure here that
                # would never show up in a log.
                if (not isinstance(number, bool) and isinstance(number, int)
                        and 1 <= number <= len(group_jobs)):
                    job = group_jobs[number - 1]
                    drop, reason, match, error, _retry, employer = _read_structured_answer(
                        json.dumps(item), job)
                    if not error:
                        answers[id(job)] = (drop, reason, match, error, employer)
    except Exception as exc:
        if progress_cb:
            progress_cb("GLOG:filter_step:claude|error|Could not read the batch results "
                        "(%s)." % str(exc)[:90], 0, 1)
        return answers

    if progress_cb:
        progress_cb("GLOG:filter_step:claude|info|Batch finished in %.0f minute(s): %d of %d "
                    "listing(s) answered.%s"
                    % ((_time.time() - started) / 60, len(answers), len(jobs),
                       '' if len(answers) == len(jobs) else
                       ' The rest will be screened one at a time.'),
                    0, len(jobs))
    return answers
