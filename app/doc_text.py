# -*- coding: utf-8 -*-
"""Read the text out of a PDF or Word file, and refuse anything else.

This was the résumé module's private machinery until a second caller appeared: an
application entered by hand takes its job description as a PDF, the way the user asked for it
([owner's note: get the job description as a PDF]). Two copies of "how do you get the words out of a
PDF" would have drifted the first time one of them was fixed -- this project has already
been bitten by exactly that with Rule 5, which lived in ten files and was changed in one.
So the machinery moved here and `resume` now imports it.

WHAT IS CHECKED, AND WHY IT IS CHECKED THIS WAY

A file is accepted only when it IS a PDF or a Word document -- judged by what is inside it,
not by its name. A text file renamed "jd.pdf" is refused, and so is a PDF renamed ".docx".
That rule is the user's, first given for the résumé ([owner's note: no input format other than these is accepted]), and it holds here for the same reason: the words are what get read, and a file that
cannot give up its words is better refused at the moment it is chosen than accepted and
found empty later.

Every refusal is a sentence the user can act on -- which file, what is wrong with it, and what
to do -- never a traceback and never a silent empty string.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

# The two accepted kinds, by extension. The extension alone is never trusted: see kind_of.
ACCEPTED_EXTENSIONS = ('.pdf', '.docx')

# Far larger than any document of this sort; a guard against picking the wrong file
# entirely -- a video, a disk image -- not a limit on real documents.
MAX_BYTES = 20 * 1024 * 1024


class DocumentError(ValueError):
    """Why a file was refused, in words the user can act on."""


def kind_of(path: Path, head: bytes) -> str:
    """'pdf' or 'docx', from the file's own contents. Raises DocumentError for anything else.

    A PDF begins with "%PDF-" (a few bytes of junk before it are allowed by the format, so
    the first kilobyte is searched). A .docx is a ZIP archive holding word/document.xml --
    being a ZIP is not enough, since .xlsx and .pptx are ZIPs too.
    """
    extension = path.suffix.lower()
    if extension == '.doc':
        raise DocumentError(
            'This is an old Word file (.doc), which cannot be read. Open it in Word and use '
            '"Save As" -> "Word Document (.docx)", or save it as PDF, then choose that file.')
    if extension not in ACCEPTED_EXTENSIONS:
        raise DocumentError(
            'Only PDF or Word (.docx) files are accepted. "%s" is neither.' % path.name)

    if b'%PDF-' in head[:1024]:
        kind = 'pdf'
    elif head.startswith(b'PK\x03\x04'):
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            names = set()
        if 'word/document.xml' not in names:
            raise DocumentError(
                '"%s" is not a Word document inside, even though its name ends in .docx.'
                % path.name)
        kind = 'docx'
    else:
        raise DocumentError(
            '"%s" is not really a %s file inside. Only PDF or Word (.docx) files are accepted.'
            % (path.name, 'PDF' if extension == '.pdf' else 'Word'))

    if '.' + kind != extension:
        raise DocumentError(
            '"%s" is named %s but is a %s file inside. Rename it to end in .%s and choose it '
            'again.' % (path.name, extension, kind.upper() if kind == 'pdf' else 'Word', kind))
    return kind


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Many PDFs are "encrypted" with an empty password purely to stop editing.
            try:
                reader.decrypt('')
            except Exception:
                pass
        return '\n'.join((page.extract_text() or '') for page in reader.pages)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError('The PDF could not be read (%s). Try saving it again as PDF.'
                            % str(exc)[:120])


def docx_text(data: bytes) -> str:
    import docx
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError('The Word file could not be read (%s). Try saving it again as '
                            '.docx.' % str(exc)[:120])
    lines = [paragraph.text for paragraph in document.paragraphs]
    # Many templates lay out the whole page in a table; its text is not in the paragraphs
    # above at all. Found on real résumés, and job descriptions are exported the same way.
    for table in document.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                text = cell.text.strip()
                if text and text not in cells:
                    cells.append(text)
            if cells:
                lines.append(' | '.join(cells))
    return '\n'.join(lines)


def tidy(text: str) -> str:
    """Spacing tidied line by line, blank runs collapsed -- the words themselves untouched."""
    out: list = []
    for line in str(text or '').replace('\r', '\n').split('\n'):
        line = ' '.join(line.split())
        if line or (out and out[-1]):
            out.append(line)
    return '\n'.join(out).strip()


def read_document_text(source) -> tuple:
    """Check a chosen file and read its text, without saving anything. Returns (kind, text).

    Raises DocumentError with a message for the user when the file is not a readable PDF or Word
    document. Callers that need more -- a minimum length, a particular use -- add their own
    check on top; this one answers only "can these words be read".
    """
    path = Path(source)
    if not path.is_file():
        raise DocumentError('The file "%s" does not exist.' % path)
    size = path.stat().st_size
    if size == 0:
        raise DocumentError('"%s" is empty.' % path.name)
    if size > MAX_BYTES:
        raise DocumentError('"%s" is %.0f MB, which is far too large.'
                            % (path.name, size / 1024 / 1024))
    data = path.read_bytes()
    kind = kind_of(path, data[:4096])
    return kind, tidy(pdf_text(data) if kind == 'pdf' else docx_text(data))
