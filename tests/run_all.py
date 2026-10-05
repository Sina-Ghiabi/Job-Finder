"""Runs the whole RoleHound test campaign and prints one consolidated verdict.

    .venv\\Scripts\\python tests\\run_all.py            # everything, including live APIs
    .venv\\Scripts\\python tests\\run_all.py --offline  # skip the suite that spends money

Suites 1-5 are free and fast (~1 minute). Suite 6 makes REAL calls: every free JSON API,
one real Claude screening, and one small real Apify actor run -- it reads the PACKAGED
app's credentials from %APPDATA%\\JobDesk\\settings.json, and skips the Apify run if less
than $0.30 of that account's monthly budget is left.

Exit code is 0 only when every assertion passes.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PY = os.path.join(APP, '.venv', 'Scripts', 'python.exe')
if not os.path.exists(PY):
    PY = sys.executable

OFFLINE = '--offline' in sys.argv

SUITES = [
    # Static analysis first: it is fast, it needs no fixtures, and a type error is worth
    # knowing about before spending a minute on the behavioural suites.
    ('Static analysis', 't0_static.py'),
    ('Rules & helpers', 't1_rules.py'),
    ('Data sources', 't2_sources.py'),
    ('Storage', 't3_storage.py'),
    ('Pipeline integration', 't4_pipeline.py'),
    ('UI & export', 't5_ui.py'),
    # The one path that spends money, given a suite of its own at Sina's request: a real
    # run costs about three dollars, so it is the least casually exercised code in the app
    # and the most expensive to get wrong.
    ('run_search', 't7_run_search.py'),
    # Both of these were written and then never listed here, so the campaign reported ALL
    # GREEN without running either of them -- a test that is not in the runner is a test
    # that does not exist. Suite 8 is the metamorphic and combinatorial work from the empty
    # German search; suite 9 is the quote guard that can overturn a Claude removal, and it
    # is offline because the guard is a pure function of the words it is given.
    ('Invariants & combinatorial', 't8_invariants.py'),
    ('Claude quote guard', 't9_claude_guard.py'),
    # The per-platform filters. Offline: it asserts what each actor is ASKED, which is a
    # pure function of the table and the chosen settings. What each actor then DOES with
    # the request was measured against the live source and is written down in
    # app/pipeline/actor_filters.py, because that part cannot be asserted for free.
    ('Per-platform actor filters', 't10_actor_filters.py'),
]
if not OFFLINE:
    SUITES.append(('LIVE APIs', 't6_live.py'))

SUMMARY_RE = re.compile(r':\s*(\d+)/(\d+) passed,\s*(\d+) failed,\s*(\d+) errored')


# An offline suite that has not finished in fifteen minutes is stuck, and saying so is the
# point. The live suite is different and needs its own number: it waits on Anthropic's
# **batch queue**, which queues rather than answers, and on a slow day that wait is the whole
# runtime rather than a hang.
#
# Measured on 23 September 2026: batches that had been ending in seconds all morning sat
# `in_progress` for over forty minutes, and the live suite timed out at 900s three times in a
# row. Run on its own with a longer ceiling, the same code passed 64 of 65 -- the one failure
# was remoteok's own timeout, which was a real fault and is fixed.
#
# So 900 was reporting a working suite as broken, which is O-7 in a third disguise, and the
# rule from it applies here too: a ceiling has to clear what the thing being measured
# actually takes. _BATCH_MAX_WAIT_SECONDS is 24 hours because that is Anthropic's own
# guarantee; this is not that patient, but it is patient enough for a queue that is merely
# busy.
_SUITE_TIMEOUT_SECONDS = 900
_LIVE_SUITE_TIMEOUT_SECONDS = 3600


def run(path):
    limit = _LIVE_SUITE_TIMEOUT_SECONDS if path.endswith('t6_live.py') else _SUITE_TIMEOUT_SECONDS
    try:
        r = subprocess.run([PY, '-u', path], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=limit, cwd=APP)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return '<<TIMEOUT after %d minutes>>' % (limit // 60)


print('=' * 78)
print('RoleHound test campaign' + ('  (offline)' if OFFLINE else '  (including live APIs)'))
print('=' * 78)

grand = {'pass': 0, 'bad': 0}
problems = []

for label, filename in SUITES:
    out = run(os.path.join(HERE, filename))
    m = SUMMARY_RE.search(out)
    if not m:
        print(f'  !! {label:<24} NO SUMMARY -- the suite crashed')
        problems.append((label, out[-900:]))
        grand['bad'] += 1
        continue
    passed, total, failed, errored = (int(g) for g in m.groups())
    grand['pass'] += passed
    grand['bad'] += failed + errored
    mark = 'OK ' if failed + errored == 0 else '!! '
    print(f'  {mark}{label:<24} {passed}/{total} passed'
          + ('' if failed + errored == 0 else f'  ({failed} failed, {errored} errored)'))
    if failed + errored:
        problems.append((label, '\n'.join(l for l in out.splitlines()
                                          if l.strip().startswith(('FAIL', 'ERROR')))))

print()
print('=' * 78)
print(f"TOTAL: {grand['pass']} assertions passed, {grand['bad']} failed/errored")
for label, detail in problems:
    print(f'\n--- {label} ---\n{detail[:1200]}')
print('\nVERDICT:', 'ALL GREEN' if grand['bad'] == 0 else f"{grand['bad']} PROBLEM(S)")
print('=' * 78)
sys.exit(0 if grand['bad'] == 0 else 1)
