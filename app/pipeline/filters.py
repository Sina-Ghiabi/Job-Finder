"""reapply_filters -- the Filter button's whole pipeline."""
from __future__ import annotations

import collections
import hashlib
import html
import json
import re
from pathlib import Path

import anthropic
# Dedup compares every title against every other one -- 2,199 listings is 4.8M pairs, plus a
# full-description comparison for each pair that gets through. rapidfuzz does that in about
# 7 seconds; difflib was measured 231x slower on the same work, which is the difference
# between a step nobody notices and half an hour.
import numpy as _np
from rapidfuzz import fuzz as rf_fuzz, process as rf_process

from . import country_rules
from . import job_field_words
from . import title_equivalents
from . import chosen_filters
from .drop_note import clear_drop_note, listing_text_without_note, set_drop_note
from .sources_norm import strip_site_name_from_title, unmirror_markdown_row
from .pages import is_editorial_page, remove_dead_postings
from .profiles import job_profile
from .search_title import (LEVEL_ROW_KEY, ROW_KEY as TITLE_ROW_KEY, WORK_MODE_ROW_KEY,
                           clean_level, clean_title, clean_work_mode)
from .rules import (
    CATEGORY_ORDER,
    _DEDUP_DESCRIPTION_SIMILARITY_THRESHOLD,
    _DEDUP_TITLE_SIMILARITY_THRESHOLD,
    _remove_fake_listings_list,
    NEEDS_TRANSLATION_KEY,
    categorize,
    seniority_of,
    classify_language,
    country_language_rule_hit,
    country_rule_hit,
    silent_about_english,
    dedup_quality,
    dedup_title_key,
    is_unpaid,
    passes_work_location_rule,
)
from .language import english_requirement_of, requires_language_besides_english
from .claude_screen import (
    FILTER_CLAUDE_STEP_CHECKLIST,
    _claude_screen_cache_key,
    APPLY_NOTE_KEY,
    APPLY_VERDICT_KEY,
    RESUME_GAPS_KEY,
    RESUME_MATCH_CACHE_KEY,
    RESUME_MATCH_KEY,
    RESUME_MATCH_MINIMUM,
    RESUME_STRENGTHS_KEY,
    claude_resume_match,
    claude_screen_batch,
    claude_screen_one,
    resume_match_cache_key,
)
from .claude_screen.prompt import current_resume_text
from .sponsorship import (
    NO_SPONSORSHIP_PROCESS_COUNTRIES,
    _apply_sponsor_list_matches_to_jobs,
    has_sponsorship_restriction,
)


# How alike two titles must be, once the board's tail is off, for the same employer to mean
# the same job. High on purpose: "Data Scientist" and "Data Engineer" at one company are two
# jobs, and at 90 they stay two.
_DEDUP_SAME_EMPLOYER_TITLE_CUT = 90

# The legal-form words and country suffixes a company name picks up on one board and not on
# another -- "Metyis" vs "Metyis BV", "Genmab" vs "Genmab Netherlands".
_COMPANY_NOISE = re.compile(
    r'\b(bv|b\.v|nv|n\.v|inc|incorporated|ltd|limited|llc|plc|gmbh|mbh|ag|sa|sas|srl|spa|'
    r'a/s|as|ab|oy|oyj|aps|kg|co|corp|corporation|company|group|holding|holdings|'
    r'international|global|nederland|netherlands|deutschland|norge|norway|austria|'
    r'oesterreich|the)\b', re.I)

# What a board adds to a title that the employer never wrote: "Data Science Analyst at
# Metyis", "Junior Climate Data Scientist at Robeco | Quant Jobs", "X - Welcome to the
# Jungle". Everything from the first of these onwards is the board talking.
_TITLE_TAIL = re.compile(r'\s+\bat\b\s+|\s*\|\s*|\s+[-–—]\s+|\s*\(\s*(?:remote|hybrid|'
                         r'on[- ]site)\s*\)\s*', re.I)


def _url_host(url) -> str:
    found = re.search(r'https?://([^/]+)', str(url or ''), re.I)
    return found.group(1).lower().replace('www.', '') if found else ''


def _dedup_company_key(company) -> str:
    """An employer name reduced to what two boards would agree on. Empty when unusable."""
    text = re.sub(r'[^a-z0-9 ]+', ' ', str(company or '').lower())
    text = ' '.join(_COMPANY_NOISE.sub(' ', text).split())
    # One letter or one digit is not an employer, and neither is a board's placeholder.
    return text if len(text) >= 3 else ''


def _dedup_title_head(title) -> str:
    """The job title without whatever the board appended to it."""
    head = _TITLE_TAIL.split(str(title or ''), 1)[0]
    head = re.sub(r'[^a-z0-9 ]+', ' ', head.lower())
    head = ' '.join(head.split())
    return head if len(head) >= 4 else ''


def _dedup_fingerprint(jobs: list[dict]) -> str:
    """A fingerprint of exactly what the duplicate check reads: url, title, company, text.

    Deliberately NOT filter_signature.pool_fingerprint, which hashes only the URLs and their
    count. That is the right answer for a Claude verdict -- a listing whose description was
    re-fetched is still the same listing -- but it is the wrong answer here, because the
    duplicate check compares the titles and the descriptions themselves. A pool with the same
    URLs and one re-fetched description can dedup differently, and a cache keyed on URLs alone
    would hand back the old answer.

    The descriptions are hashed raw. reapply_filters strips our own removal note from every row
    before this runs, so there is nothing run-dependent left in them -- without that, a row
    flagged last time would carry a note, change the fingerprint, and the cache would miss on
    every single run.
    """
    digest = hashlib.sha256()
    for job in jobs:
        for field in ('url', 'title', 'company', 'description'):
            digest.update(str(job.get(field) or '').encode('utf-8', 'replace'))
            digest.update(b'\x00')
        digest.update(b'\x01')
    return '%d:%s' % (len(jobs), digest.hexdigest()[:32])


def _dedup_cache_path():
    from app import storage
    return Path(storage.DATA_DIR) / 'dedup_cache.json'


def _cached_dedup(fingerprint: str, count: int):
    """The kept indices for this exact pool, or None.

    Indices rather than URLs, because a pool can hold two rows with no URL at all and they are
    not interchangeable -- one may be the full posting and the other a truncated mirror. The
    fingerprint pins the order, so the indices mean the same thing they did when they were
    written.
    """
    try:
        stored = json.loads(_dedup_cache_path().read_text(encoding='utf-8'))
    except Exception:
        return None
    if stored.get('fingerprint') != fingerprint:
        return None
    kept = stored.get('kept')
    if not isinstance(kept, list) or (kept and max(kept) >= count):
        return None            # a cache from a different pool, or corrupt
    return kept


def _remember_dedup(fingerprint: str, kept_indices: list) -> None:
    try:
        path = _dedup_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # One entry only. The Bank is the pool, and a Filter is always run against the latest
        # one -- keeping a history would grow a file nobody reads.
        path.write_text(json.dumps({'fingerprint': fingerprint, 'kept': kept_indices}),
                        encoding='utf-8')
    except Exception:
        pass                   # an unwritable cache costs the next run its 90 seconds, no more


