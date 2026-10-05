# -*- coding: utf-8 -*-
"""The other names employers give the job Sina typed -- asked of Claude once, then cached.

WHY THIS EXISTS

The field rule asks whether a listing's title names the job being searched for, and it asks it
literally: every word of "Data Science" has to appear in the title. Measured on Sina's own Bank
of 8,768 listings it removed 7,737 of them -- 88% -- before any other rule ran and before
Claude ever saw them. A sample of 27 of those removals, each read by Claude on its own, found
15 were real data-science jobs: "Junior AI Engineer", "Machine Learning Engineer", "Software
Engineer - Applied AI & 3D", "Product Owner - Data Strategy". A 56% error rate on the largest
filter in the app, and the one place where being wrong is unrecoverable, because the listing
never reaches the judge.

WHY NOT A HAND-WRITTEN LIST

Because there was one, and Sina removed it. `job_field_words.py` used to hold about 150 field
words in thirteen languages; he replaced the lot with a single typed title -- "من یک عنوان رو
برات مینویسم و باید اون عنوان جای همه ی اینها بشینه". The measurement recorded there is why a
list is not the answer either: those 150 words kept 7,649 of 8,801 listings, so the filter was
not filtering, it was just forwarding the bill to Claude.

A list also cannot know what he typed. It is written for "Data Science" and says nothing useful
the day he types "Data Engineer".

WHAT THIS DOES INSTEAD

One request, about the TITLE and nothing else -- no listing is sent, nothing is read. Claude
answers with the titles that are the same work under another name, and the answer is cached on
disk per title, so the second run of the same search costs nothing at all.

    "Data Science"  ->  Data Scientist, Machine Learning Engineer, ML Engineer,
                        AI Engineer, Applied Scientist, Decision Scientist, ...

Then every one of those is expanded exactly as Sina asked for -- "اول همون نتایج خام رو پیدا
کنه / بعد مثلا اگر Data Science بود بعدش Data Scientist رو هم بگرده / بعد مثلا اگر ML Engineer
بود ML Engineering رو هم بگرده / مثلا اگر AI Engineer بود Junior AI Engineer و Junior AI
Engineering رو هم بگرده" -- in three widening rings:

    1. the equivalents as Claude gave them          ML Engineer
    2. each one's twin form                         ML Engineering
    3. each form with the chosen Level's words       Junior ML Engineer, Junior ML Engineering

Rings 1 and 2 are what the FILTER matches on. Ring 3 is for the SEARCH, where the strings are
sent verbatim to a job board and "Junior ML Engineer" genuinely returns listings "ML Engineer"
does not -- measured at 245 extra listings on a real Austrian run, which is why entry_keywords
exists at all. The filter does not need ring 3: its match is word-by-word, so "ML Engineer"
already keeps a listing titled "Junior ML Engineer".

WHAT HAPPENS WHEN IT CANNOT ASK

Nothing breaks and nothing widens. No key, no credit, a refused request, an unreadable answer:
the equivalents are empty and the field rule behaves exactly as it does today. A failure here
must never delete a listing, and it cannot -- widening is all this can do.

HOW THE FAR-OFF ONES ARE REMOVED: A SCORE, NOT A LIST

There was a hand-written NEVER_THESE here for a few sentences of this file's life, and Sina
killed it with one question: "آخه من هزار تا Title میخوام جستجو کنم / الان Never these به چه
درد من میخوره ؟" He is right. A blacklist is written for one field and says nothing the day he
searches something else, and nobody is going to maintain a thousand of them.

So Claude scores every candidate for how much it is THE SAME WORK as the title typed, and
anything at or below `MINIMUM_SIMILARITY` is dropped. His rule, in his words: "تو باید کار
هایی رو بیاری که بالای 35 درصد شباهت دارند / غیر از این بود حذف کن".

Nothing in this module knows anything about data science, or about any other field. That is
the point -- "و این نباید مختص به این Filed باشه / شاید اصلا من Supply Chain Management
جستجو کردم". The question asks about the title it is given, whatever that title is.

A title that belongs more to a NEIGHBOURING job scores low here on purpose, and that is also
his instruction: "اگر بیشتر از Data Science به Data Engineer نزدیکه، بذار موقعی که من Data
Engineer سرچ کردم بره بگرده و بیاره". It is not lost -- it comes back with a high score when
he searches that neighbouring title instead, which is where it belongs. An honest overlap
scores high under both, and that is correct too.

WHAT SINA REJECTS IS REMEMBERED, PER TITLE

The score is a judgement and judgements are sometimes wrong, so whatever he rejects for a
given title is written next to that title's answer and never offered again for it. One
decision, remembered -- not a list anybody maintains.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .search_title import clean_title, role_form, title_forms

# Sina's number, and he gave it twice: "تو باید کار هایی رو بیاری که بالای 35 درصد شباهت
# دارند / غیر از این بود حذف کن", then again after I argued against it -- "ولی در کل این قانون
# رو بذار که زیر 35 درصد بود حذف کن". BELOW 35 is dropped, so 35 itself stays.
#
# WHAT I TOLD HIM BEFORE HE CONFIRMED IT, because the next person to read this needs to know:
# the scores do not track reality closely. Measured on his own Bank, "Analytics Engineer"
# scored 70 here and only 15% of the listings it brought in were really the work he wants,
# while "Quantitative Analyst" scored 65 and measured 78%. The scores also cluster high, so a
# cut at 35 removes only the obviously-unrelated ("Business Analyst" 35, "Database
# Administrator" 20) and lets "Data Analyst" through at 60.
#
# That is no longer a problem, and this is the design that makes it not one: the threshold is
# not the only control any more. Everything above it is searched and KEPT, and Sina chooses
# what to look at with the column filters in the Jobs table -- reversibly, per view, on the
# real listings in front of him. His own words for why that is better: "دیگه اینطوری هرچی
# Related هست رو میاری من خودم میگم چی نشونم بدی چی نشونم ندی".
#
# So this line removes the clearly-unrelated, and nothing else pretends to be a judgement.
MINIMUM_SIMILARITY = 35

# How many equivalents are worth asking for. A cap, not a target: Claude is told that fewer is
# better than padding, and the score is what actually decides.
MAX_EQUIVALENTS = 12

# Bumped when the question or this file's rules change, so a cached answer from an older
# version is re-asked instead of trusted. The same reason every other cache key in this
# project carries a version.
#
# v2: the answer carries a similarity score per title and the blacklist is gone.
PROMPT_VERSION = 'v2'

_QUESTION = """Someone is searching job boards for one kind of work, and has typed its name.

