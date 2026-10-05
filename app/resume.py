# -*- coding: utf-8 -*-
"""The résumé the user uploads in Search: accepted only as PDF or Word, read once, kept locally.

The user's rule, in his words: [owner's note: either PDF or Word] and [owner's note: no input format other than these is accepted]. So a file is accepted only when it IS a PDF or a Word document -- judged by what is
inside it, not by its name. A text file renamed "cv.pdf" is refused, and so is a PDF renamed
"cv.docx".

WHAT "WORD" MEANS HERE

.docx, the format Word has saved in since 2007. The older .doc is a different, binary format
that nothing in this app can read; it is refused with a message saying how to save it as
.docx, rather than accepted and then read as an empty résumé.

WHAT HAPPENS TO IT

The file is copied into the app's own data folder, so moving or deleting the original never
breaks a search. Its text is read out once, here, and saved beside it; everything else in
the app reads that text. Claude receives the text -- never the file -- so PDF and Word take
one path, and the résumé can sit in the cached part of each prompt.

A résumé that yields almost no text is refused too. That is what a scanned PDF looks like --
a picture of a page with no letters in it -- and accepting it would mean every listing is
judged against an empty résumé without anyone noticing.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app import doc_text, storage


# Resolved when asked, not when this module is imported: the data folder is storage's to
# decide, and the test harness moves it to a temporary folder -- a path fixed at import time
# would have tests reading, or replacing, the résumé the user really uploaded.
def resume_dir() -> Path:
    return storage.DATA_DIR / 'resume'


def _text_path() -> Path:
    return resume_dir() / 'resume.txt'


def _name_path() -> Path:
    return resume_dir() / 'original_name.txt'

# Reading a PDF or Word file is not a résumé question -- an application entered by hand
# takes its job description the same way -- so that machinery lives in doc_text and this
# module keeps only what is specific to a résumé. Re-exported here because callers, the
# tests included, have always asked resume for them.
ACCEPTED_EXTENSIONS = doc_text.ACCEPTED_EXTENSIONS
MAX_BYTES = doc_text.MAX_BYTES

# What the file picker offers. The user's rule is enforced again on the chosen file, because a
# picker filter is a suggestion -- typing a name into the box gets past it.
FILE_DIALOG_FILTER = 'Résumé (PDF or Word) (*.pdf *.docx)'

# Fewer letters than this is not a résumé that can be judged against -- almost always a
# scanned PDF with no text layer. A one-page CV holds well over a thousand.
MIN_TEXT_CHARS = 200

# An alias, not a new class: every `except resume.ResumeError` in the app and in the tests
# must keep catching exactly what it caught before this moved.
ResumeError = doc_text.DocumentError


def read_resume_file(source) -> tuple:
    """Check a chosen file and read its text, without saving anything.

    Returns (kind, text). Raises ResumeError with a message for the user when the file is not a
    readable PDF or Word résumé.
    """
    path = Path(source)
    size = path.stat().st_size if path.is_file() else 0
    if size > MAX_BYTES:
        raise ResumeError('"%s" is %.0f MB, which is far too large for a résumé.'
                          % (path.name, size / 1024 / 1024))
    kind, text = doc_text.read_document_text(path)
    letters = sum(1 for ch in text if ch.isalnum())
    if letters < MIN_TEXT_CHARS:
        raise ResumeError(
            'Almost no text could be read from "%s" (%d letters). This is usually a scanned '
            'PDF -- a picture of the page. Export the résumé from Word or your CV editor as a '
            'PDF or .docx and choose that file.' % (path.name, letters))
    return kind, text


def save_resume(source) -> dict:
    """Accept a résumé: check it, copy it into the data folder, and save its text.

    Returns {'name', 'kind', 'path', 'text', 'fingerprint'}. Nothing is replaced unless the
    new file is accepted -- a refused file leaves the previous résumé exactly as it was.
    """
    path = Path(source)
    kind, text = read_resume_file(path)
    folder = resume_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('resume.' + kind)
    temp = folder / ('resume.' + kind + '.new')
    shutil.copyfile(path, temp)
    for old in folder.glob('resume.*'):
        if old.suffix.lower() in ACCEPTED_EXTENSIONS and old != target:
            old.unlink()
    temp.replace(target)
    _text_path().write_text(text, encoding='utf-8')
    _name_path().write_text(path.name, encoding='utf-8')
    return {'name': path.name, 'kind': kind, 'path': str(target), 'text': text,
            'fingerprint': fingerprint(text)}


# The text as last read, with the file's size and modification time it was read at. A Filter
# run asks for the résumé once per listing -- it is part of every Claude cache key -- and
# several hundred reads of the same file are pointless while it has not changed.
_READ_CACHE: dict = {}


def load_resume_text() -> str:
    """The saved résumé's text, or '' when none has been uploaded."""
    path = _text_path()
    try:
        stat = path.stat()
    except OSError:
        return ''
    stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    if _READ_CACHE.get('stamp') != stamp:
        try:
            text = path.read_text(encoding='utf-8').strip()
        except OSError:
            return ''
        _READ_CACHE.update(stamp=stamp, text=text)
    return _READ_CACHE['text']


def resume_name() -> str:
    """The name of the file the user chose, for showing in Search. '' when there is none."""
    try:
        return _name_path().read_text(encoding='utf-8').strip() if load_resume_text() else ''
    except OSError:
        return ''


def fingerprint(text) -> str:
    """A short hash of the résumé text. Part of every Claude cache key that reads the
    résumé, so a verdict reached for one résumé is never reused for another."""
    return hashlib.sha256(str(text or '').encode('utf-8')).hexdigest()[:12]


def remove_resume() -> None:
    """Forget the saved résumé."""
    folder = resume_dir()
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    _READ_CACHE.clear()
