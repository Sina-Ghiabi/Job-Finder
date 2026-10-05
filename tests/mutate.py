# -*- coding: utf-8 -*-
"""Mutation testing: break one rule at a time and check that some test notices.

WHY THIS IS THE TEST THAT EXPLAINS THE OTHERS

The user's German search came back empty while 2,559 assertions passed. The obvious question is how
both can be true, and the answer is that a passing test proves nothing about coverage -- it only
proves that the thing it looks at is as it was. A rule can be narrowed to uselessness without a
single assertion touching the narrowed part.

This measures that directly. Each mutation below is a small, plausible change to a rule -- the
kind a person makes while tuning -- applied to the source on disk, with the suites then run
against it. If every suite still passes, the mutation SURVIVED, which means nothing in 2,600
assertions is watching that behaviour. A surviving mutation is a hole, and it is named.

    mutation killed    = a test failed = that behaviour is covered
    mutation survived  = every test passed = nothing is watching it

HOW IT IS SAFE

The file is read, changed in memory, written, the suites run, and the original is put back in a
finally block -- and the original bytes are held in memory the whole time, so an interrupted run
restores on the next one. It also refuses to start if git reports the working tree dirty for the
files it touches, because a crash mid-run must never be able to lose real edits.

Run it with:   .venv\\Scripts\\python.exe tests/mutate.py
It takes a while: every mutation runs the suites from scratch.
"""
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PY = os.path.join(APP, '.venv', 'Scripts', 'python.exe')
if not os.path.exists(PY):
    PY = sys.executable
out = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

# Which suites to run per mutation. The fast, offline ones -- suite 2 and 6 talk to the network
# and 7 is slow, and none of the three reads the rules being mutated.
SUITES = ('t1_rules.py', 't4_pipeline.py', 't8_invariants.py')

# Each mutation is (file, what to find, what to replace it with, what it breaks).
#
# They are chosen to be the mistakes this project has ACTUALLY made, not arbitrary character
# swaps: a threshold nudged, a guard inverted, a rule narrowed to the title, a cap loosened.
MUTATIONS = [
    ('app/pipeline/rules.py',
     "_DEDUP_TITLE_SIMILARITY_THRESHOLD = 0.90",
     "_DEDUP_TITLE_SIMILARITY_THRESHOLD = 0.60",
     'the duplicate threshold, loosened until unrelated jobs merge'),

    ('app/pipeline/rules.py',
     "    ('Part-Time', _PART_TIME_TITLE, _PART_TIME_IN_BODY, _PART_TIME_IS_OPTIONAL),",
     "    ('Part-Time', _PART_TIME_TITLE, None, None),",
     'Part-Time narrowed to the title -- the exact bug that emptied a real search'),

    ('app/pipeline/rules.py',
     "    ('Internship', _INTERNSHIP_TITLE, _INTERNSHIP_IN_BODY, _NOT_AN_INTERNSHIP),",
     "    ('Internship', _INTERNSHIP_TITLE, _INTERNSHIP_IN_BODY, None),",
     'the "not an internship" guard removed'),

    # The find string carries no trailing newline: the file is read as bytes and decoded, so a
    # "\n" here has to match the file's real line ending. The first version of this mutation
    # included one, matched nothing on a CRLF checkout, and reported itself as SKIPPED -- which
    # is the right thing to do rather than silently measuring nothing.
    ('app/pipeline/rules.py',
     "    ('PhD', _PHD_TITLE, None, None),",
     "    ('PhD', _PHD_TITLE, _PHD_TITLE, None),",
     'the PhD rule made to read the body, where "a PhD is a plus" appears constantly'),

    ('app/pipeline/title_equivalents.py',
     "MINIMUM_SIMILARITY = 35",
     "MINIMUM_SIMILARITY = 95",
     'the similarity floor raised until every other name for the job is dropped'),

    ('app/pipeline/chosen_filters.py',
     "        if named & wanted:",
     "        if True:",
     'the country choice made to keep everything'),

    ('app/pipeline/chosen_filters.py',
     "    if floor <= 0:\n        return jobs, 0",
     "    if floor <= 0:\n        return [], len(jobs)",
     'the match floor emptying the pool when no floor was set'),

    ('app/pipeline/filters.py',
     "    if wanted_fields:",
     "    if False:",
     'the chosen job titles ignored'),
]


def read(path):
    with open(os.path.join(APP, path), 'rb') as handle:
        return handle.read()


def write(path, data):
    with open(os.path.join(APP, path), 'wb') as handle:
        handle.write(data)


def suites_pass():
    """True when every suite passes. A crash counts as a failure, which is a kill."""
    for suite in SUITES:
        result = subprocess.run([PY, os.path.join('tests', suite)], cwd=APP,
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=2400)
        if result.returncode != 0:
            return False, suite
    return True, ''


def dirty_files():
    try:
        result = subprocess.run(['git', 'status', '--porcelain'], cwd=APP,
                                capture_output=True, text=True, timeout=120)
    except Exception:
        return []            # no git here; the in-memory restore is still the real guard
    touched = {path for path, _f, _t, _w in MUTATIONS}
    out_list = []
    for line in result.stdout.splitlines():
        name = line[3:].strip().replace('\\', '/')
        if name in touched:
            out_list.append(name)
    return out_list


def main():
    dirty = dirty_files()
    if dirty:
        out.write('These files have uncommitted changes and this script rewrites them:\n')
        for name in dirty:
            out.write('   %s\n' % name)
        out.write('\nCommit or stash first. A crash mid-run must not be able to lose them.\n')
        return 2

    out.write('mutation testing -- %d mutations, suites %s\n'
              % (len(MUTATIONS), ', '.join(SUITES)))
    out.write('=' * 78 + '\n')

    started = time.time()
    baseline, failing = suites_pass()
    out.write('baseline (nothing mutated): %s\n\n'
              % ('all suites pass' if baseline else 'ALREADY FAILING in ' + failing))
    if not baseline:
        out.write('Fix the suites before measuring what they cover.\n')
        return 2

    survived = []
    for at, (path, find, replace, what) in enumerate(MUTATIONS, start=1):
        original = read(path)
        text = original.decode('utf-8')
        if text.count(find) != 1:
            out.write('%2d. SKIPPED  %s\n      the code it patches has moved (%d matches)\n'
                      % (at, what, text.count(find)))
            continue
        try:
            write(path, text.replace(find, replace, 1).encode('utf-8'))
            passed, where = suites_pass()
        finally:
            write(path, original)
        if passed:
            survived.append((what, path))
            out.write('%2d. SURVIVED %s\n      nothing in the suites noticed -- this is a hole\n'
                      % (at, what))
        else:
            out.write('%2d. killed   %s   (%s failed)\n' % (at, what, where))

    out.write('\n' + '=' * 78 + '\n')
    out.write('%d of %d mutations killed, in %.0f minutes\n'
              % (len(MUTATIONS) - len(survived), len(MUTATIONS), (time.time() - started) / 60))
    if survived:
        out.write('\nUNCOVERED BEHAVIOUR -- a test is missing for each of these:\n')
        for what, path in survived:
            out.write('   %-62s %s\n' % (what, path))
    else:
        out.write('\nEvery mutation was caught.\n')
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(main())
