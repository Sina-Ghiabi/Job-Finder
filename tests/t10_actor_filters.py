# -*- coding: utf-8 -*-
"""Suite 10 -- the per-platform filters: shown only if sent, sent only if shown.

WHY THIS SUITE EXISTS

f_WT=2 was sent to LinkedIn on every Remote search this app ever ran, and it does nothing:
the same URL without it returns the identical 300 jobs. For four months the premise of the
whole search -- Sina works from his desk in Turin and is not moving -- never reached the
largest source in the app, and nothing noticed, because two tests asserted the parameter was
in the URL and called that "LinkedIn's own remote filter".

The Search window he then asked for could have made that permanent: a tick box for a
parameter the actor drops looks like control and is decoration. So the window is built from
`actor_filters.FIELDS`, the request builders read the choices back through the same table,
and this suite holds the two halves together:

    a field in the table must reach the actor's run input
    a field that reaches the run input must be in the table

Plus the thing the table is for: everything in it was measured against the live actor, and
the parameters that were measured and dropped must stay out.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, summary                       # noqa: E402

from app import pipeline                                          # noqa: E402
from app.pipeline import actor_filters as af                      # noqa: E402
from app.pipeline.search.runner import _actor_request             # noqa: E402

DATES = {'linkedin': 'pastMonth', 'indeed': '14', 'glassdoor': 30}


def asked(platform, settings=None, not_remote=False, limit=100000):
    _actor, run_input, _norm = _actor_request(
        platform, 'Q', 'country', 'Netherlands', 'Netherlands', limit, DATES,
        not_remote, settings)
    return run_input


# ---------------------------------------------------------------------------------------
section('10.1  the measured truth: what is offered, and what is deliberately not')
# ---------------------------------------------------------------------------------------
# Each of these was proved by running the same query twice against the live actor with one
# parameter changed and comparing the returned job ids. The dropped ones returned an
# identical set, so they are decoration, and a control for them would be a lie.
# LinkedIn's list changed with the actor on 4 October 2026. curious_coder dropped f_WT, f_E and
# sortBy; apimaestro honours `remote` and `sort` and drops only experienceLevel -- all five of
# its levels returned the same 96 of 100 job ids. The old three are kept in the list as keys
# the new actor was never sent, so a future edit that "restores" them is caught either way.
PROVEN_DROPPED = {
    'linkedin': ['f_WT', 'f_E', 'sortBy', 'experienceLevel', 'limitPerSource'],
    'glassdoor': ['sortBy'],
}
for _platform, _dead in PROVEN_DROPPED.items():
    _offered = {field.key for field in af.fields_for(_platform)}
    for _key in _dead:
        check('%s does not offer %s -- measured as ignored' % (_platform, _key),
              _key not in _offered, sorted(_offered))

# Untested is not the same as broken, and neither belongs in the window. These are real
# fields on the actors' published schemas that nobody has measured yet; they belong here the
# day they are, and not before.
UNTESTED = {
    'linkedin': ['company_id', 'page_number', 'distance', 'geoId', 'splitByLocation'],
    'glassdoor': ['radius', 'excludeJobIds'],
}
for _platform, _unknown in UNTESTED.items():
    _offered = {field.key for field in af.fields_for(_platform)}
    for _key in _unknown:
        check('%s does not offer %s -- never measured' % (_platform, _key),
              _key not in _offered, sorted(_offered))

# And the ones that were measured working must be there, or the measurement bought nothing.
PROVEN_WORKING = {
    'glassdoor': ['remoteWorkType', 'minRating', 'employerSizes', 'easyApply', 'limit'],
    'linkedin': ['remote', 'limit', 'sort', 'easy_apply', 'under_10_applicants'],
    'indeed': ['limit'],
}
for _platform, _live in PROVEN_WORKING.items():
    _offered = {field.key for field in af.fields_for(_platform)}
    for _key in _live:
        check('%s offers %s -- measured as honoured' % (_platform, _key),
              _key in _offered, sorted(_offered))

# Google is driven entirely by the queries built for it and has no actor filters of its own,
# so it must get no box rather than an empty one.
check('google has no filter fields of its own', af.fields_for('google') == [])
check('an unknown platform asks for nothing', af.fields_for('nonesuch') == [])


# ---------------------------------------------------------------------------------------
section('10.2  off means off: nothing narrows the search unless he chose it')
# ---------------------------------------------------------------------------------------
# Sina's standing rule for this whole project. An actor's own default is not his choice
# either, so every control's off position sends NO key at all.
_defaults = {af.SETTINGS_KEY: af.defaults()}
for _platform in ('linkedin', 'glassdoor', 'indeed'):
    _bare = asked(_platform)
    _with_defaults = asked(_platform, _defaults)
    # remoteWorkType defaults ON, and the builder already sets it for a Remote search, so
    # the two agree there rather than differing.
    if _platform == 'indeed':
        # The one platform whose remote switch is not set by the builder: its default is Remote
        # (the Search mode's default), which replaces the place with "remote". Everything
        # else it sends is identical.
        _with_defaults = {k: v for k, v in _with_defaults.items() if k != 'location'}
    check('%s asked with defaults matches asked with nothing' % _platform,
          _bare == _with_defaults, (_bare, _with_defaults))

for _field in af.fields_for('glassdoor'):
    if _field.key == 'remoteWorkType':
        continue
    check('glassdoor %s sends nothing when left off' % _field.key,
          _field.send_value(_field.default) is None, _field.default)
check('a choice left on "any" sends nothing',
      af.Field('x', 'x', af.CHOICE).send_value('any') is None)
check('a flag left unticked sends nothing',
      af.Field('x', 'x', af.FLAG).send_value(False) is None)
check('a number left at zero sends nothing',
      af.Field('x', 'x', af.NUMBER).send_value(0) is None)
check('a number that is not a number sends nothing',
      af.Field('x', 'x', af.NUMBER).send_value('lots') is None)


# ---------------------------------------------------------------------------------------
section('10.3  a choice reaches the actor under the key the actor wants')
# ---------------------------------------------------------------------------------------
PICKED = {af.SETTINGS_KEY: {
    'linkedin': {'limit': 20, 'remote': 'hybrid', 'sort': 'recent', 'easy_apply': 'true',
                 'under_10_applicants': 'true'},
    'glassdoor': {'limit': 300, 'remoteWorkType': True, 'minRating': 4,
                  'employerSizes': '1', 'easyApply': True},
    'indeed': {'limit': 250},
}}
_gd = asked('glassdoor', PICKED)
check('glassdoor is asked for the rating floor', _gd.get('minRating') == 4, _gd)
check('  ...the company size', _gd.get('employerSizes') == '1', _gd)
check('  ...Easy Apply', _gd.get('easyApply') is True, _gd)
check('  ...remote only', _gd.get('remoteWorkType') is True, _gd)
check('  ...and its own row limit, replacing the global one',
      _gd.get('limit') == 300, _gd)

_in = asked('indeed', PICKED)
check('indeed is asked for its own row limit', _in.get('limit') == 250, _in)
check('  ...and keeps the date window it was already given',
      _in.get('datePosted') == '14', _in)

# LinkedIn, on the actor that replaced curious_coder. Its pair of row-limit keys is gone --
# `limit` here is a PAGE size of at most 100 and Sina's cap is `maxResults`, an instruction to
# _run_linkedin_pages that is removed before anything is sent.
_li = asked('linkedin', PICKED)
check('linkedin is asked for the Results limit as the actor\'s own `limit`',
      _li.get('limit') == 20, _li)
check('  ...and Workplace Type is sent as the actor\'s own value, not translated',
      _li.get('remote') == 'hybrid', _li)
check('  ...the sort order', _li.get('sort') == 'recent', _li)
check('  ...Easy Apply', _li.get('easy_apply') == 'true', _li)
check('  ...under 10 applicants', _li.get('under_10_applicants') == 'true', _li)
check('  ...no old-actor key survives, and no instruction of ours is sent under its name',
      not ({'limitPerSource', 'count', 'urls', 'autoConvertToAiSearch', 'allWorkplaces',
            'maxResults'} & set(_li)), _li)
check('Workplace Type Any sends nothing at all',
      'remote' not in asked('linkedin', {af.SETTINGS_KEY: {'linkedin': {'remote': ''}}}),
      asked('linkedin', {af.SETTINGS_KEY: {'linkedin': {'remote': ''}}}))

# The off positions send nothing, so an untouched window cannot narrow a search by itself.
_plain = asked('linkedin', {af.SETTINGS_KEY: {'linkedin': {}}})
check('an untouched LinkedIn window sends what a window-less call sends, remote included',
      set(_plain) == {'keywords', 'location', 'limit', 'date_posted', 'remote'}, _plain)

# Removed again for the two cases where it has no meaning, whatever the window says.
# The work mode no longer decides this: the window does, and PICKED says hybrid.
check('a Not Remote search sends what the window says -- here hybrid -- not what the mode implies',
      asked('linkedin', PICKED, True).get('remote') == 'hybrid', asked('linkedin', PICKED, True))

# The query reaches LinkedIn as written, on both work modes.
for _not_remote in (False, True):
    check('the query stays literal whatever else is chosen (%s remote)'
          % ('not' if _not_remote else 'is'),
          asked('linkedin', PICKED, _not_remote).get('keywords') == 'Q',
          asked('linkedin', PICKED, _not_remote))


# ---------------------------------------------------------------------------------------
section('10.4  a half-written or hostile settings file cannot stop a search')
# ---------------------------------------------------------------------------------------
# These arrive from a settings.json written by an older build, or by hand. None of them may
# raise: a search refusing to start over a stray value in a filter box would be a far worse
# bug than the filter being ignored.
HOSTILE = [
    None,
    {},
    {af.SETTINGS_KEY: None},
    {af.SETTINGS_KEY: {}},
    {af.SETTINGS_KEY: {'linkedin': None}},
    {af.SETTINGS_KEY: {'linkedin': {'limitPerSource': None}}},
    {af.SETTINGS_KEY: {'linkedin': {'limitPerSource': 'four hundred'}}},
    {af.SETTINGS_KEY: {'glassdoor': {'minRating': 'excellent'}}},
    {af.SETTINGS_KEY: {'glassdoor': {'easyApply': 'yes please'}}},
    {af.SETTINGS_KEY: {'unknownPlatform': {'whatever': 1}}},
    {af.SETTINGS_KEY: {'linkedin': {'limitPerSource': -5}}},
]
for _at, _shape in enumerate(HOSTILE):
    _errors = []
    for _platform in ('linkedin', 'glassdoor', 'indeed'):
        try:
            asked(_platform, _shape)
        except Exception as _exc:                                 # noqa: BLE001
            _errors.append('%s: %s' % (_platform, type(_exc).__name__))
    check('settings shape %d is survivable' % _at, not _errors, _errors)

check('a negative row limit is treated as no limit',
      'limitPerSource' not in af.apply_to_request(
          {}, {af.SETTINGS_KEY: {'linkedin': {'limitPerSource': -5}}}, 'linkedin'))
check('an unreadable rating is simply not sent',
      'minRating' not in af.apply_to_request(
          {}, {af.SETTINGS_KEY: {'glassdoor': {'minRating': 'excellent'}}}, 'glassdoor'))


# ---------------------------------------------------------------------------------------
section('10.5  the window and the table cannot drift apart')
# ---------------------------------------------------------------------------------------
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication                        # noqa: E402

_app = QApplication.instance() or QApplication([])
from app.ui.setup_wizard import SetupWizard                       # noqa: E402

_wizard = SetupWizard({})
check('the window builds a box for every platform that has filters',
      set(_wizard.actor_filter_inputs) == {p for p in af.FIELDS if af.FIELDS[p]},
      sorted(_wizard.actor_filter_inputs))
for _platform, _widgets in _wizard.actor_filter_inputs.items():
    check('%s has a control for every field in the table' % _platform,
          set(_widgets) == {f.key for f in af.fields_for(_platform)},
          (sorted(_widgets), sorted(f.key for f in af.fields_for(_platform))))

# Read back with nothing touched: it must equal the defaults, or opening the window and
# pressing Save would silently narrow the next search.
check('an untouched window reads back exactly the defaults',
      _wizard._selected_actor_filters() == af.defaults(),
      (_wizard._selected_actor_filters(), af.defaults()))

# EVERY PARAMETER IS A DROPDOWN, WITH NO EXPLANATORY TEXT -- Sina: "برای پارامتر های Actor ها
# توضیح ننویس و زیر هم تمام پارامتر هایی که میتونیم به یک Actor بدیم رو بنویس عبارتش رو و جلوش
# یک Dropdown بذار". A tick used to be a checkbox and a number a spin box; asserting the kind of
# widget is how the next edit cannot quietly bring either back.
from PySide6.QtWidgets import QComboBox, QLabel, QWidget       # noqa: E402

for _platform, _widgets in _wizard.actor_filter_inputs.items():
    for _key, _widget in _widgets.items():
        check('%s %s is a dropdown' % (_platform, _key), isinstance(_widget, QComboBox),
              type(_widget).__name__)
_panel_text = []
_titles = []
for _box in _wizard.findChildren(QWidget):
    if _box.property('actor_platform'):
        _labs = _box.findChildren(QLabel)
        _titles += [lab.text() for lab in _labs if lab.objectName() == 'PlatformTitle']
        _panel_text += [lab.text() for lab in _labs if lab.objectName() != 'PlatformTitle']
check('each platform has a title of its own, drawn as a label (not a clipped group box)',
      sorted(_titles) == ['Glassdoor', 'Indeed', 'LinkedIn'], _titles)
_labels_expected = {f.label for p in af.FIELDS for f in af.fields_for(p)}
check('the panels carry no prose -- every label is a parameter name',
      set(_panel_text) <= _labels_expected, sorted(set(_panel_text) - _labels_expected))
check('  ...and no field hint reaches the window',
      not any(f.hint and f.hint in ' '.join(_panel_text) for p in af.FIELDS
              for f in af.fields_for(p)))
check('  ...and neither does the per-actor note',
      not any(af.note_for(p) and af.note_for(p) in ' '.join(_panel_text) for p in af.FIELDS))

# The parameters are named in the actors' own words, as their input schemas title them.
_LABELS = {'linkedin': {'limit': 'Results limit', 'remote': 'Workplace Type',
                        'sort': 'Sort Order', 'easy_apply': 'Easy Apply Only',
                        'under_10_applicants': 'Under 10 Applicants'},
           'glassdoor': {'limit': 'Results limit', 'remoteWorkType': 'Remote only',
                         'minRating': 'Minimum rating', 'employerSizes': 'Company sizes',
                         'easyApply': 'Easy Apply'},
           'indeed': {'limit': 'Results limit'}}
for _platform, _names in _LABELS.items():
    for _key, _label in _names.items():
        _got = [f.label for f in af.fields_for(_platform) if f.key == _key]
        check('%s %s is labelled "%s"' % (_platform, _key, _label), _got == [_label], _got)

# A number offers a list, with 0 meaning no limit, and a ceiling the actor can accept.
for _platform in ('linkedin', 'glassdoor', 'indeed'):
    for _f in af.fields_for(_platform):
        if _f.kind != af.NUMBER:
            continue
        _opts = _f.dropdown_options()
        check('%s %s offers 0 for no limit' % (_platform, _f.key), _opts[0][0] == 0, _opts)
        check('  ...and nothing above what the actor accepts', max(v for v, _ in _opts) <= _f.maximum,
              _opts)
# A value saved under the old spin box is kept, not silently replaced.
_f = [f for f in af.fields_for('linkedin') if f.key == 'limit'][0]
check('a saved 30 that is not on the list is added to it, not lost',
      30 in [v for v, _ in _f.dropdown_options(30)], _f.dropdown_options(30))
_w = _wizard._actor_filter_widget(_f, 30)
check('  ...and the dropdown shows it selected', _w.currentData() == 30, _w.currentData())
check('Workplace Type offers exactly the actor\'s own four values',
      [v for v, _l in [f for f in af.fields_for('linkedin') if f.key == 'remote'][0].options]
      == ['', 'remote', 'onsite', 'hybrid'])
check('a tick reads as No / Yes', [l for _v, l in af.Field('x', 'x', af.FLAG).dropdown_options()]
      == ['No', 'Yes'])

# And what he picks must survive the round trip through the window's own widgets.
_li = _wizard.actor_filter_inputs['linkedin']['limit']
_li.setCurrentIndex(_li.findData(50))
_gl = _wizard.actor_filter_inputs['glassdoor']
_gl['minRating'].setCurrentIndex(_gl['minRating'].findData(4))
_gl['employerSizes'].setCurrentIndex(_gl['employerSizes'].findData('1'))
_gl['easyApply'].setCurrentIndex(_gl['easyApply'].findData(True))
_read = _wizard._selected_actor_filters()
check('a chosen row limit survives the window', _read['linkedin']['limit'] == 50,
      _read['linkedin'])
check('a chosen rating survives the window', _read['glassdoor']['minRating'] == 4,
      _read['glassdoor'])
check('a chosen company size survives the window',
      _read['glassdoor']['employerSizes'] == '1', _read['glassdoor'])
check('a chosen tick survives the window, as a real boolean',
      _read['glassdoor']['easyApply'] is True, _read['glassdoor'])
check('  ...and a number comes back as an int, not a string',
      isinstance(_read['linkedin']['limit'], int), _read['linkedin'])
# Every dropdown stores the value the actor wants, not the label a person reads -- the
# labels are prose and will be reworded.
for _platform in _wizard.actor_filter_inputs:
    for _field in af.fields_for(_platform):
        _combo = _wizard.actor_filter_inputs[_platform][_field.key]
        _stored = [_combo.itemData(_at) for _at in range(_combo.count())]
        check('%s %s stores the actor\'s own values' % (_platform, _field.key),
              _stored == [value for value, _label in _field.dropdown_options(
                  _wizard._selected_actor_filters()[_platform][_field.key])], _stored)

# Saving must carry them, under the name the table owns.
from PySide6.QtCore import Qt                                     # noqa: E402

_wizard.token_input.setText('t')
_wizard.title_input.setText('Data Science')
_wizard.countries_tree.topLevelItem(0).setCheckState(0, Qt.Checked)
if _wizard._build_result_settings():
    check('Save writes the filters under the table\'s own key',
          _wizard.result_settings.get(af.SETTINGS_KEY) == _read,
          _wizard.result_settings.get(af.SETTINGS_KEY))
else:
    check('Save writes the filters under the table\'s own key', False,
          'the form would not validate')

# The worker has to be able to carry them, or the window is decoration.
import inspect                                                    # noqa: E402

from app.search_worker import SearchWorker                         # noqa: E402

check('SearchWorker accepts the filters',
      'actor_filter_settings' in inspect.signature(SearchWorker.__init__).parameters)
check('run_search accepts the filters',
      'actor_filter_settings' in inspect.signature(pipeline.run_search).parameters)


# ---- Indeed's own remote term: `location` = "remote", as the actor documents it ----
from app.pipeline.search import runner as _rn  # noqa: E402
_DS = {'indeed': '7', 'linkedin': 'pastWeek', 'glassdoor': 7}
_R = {af.SETTINGS_KEY: {'indeed': {'location': 'remote'}}}
_A = {af.SETTINGS_KEY: {'indeed': {'location': ''}}}
_ri = lambda cfg, where, ctry: _rn._actor_request('indeed', 'Q', 'city' if where != ctry else 'country',  # noqa: E731
                                                  where, ctry, 100, _DS, False, cfg)[1]
check('Indeed Remote sends location=remote inside the country',
      _ri(_R, 'Berlin', 'Germany').get('location') == 'remote'
      and _ri(_R, 'Berlin', 'Germany').get('country') == 'de', _ri(_R, 'Berlin', 'Germany'))
check('Indeed Any keeps the searched city', _ri(_A, 'Berlin', 'Germany').get('location') == 'Berlin',
      _ri(_A, 'Berlin', 'Germany'))
check('Indeed Any in a country search sends no location at all',
      'location' not in _ri(_A, 'Germany', 'Germany'))
check('Italy is no exception: Remote sends location=remote for a city and for the country',
      _ri(_R, 'Turin', 'Italy').get('location') == 'remote'
      and _ri(_R, 'Italy', 'Italy').get('location') == 'remote',
      (_ri(_R, 'Turin', 'Italy'), _ri(_R, 'Italy', 'Italy')))
check('Indeed offers exactly Any and Remote',
      [v for v, _l in [f for f in af.fields_for('indeed') if f.key == 'location'][0].options]
      == ['', 'remote'])

sys.exit(summary('Suite 10 -- per-platform actor filters'))