def _remove_duplicates_list(jobs: list[dict]) -> tuple[list[dict], int]:
    """Step 1 of reapply_filters (the Filter button): same URL -> duplicate, then Sina's
    rule -- clean the two titles down to their words, and if those say it is the same job,
    the two DESCRIPTIONS decide.

    This deliberately no longer groups by company name. Grouping by company only ever
    compared listings that HAD one, and on a real search most do not: 1,189 of 2,199
    Netherlands rows arrived with no company at all, so their only duplicate check was an
    exact URL match. Comparing the text instead found 204 more duplicates on those same
    rows, including every copy the old rule could not see because one source wrote "KPMG"
    and another wrote "Klynveld Peat Marwick Goerdeler".

    It compares each listing as the board wrote it, in whatever language that is.
    Two copies of one posting in different languages are not caught here; two copies in the
    same language -- which is what a republisher like EURES actually produces -- are.

    THE ANSWER IS REMEMBERED, BECAUSE THE POOL USUALLY HAS NOT CHANGED

    This is the most expensive thing the Filter does -- 90 seconds on 26,826 rows even after
    the scan was made parallel -- and Sina re-runs the Filter constantly: a different Level, a
    different country, Claude on or off. None of those change which rows are duplicates of each
    other. So the verdict is stored against a fingerprint of the pool, and a re-filter of the
    same Bank skips the whole thing.
    """
    fingerprint = _dedup_fingerprint(jobs)
    remembered = _cached_dedup(fingerprint, len(jobs))
    if remembered is not None:
        return [jobs[i] for i in remembered], len(jobs) - len(remembered)

    keep = [True] * len(jobs)

    # Best copy first, so the one that survives a merge is the employer's own full posting
    # rather than a republisher's truncated excerpt.
    order = sorted(range(len(jobs)), key=lambda i: dedup_quality(jobs[i]), reverse=True)

    # The exact-address pass walks the same best-first order the title pass below always
    # has. It used to walk the list as it arrived, keeping whichever copy came FIRST -- and
    # that stopped being harmless once Markdown mirrors were put back on their real address
    # (see unmirror_markdown_row). wearedevelopers.com serves each vacancy twice, and 16 of
    # the 95 mirror copies on disk carry no text at all; arriving first, an empty mirror
    # would have removed the full HTML posting that shares its address.
    seen_urls: dict[str, int] = {}
    for i in order:
        url = (jobs[i].get('url') or '').strip().lower()
        if not url:
            continue
        if url in seen_urls:
            keep[i] = False
        else:
            seen_urls[url] = i

    titles = [dedup_title_key(job.get('title'), job.get('company')) for job in jobs]
    # Our own removal note is stripped before anything is compared. One copy of a vacancy
    # having been flagged last run and the other not would otherwise push two identical
    # postings apart, and the duplicate would survive as a second row.
    bodies = [' '.join(listing_text_without_note(job.get('description')).split()).lower()
              for job in jobs]
    # HOW THIS GOT FAST, AND THE TWO ATTEMPTS THAT DID NOT
    #
    # This was the whole cost of a Filter run: 294 of the 305 seconds it took on 26,826 rows.
    # Two optimisations aimed at what looked expensive both measured 0.9x -- slightly SLOWER --
    # and cProfile is what finally said where the time was. Both failures are recorded because
    # each was a plausible idea that a measurement had to kill:
    #
    #   1. Indexing the titles by length and comparing only within the band a 90% match is
    #      algebraically possible in. The bound is real (the shorter title must be at least
    #      81.8% of the longer), but building the candidate list per row moved work OUT of
    #      rapidfuzz's C++ and into a Python list comprehension run 26,826 times.
    #   2. Batching every body comparison into one cpdist call. That removed the old loop's
    #      laziness -- it had skipped any row already removed -- so it scored 1.16 million
    #      pairs where the old code scored a fraction of them. cpdist itself was 226 of the
    #      294 seconds.
    #
    # What the profile actually showed, once the title scan was batched: the titles cost 8
    # seconds and the BODIES cost 226. So the fix has to be about the bodies, and it is not
    # about comparing them faster. It is about comparing them fewer times.
    #
    # 26,812 rows carry only 14,770 distinct descriptions -- republishers hand the same text
    # round, and a board that lists a vacancy twice lists it identically. Those 1.16 million row
    # pairs are only 119,788 distinct pairs OF TEXT, so the old code was computing the same
    # comparison an average of 9.7 times. Every repeat is now a dictionary lookup.
    #
    # The order of removals is untouched, and that is what keeps the answer identical: which
    # copy of a pair survives depends on walking `order` best-first, and only the SCORES are
    # precomputed. Verified survivor for survivor against the old algorithm on the real Bank.
    title_cut = _DEDUP_TITLE_SIMILARITY_THRESHOLD * 100
    body_cut = _DEDUP_DESCRIPTION_SIMILARITY_THRESHOLD * 100

    similar_titles: dict = {}
    live = [i for i in range(len(jobs)) if titles[i] and bodies[i]]
    if live:
        live_titles = [titles[i] for i in live]
        # In chunks, because the full matrix for 26,812 titles would be 686 MB. A 2,000-row
        # chunk against all of them is 54 MB, which is the trade this makes.
        for start in range(0, len(live), 2000):
            block = live[start:start + 2000]
            scores = rf_process.cdist(
                [titles[i] for i in block], live_titles, scorer=rf_fuzz.ratio,
                score_cutoff=title_cut, dtype=_np.uint8, workers=-1)
            for row_at, column_at in _np.argwhere(scores >= title_cut):
                i = block[int(row_at)]
                j = live[int(column_at)]
                if i != j:
                    similar_titles.setdefault(i, []).append(j)

    # One verdict per distinct pair of description texts, not per pair of rows, and all of them
    # computed in one parallel call.
    #
    # Both halves of that matter, and the profiler measured each. Keying on the text collapsed
    # 1,157,770 row pairs into 119,788 distinct text pairs -- the old code was recomputing the
    # same comparison an average of 9.7 times, because 26,812 rows carry only 14,770 distinct
    # descriptions. Handing the remainder to cpdist instead of calling token_set_ratio in a
    # Python loop uses every core: 86,526 sequential calls cost 70 seconds, and the same work
    # in one call costs about a sixth of that.
    #
    # Identical text is settled without any comparison, which is 7% of the pairs outright.
    body_verdicts: dict = {}
    to_score: list = []
    for i, similar in similar_titles.items():
        for j in similar:
            key = (bodies[i], bodies[j]) if bodies[i] <= bodies[j] else (bodies[j], bodies[i])
            if key in body_verdicts:
                continue
            if key[0] == key[1]:
                body_verdicts[key] = True
            else:
                body_verdicts[key] = None        # a placeholder, so it is only queued once
                to_score.append(key)
    if to_score:
        scores = rf_process.cpdist([left for left, _right in to_score],
                                   [right for _left, right in to_score],
                                   scorer=rf_fuzz.token_set_ratio, workers=-1)
        for at, key in enumerate(to_score):
            body_verdicts[key] = float(scores[at]) >= body_cut

    def same_posting(i, j):
        key = (bodies[i], bodies[j]) if bodies[i] <= bodies[j] else (bodies[j], bodies[i])
        return bool(body_verdicts.get(key))

    for i in order:
        # A title that cleans away to nothing carries no evidence either way -- and two
        # empty strings score a perfect match, which would merge unrelated postings.
        if not keep[i] or not titles[i] or not bodies[i]:
            continue
        for j in similar_titles.get(i, ()):
            # Still lazy, still in the old order: a row already removed is never compared, and
            # that is both the speed and the reason the answer does not move.
            if keep[j] and same_posting(i, j):
                keep[j] = False

    # One more pass, for the copies the text test cannot see. Two boards carrying the same
    # vacancy render it differently -- QuantumBlack's Data Scientist was 3,802 characters on
    # qarera and 1,929 on LinkedIn -- so their descriptions never reach the threshold above,
    # and the title pass misses them too whenever a board appends its own tail ("Data Science
    # Analyst at Metyis", "Junior Climate Data Scientist at Robeco | Quant Jobs").
    #
    # Measured on a real Amsterdam result: 8 pairs survived into the 48 listings Sina was
    # shown, every one of them the same job on two different sites. What identifies them is
    # not the text but the employer: same employer, same job title, two addresses.
    #
    # Three conditions, so a company advertising two real openings under one title is not
    # merged: the employer must be named on both and match, the titles must match once the
    # board's tail is off, and the two must be in the same country when both say one. Rows
    # from the SAME host are left to the passes above -- a board that lists a job twice is a
    # different problem, and its two copies usually do have matching text.
    companies = [_dedup_company_key(job.get('company')) for job in jobs]
    heads = [_dedup_title_head(job.get('title')) for job in jobs]
    hosts = [_url_host(job.get('url')) for job in jobs]
    for i in order:
        if not keep[i] or not companies[i] or not heads[i]:
            continue
        for j in order:
            if j == i or not keep[j] or companies[j] != companies[i] or not heads[j]:
                continue
            if hosts[i] and hosts[i] == hosts[j]:
                continue
            country_i = str(jobs[i].get('country') or '').strip().lower()
            country_j = str(jobs[j].get('country') or '').strip().lower()
            if country_i and country_j and country_i != country_j:
                continue
            if rf_fuzz.token_set_ratio(heads[i], heads[j]) >= _DEDUP_SAME_EMPLOYER_TITLE_CUT:
                keep[j] = False

    removed = keep.count(False)
    _remember_dedup(fingerprint, [i for i, k in enumerate(keep) if k])
    return [job for job, k in zip(jobs, keep) if k], removed


