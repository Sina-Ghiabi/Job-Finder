# -*- coding: utf-8 -*-
"""The filters each Apify actor really honours -- one table, read by the window and the request.

WHY THIS IS A TABLE AND NOT A FORM

Sina's instruction: "در بخش Search برای هر Actor عبارت های Filter دقیق اون Actor رو قرار بده که
ما فقط Select کنیم که جای هیچ اشتباهی نباشه" -- per actor, the actor's own filters, selected
rather than typed, with no room for a mistake. Then, once the testing came in: "فقط مواردی رو
بذار که مطمئنی کار میکنن و اون مواردی که کار نمیکنن رو لازم نیست بذاری".

Both are structural requirements, not layout preferences, so they are met structurally: this
table is the only place a filter is described, the Search window builds its controls FROM it,
and the request builders read the chosen values back THROUGH it. A field cannot appear in the
window without being sent, and cannot be sent without appearing in the window.

NOTHING IS HERE THAT WAS NOT MEASURED

Every entry was proved against the live actor on a real account, by running the same query
twice with one parameter changed and comparing the returned job ids. A pair that comes back
identical is a parameter the actor dropped. What that test found:

  HONOURED                              DROPPED (and therefore absent below)
  --------                              ------------------------------------
  linkedin  date_posted, remote         linkedin  experienceLevel (all 5 levels: same ids)
            sort, easy_apply            glassdoor sortBy
            under_10_applicants
  glassdoor daysOld, limit
            remoteWorkType              (curious_coder, REPLACED 4 Oct 2026: f_WT, f_E and
            minRating                    sortBy were all dropped by it -- see Document T-6/T-16)
            employerSizes
            easyApply
  indeed    datePosted, limit

The dropped ones are the reason this file exists. f_WT=2 has been sent on every Remote search
this app has ever run, and removing it returned the identical 300 jobs -- so the premise of
the search, that Sina works from home in Turin, never reached LinkedIn at all. Putting it in a
window as a tick box would have made that failure permanent and invisible.

Three of LinkedIn's schema fields (under10Applicants, distance, geoId) and two of Glassdoor's
(radius, excludeJobIds) are untested. They are absent for that reason alone, and belong here
the day they are measured -- not before.

WHAT IS NOT HERE BECAUSE IT LIVES ELSEWHERE

The date window. It has always been per-actor -- settings['date_values'] carries one value per
platform and the wizard's own date section sets them -- so repeating it here would give two
controls for one value.
"""
from __future__ import annotations

# How a control is drawn, and how its value is read back.
#
#   choice  a dropdown. `options` is (value, label) pairs; the first is the "don't filter"
#           entry and sends nothing.
#   flag    a checkbox. Sends True when ticked, nothing when not.
#   number  a spin box. Sends the number; `zero_means` says what 0 stands for.
CHOICE, FLAG, NUMBER = 'choice', 'flag', 'number'

SETTINGS_KEY = 'actor_filters'


class Field:
    """One filter on one actor: how to draw it, and the key the actor wants it under."""

    def __init__(self, key, label, kind, options=None, default=None, hint='',
                 minimum=0, maximum=100000, step=100, zero_means='', also_sets=(),
                 presets=None, flag_labels=('No', 'Yes')):
        self.key = key
        self.label = label
        self.kind = kind
        self.options = list(options or ())
        self.default = default
        self.hint = hint
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.zero_means = zero_means
        # Other keys that must carry the same value. The LinkedIn actor reads BOTH `count`
        # and `limitPerSource`, and the billed runs sent them as a pair; setting one and
        # leaving the other at the global figure is how a 400-row cap quietly fetches 500.
        self.also_sets = tuple(also_sets)
        # What a number's dropdown offers. A spin box was the control until Sina asked for a
        # dropdown on every parameter ("جلوش یک Dropdown بذار"); a number has no natural list,
        # so the list is chosen here, per field, and always contains 0 for "no limit".
        self.presets = tuple(presets or ())
        # How a tick reads as a dropdown: (off label, on label).
        self.flag_labels = tuple(flag_labels)

    def dropdown_options(self, current=None):
        """[(stored value, label)] for this field as a dropdown -- whatever its kind.

        Every parameter is a dropdown now, so the window asks the FIELD what to offer instead
        of choosing a widget per kind. A saved value that is not on the list (a 400 chosen
        under the old spin box, say) is appended rather than dropped: opening the window and
        saving must never quietly change what he picked.
        """
        options: list
        if self.kind == FLAG:
            options = [(False, self.flag_labels[0]), (True, self.flag_labels[1])]
        elif self.kind == CHOICE:
            options = list(self.options)
        else:
            values = list(self.presets) or [0]
            options = [(n, (self.zero_means or 'None') if not n else '{:,}'.format(n))
                       for n in values]
        if current is not None and self.kind == NUMBER:
            try:
                number = int(current)
            except (TypeError, ValueError):
                number = None
            if number is not None and number >= 0 and number not in [v for v, _ in options]:
                options.append((number, '{:,}'.format(number)))
                options.sort(key=lambda pair: pair[0])
        return options

    def send_value(self, chosen):
        """What to put in the run input for this chosen value, or None to send nothing.

        The "off" position of every control sends NOTHING rather than a neutral value. That
        is deliberate: Sina's standing rule is that the search never narrows by something he
        did not choose, and an actor's own default is not his choice either.
        """
        if self.kind == FLAG:
            return True if chosen else None
        if self.kind == CHOICE:
            if chosen in (None, '', 'any'):
                return None
            # Only a value this field really offers. A settings.json edited by hand, or
            # written by an older build whose options differed, can hold anything -- and
            # without this check 'excellent' was sent to Glassdoor as a minimum rating.
            # Caught by its own test: the suite asserted an unreadable rating is not sent,
            # and it was.
            allowed = [value for value, _label in self.options]
            return chosen if chosen in allowed else None
        if self.kind == NUMBER:
            try:
                number = int(chosen)
            except (TypeError, ValueError):
                return None
            return number if number > 0 else None
        return None