Employers give the same work different titles. List the job titles an employer would use for
THE SAME WORK, so the search does not miss them, and score each one.

THE SCORE is how much that title means the same work as the one typed, from 0 to 100:

  100  the same job, different words -- a straight synonym
   80  the same work in practice; someone doing one could do the other
   50  overlapping work, but a different job with different daily tasks
   35  adjacent: shares tools or a department, but is its own profession
    0  unrelated work

Score a title LOW when it belongs more naturally to a NEIGHBOURING job than to the one typed,
even if the two sit in the same department and share vocabulary. The search for that
neighbouring job will find it under its own name; it does not need to be dragged in here.
Judge by what the person actually does all day, not by words the two titles have in common.

The rest:

* Give the singular role form an advert would use in its title: "ML Engineer", not
  "ML Engineering" and not "ML Engineers".
* No seniority words -- no "Junior", "Senior", "Lead", "Principal". Those are added afterwards.
* No location, company, bracket, "(m/w/d)", or anything that is not the title itself.
* Include the common abbreviation where employers really use one ("ML Engineer" alongside
  "Machine Learning Engineer"), because a job board matches the exact words.
* At most %d titles. Fewer is better than padding the list: score honestly and let the low
  scores be low rather than leaving a title out.
* English titles only. Other languages are handled separately.

