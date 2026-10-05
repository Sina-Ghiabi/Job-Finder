"""Local JSON persistence for settings and job applications, no server involved."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path


def _resolve_data_dir() -> Path:
    """Frozen (.exe) builds must not store data next to a temp/unpacked path --
    use a stable per-user folder instead. In dev, keep it next to the repo."""
    if getattr(sys, 'frozen', False):
        base = os.environ.get('APPDATA') or str(Path.home())
        return Path(base) / 'JobDesk'
    return Path(__file__).resolve().parent.parent / 'data'


DATA_DIR = _resolve_data_dir()
DOCUMENTS_DIR = DATA_DIR / 'documents'
SETTINGS_PATH = DATA_DIR / 'settings.json'
APPLICATIONS_PATH = DATA_DIR / 'applications.json'
JOBS_PATH = DATA_DIR / 'jobs.json'
# The Bank: everything a search brought back, before any filtering. jobs.json holds what the
# last Filter kept, which is why it cannot also be the pool -- the first Filter would eat it,
# and trying another Level or Remote / Not Remote would mean paying Apify for the same
# listings twice. The Bank is written once per search and only ever read after that, so a
# Filter can be re-run against the full pool as many times as Sina likes, for free.
BANK_PATH = DATA_DIR / 'bank.json'

STATUS_CHOICES = ['Processing', 'Accept', 'Reject']
STATUS_COLORS = {
    'Processing': '#F5A623',  # yellow/orange
    'Accept': '#2ECC71',      # green
    'Reject': '#E74C3C',      # red
}


# Anything that went wrong reading a file, waiting for the UI to collect it.
#
# These loaders are deliberately forgiving -- a corrupt or half-synced file returns empty
# rather than crashing the app, which is right. What was missing is that it also said
# nothing: jobs.json is not a cache, it is what a paid search produced, and a file that
# silently reads as empty looks exactly like "no results" from the outside. This is a
# plain list rather than a callback because storage is imported by everything and takes no
# progress_cb; the UI drains it and logs each entry in red.
_LOAD_PROBLEMS: list[str] = []


def _record_load_problem(message: str) -> None:
    if message not in _LOAD_PROBLEMS:
        _LOAD_PROBLEMS.append(message)


def take_load_problems() -> list[str]:
    """Everything that failed to load since the last call, and clears the list."""
    problems = list(_LOAD_PROBLEMS)
    _LOAD_PROBLEMS.clear()
    return problems


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    _ensure_dirs()
    if not SETTINGS_PATH.exists():
        return {}
    try:
        loaded = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        _record_load_problem(
            'settings.json could not be read (%s) — Job Finder is starting with no saved '
            'settings, so API keys and your last search setup are missing. The file is at '
            '%s.' % (e, SETTINGS_PATH))
        return {}
    # Catching JSONDecodeError alone is not enough: a file can be perfectly valid JSON
    # and still be the wrong SHAPE -- `null`, `"hello"`, or a list -- and each of those
    # used to be returned as-is, so every caller doing settings.get(...) crashed. This
    # is not hypothetical: the app's folder lives in OneDrive, and a sync conflict or a
    # half-finished write produces exactly these files.
    if not isinstance(loaded, dict):
        _record_load_problem(
            'settings.json is valid JSON but the wrong shape (%s, expected an object) — '
            'Job Finder is starting with no saved settings, so API keys and your last search '
            'setup are missing. A OneDrive sync conflict or a half-finished write produces '
            'exactly this. The file is at %s.'
            % (type(loaded).__name__, SETTINGS_PATH))
        return {}
    return loaded


def save_settings(settings: dict) -> None:
    _write_json(SETTINGS_PATH, settings)


# ---------------------------------------------------------------------------------------
# Surviving a crash mid-search
# ---------------------------------------------------------------------------------------
#
# A three-hour German search died with a segmentation fault part-way through fetching the
# postings it had just found. Three hours of work and $6.40 of Apify credit, and **every
# listing collected went with it** -- because run_search holds everything in memory and
# writes nothing until it returns.
#
# A crash inside a C library cannot be caught by anything in Python, so there is no way to
# handle it; the only defence is to have written the rows down already. This is that: after
# each stage, whatever has been collected so far goes to disk. If the process dies, the next
# start finds the file and says so, and the work is still there.
#
# Deliberately a separate file from jobs.json rather than writing into it. A half-finished
# search is not a result -- it has not been deduplicated, dated or filtered -- and silently
# merging it into the real list would make a crashed run indistinguishable from a good one.
SEARCH_CHECKPOINT_PATH = DATA_DIR / 'search_checkpoint.json'

# What the last Filter was asked for, and what it answered. Sina's rule for the Filter
# window: the same choices must show the previous answer instead of paying for it again, and
# any change must redo the work.
#
# Its own file rather than a corner of jobs.json, for the same reason the Bank is its own
# file: this is bookkeeping about a result, not the result. A damaged or missing one has to
# mean "filter again", which is merely slow, and never "here is an answer" -- so every reader
# below treats anything it cannot parse as absent.
FILTER_STATE_PATH = DATA_DIR / 'filter_state.json'


def save_search_checkpoint(stage: str, rows: list) -> None:
    """Write down what a running search has collected so far. Never raises.

    Called between stages, so a failure to write must not be able to stop the search it is
    protecting -- the checkpoint is insurance, and insurance that can cost you the thing it
    insures is worse than none.
    """
    try:
        _write_json(SEARCH_CHECKPOINT_PATH, {
            'stage': str(stage),
            'saved_at': datetime.now().isoformat(timespec='seconds'),
            'count': len(rows),
            'rows': rows,
        })
    except Exception:                                           # noqa: BLE001
        pass


def load_search_checkpoint() -> dict | None:
    """A crashed search's listings, or None when the last search finished properly."""
    if not SEARCH_CHECKPOINT_PATH.exists():
        return None
    try:
        with open(SEARCH_CHECKPOINT_PATH, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except Exception as exc:                                    # noqa: BLE001
        _record_load_problem('A checkpoint from an interrupted search could not be read '
                             '(%s), so its listings are lost.' % exc)
        return None
    return data if isinstance(data, dict) and data.get('rows') else None


def clear_search_checkpoint() -> None:
    """Drop the checkpoint. Called when a search finishes, which is what makes its presence
    at startup mean "the last one did not"."""
    try:
        SEARCH_CHECKPOINT_PATH.unlink()
    except Exception:                                           # noqa: BLE001
        pass


_LEGACY_STATUS_MAP = {'Accepted': 'Accept', 'Rejected': 'Reject'}


def load_applications() -> list[dict]:
    _ensure_dirs()
    if not APPLICATIONS_PATH.exists():
        return []
    try:
        applications = json.loads(APPLICATIONS_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        _record_load_problem(
            'applications.json could not be read (%s) — the Applications page will look '
            'empty even though the file still exists at %s. Do not apply to anything until '
            'this is sorted, or the file will be overwritten.' % (e, APPLICATIONS_PATH))
        return []
    # Same shape check as load_jobs. Without it the migration loop below calls
    # record.get() on whatever parsed, so a file containing `null`, a string, or a list
    # of numbers raised straight out of here and took the Applications page with it.
    if not isinstance(applications, list):
        _record_load_problem(
            'applications.json is valid JSON but the wrong shape (%s, expected a list) — '
            'the Applications page will look empty. The file is at %s.'
            % (type(applications).__name__, APPLICATIONS_PATH))
        return []
    applications = [record for record in applications if isinstance(record, dict)]

    migrated = False
    for record in applications:
        old_status = record.get('status')
        if old_status in _LEGACY_STATUS_MAP:
            record['status'] = _LEGACY_STATUS_MAP[old_status]
            migrated = True
    if migrated:
        save_applications(applications)

    return applications


def save_applications(applications: list[dict]) -> None:
    _write_json(APPLICATIONS_PATH, applications)


def add_application(job: dict, document_paths: list[str], apply_date: str = '') -> dict:
    """Copies the chosen documents into data/documents/<application_id>/ and records the application.

    `apply_date` is for applications entered by hand: Sina applies to things outside Job Finder
    -- "شاید مثلا من برای یک کار در LinkedIn اقدام کردم و میخواستم به کار هام اضافه کنم" --
    and those were applied to on some earlier day, not today. Left empty it means today,
    which is what every application made through the app itself wants. Format is dd/mm/yyyy,
    the same one `_parse_apply_date` on the Applications page reads.

    A hand-entered application is otherwise an ordinary record built from an ordinary job
    dict, and goes through this same function deliberately: one record shape means the
    status menu, the documents folder, the Remove button and the Excel export all work on it
    without knowing where it came from.
    """
    _ensure_dirs()
    app_id = str(uuid.uuid4())
    app_folder = DOCUMENTS_DIR / app_id
    app_folder.mkdir(parents=True, exist_ok=True)

    stored_documents = []
    for src in document_paths:
        src_path = Path(src)
        if not src_path.exists():
            continue
        dest_path = app_folder / src_path.name
        shutil.copy2(src_path, dest_path)
        stored_documents.append(str(dest_path))

    record = {
        'id': app_id,
        'title': job.get('title'),
        'company': job.get('company'),
        'country': job.get('country'),
        'location': job.get('location'),
        'platform': job.get('platform'),
        'category': job.get('Category'),
        # Beside category, and for the same reason: both are columns Sina filters on
        # rather than values the Filter deleted by. A record is a curated dict, so a
        # new field has to be listed here or it is silently dropped.
        'seniority': job.get('Seniority'),
        'sponsorship_visa': job.get('sponsorship_visa'),
        # Application records are a curated dict, not a copy of the job --
        # a new field has to be listed here or it is silently dropped.
        'apply_verdict': job.get('apply_verdict'),
        'apply_note': job.get('apply_note'),
        # What the résumé match said when this was applied to: the score, and the two
        # sentences behind it. Worth keeping with the application -- months later, "why did
        # I think this one fitted?" is exactly what a record is for.
        'claude_match': job.get('claude_match'),
        'resume_strengths': job.get('resume_strengths'),
        'resume_gaps': job.get('resume_gaps'),
        'search_title': job.get('_search_title'),
        'search_level': job.get('_search_level'),
        'url': job.get('url'),
        'description': job.get('description'),
        'documents': stored_documents,
        'status': 'Processing',
        'apply_date': str(apply_date or '').strip() or datetime.now().strftime('%d/%m/%Y'),
        # Which applications Sina typed in himself. Recorded because it explains why a row
        # has no Match %, no verdict and no description: nothing read this listing, there
        # was no listing to read.
        'added_by_hand': bool(job.get('added_by_hand')),
    }

    applications = load_applications()
    applications.append(record)
    save_applications(applications)
    return record


def update_application_status(app_id: str, status: str) -> None:
    applications = load_applications()
    for record in applications:
        if record['id'] == app_id:
            record['status'] = status
            break
    save_applications(applications)


def delete_application(app_id: str) -> list[dict]:
    """Removes the application record and its copied documents folder."""
    applications = [a for a in load_applications() if a.get('id') != app_id]
    save_applications(applications)

    app_folder = DOCUMENTS_DIR / app_id
    if app_folder.is_dir():
        shutil.rmtree(app_folder, ignore_errors=True)

    return applications


def sanitize_filename(name: str | None) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name or '').strip()
    return name or 'Company'


def default_zip_name(record: dict) -> str:
    return f"{sanitize_filename(record.get('company'))}_Documents.zip"


def build_documents_zip(record: dict, target_path: str) -> str:
    """Writes a zip to target_path containing the job description as a .txt file plus
    every document attached to this application, all nested inside a folder named after
    the zip itself -- so extracting it produces one tidy folder, not scattered files."""
    folder_name = Path(target_path).stem
    with zipfile.ZipFile(target_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f'{folder_name}/Job Description.txt', record.get('description') or '')
        for doc_path in record.get('documents') or []:
            path = Path(doc_path)
            if path.exists():
                zf.write(path, arcname=f'{folder_name}/{path.name}')
    return target_path


def load_jobs() -> list[dict]:
    _ensure_dirs()
    if not JOBS_PATH.exists():
        return []
    try:
        loaded = json.loads(JOBS_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        _record_load_problem(
            'jobs.json could not be read (%s) — every saved listing is missing from this '
            'session. This file is what your paid searches produced, not a cache: it is at '
            '%s, and a copy should be taken before running another search, which would '
            'overwrite it.' % (e, JOBS_PATH))
        return []
    # Shape check, not just a parse check -- see load_settings for why. jobs.json matters
    # more than the others: a search costs real Apify credit, so this file is not a cache,
    # it is the thing that was paid for. Individual non-dict entries are dropped rather
    # than failing the whole file, so one bad row cannot cost every good one.
    if not isinstance(loaded, list):
        _record_load_problem(
            'jobs.json is valid JSON but the wrong shape (%s, expected a list) — every '
            'saved listing is missing from this session. Take a copy of %s before running '
            'another search, which would overwrite it.'
            % (type(loaded).__name__, JOBS_PATH))
        return []
    jobs = [job for job in loaded if isinstance(job, dict)]
    if len(jobs) != len(loaded):
        _record_load_problem(
            '%d entry(ies) in jobs.json were not listings and had to be dropped — the file '
            'at %s is partly damaged.' % (len(loaded) - len(jobs), JOBS_PATH))
    return jobs


def _json_safe(value):
    """Fallback for values `json` doesn't know how to encode at all (dates, Decimals,
    numpy scalars). Deliberately does NOT try to handle NaN/Infinity: `json.dumps` only
    consults `default=` for types it does not recognise, and `float` IS recognised -- so
    this is never called for a NaN no matter what it contains. An earlier version of this
    function claimed to map NaN to None here, which could not work for exactly that
    reason. Non-finite floats are handled by _json_sanitize below instead, where they
    actually can be."""
    return str(value)


def _json_sanitize(value):
    """Recursively replaces every non-finite float (NaN, inf, -inf) with None.

    Real bug this fixes: pandas fills a missing key with NaN, Python's json module writes
    it as a bare `NaN` literal, and that is not valid JSON -- it reads back fine here, so
    the app never noticed, while every other reader (jq, JSON.parse, an editor's
    validator) rejects the file. The previous guard only walked the TOP level of each
    record, so a NaN nested inside a list or dict still raised `ValueError` straight out
    of the save -- turning a bad-file problem into a crash in a function every save path
    calls (Filter, Apply, Remove, Clear). It also missed `inf` entirely, since the test
    used was `v != v`, which is False for infinity."""
    if isinstance(value, float):
        # NaN != itself; inf/-inf are finite-checked separately. math.isfinite covers all
        # three in one test and is correct for int/float alike.
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_sanitize(v) for v in value]
    return value


def _write_json(path: Path, payload) -> None:
    """The one place any of this app's JSON files get written.

    Every saver goes through here so the NaN rule is stated once instead of per-file --
    a real gap otherwise: an earlier round hardened save_jobs alone, leaving
    save_applications still writing bare NaN literals into applications.json even though
    add_application copies its fields straight off a job dict (which is exactly where a
    pandas NaN comes from). allow_nan=False is kept as a backstop: after _json_sanitize
    it should never fire, and if it ever does that's a real bug worth surfacing rather
    than silently writing a broken file."""
    _ensure_dirs()
    text = json.dumps(
        _json_sanitize(payload), indent=2, ensure_ascii=False, default=_json_safe, allow_nan=False,
    )
    path.write_text(text, encoding='utf-8')


def save_jobs(jobs: list[dict]) -> None:
    _write_json(JOBS_PATH, jobs)


def save_bank(jobs: list[dict]) -> None:
    """Stores the unfiltered pool a search produced, with the date it was searched."""
    _write_json(BANK_PATH, {'saved_at': datetime.now().isoformat(timespec='seconds'),
                            'rows': jobs})


def add_to_bank(new_jobs: list[dict]) -> int:
    """Puts a search's listings into the Bank, above what is already there. Returns the total.

    Keyed by URL so re-searching the same city does not bank the same posting twice, and the
    newest copy of a posting wins -- it is the one whose description was just read.
    """
    existing, _saved_at = load_bank()
    seen, pool = set(), []
    for job in list(new_jobs) + existing:
        key = str(job.get('url') or job.get('id') or '')
        if key and key in seen:
            continue
        seen.add(key)
        pool.append(job)
    save_bank(pool)
    return len(pool)


def clear_bank() -> None:
    _write_json(BANK_PATH, {'saved_at': datetime.now().isoformat(timespec='seconds'),
                            'rows': []})


def save_filter_state(signature: str, choices: dict, described: str, kept: int) -> None:
    """Remember that this exact Filter was run, and what it kept.

    The survivors themselves are already in jobs.json -- writing them twice would be a second
    copy to keep in step, and the first one to go stale would be the one nobody looked at.
    This records only what is needed to decide whether that file still answers the question
    being asked.
    """
    _write_json(FILTER_STATE_PATH, {
        'signature': str(signature or ''),
        'choices': dict(choices or {}),
        'described': str(described or ''),
        'kept': int(kept or 0),
        'saved_at': datetime.now().isoformat(timespec='seconds'),
    })


def load_filter_state() -> dict:
    """What the last Filter was run with, or {} when that cannot be established.

    Deliberately silent about its own failures, unlike load_jobs and load_bank: those hold
    something a search paid for, and a reader who gets an empty answer needs to know why.
    This holds a shortcut. Losing it costs one re-filter and nothing else, so a damaged file
    simply means the shortcut is unavailable.
    """
    _ensure_dirs()
    if not FILTER_STATE_PATH.exists():
        return {}
    try:
        loaded = json.loads(FILTER_STATE_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}
    # Valid JSON of the wrong shape is a real case here -- the data folder lives in OneDrive,
    # where a sync conflict writes whatever it likes. See load_settings for the same guard.
    if not isinstance(loaded, dict) or not loaded.get('signature'):
        return {}
    return loaded


def clear_filter_state() -> None:
    """Forget the shortcut. Called when the filters are taken off, and after a new search."""
    try:
        if FILTER_STATE_PATH.exists():
            FILTER_STATE_PATH.unlink()
    except OSError:
        pass


def load_bank() -> tuple[list[dict], str]:
    """The pool and when it was searched. Empty when no search has run since the Bank existed.

    Forgiving in the same way as load_jobs, and for a stronger reason: this file is the only
    copy of what a paid search returned. A damaged row is dropped, never the whole pool.
    """
    _ensure_dirs()
    if not BANK_PATH.exists():
        return [], ''
    try:
        loaded = json.loads(BANK_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        _record_load_problem(
            'bank.json could not be read (%s) — the Filter will fall back to the listings '
            'showing now, which are already filtered. The Bank is at %s.' % (e, BANK_PATH))
        return [], ''
    if not isinstance(loaded, dict) or not isinstance(loaded.get('rows'), list):
        _record_load_problem(
            'bank.json is valid JSON but the wrong shape — the Filter will fall back to the '
            'listings showing now. The Bank is at %s.' % BANK_PATH)
        return [], ''
    rows = [job for job in loaded['rows'] if isinstance(job, dict)]
    if len(rows) != len(loaded['rows']):
        _record_load_problem(
            '%d entry(ies) in bank.json were not listings and had to be dropped — the file '
            'at %s is partly damaged.' % (len(loaded['rows']) - len(rows), BANK_PATH))
    return rows, str(loaded.get('saved_at') or '')


def prepend_jobs(new_jobs: list[dict]) -> list[dict]:
    """Adds newly-found listings above whatever was already saved, giving each a stable id."""
    for job in new_jobs:
        job['id'] = str(uuid.uuid4())
    merged = new_jobs + load_jobs()
    save_jobs(merged)
    return merged


def delete_job(job_id: str) -> list[dict]:
    jobs = [j for j in load_jobs() if j.get('id') != job_id]
    save_jobs(jobs)
    return jobs


def clear_jobs() -> None:
    save_jobs([])


def clear_applications() -> None:
    """Deletes every logged application and all of their copied documents."""
    save_applications([])
    if DOCUMENTS_DIR.is_dir():
        shutil.rmtree(DOCUMENTS_DIR, ignore_errors=True)
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def export_excels(chosen_path: str) -> tuple[str, str]:
    """chosen_path is whatever the user picked in a Save-As dialog (e.g. .../MyExport.xlsx).
    Writes '<name>_Jobs.xlsx' and '<name>_Applications.xlsx' next to it, both styled
    (colored header, zebra rows, colored Type/Status badges, clickable links). Returns
    their paths."""
    from app import excel_export

    chosen = Path(chosen_path)
    target_dir = chosen.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = chosen.stem or 'JobFinder_Export'

    jobs_path = target_dir / f'{prefix}_Jobs.xlsx'
    excel_export.build_jobs_workbook(load_jobs()).save(jobs_path)

    apps_path = target_dir / f'{prefix}_Applications.xlsx'
    excel_export.build_applications_workbook(load_applications()).save(apps_path)

    return str(jobs_path), str(apps_path)