# Static checklists shown in the Log under their own step, one line per rule, each
# marked "Checked" once that step's real work (already run against every listing by
# that point) is done -- Sina asked for the actual rule names visible in the Log
# itself, not just each step's own single summary count. Order matches the order each
# rule is actually checked in code (the loop above for FILTER_RULES_STEP_CHECKLIST,
# CLAUDE_SCREEN_SYSTEM_PROMPT's Rule 1-9 for FILTER_CLAUDE_STEP_CHECKLIST).
# What the Log lists for this step, and it must match what the step actually runs: a
# checklist naming a rule that no longer fires is O-2 in another costume -- the Log line is
# the only thing that says why a listing went.
FILTER_RULES_STEP_CHECKLIST = [
    'Work Location rule',
    # Named for what it does NOW, which is much narrower than "a language besides English":
    # since T-12 the pairing "English and Dutch" is kept and labelled, so the only listings
    # this line removes are the ones that want another language INSTEAD of English. O-2 --
    # the Log must say why -- and a line that overstates what it deleted is the same fault.
    'Wants another language instead of English',
    'Text-based sponsorship restriction',
    'Unpaid',
]


def _rules_checklist(profile=None) -> list:
    """The checklist, unchanged by the Level now that no Level rule runs in this step.

    It used to rename the last line per profile -- "Too senior" was Junior's name for it and
    the Log said "Wrong level for Mid" at Mid -- because the step really did delete for the
    Level. It no longer does: seniority is reported in the Seniority column and narrowed
    there. A checklist that still named the rule would be claiming a check that cannot fire,
    which is `O-2`'s fault in another costume: the Log line is the only thing that says why a
    listing went, so it may not list what never happens.

    `profile` is kept in the signature. Every caller passes it, the tests call it both ways,
    and a Level rule could legitimately come back here one day -- but it would have to be
    added to FILTER_RULES_STEP_CHECKLIST deliberately rather than appear by renaming.
    """
    return FILTER_RULES_STEP_CHECKLIST


def _step_dedup(jobs, progress_cb):
    """Step 2 -- drop duplicates and likely-fake listings. Returns the surviving list."""
    if progress_cb:
        progress_cb("FILTER_STEP_START:dedup|Removing Duplicates & Fake Listings", 0, 1)
    jobs, _dup_removed = _remove_duplicates_list(jobs)
    jobs, _fake_removed = _remove_fake_listings_list(jobs)
    if progress_cb:
        progress_cb(
            f"FILTER_STEP_DONE:dedup|Removing Duplicates & Fake Listings|{_dup_removed + _fake_removed} removed",
            0, 1,
        )
    return jobs


def _place_with_reasons(jobs, progress_cb, countries, cities):
    """filter_by_place, plus a Log line naming each country it removed and how many.

    Inherited from the step this replaced. "376 removed" says the filter fired; "In Germany
    (211 removed), in Belgium (98 removed)" says whether it fired on the right thing, and
    that is the difference between noticing a mis-ticked country and not.
    """
    kept, removed = chosen_filters.filter_by_place(jobs, countries, cities)
    if removed and progress_cb:
        survivors = {id(job) for job in kept}
        dropped: dict = {}
        for job in jobs:
            if id(job) in survivors:
                continue
            name = str(job.get('country') or '').strip()
            dropped[name] = dropped.get(name, 0) + 1
        for name, count in sorted(dropped.items(), key=lambda kv: -kv[1]):
            # A row with no country at all gets its own sentence rather than being forced
            # into "In , which you did not ask for".
            line = ('Never says which country it is in (%d removed)' % count if not name
                    else 'In %s, which you did not ask for (%d removed)' % (name, count))
            progress_cb('FILTER_STEP_ITEM:chosen|%s' % line, 0, 1)
    return kept, removed


def _step_chosen(jobs, progress_cb, countries, cities, date_range, categories,
                 sponsorship):
    """Apply the Filter window's own choices, and say what each one did.

    Every one of these is silent unless Sina chose it. What each one does when he HAS chosen
    is documented in chosen_filters, including the two that do not keep a silent listing.

    This step also absorbed the old `_step_place`, which asked the same question about the
    country only in a Not Remote search and answered it leniently. Once Sina asked for the
    strict answer -- "اگر نوشتم Netherlands یعنی فقط Netherlands میخوام" -- that step could
    never remove anything this one had not already removed, so it became a second answer to
    a question that now has one. Its Log line was worth keeping, though: it named every
    country it dropped and how many, which is how a wrong country selection is spotted at a
    glance, so that breakdown moved here.
    """
    started = len(jobs)
    # The heading is opened before anything runs, not on the first removal, because the
    # country filter writes its own breakdown lines as it goes -- opening late put those
    # lines above the heading they belong under. It is opened only when there is something
    # to report: with nothing chosen this step is invisible, as it should be.
    chose_something = bool(countries or cities or categories or sponsorship
                           or chosen_filters.is_a_date_window(date_range))
    if chose_something and progress_cb:
        progress_cb('FILTER_STEP_START:chosen|What You Asked For', 0, 1)
    say = progress_cb if chose_something else None

    steps = (
        ('the country you chose', lambda rows: _place_with_reasons(
            rows, say, countries, cities)),
        # THE KIND OF ROLE NO LONGER DELETES EITHER, for the same reason as the Level above.
        #
        # `filter_by_category` used to run here. On the real Netherlands run it removed 295 of
        # the 321 listings that had survived everything else -- every full-time job, because
        # Part-Time was ticked -- and left him 4. Sina's instruction: "میتونی Filter مربوط به
        # Type رو برداری اما من در جدولی که بهم نمایش میده خودم برم انتخاب کنم چه نوع Type
        # کار هایی رو بهم نشون بده".
        #
        # The Type column and its filter button were already there; what was missing was
        # letting the pool keep its other kinds. `categories` is still accepted and still
        # saved, so an older settings.json loads unchanged -- it is simply not read here.
        # `filter_by_category` itself stays, with its tests: it is correct, and `T-3` in the
        # README is about what happens when a correct rule has no caller AND no assertion.
        ('the sponsorship you chose', lambda rows: chosen_filters.filter_by_sponsorship(
            rows, sponsorship)),
        ('how recently it was posted', lambda rows: chosen_filters.filter_by_date(
            rows, date_range)),
    )
    for label, run in steps:
        jobs, removed = run(jobs)
        if removed and say:
            say('FILTER_STEP_ITEM:chosen|Not %s (%d removed)' % (label, removed), 0, 1)
    if chose_something and progress_cb:
        progress_cb('FILTER_STEP_DONE:chosen|What You Asked For|%d removed, %d left'
                    % (started - len(jobs), len(jobs)), 0, 1)
    return jobs, started - len(jobs)


def _step_work_location(jobs, progress_cb, cancelled, profile=None):
    """The Work Location rule, read in the listing's own language.

    It is the largest single filter -- on a real Netherlands search it removes about 85% of
    what reaches it -- and it needs no English, which is why nothing has to be translated
    only ever paid for on listings that could still survive.

    Three questions, and no fourth. See passes_work_location_rule: Milan or Turin anywhere keeps
    the listing outright; an on-site or hybrid term with no remote term anywhere drops it;
    a phrase explicitly denying remote work drops it. A listing that simply says nothing
    about where the work happens is KEPT and left for Claude, because silence is not
    evidence -- the old rule deleted it, which is what made every text-less source
    (arbeitsagentur.de, Jooble, jobs.ch, SwissDevJobs) produce nothing but deletions.
    """
    # Which of the two searches this is, said in the Log: the same step keeps opposite
    # listings in the two, and a count without the mode beside it would be unreadable.
    mode_now = jobs[0].get(WORK_MODE_ROW_KEY) if jobs else None
    label = ('Checking Work Location — Any (keeps every listing)' if mode_now == 'any'
             else 'Checking Work Location — Not Remote' if mode_now == 'not_remote'
             else 'Checking Work Location')
    if progress_cb:
        progress_cb("FILTER_STEP_START:work_location|%s" % label, 0, 1)
    vocabulary = profile.vocabulary if profile is not None else None
    kept = [job for job in jobs
            if not cancelled() and passes_work_location_rule(job, vocabulary)]
    removed = len(jobs) - len(kept)
    if progress_cb:
        progress_cb(
            f"FILTER_STEP_DONE:work_location|{label}|{removed} removed, "
            f"{len(kept)} left", 0, 1)
    return kept, removed