# The cost lever, and the reason it is per actor rather than one number for all three.
# Measured, same 300 rows from each: LinkedIn $0.600, Glassdoor $0.081, Indeed $0.001. The
# expensive one is also the one whose remote filter does nothing, so it is paid for office
# jobs the Work Location rule then deletes -- which makes "how many rows will I buy from
# THIS source" the only real control over what a search costs.
_LIMIT_HINT = ('Rows bought from this source per query. LinkedIn bills $0.005 a row '
               '($0.50 per 100), Glassdoor and Indeed a small fraction of that.')

FIELDS = {
    # apimaestro/linkedin-jobs-scraper-api since 4 October 2026 (Document T-16). Every field here
    # was measured on the live actor by the method above; experienceLevel was measured TOO and
    # is deliberately absent -- all five of its levels returned the same 96 of 100 job ids, so
    # it does nothing, and Seniority is classified in the table rather than asked of any actor.
    'linkedin': [
        # EVERY ROW HERE IS THE ACTOR'S OWN PARAMETER, and the value chosen is the value sent --
        # Sina: "بعد هر انتخابی که کردم اونجا مستقیما در مقدار پارامتر مربوطه به اون Actor قرار
        # داده بشه". Two of them used to be instructions to the app under an actor's name
        # (`allWorkplaces`, `maxResults`); neither exists any more.
        #
        # `remote`, with the actor's own four values. The Remote / Not Remote choice above the
        # panel SETS this dropdown (Remote -> remote, Not Remote -> Any) and he can then change it;
        # what it shows is what is sent. One value only -- the actor cannot be asked for "anything
        # but remote".
        Field('remote', 'Workplace Type', CHOICE,
              options=[('', 'Any'), ('remote', 'Remote'), ('onsite', 'On-site'),
                       ('hybrid', 'Hybrid')],
              default='remote',
              hint='Measured: with remote, 100 of 100 rows were tagged Remote and only 43 ids '
                   'matched the unfiltered run, so it searches deeper for remote jobs rather '
                   'than trimming the same list.'),
        # `limit` is the actor's page size and it accepts 1-100. Whatever is chosen is sent as
        # `limit`; 0 sends nothing, which is the actor's maximum of 100 per call, and the pages
        # are then walked. Under 100 one call is the whole answer, because a page shorter than
        # 100 is the last page.
        Field('limit', 'Results limit', NUMBER,
              default=0, minimum=0, maximum=100, step=10, zero_means='Max',
              presets=(0, 10, 20, 50, 100),
              hint='The actor bills $0.005 a row: 20 rows is $0.10, and "Max" walks every page '
                   '(about 155 Remote rows, $0.78).'),
        Field('sort', 'Sort Order', CHOICE,
              options=[('', 'LinkedIn default'), ('recent', 'Most recent first'),
                       ('relevant', 'Most relevant first')],
              default='',
              hint='Measured: "recent" put the median age of the first 30 results at 10 days '
                   'against 17, and returned a different 36% of the jobs.'),
        Field('easy_apply', 'Easy Apply Only', CHOICE,
              options=[('', 'Any'), ('true', 'Yes')], default='',
              hint='Measured: 100 rows became 38, every one of them Easy Apply.'),
        Field('under_10_applicants', 'Under 10 Applicants', CHOICE,
              options=[('', 'Any'), ('true', 'Yes')], default='',
              hint='Measured: 100 rows became 18. The actor leaves the applicant count '
                   'empty on those rows, so the effect shows in the number of results '
                   'rather than inside each one.'),
    ],
    'glassdoor': [
        Field('limit', 'Results limit', NUMBER,
              default=0, minimum=0, maximum=1000, step=50, zero_means='No limit',
              presets=(0, 50, 100, 200, 300, 500, 1000),
              hint=_LIMIT_HINT + ' Its own ceiling is 1,000.'),
        # The only filter in this app that really keeps office work out of a Remote search.
        # Measured: without it 300 rows and 84% of titles in the field; with it 15 rows and
        # 100% in the field. Left as a tick rather than tied to the Remote/Not Remote choice
        # so that the window shows what is sent instead of deciding it somewhere else.
        Field('remoteWorkType', 'Remote only', FLAG, default=True,
              hint='Glassdoor applies this itself, before the rows are counted — so it '
                   'costs nothing and nothing office-based is paid for. The one real '
                   'remote filter among the three sources.'),
        Field('minRating', 'Minimum rating', CHOICE,
              options=[('', 'Any rating'), (3, '3.0 and above'), (3.5, '3.5 and above'),
                       (4, '4.0 and above'), (4.5, '4.5 and above')],
              default='',
              hint='Measured: asking for 4.0 took 300 rows to 222, and the 143 rated '
                   'below 4 became 0.'),
        Field('employerSizes', 'Company sizes', CHOICE,
              options=[('', 'Any size'), ('1', '1–200 employees'),
                       ('2', '201–500'), ('3', '501–1,000'),
                       ('4', '1,001–5,000'), ('5', '5,001+')],
              default='',
              hint='Measured: asking for 1–200 took 300 rows to 94.'),
        Field('easyApply', 'Easy Apply', FLAG, default=False,
              hint='Measured: 300 rows became 224, every one of them Easy Apply '
                   '(48 of 300 were, unfiltered).'),
    ],
    'indeed': [
        # Indeed's own way to ask for remote work: the actor documents `location` as "City, state,
        # zip code, or "remote"". Measured, 10 rows each: Germany -> 10 of 10 Home Office / remote,
        # US -> 10 of 10 Remote; Netherlands -> 0 rows (Indeed.nl lists almost none) -- an honest
        # empty answer, not a failure. Any sends nothing here, so the searched place is used.
        Field('location', 'Location', CHOICE,
              options=[('', 'Any'), ('remote', 'Remote')], default='remote',
              hint='Remote replaces the searched place with "remote" inside the country.'),
        Field('limit', 'Results limit', NUMBER,
              default=0, minimum=0, maximum=1000, step=50, zero_means='No limit',
              presets=(0, 50, 100, 200, 300, 500, 1000),
              hint=_LIMIT_HINT + ' Its own ceiling is 1,000.'),
    ],
}