This applies to ANY field. The title typed may be Supply Chain Management, Nursing,
Structural Engineering or anything else; nothing about the answer should assume a subject.
""" % MAX_EQUIVALENTS

_SCHEMA = {
    'type': 'object',
    'properties': {
        'equivalents': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string',
                              'description': 'The job title, singular role form.'},
                    'same_work': {'type': 'integer',
                                  'description': '0-100: how much this is the same work.'},
                    'closest_to': {
                        'type': 'string',
                        'description': 'The job this title belongs to most naturally -- the '
                                       'typed title itself when it really is the same work.'},
                    'because': {'type': 'string',
                                'description': 'One short sentence for the score.'},
                },
                'required': ['title', 'same_work', 'closest_to', 'because'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['equivalents'],
    'additionalProperties': False,
}


def _cache_path():
    from app import storage
    return storage.DATA_DIR / 'title_equivalents.json'


def _load_cache() -> dict:
    try:
        return json.loads(Path(_cache_path()).read_text(encoding='utf-8'))
    except Exception:
        # A missing or corrupt cache is not an error worth raising: the answer is re-asked.
        return {}


def _save_cache(cache: dict) -> None:
    try:
        path = Path(_cache_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass       # An unwritable cache costs one request next time, nothing more.


def _cache_key(title: str) -> str:
    return '%s|%s' % (PROMPT_VERSION, clean_title(title).lower())


_SENIORITY = re.compile(r'\b(junior|senior|lead|principal|staff|head|chief|entry[- ]level'
                        r'|graduate|associate|trainee|intern|werkstudent)\b', re.I)


def _tidy(candidates, searched: str) -> list:
    """The answer, cleaned into [{title, same_work, closest_to, because}] -- ALL of them.

    Nothing is dropped for being too far here: the score is kept and the caller decides. That
    separation is deliberate, because the Log has to be able to say "this was dropped, and it
    scored 15" rather than leaving Sina to wonder what was asked and what came back.
    """
    out: list = []
    seen = {form.lower() for form in title_forms(searched)}
    for raw in (candidates or []):
        if isinstance(raw, str):                       # tolerated: an answer without scores
            raw = {'title': raw, 'same_work': 100, 'closest_to': '', 'because': ''}
        if not isinstance(raw, dict):
            continue
        title = ' '.join(str(raw.get('title') or '').replace('"', ' ').split())
        if not title or len(title) > 60:
            continue
        # A bracketed gender tag or a location slipped into the title.
        title = re.sub(r'\s*[\(\[].*?[\)\]]\s*', ' ', title).strip()
        title = _SENIORITY.sub('', title).strip()
        title = ' '.join(title.split())
        if not title or len(title) < 3 or title.lower() in seen:
            continue
        seen.add(title.lower())
        try:
            score = int(raw.get('same_work'))            # type: ignore[arg-type]
        except (TypeError, ValueError):
            # No usable score means no evidence that it is far off, and this module only ever
            # widens -- so it is kept and the Filter's own Claude pass judges the listings.
            score = 100
        out.append({'title': title, 'same_work': max(0, min(100, score)),
                    'closest_to': ' '.join(str(raw.get('closest_to') or '').split()),
                    'because': ' '.join(str(raw.get('because') or '').split())[:200]})
        if len(out) >= MAX_EQUIVALENTS:
            break
    return sorted(out, key=lambda row: -row['same_work'])


def close_enough(candidates, rejected=None) -> list:
    """The titles worth searching for: scored above MINIMUM_SIMILARITY and not rejected.

    `rejected` is what Sina has already turned down for this title -- see rejections_for.
    """
    turned_down = {str(name).strip().lower() for name in (rejected or [])}
    return [row['title'] for row in (candidates or [])
            if row.get('same_work', 0) >= MINIMUM_SIMILARITY
            and row['title'].lower() not in turned_down]


def too_far(candidates, rejected=None) -> list:
    """The ones left out, as (title, score, why) -- so the Log can show what was dropped."""
    turned_down = {str(name).strip().lower() for name in (rejected or [])}
    out = []
    for row in (candidates or []):
        if row.get('same_work', 0) < MINIMUM_SIMILARITY:
            out.append((row['title'], row.get('same_work', 0),
                        row.get('because') or 'scored too far from the title'))
        elif row['title'].lower() in turned_down:
            out.append((row['title'], row.get('same_work', 0), 'you turned this one down'))
    return out


def ask_claude(client, title: str) -> tuple:
    """(equivalents, error). One request about the title; no listing is sent."""
    from .claude_screen.prompt import CLAUDE_MODEL

    body = 'The title Sina typed: %s' % clean_title(title)
    last = ''
    for attempt in range(3):
        try:
            answer = client.messages.create(
                model=CLAUDE_MODEL, max_tokens=700, system=_QUESTION,
                messages=[{'role': 'user', 'content': body}],
                tools=[{'name': 'equivalents',
                        'description': 'The titles that mean the same work.',
                        'input_schema': _SCHEMA}],
                tool_choice={'type': 'tool', 'name': 'equivalents'})
        except Exception as exc:
            last = str(exc)[:160]
            # Retried, but not for long: this runs at the start of a Filter and a stuck
            # retry loop here would hold up everything behind it.
            time.sleep(1.5 * (attempt + 1))
            continue
        for block in answer.content:
            if getattr(block, 'type', '') == 'tool_use':
                given = (block.input or {}).get('equivalents')
                return (_tidy(given, title), '')
        last = 'the answer carried no equivalents'
    return ([], last)


def rejections_for(title) -> list:
    """The titles Sina has turned down for this search title."""
    entry = _load_cache().get(_cache_key(clean_title(title))) or {}
    return list(entry.get('rejected') or [])


def reject(title, equivalent) -> list:
    """Remember that Sina does not want this equivalent for this title. Returns the new list.

    Stored against the title rather than globally, which is the whole difference between this
    and the blacklist it replaced: a thousand searched titles each keep their own decisions,
    and none of them is anybody's job to maintain.
    """
    wanted = clean_title(title)
    key = _cache_key(wanted)
    cache = _load_cache()
    entry = cache.setdefault(key, {'candidates': [], 'rejected': []})
    name = ' '.join(str(equivalent or '').split())
    rejected = list(entry.get('rejected') or [])
    if name and name.lower() not in {r.lower() for r in rejected}:
        rejected.append(name)
    entry['rejected'] = rejected
    cache[key] = entry
    _save_cache(cache)
    return rejected


def candidates_for(title, client=None, progress_cb=None) -> list:
    """Every candidate with its score: from the cache, or asked once and cached.

    `client` may be None -- with no Claude there are no candidates at all, and the field rule
    is exactly as strict as it was before this module existed.
    """
    wanted = clean_title(title)
    key = _cache_key(wanted)
    cache = _load_cache()
    entry = cache.get(key)
    if entry and entry.get('candidates'):
        return list(entry['candidates'])

    if client is None:
        return []

    found, error = ask_claude(client, wanted)
    if error:
        if progress_cb:
            progress_cb('GLOG:filter_step:field|warning|Could not ask Claude for other names '
                        'for "%s" (%s). The title is matched exactly, as before.'
                        % (wanted, error), 0, 1)
        return []

    entry = cache.get(key) or {}
    entry['candidates'] = found
    entry.setdefault('rejected', [])
    entry['asked_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    cache[key] = entry
    _save_cache(cache)
    return found


def equivalents_for(title, client=None, progress_cb=None) -> list:
    """The titles this search should also look for -- scored, thresholded, Sina's rejections
    removed -- and the Log told what was kept and what was dropped, with the scores.

    Saying what was DROPPED matters as much as what was kept. A title missing from a search is
    invisible otherwise, and the score is the only thing that explains it.
    """
    wanted = clean_title(title)
    candidates = candidates_for(wanted, client, progress_cb)
    if not candidates:
        return []
    rejected = rejections_for(wanted)
    kept = close_enough(candidates, rejected)
    dropped = too_far(candidates, rejected)
    if progress_cb:
        scored = {row['title']: row['same_work'] for row in candidates}
        if kept:
            progress_cb('GLOG:filter_step:field|info|%s is also searched as: %s'
                        % (wanted, ', '.join('%s (%d%%)' % (name, scored.get(name, 0))
                                             for name in kept)), 0, 1)
        else:
            progress_cb('GLOG:filter_step:field|info|Nothing else scored above %d%% for '
                        '"%s", so only that title is searched for.'
                        % (MINIMUM_SIMILARITY, wanted), 0, 1)
        if dropped:
            progress_cb('GLOG:filter_step:field|info|Not used, too far from %s: %s'
                        % (wanted, '; '.join('%s (%d%%) — %s' % (name, score, why)
                                             for name, score, why in dropped)), 0, 1)
    return kept


def scores_for(title, equivalents=None) -> dict:
    """{base title: score} for the titles being searched. The typed title is 100.

    Base names only, matching what the Filter window offers and what each row is credited to.
    The twin forms need no entry of their own: a row titled "Junior Data Engineering" is
    credited to "Data Engineer", because that is the name Sina ticked and the name he sees.
    """
    by_title = {row['title'].lower(): row['same_work']
                for row in candidates_for(title, None) or []}
    out: dict = {clean_title(title): 100}
    for name in (equivalents or []):
        out[name] = by_title.get(name.lower(), 100)
    return out


def searched_titles(title, equivalents=None) -> list:
    """[(base title, similarity)] for the Filter window's list, closest first.

    What the window shows and what it ticks -- base names, never the twin forms. The forms are
    still searched and still matched; they are just not separate choices, because "Data
    Engineer" and "Data Engineering" are one job with two spellings.
    """
    scores = scores_for(title, equivalents)
    typed = clean_title(title)
    rows = [(typed, 100)] + [(name, scores.get(name, 100)) for name in (equivalents or [])
                             if name.lower() != typed.lower()]
    return sorted(rows, key=lambda row: -row[1])


def filter_titles(title, equivalents=None) -> list:
    """Rings 1 and 2: what the FIELD RULE matches on -- the title, the equivalents, and the
    twin form of each.

    Ring 3 is deliberately absent. The field rule matches word by word, so "ML Engineer"
    already keeps a listing titled "Junior ML Engineer", and adding the prefixed forms here
    would be a longer list that changes no answer.
    """
    out: list = []
    seen = set()
    for name in [title] + list(equivalents or []):
        for form in title_forms(name):
            low = form.lower()
            if low not in seen:
                seen.add(low)
                out.append(form)
    return out


def search_phrases(title, equivalents=None, level_words=None) -> list:
    """Rings 1, 2 and 3, in that order: what the SEARCH asks a job board for.

    The order is Sina's: the raw titles first, then each one's twin, then the Level's words on
    every form. A job board matches the exact phrase, so "Junior ML Engineer" really does
    return listings that "ML Engineer" does not -- 245 of them on one real run, which is why
    the entry-level query exists at all.

    `level_words` is (prefixes, suffixes) for the Level being searched, as
    search/queries.py holds them. Without it, only rings 1 and 2 come back.
    """
    ring1: list = []
    ring2: list = []
    seen = set()
    for name in [title] + list(equivalents or []):
        forms = title_forms(name)
        for index, form in enumerate(forms):
            low = form.lower()
            if low in seen:
                continue
            seen.add(low)
            (ring1 if index == 0 else ring2).append(form)

    ring3: list = []
    prefixes, suffixes = (level_words or ((), ()))
    for form in ring1 + ring2:
        role = role_form(form)
        for word in prefixes:
            ring3.append('%s %s' % (word, role))
            if role != form:
                ring3.append('%s %s' % (word, form))
        for word in suffixes:
            ring3.append('%s %s' % (role, word))
    # Dedup ring 3 while keeping the order the loop produced.
    ordered: list = []
    for phrase in ring3:
        if phrase.lower() not in seen:
            seen.add(phrase.lower())
            ordered.append(phrase)
    return ring1 + ring2 + ordered