# Two of the four entries below are not section names. `None` means silent_about_english,
# which asks the opposite question; this one means country_language_rule_hit, which is the
# same section plus the English-beside cancel. A sentinel object rather than a string, so it
# can never collide with a real section name in country_rules.
_COUNTRY_LANGUAGE = object()

# The rules the country vocabulary answers, after the Remote rule and in the order Sina
# listed them. Each is (label, section, what it means when it matches).
COUNTRY_RULE_SECTIONS = [
    # First, and deliberately: a non-English posting that never once names English, in any
    # spelling. Sina's rule. It runs here rather than after translation because that is
    # what makes it free -- on the real Netherlands data it removes 503 listings and 92%
    # of the entire DeepL bill, none of which now gets translated at all.
    #
    # Not a section lookup like the others: silent_about_english asks the opposite question
    # (nothing matched anywhere), and only of listings that need translating.
    ('Non-English posting that never mentions English', None),
    # Also not a plain section lookup any more, and for the T-12 reason: the phrase list
    # alone would go on deleting "Fluent Dutch and English required". country_language_rule_hit
    # is the same list with the English-beside cancel the regex rule uses.
    ('Wants another language instead of English', _COUNTRY_LANGUAGE),
    ('Says it will not sponsor a visa', 'no_sponsorship'),
    ('Unpaid', 'unpaid'),
    # ('Too senior', 'senior') USED TO BE HERE, and it was the second place the Level
    # deleted. _step_rules had one check in English; this one asked the same question in
    # the posting's own language, with each profile's own word list swapped in -- which is
    # why the Log said "Wrong level for Mid" rather than "Too senior".
    #
    # Removing only the _step_rules check left this one running, and the measurement showed
    # it plainly: the same Bank filtered at junior kept 151 rows including 49 Senior ones,
    # at mid kept 101 and not a single Senior row. Same pool, same rules, different Level,
    # and the only difference was this list. A rule that lives in two places is two rules
    # (rule 5 of the nine), and this is that, found by comparing outputs rather than by
    # reading the code.
    #
    # The vocabularies keep their `senior` sections -- the Internship and Thesis modules
    # read them, and `is_too_senior` is still tested. Nothing is deleted for its level in
    # the job pass any more; `seniority_of` labels it and the column filters it.
]


def describe_languages(counts) -> str:
    """"Dutch 812, English 340, German 12, unknown 4" -- most common first."""
    parts = []
    for code, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        vocabulary = country_rules.DETECTED_TO_VOCABULARY.get(code)
        name = country_rules.LANGUAGES[vocabulary]['name'] if vocabulary else code
        parts.append('%s %d' % (name, count))
    return ', '.join(parts) or 'none'


def _country_rule_sections(profile=None) -> list:
    """COUNTRY_RULE_SECTIONS for a profile. Junior's is COUNTRY_RULE_SECTIONS itself; every
    other profile's is the same list with its own wrong-level section where Junior's
    "Too senior" sits."""
    if profile is None or profile.level_section == 'senior':
        return COUNTRY_RULE_SECTIONS
    return [(profile.level_label, profile.level_section) if section == 'senior'
            else (label, section) for label, section in COUNTRY_RULE_SECTIONS]


def _step_country_rules(jobs, progress_cb, cancelled, profile=None):
    """The selected countries' own vocabulary, applied in the listing's own language.

    Sina's design, in two halves.

    First, work out what language each posting is actually written in, and record it on the
    row along with whether it is already English. That one answer drives everything
    after it: an English posting is checked against the English object and flagged as
    and nothing else; a Dutch one is checked against the Dutch object and English together.
    Until now every listing from a country was checked against every
    language that country's ads are written in -- four vocabularies at once for Belgium, so
    a French phrase could fire on a Dutch advert.

    Then the rest of that country's object: the language demand, the visa refusal, the
    unpaid marker, the seniority marker -- all asked in the posting's own language, before
    a translator has had a chance to blur any of them.

    This does not replace _step_rules below. That one asks the same questions again in
    English, after translation, and it has to: a German posting that says
    "verhandlungssicheres Deutsch" is caught here, and one that only says it in an English
    paragraph further down is caught there. Two passes, same questions, different
    languages -- which is the whole point of the country object.

    Returns (kept, removed).
    """
    if progress_cb:
        progress_cb("FILTER_STEP_START:country|Word Check — 13 Language Vocabularies", 0, 1)

    languages: collections.Counter = collections.Counter()
    for job in jobs:
        if cancelled():
            break
        languages[classify_language(job)] += 1

    vocabulary = profile.vocabulary if profile is not None else None
    sections = _country_rule_sections(profile)
    kept = []
    hits: dict = {label: 0 for label, _section in sections}
    for job in jobs:
        if cancelled():
            break
        # Milan and Turin are exempt from the Work Location rule, not from these. A
        # Milanese posting demanding native Italian is still no use to Sina.
        matched = ''
        for label, section in sections:
            if section is None:
                matched = ('never mentions English'
                           if silent_about_english(job, vocabulary) else '')
            elif section is _COUNTRY_LANGUAGE:
                matched = country_language_rule_hit(job, vocabulary)
            else:
                matched = country_rule_hit(section, job, vocabulary)
            if matched:
                hits[label] += 1
                break
        if not matched:
            kept.append(job)

    removed = len(jobs) - len(kept)
    if progress_cb:
        for label, _section in sections:
            progress_cb(f"FILTER_STEP_ITEM:country|{label} ({hits[label]} removed)", 0, 1)
        progress_cb("GLOG:filter_step:country|info|Languages found: %s."
                    % describe_languages(languages), 0, 1)
        to_translate = sum(1 for job in kept if job.get(NEEDS_TRANSLATION_KEY))
        # Not "flagged for translation" any more -- nothing is translated. The flag says
        # which vocabulary the rules below will read a listing in, which is the thing that
        # replaced translating it.
        progress_cb("GLOG:filter_step:country|info|%d listing(s) read in their own language, "
                    "%d already in English."
                    % (to_translate, len(kept) - to_translate), 0, 1)
        progress_cb(f"FILTER_STEP_DONE:country|Word Check — 13 Language Vocabularies|{removed} removed",
                    0, 1)
    return kept, removed


