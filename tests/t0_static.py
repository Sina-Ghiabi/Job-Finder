"""Suite 0 -- static analysis: pyflakes and mypy over the whole app.

These catch a different class of problem than the other five suites. A test only checks
the path it actually runs; a type checker checks every path in every function, including
the error branches nothing exercises. That is exactly where this project's most expensive
bugs lived -- a value that is a str on the happy path, None or a pandas NaN on another.

Neither tool is a formality here: mypy's first real run found 41 findings, and the
triage was consistent -- every function it flagged for receiving None already guarded
against it, so the ANNOTATIONS were wrong, not the code. An annotation that promises
`str` on a function that handles None is worse than none at all, because it invites
someone to delete the guard.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, summary

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PY = os.path.join(APP, '.venv', 'Scripts', 'python.exe')
if not os.path.exists(PY):
    PY = sys.executable


def run(args):
    r = subprocess.run([PY, '-m'] + args, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', cwd=APP, timeout=600)
    return (r.stdout or '') + (r.stderr or '')


section('0.1  pyflakes -- undefined names and unused imports')

TARGETS = []
for sub in ('app', os.path.join('app', 'ui'), os.path.join('app', 'pipeline'),
            os.path.join('app', 'pipeline', 'search')):
    d = os.path.join(APP, sub)
    if os.path.isdir(d):
        TARGETS += [os.path.join(sub, f) for f in sorted(os.listdir(d)) if f.endswith('.py')]

check('found the app modules to lint', len(TARGETS) >= 25, len(TARGETS))

flakes = run(['pyflakes'] + TARGETS)
flake_lines = [l for l in flakes.splitlines()
               if l.strip() and 'unable to detect undefined names' not in l]
check('pyflakes reports nothing across the whole app',
      not flake_lines, flake_lines[:6])

section('0.2  mypy -- type consistency across every path, not just the ones tests run')

out = run(['mypy'])
errors = [l for l in out.splitlines() if ': error:' in l]
check('mypy reports no errors', not errors, errors[:6])
check('mypy actually checked the app (did not abort early)',
      'no issues found in' in out or errors, out.strip().splitlines()[-1:] if out.strip() else '<no output>')

# check_untyped_defs is the setting that makes this meaningful: without it mypy skips the
# body of every unannotated function, which is most of them, and reports almost nothing
# while looking green.
cfg = open(os.path.join(APP, 'mypy.ini'), encoding='utf-8').read()
check('mypy.ini still enables check_untyped_defs',
      'check_untyped_defs = True' in cfg)
check('mypy.ini still skips site-packages (PySide6 ships an unparseable stub)',
      'no_site_packages = True' in cfg)

section('0.3  the fetch ladder has all four rungs available')

# fetcher.py imports curl_cffi and playwright defensively: if either is missing the ladder
# drops rungs and keeps working. That is right for robustness and dangerous for packaging,
# because the failure is completely silent -- the app just goes back to being unable to
# open the sites those rungs exist for, with every other test still green. So assert here
# that they are actually importable.
try:
    from curl_cffi import requests as _curl_requests
    _have_curl = hasattr(_curl_requests, 'get')
    _curl_error = ''
except Exception as exc:
    _have_curl, _curl_error = False, f'{type(exc).__name__}: {exc}'
check('curl_cffi imports (rungs 2 and 3: the TLS-fingerprint and crawler routes)',
      _have_curl, _curl_error)

try:
    import playwright.sync_api as _pw_api
    _have_pw = hasattr(_pw_api, 'sync_playwright')
    _pw_error = ''
except Exception as exc:
    _have_pw, _pw_error = False, f'{type(exc).__name__}: {exc}'
check('playwright imports (rung 4: the full browser route)', _have_pw, _pw_error)

# The spec file has to name curl_cffi explicitly: PyInstaller cannot see an import that
# happens inside a function by name. collect_submodules is the line that matters -- it
# brings in the compiled _wrapper.pyd, which is where libcurl lives.
_spec = open(os.path.join(APP, 'RoleHound.spec'), encoding='utf-8').read()
check('the PyInstaller spec collects curl_cffi submodules',
      "collect_submodules('curl_cffi')" in _spec)

# Assert the mechanism, not just the spec text. collect_dynamic_libs currently returns
# nothing for curl_cffi, so a spec that relied on it alone would ship a broken app while
# looking correct -- which is why this checks that the compiled extension is really among
# what gets collected.
try:
    from PyInstaller.utils.hooks import collect_submodules as _collect
    _curl_modules = _collect('curl_cffi')
    _collect_error = ''
except Exception as exc:
    _curl_modules, _collect_error = [], f'{type(exc).__name__}: {exc}'
check('collecting curl_cffi actually yields its modules',
      len(_curl_modules) > 5, _collect_error or len(_curl_modules))
check('  ...including the compiled extension that carries libcurl',
      any('_wrapper' in m for m in _curl_modules),
      [m for m in _curl_modules if 'wrap' in m] or _curl_modules[:5])


# ------------------------------------------------------------------- 0.one-at-a-time ----
section('0.one-at-a-time  every Claude module asks about one listing per request')
# Sina asked for this outright: "مگه قرار نشد یکی یکی بفرستیم تا درست کار کنه". Two of the
# three modules were changed then and the Job module was not, so a Junior search -- the one he
# actually runs -- kept bundling three listings per request. Measured in screen.py's own
# table, three agrees with one-at-a-time 96.7% of the time, and every disagreement is a
# listing wrongly KEPT. He reported one: Simon-Kucher's Amsterdam internship, which states
# "able to work from our Amsterdam office during the internship period" and came back with a
# 68% match and apply_verdict 'apply'.
#
# This is a static check on purpose. The three numbers live in three files, and a question
# answered in three places drifts the first time one of them is touched -- the Rule 5 mistake,
# which lived in ten files and was changed in one. Asserted here, that costs a failing test
# instead of a wrongly kept job.
from app.pipeline.claude_screen import screen as _job_screen          # noqa: E402
from app.pipeline.internship import claude as _intern_claude          # noqa: E402
from app.pipeline.thesis import claude as _thesis_claude              # noqa: E402

for _name, _size in (('the Job module', _job_screen._BATCH_GROUP_SIZE),
                     ('the Internship module', _intern_claude._GROUP_SIZE),
                     ('the Thesis module', _thesis_claude._GROUP_SIZE)):
    check('%s sends one listing per request' % _name, _size == 1, _size)

# And the comment that explains why, so the next person to reach for a cheaper number reads
# the measurement first rather than rediscovering it on Sina's results.
_screen_src = open(os.path.join(APP, 'app', 'pipeline', 'claude_screen', 'screen.py'),
                   encoding='utf-8').read()
check('  ...and screen.py still records what bundling cost',
      'wrongly KEPT' in _screen_src and 'Simon-Kucher' in _screen_src)

sys.exit(summary('Suite 0 -- static analysis'))
