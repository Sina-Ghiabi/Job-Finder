"""Shared harness for the Job Finder comprehensive test campaign."""
import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

_results = {'pass': 0, 'fail': 0, 'error': 0}
_failures = []
_current_section = ['']


def section(name):
    _current_section[0] = name
    print()
    print('-' * 76)
    print(name)
    print('-' * 76)


def check(name, condition, detail=''):
    """A single assertion. `condition` may be a bool or a zero-arg callable."""
    try:
        ok = condition() if callable(condition) else bool(condition)
    except Exception as e:
        _results['error'] += 1
        _failures.append((_current_section[0], name, f'{type(e).__name__}: {e}'))
        print(f'  ERROR  {name}\n         {type(e).__name__}: {e}')
        return False
    if ok:
        _results['pass'] += 1
        print(f'  pass   {name}')
        return True
    _results['fail'] += 1
    _failures.append((_current_section[0], name, str(detail)))
    print(f'  FAIL   {name}' + (f'\n         {detail}' if detail else ''))
    return False


def check_raises(name, fn, exc=Exception):
    try:
        fn()
    except exc:
        return check(name, True)
    except Exception as e:
        return check(name, False, f'raised {type(e).__name__} instead of {exc.__name__}: {e}')
    return check(name, False, 'did not raise')


def check_no_raise(name, fn):
    try:
        fn()
        return check(name, True)
    except Exception as e:
        return check(name, False, f'{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}')


def isolated_storage():
    """Points app.storage at a fresh temp dir so no test can touch real user data.

    Also takes the waiting out of enrichment's retries. Those pauses add up to ten minutes
    of real sleeping per call, which is right in a search measured in hours and absurd in a
    test suite -- and several suites drive a whole search. What is worth testing is that it
    asks again, and how many times; both survive the pauses being zero.
    """
    from app import storage
    tmp = Path(tempfile.mkdtemp()) / 'jd'
    storage.DATA_DIR = tmp
    storage.DOCUMENTS_DIR = tmp / 'documents'
    storage.SETTINGS_PATH = tmp / 'settings.json'
    storage.APPLICATIONS_PATH = tmp / 'applications.json'
    storage.JOBS_PATH = tmp / 'jobs.json'
    storage.BANK_PATH = tmp / 'bank.json'
    storage._ensure_dirs()
    try:
        from app.pipeline import enrich
        enrich.ENRICH_RETRY_PAUSES = (0,) * len(enrich.ENRICH_RETRY_PAUSES)
    except Exception:
        pass
    return tmp


def summary(title):
    total = _results['pass'] + _results['fail'] + _results['error']
    print()
    print('=' * 76)
    print(f"{title}: {_results['pass']}/{total} passed, "
          f"{_results['fail']} failed, {_results['error']} errored")
    if _failures:
        print()
        for sec, name, detail in _failures:
            print(f'  [{sec}] {name}')
            if detail:
                print(f'      {detail.splitlines()[0][:150]}')
    print('=' * 76)
    return _results['fail'] + _results['error']