def _step_rules(jobs, progress_cb, cancelled, profile=None):
    """Step 4 -- the six content rules. Returns (kept, removed_by_keywords).

    The rules run in this exact order, and each one that matches removes the listing
    outright; nothing here needs confirmation from the user.
    """
    if progress_cb:
        progress_cb("FILTER_STEP_START:rules|Sentence Check — Reading Requirements", 0, 1)
    vocabulary = profile.vocabulary if profile is not None else None
    # THE LEVEL NO LONGER DELETES ANYTHING HERE.
    #
    # `profile.is_wrong_level` used to run in this loop and remove every listing whose level
    # did not match the one chosen in Search. Sina's instruction, after seeing that Claude's
    # rule 4 had done the same thing 19 times in one run: "نباید Filter کنه باید اون هارو
    # دسته بندی کنه ... و دیگه هیچی نباید حذف بشه". So the level is written onto the row as
    # `Seniority` a few lines below and shown as a column with its own filter button; he
    # narrows by it in the table, where changing his mind costs nothing instead of costing a
    # re-filter.
    #
    # The profile is still read for its `vocabulary` -- each Level has its own word lists and
    # the Work Location rule above uses them -- so `search_level` remains a real choice. It
    # simply no longer decides what survives.
    #
    # `is_wrong_level` and `is_too_senior` are left in place and still tested: they are what
    # the Internship and Thesis modules use, and removing a working rule because one caller
    # stopped needing it is how a module becomes unreachable (see L-2).
    kept = []
    for job in jobs:
        if cancelled():
            break
        if not passes_work_location_rule(job, vocabulary):
            continue
        if requires_language_besides_english(job):
            continue
        if has_sponsorship_restriction(job):
            continue
        if is_unpaid(job):
            continue
        job['Category'] = categorize(job)
        # Beside Category, and for the same reason: the Jobs table shows both as
        # columns with their own Excel-style filter, and neither is a filter here any
        # more. seniority_of prefers Claude's own answer when the row has one.
        job['Seniority'] = seniority_of(job)
        # And beside both, for the third thing he picks out in the table. Written AFTER the
        # language rule above has had its say, so every row that reaches here is either
        # 'English only' or 'English + Other' -- 'Other only' is what the rule just deleted.
        job['English'] = english_requirement_of(job)
        kept.append(job)

    removed_by_keywords = len(jobs) - len(kept)
    if progress_cb:
        # Static checklist of the 6 rules this step actually ran, in the same order
        # they're checked above -- Sina asked for these to be visible in the Log, not
        # just the step's own single summary line. All 6 genuinely did run against
        # every listing by the time this fires (the loop above already finished), so
        # every one is real, not a guess.
        for rule_label in _rules_checklist(profile):
            progress_cb(f"FILTER_STEP_ITEM:rules|{rule_label}", 0, 1)
        progress_cb(f"FILTER_STEP_DONE:rules|Sentence Check — Reading Requirements|{removed_by_keywords} removed", 0, 1)
    return kept, removed_by_keywords


# How well a listing has to match to be worth showing. Moved to part two with the score
# itself -- see claude_screen/worth.py -- and kept under its old name for anything that reads
# it. Below it a listing is flagged, not deleted: it still appears in the review dialog.
CLAUDE_MATCH_MINIMUM = RESUME_MATCH_MINIMUM


def _step_claude(kept, anthropic_api_key, progress_cb, cancelled):
    """Step 5 -- Claude's final screening pass. Returns the list of flagged listings.

    Flags only; it never removes anything itself. Each entry is
    {'job': <the job dict>, 'reason': <why Claude wants it gone>} and the caller confirms
    with the user before anything is deleted.
    """
    claude_flagged = []
    if progress_cb:
        progress_cb("FILTER_STEP_START:claude|Claude Review", 0, 1)
    client = anthropic.Anthropic(api_key=anthropic_api_key)
    claude_errors = []
    cache_hits = 0
    fresh_screens = 0

    # Everything that actually needs a real call, sent as ONE batch at half price. Listings
    # whose stored decision still matches their content are not in it -- they cost nothing
    # either way. If the batch cannot be created the dict comes back empty and the loop
    # below screens them one at a time exactly as before, so this can only save money, not
    # lose a run.
    needs_screening = [job for job in kept
                       if job.get('claude_screen_cache_key') != _claude_screen_cache_key(job)]
    batched = {}
    if needs_screening and not cancelled():
        batched = claude_screen_batch(client, needs_screening, progress_cb, cancelled)

    for job in kept:
        # Cache-first: a job whose exact screening input (title/company/location/
        # platform/employment_type/seniority_level/description) AND the current
        # CLAUDE_SCREEN_SYSTEM_PROMPT text both hash identically to what produced
        # its last stored decision needs no real API call at all -- Sina flagged
        # that every Filter re-run was resending every listing to Claude in full,
        # even ones already checked with nothing changed. See
        # _claude_screen_cache_key for exactly what's hashed and why.
        if cancelled():
            break  # keep every decision made so far; the caller shows what survived

        cache_key = _claude_screen_cache_key(job)
        if job.get('claude_screen_cache_key') == cache_key:
            cache_hits += 1
            # claude_screen_user_kept records that Sina already saw this exact flag
            # in ClaudeReviewDialog and chose to keep the listing anyway. Real bug
            # fixed here: without it, the cached DROP verdict re-flagged the same
            # listing on EVERY future Filter run -- and because a cache hit makes no
            # API call, Claude could never revise its own verdict either. He had to
            # re-type that row number forever, and one absent-minded "Remove
            # Flagged" would delete it.
            if job.get('claude_screen_drop') and not job.get('claude_screen_user_kept'):
                reason = job.get('claude_screen_reason') or 'unspecified reason'
                # Rewritten from the stored verdict rather than carried over in the text, so
                # a cached drop reads exactly like a fresh one and a row Sina later keeps by
                # hand loses its note on the next run instead of keeping a stale claim.
                set_drop_note(job, reason, job.get('claude_screen_evidence'))
                claude_flagged.append({'job': job, 'reason': reason})
            else:
                clear_drop_note(job)
            continue

        fresh_screens += 1
        if id(job) in batched:
            drop, reason, _match, error, employer = batched[id(job)]
        else:
            drop, reason, _match, error, employer = claude_screen_one(client, job)
        if error:
            claude_errors.append(error)
            # Deliberately NOT caching an errored call -- a transient API/network
            # failure must be retried on the next Filter run, not silently frozen
            # in as "no decision" forever.
        else:
            # No score is written here any more. This part decides KEEP or DROP by the
            # Level's profile; the Match % comes from part two, against the résumé, and
            # writing this part's empty score over it would wipe a real one.
            job['claude_screen_cache_key'] = cache_key
            job['claude_screen_drop'] = drop
            job['claude_screen_reason'] = reason
            # The employer comes back from the same call now. Only written when the source
            # gave no name of its own -- a name the board actually reported is better
            # evidence than one read out of prose.
            if employer and not str(job.get('company') or '').strip():
                job['company'] = employer
                job['company_source'] = 'claude'
            # The listing's content (or a rule) changed, so this is a genuinely new
            # verdict -- any earlier override no longer applies to it.
            job.pop('claude_screen_user_kept', None)

        # The low-score drop that used to follow here moved to part two with the score:
        # a role can pass all eight questions and still be nothing to do with Sina, and it
        # is the résumé match that now says so (see step_resume_match).
        if drop:
            reason = reason or 'unspecified reason'
            # The quote behind the verdict was recorded by _read_structured_answer, which is
            # the only place it exists. Note first, so a listing is never flagged without one.
            set_drop_note(job, reason, job.get('claude_screen_evidence'))
            claude_flagged.append({'job': job, 'reason': reason})
        else:
            # Kept -- and a listing kept now may have been dropped last run, so the note goes
            # whether or not this pass put one there.
            job.pop('claude_screen_evidence', None)
            clear_drop_note(job)

    if progress_cb:
        # Same static checklist idea as the "Sentence Check — Reading Requirements" step above --
        # Rule 9 Part A (degree completion) is deliberately NOT listed here since
        # it's disabled in the prompt itself (see CLAUDE_SCREEN_SYSTEM_PROMPT's
        # Rule 9), so only Part B (renamed to just "University enrollment rule",
        # since "degree completion" no longer applies) shows as actually checked.
        for rule_label in FILTER_CLAUDE_STEP_CHECKLIST:
            progress_cb(f"FILTER_STEP_ITEM:claude|{rule_label}", 0, 1)
        if cache_hits:
            progress_cb(
                f"GLOG:filter_step:claude|info|{cache_hits} listing(s) unchanged since their last real Claude screen -- reused, no new API call.",
                0, 1,
            )
        detail = f"{len(claude_flagged)} flagged, {fresh_screens} screened, {cache_hits} cached"
        if claude_errors:
            detail += f", {len(claude_errors)} error(s)"
        progress_cb(f"FILTER_STEP_DONE:claude|Claude Review|{detail}", 0, 1)
    return claude_flagged