# Said in the window under each actor, so a short panel reads as a finding rather than as
# something unfinished. Sina asked why a search costs what it does; this is the answer in the
# place where he would otherwise wonder.
NOTES = {
    'linkedin': ("Every filter here was measured against the live actor. Every row comes "
                 "back with LinkedIn's own Hybrid / On-site / Remote tag, and the Work "
                 "Location rule trusts that tag over the advert's wording. \"Remote jobs "
                 "only\" is a recall setting, not a decision: nothing is deleted here and "
                 "the Filter still decides. A Remote search asks for remote jobs only; "
                 "tick the box to see Hybrid and On-site too. Not sent for a Not Remote "
                 "search or for Italy. Experience level was tested and does nothing, so it is not "
                 "offered -- Seniority is a column, not a filter."),
    'glassdoor': ('Every filter here was measured against the live actor. It is also the '
                  'cheapest of the three per row, and the only one that can refuse '
                  'office work before charging for it.'),
    'indeed': ('This actor has five fields in total and the app sends all of them. Its '
               'only remote switch is the word "remote" in `location`; it has no seniority '
               'filter, and its date window stops at 14 days.'),
}


def fields_for(platform):
    return FIELDS.get(str(platform or '').lower(), [])


def note_for(platform):
    return NOTES.get(str(platform or '').lower(), '')


def defaults():
    """What the window opens showing before Sina has ever saved anything."""
    return {platform: {field.key: field.default for field in fields}
            for platform, fields in FIELDS.items()}


def chosen_for(settings, platform):
    """The saved choices for one actor, with anything missing filled from the defaults."""
    saved = ((settings or {}).get(SETTINGS_KEY) or {}).get(
        str(platform or '').lower()) or {}
    out = {}
    for field in fields_for(platform):
        out[field.key] = saved.get(field.key, field.default)
    return out


def apply_to_request(run_input, settings, platform):
    """Put the chosen filters into a run input, and return it.

    Only ever ADDS keys. A field left in its off position sends nothing, so a request built
    without any of this is unchanged -- which is what keeps the existing per-actor request
    builders, and every test written against them, correct.

    The exception is the row limit: the builders already set one from the global
    `limit_per_call`, so a per-actor number REPLACES it rather than sitting beside it. That
    is the whole point of having it per actor -- $0.005 a row on LinkedIn against a small
    fraction of that elsewhere.
    """
    chosen = chosen_for(settings, platform)
    for field in fields_for(platform):
        value = field.send_value(chosen.get(field.key))
        if value is None:
            continue
        run_input[field.key] = value
        for twin in field.also_sets:
            run_input[twin] = value
    return run_input