def _step_sponsorship(kept, anthropic_api_key, claude_flagged, progress_cb, should_cancel):
    """Step 6 -- fill in each listing's Sponsorship Visa value.

    Runs last because it does its own company legal-name resolution internally
    (cache-first, see _apply_sponsor_list_matches_to_jobs), decoupled from Claude Review.
    """
    if progress_cb:
        progress_cb("FILTER_STEP_START:sponsorship|Checking Sponsorship Visa", 0, 1)
    for job in kept:
        if not job.get('sponsorship_visa'):
            job['sponsorship_visa'] = 'Unknown'
        if job.get('country') in NO_SPONSORSHIP_PROCESS_COUNTRIES:
            job['sponsorship_visa'] = "Employer's Discretion"
    # Real bug fixed here too: this used to always pass progress_cb=None, so the
    # "Sponsorship Visa list for X loaded/could not be refreshed" lines built into
    # _load_sponsor_list never actually reached the Log at all, even though the
    # plumbing for them already existed.
    #
    # no_paid_lookup_for: running this on the FULL kept list (flagged listings included)
    # was correct while the step was genuinely free -- a cached HTTP fetch plus a local
    # string compare. It stopped being free once company legal-name resolution moved in
    # here, since a cache MISS now costs a real, billed Claude web search. Listings
    # Claude just flagged are the ones most likely to be deleted seconds later in
    # ClaudeReviewDialog, so they still get the free register match and any cached legal
    # name, but never trigger a fresh paid lookup. Identity (not job['id']) is used
    # because a hand-edited jobs.json row can legitimately have no id.
    _apply_sponsor_list_matches_to_jobs(
        kept, anthropic_api_key=anthropic_api_key, progress_cb=progress_cb,
        no_paid_lookup_for={id(item['job']) for item in claude_flagged},
        should_cancel=should_cancel,
    )
    if progress_cb:
        progress_cb("FILTER_STEP_DONE:sponsorship|Checking Sponsorship Visa|", 0, 1)


def _step_merge_twins(kept, claude_flagged, progress_cb=None):
    """One job on two boards, caught after Claude has named the employer.

    The dedup step runs first, before anything has read the posting, and at that point most
    rows carry no employer at all -- the Filter clears the guessed ones on purpose. So the
    same-employer test there only catches the listings that arrived with a company name, and
    the copies that matter most to Sina slip through: a real Amsterdam result showed him
    QuantumBlack's Data Scientist twice, Metyis' Data Science Analyst twice, Robeco's Junior
    Climate Data Scientist twice -- 8 pairs among 48 listings.

    By this point Claude has quoted the employer out of each posting, which is exactly the
    evidence that was missing. Same employer, same job title once the board's tail is off,
    two different sites: one job. The copy with the fuller description survives, and a
    flagged copy is never the one kept -- a listing Claude objected to must not replace the
    twin it did not.
    """
    if len(kept) < 2:
        return kept, 0
    flagged_ids = {id(entry['job']) for entry in (claude_flagged or [])}
    order = sorted(range(len(kept)),
                   key=lambda i: (id(kept[i]) not in flagged_ids, dedup_quality(kept[i])),
                   reverse=True)
    companies = [_dedup_company_key(job.get('company')) for job in kept]
    heads = [_dedup_title_head(job.get('title')) for job in kept]
    hosts = [_url_host(job.get('url')) for job in kept]
    keep = [True] * len(kept)
    merged = []
    for i in order:
        if not keep[i] or not companies[i] or not heads[i]:
            continue
        for j in order:
            if j == i or not keep[j] or companies[j] != companies[i] or not heads[j]:
                continue
            if hosts[i] and hosts[i] == hosts[j]:
                continue
            # One employer can run the same role in two countries, and those are two jobs.
            country_i = str(kept[i].get('country') or '').strip().lower()
            country_j = str(kept[j].get('country') or '').strip().lower()
            if country_i and country_j and country_i != country_j:
                continue
            if rf_fuzz.token_set_ratio(heads[i], heads[j]) >= _DEDUP_SAME_EMPLOYER_TITLE_CUT:
                keep[j] = False
                merged.append((kept[j], kept[i]))
    if not merged:
        return kept, 0
    # A merged-away copy must not stay in the review dialog pointing at a row that is gone.
    if claude_flagged:
        dropped = {id(job) for job, _twin in merged}
        claude_flagged[:] = [e for e in claude_flagged if id(e['job']) not in dropped]
    if progress_cb:
        progress_cb('FILTER_STEP_START:twins|The Same Job on Two Sites', 0, 1)
        for job, twin in merged[:12]:
            progress_cb('FILTER_STEP_ITEM:twins|%s at %s — also on %s'
                        % (str(job.get('title'))[:48], str(job.get('company'))[:28],
                           _url_host(twin.get('url'))), 0, 1)
        progress_cb('FILTER_STEP_DONE:twins|The Same Job on Two Sites|%d removed, %d left'
                    % (len(merged), sum(keep)), 0, 1)
    return [job for job, k in zip(kept, keep) if k], len(merged)


def _step_sort(kept, anthropic_api_key, progress_cb):
    """Step 7 -- order the survivors for display."""
    if progress_cb:
        progress_cb("FILTER_STEP_START:sort|Sorting Results", 0, 1)
    if anthropic_api_key:
        # Part two scored every survivor against Sina's résumé -- sort the whole list by
        # that match percentage, best match first. A listing with no parseable score
        # (e.g. that one API call errored) sorts last, not first.
        kept.sort(key=lambda j: -(j.get('claude_match') if j.get('claude_match') is not None else -1))
    else:
        category_ranks = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        kept.sort(key=lambda j: (
            category_ranks.get(j.get('Category'), len(CATEGORY_ORDER)),
            0 if j.get('country') == 'Italy' else 1,
        ))
    if progress_cb:
        progress_cb("FILTER_STEP_DONE:sort|Sorting Results|", 0, 1)



def _resume_match_flag_reason(job):
    """Why part two wants this listing gone, or None. A "skip", or a score under the floor."""
    verdict = str(job.get(APPLY_VERDICT_KEY) or '').lower()
    match = job.get(RESUME_MATCH_KEY)
    if verdict == 'skip':
        return job.get(APPLY_NOTE_KEY) or 'not worth applying to'
    if isinstance(match, int) and not isinstance(match, bool) and match < RESUME_MATCH_MINIMUM:
        return 'Only %d%% match with your résumé' % match
    return None


def step_resume_match(kept, claude_flagged, anthropic_api_key, progress_cb=None,
                      should_cancel=None):
    """Part two, for every Level: how well does each survivor match Sina's résumé?

    Part one decided KEEP or DROP by the Level's profile. This asks the question Sina has
    when he opens the app -- "چند درصد ... با رزومه ای که آپلود کردی همخونی داره" -- and
    writes the Match %, what fits, what is missing, and apply / check / skip.

    A "skip", or a score under RESUME_MATCH_MINIMUM, is flagged the way every other Claude
    verdict is -- added to `claude_flagged`, not erased -- so it still appears in the review
    dialog and can be kept by hand. A listing kept by hand is not flagged again for the same
    answer.

    It runs only on what survived part one, and a listing whose text, title, Level and résumé
    are unchanged since its last answer is not asked again. Used by reapply_filters for the
    four job Levels, and by the Filter worker for Thesis and Internship.
    """
    if not anthropic_api_key:
        return
    resume_text = current_resume_text()
    if not resume_text:
        return
    flagged_ids = {id(entry['job']) for entry in claude_flagged}
    shown = [job for job in kept if id(job) not in flagged_ids]
    if not shown or (should_cancel and should_cancel()):
        return

    if progress_cb:
        progress_cb("FILTER_STEP_START:worth|Résumé Match", 0, 1)

    keys = {id(job): resume_match_cache_key(job, resume_text) for job in shown}
    needs = [job for job in shown if job.get(RESUME_MATCH_CACHE_KEY) != keys[id(job)]]
    answers = {}
    if needs:
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        answers = claude_resume_match(client, needs, resume_text, progress_cb, should_cancel)

    flagged = 0
    for job in shown:
        got = answers.get(id(job))
        if got:
            (job[RESUME_MATCH_KEY], job[APPLY_VERDICT_KEY], job[APPLY_NOTE_KEY],
             job[RESUME_STRENGTHS_KEY], job[RESUME_GAPS_KEY]) = got
            job[RESUME_MATCH_CACHE_KEY] = keys[id(job)]
            # A new answer is a new verdict: an earlier "keep it anyway" was about the old one.
            job.pop('resume_match_user_kept', None)
        elif job.get(RESUME_MATCH_CACHE_KEY) != keys[id(job)]:
            continue  # unanswered: stays visible; silence is never a reason to hide one
        reason = _resume_match_flag_reason(job)
        if reason and not job.get('resume_match_user_kept'):
            flagged += 1
            # No quote: this removal rests on a percentage against the résumé, not on a
            # sentence in the posting, and the note says so by carrying no "Quoted from"
            # line rather than inventing one.
            set_drop_note(job, reason)
            # `part` tells the review dialog which "keep it anyway" to record.
            claude_flagged.append({'job': job, 'reason': reason, 'part': 'resume'})
        else:
            clear_drop_note(job)

    if progress_cb:
        answered = sum(1 for job in shown if job.get(RESUME_MATCH_CACHE_KEY) == keys[id(job)])
        progress_cb("FILTER_STEP_DONE:worth|Résumé Match|%d of %d matched (%d cached), %d flagged"
                    % (answered, len(shown), len(shown) - len(needs), flagged), 0, 1)


def reapply_filters(jobs: list[dict], progress_cb=None, anthropic_api_key=None, should_cancel=None,
                    search_title=None, search_level=None, search_work_mode=None,
                    search_countries=None, search_cities=None,
                    date_range=None, categories=None, sponsorship=None,
                    min_match_percent=0, fields=None):
    """This is where ALL the actual content filtering happens (the raw dataset from a
    search has none of it applied). Step 1 normalizes what dedup/fake-detection need --
    right now that's just filling in a missing company name (Google-sourced listings
    never have one) by extracting it from the listing's own text, see
    _fill_missing_company_names -- so the near-duplicate check right after it (which
    groups by company+country) actually has something to group Google rows by, instead
    of only ever catching them via an exact URL match. Step 2 removes duplicates and
    likely-fake listings (moved here from run_search -- Sina asked for a raw search to
    show every listing exactly as fetched, and for Filter to be the one place all
    cleanup/filtering happens). Then runs translation + the remote/seniority/
    sponsorship/unpaid/language rules -- those are removed immediately, no confirmation
    needed.

    If an Anthropic key is configured, Claude then re-checks every survivor as a final
    safety pass, but does NOT remove anything itself: each listing it flags is returned
    in `claude_flagged` (with its reason) for the caller to confirm with the user before
    actually deleting anything.

    Returns (kept, removed_by_keywords, claude_flagged) where `kept` still includes the
    Claude-flagged listings -- the caller decides their fate.

    should_cancel: optional callable() -> bool, checked between listings in the Claude
      Review loop (by far the longest step -- one sequential API call per survivor).
      Cancelling stops sending new listings and keeps every decision already made,
      rather than discarding the run.
    """
    # Checked between every step, not only inside the Claude loop. Real gap this
    # closes: should_cancel used to be consulted in exactly one place, so cancelling
    # during translation (30 concurrent network calls -- the other genuinely slow step)
    # appeared to do nothing, and for a Filter run with no Claude key configured Cancel
    # did nothing whatsoever.
    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    if progress_cb:
        progress_cb("FILTER_START", 0, 1)


    # Rows saved by an older version still carry a company name that the deleted regex
    # guess wrote onto them, flagged company_from_text. Nothing produces that flag any
    # more, so without this the guess outlives its own code: the wrong name stays in the
    # Company column, goes to the sponsor-register match, and makes the row look named so
    # the Claude employer step skips the listing that most needs it.
    # The job title and the Level chosen in Search NOW, written onto every row. Filter judges
    # by what is in the boxes today, not by what was searched last week. And because Claude's
    # prompt and cache key read these two off the row, a verdict reached for one title or
    # one Level is never reused for another.
    title = clean_title(search_title)
    profile = job_profile(search_level)
    work_mode = clean_work_mode(search_work_mode)

    # Built once, here, for the one thing that needs Claude before the Claude step: the other
    # names employers give this job (see title_equivalents). None when there is no key, and
    # everything downstream treats that as "no equivalents" rather than as a failure.
    claude_client = None
    if anthropic_api_key:
        try:
            import anthropic
            claude_client = anthropic.Anthropic(api_key=anthropic_api_key)
        except Exception:
            claude_client = None
    for job in jobs:
        # Last run's removal note comes off before anything reads the listing. This is the
        # one line that makes the note safe: every step below -- the keyword rules, the
        # language rule, the duplicate check, the sponsorship-restriction rule, Claude --
        # reads `description`, and on a second Filter run the note is sitting in it. Left
        # there, "Rule 2 - Requires German C1" would be read as the posting demanding German.
        # It is put back, from the stored verdict, only where a removal is decided.
        clear_drop_note(job)
        if job.pop('company_from_text', None):
            job['company'] = ''
        job[TITLE_ROW_KEY] = title
        # The row remembers what was ASKED, not the profile that happened to judge it: an Any
        # search is judged by the Junior profile (every profile decides the same since T-5) and
        # must still say "Any" to the résumé-match, or Claude is told the posting is Junior.
        job[LEVEL_ROW_KEY] = 'any' if clean_level(search_level) == 'any' else profile.key
        # Remote or Not Remote: the Work Location rule and Claude's rule 1 both read it here.
        job[WORK_MODE_ROW_KEY] = work_mode
        # Rows saved before mirrors were corrected at search time still carry the ".md"
        # address and no title. Correcting them here, ahead of duplicate removal, is what
        # lets that step see them as the copies they are.
        unmirror_markdown_row(job)
        # And the site's own name on the end of a page title ("Data Engineer | FINN.no"),
        # for rows saved before the search started removing it. Here as well as there for
        # the same reason: the duplicate check reads the title, and so does Claude.
        if job.get('title'):
            job['title'] = strip_site_name_from_title(job.get('title'), job.get('url'))
        # "technology &amp; domain knowledge". Measured across the five real corpora: 26,445
        # entities, on 27-43% of listings, from the sources that hand over plain text rather
        # than HTML (strip_html already unescapes the HTML ones). No keyword verdict changes
        # when they are unescaped -- that was measured too, over all 24,295 listings -- so
        # this is not a filtering fix; it is what Sina reads in the table and the export, and
        # what Claude is given to read. The Bank keeps the untouched original.
        for field in ('title', 'description'):
            if job.get(field) and '&' in str(job[field]):
                job[field] = html.unescape(str(job[field]))

    jobs = _step_dedup(jobs, progress_cb)

    # Taken-down postings among rows saved by earlier searches. A new search removes them at
    # the pool (see run_search, right after enrichment); a vacancy saved last week may have
    # been closed since, and Filter is the only step that will ever read it again.
    jobs, _gone = remove_dead_postings(jobs)
    if progress_cb and _gone:
        progress_cb('FILTER_STEP_DONE:gone|Taken-down Postings|%d removed' % len(_gone), 0, 1)

    # A board's own editorial -- career advice, a role profile, an organisation's about page.
    # Not a vacancy and not a page OF vacancies, so the index-page rules never had anything
    # to fire on, and their addresses are title-shaped, so every other rule read them as a
    # single posting. Three reached the nine listings Claude marked "apply" on the Germany
    # run, which is where Sina found them.
    #
    # It runs here, with the cheap rules: two regexes against a URL and a title, no network.
    # In the Filter rather than only in run_search, because the Bank already holds thousands
    # of rows collected before this rule existed and re-filtering must clean them too.
    _editorial = [job for job in jobs if is_editorial_page(job)]
    if _editorial:
        _editorial_ids = {id(job) for job in _editorial}
        jobs = [job for job in jobs if id(job) not in _editorial_ids]
        if progress_cb:
            progress_cb('FILTER_STEP_DONE:editorial|Articles, Not Vacancies|%d removed'
                        % len(_editorial), 0, 1)

    # Does the title name the job in the Search box? This ran nowhere until the Austrian
    # DevOps run: `job_field_words.py` was written when the Pool was built and then never
    # imported, and of 411 jobs reaching Claude, 86 were Vertrieb, Verkauf, Copywriter,
    # Customer Support, Maschinenbau and HR -- $0.28 of Claude, per country, spent reading
    # sales jobs. It now reads the title Sina typed rather than a word list; see that file.
    #
    # It runs here, first of the content rules, because it is the cheapest of them: one
    # regex against the title, no network, no translation. Everything it removes is work the
    # remote rule, the country rules and Claude do not have to do.
    #
    # ...but asked literally it was also the WORST rule in the app. Measured on Sina's Bank:
    # 7,737 of 8,768 listings removed here, and 56% of a sample of those removals were real
    # data-science jobs titled "Junior AI Engineer", "Machine Learning Engineer", "Software
    # Engineer - Applied AI". Because this step runs first, Claude never saw them and nothing
    # downstream could put them back. So the title is widened to the other names employers
    # give the same work -- asked of Claude once per title and cached, never per listing.
    #
    # One request, and a failed one costs nothing: no equivalents means this rule is exactly
    # as strict as it was before, so the worst case of the widening is the old behaviour.
    other_names = title_equivalents.equivalents_for(title, claude_client, progress_cb)
    # Which of those titles Sina ticked in the Filter window. Empty means all of them, as
    # everywhere else in that window. This is the cheap place to narrow a run: a title left
    # out here costs nothing at all, while the same title left in is paid for twice over --
    # once when Claude screens its listings and again when it scores them against the résumé.
    wanted_fields = {str(name).strip().lower() for name in (fields or []) if str(name).strip()}
    if wanted_fields:
        left_out = [name for name in other_names if name.lower() not in wanted_fields]
        other_names = [name for name in other_names if name.lower() in wanted_fields]
        if progress_cb and left_out:
            progress_cb('GLOG:filter_step:field|info|Not reading %s this run — you left %s '
                        'unticked.' % (', '.join(left_out),
                                       'it' if len(left_out) == 1 else 'them'), 0, 1)
    # BASE NAMES ONLY, and that matters in two places at once.
    #
    # `title_is_in_field` expands whatever name it is given into that name's forms and matches
    # word by word, so "Data Engineer" already keeps "Data Engineering", "Junior Data
    # Engineer", "Junior Data Engineering" and "Data (Platform) Engineer" -- verified on all
    # of them. Passing the forms as separate names would change no verdict.
    #
    # It WOULD change what each row is credited to, and that is the bug this avoids. Sina's
    # rule: "در اون Dropdown فقط باید به من Data Engineer رو نشون میدی اما تمامی این موارد رو
    # در Filter بررسی میکنی". The window offers base names, so a row credited to the twin form
    # "Data Engineering" would answer a filter value that is never offered -- ticking "Data
    # Engineer" would hide it.
    jobs, _off_field = job_field_words.remove_off_field(jobs, title, other_names)
    # Which title found each survivor, and how similar that title is -- the two columns the
    # Jobs table sorts and filters by. Written here, on the survivors only, because this is
    # where the answer is known and nothing downstream recomputes it.
    job_field_words.stamp_field_match(
        jobs, title, other_names, title_equivalents.scores_for(title, other_names))
    removed_off_field = len(_off_field)
    if progress_cb and removed_off_field:
        progress_cb('FILTER_STEP_DONE:field|Title Check — Does It Say %s|'
                    '%d removed' % (title, removed_off_field), 0, 1)

    # The Remote rule runs BEFORE translation, and that ordering is the difference between
    # a cheap Filter and an expensive one.
    #
    # It used to run after, so every non-English listing was translated first -- on a real
    # Netherlands search that was 1,041 translations, of which the rules then threw away
    # 1,555 listings. Most of that translation was paid for and immediately discarded.
    #
    # It can run first because it no longer needs English: passes_work_location_rule reads the
    # ORIGINAL text alongside any translation (see rule_text) and its vocabulary covers the
    # languages this app searches -- "thuiswerk", "Homeoffice", "teletrabajo", "lavoro
    # agile" and the rest. On the same Netherlands data it removes about 85% of everything,
    # so what reaches translation is a few hundred listings rather than a thousand.
    #
    # Everything else still runs after translation, because the rest of the rules genuinely
    # do read English: lacks_english_mention is about the word "English", and
    # requires_language_besides_english reads phrases like "German and English".
    jobs, removed_by_remote = _step_work_location(jobs, progress_cb, _cancelled, profile)

    # And, in a Not Remote search only, where the job actually is. Remote work is answerable
    # from anywhere, so the Remote search has no business reading a country; Not Remote means
    # being in the place, and a search for Amsterdam kept a job in Paris until this step
    # existed. It also clears out the previous city: the saved pool grows with every search,
    # so an Oslo run still held 296 Vienna listings from the week before.
    # What Sina actually ticked in the Filter window. These ask nothing about the posting's
    # meaning -- only whether he asked for this country, this kind of role, this age of
    # advert -- so they run before every rule that costs reading, and long before Claude.
    #
    # They exist because the window offered them and the pipeline ignored them: a Netherlands
    # Remote filter returned German listings, because the country was only ever consulted by
    # the Not Remote rule above, which does nothing in a Remote search. See chosen_filters.
    jobs, removed_by_choice = _step_chosen(jobs, progress_cb, search_countries, search_cities,
                                           date_range, categories, sponsorship)

    # Then the rest of the selected country's own vocabulary, still in the posting's own
    # language: never-mentions-English, the language demand, the visa refusal, unpaid. The
    # same questions _step_rules asks below in English -- asked here first, before a
    # translator could blur them, and answered from the words that country's job ads really
    # use. Seniority USED to be in that list, and its removal is T-14: it was the second of
    # the two places the Level deleted, and taking out only the other one left it running.
    jobs, removed_by_country = _step_country_rules(jobs, progress_cb, _cancelled, profile)

    # No translation step. See the module note on _step_language, which is kept for the
    # moment as dead code rather than deleted, because the machinery behind it -- two keys,
    # quota rotation, the 429 throttle -- took real measurement to get right and may be
    # wanted again if the vocabulary ever stops being enough.
    kept, removed_by_keywords = _step_rules(jobs, progress_cb, _cancelled, profile)
    removed_by_keywords += (removed_by_remote + removed_by_country
                            + removed_off_field + removed_by_choice + len(_gone))

    # Claude's two parts only exist when a Claude key is configured AND a résumé has been
    # uploaded. Every fact about Sina now comes from the résumé, so without one both parts
    # would judge against nobody -- they are skipped, loudly, rather than run blind.
    claude_flagged = []
    claude_key = anthropic_api_key
    if claude_key and not current_resume_text():
        if progress_cb:
            progress_cb('WARNING: Claude was skipped — no résumé has been uploaded. Choose '
                        'your résumé (PDF or Word) in Search and run Filter again.', 0, 1)
        claude_key = None
    if claude_key:
        claude_flagged = _step_claude(kept, claude_key, progress_cb, _cancelled)
        # Part two, before sponsorship and sorting: the Match % it writes is what the list is
        # sorted by, and what it flags is spared a paid legal-name lookup below.
        step_resume_match(kept, claude_flagged, claude_key, progress_cb, should_cancel)
        # The match floor, which can only be applied once there is a score to compare.
        # A listing Claude never reached keeps its place: an absent score is not a low one.
        kept, below_floor = chosen_filters.filter_by_match(kept, min_match_percent)
        if below_floor:
            removed_by_keywords += below_floor
            if progress_cb:
                progress_cb('FILTER_STEP_DONE:floor|Résumé Match Floor|%d below %s%%, '
                            '%d left' % (below_floor, min_match_percent, len(kept)), 0, 1)

    # Now that Claude has read the employer off each posting, the copies the first dedup
    # could not see become visible -- see _step_merge_twins.
    kept, merged_twins = _step_merge_twins(kept, claude_flagged, progress_cb)
    removed_by_keywords += merged_twins

    _step_sponsorship(kept, claude_key, claude_flagged, progress_cb, should_cancel)
    _step_sort(kept, claude_key, progress_cb)

    if progress_cb:
        progress_cb("FILTER_END", 0, 1)

    return kept, removed_by_keywords, claude_flagged

