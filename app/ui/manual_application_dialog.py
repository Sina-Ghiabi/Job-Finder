# -*- coding: utf-8 -*-
"""Add an application Sina made outside RoleHound, filling in by hand what Apply fills in
automatically.

His words: "میخوام در بخش ای که کار های Apply شده رو قرار می دهیم میخوام که بشه به صورت دستی
هم وارد کرد / شاید مثلا من برای یک کار در LinkedIn اقدام کردم و میخواستم به کار هام اضافه
کنم". RoleHound finds jobs and he applies to them from the Jobs page -- but he also applies to
things it never found, straight on LinkedIn or a company's own site, and those belonged in
the same list. A record of what he has applied to is only useful if it is ALL of it.

EVERY FIELD APPLY CARRIES, AND NOTHING ELSE

Then: "ببین چه اطلاعاتی موقعی که دکمه ی Apply میزنیم به صفحه ی add_application انتقال داده
میشه / در حالت دستی برای تمامی بخش ها یک Input یا یک انتخاب File بزن". So this window is
built from `storage.add_application`'s record, field by field, and the FIELDS constant below
is the list -- one input for every value the automatic path passes, in the four groups they
naturally fall into:

    The job          title, company, country, city, link, found on, type
    The application  applied on, sponsorship, documents, job description
    What Claude said match %, verdict, note, strengths, gaps
    The search       search title, level

The last two groups exist because they are on the record. A row applied to through the app
carries Claude's reasoning and the search that found it, and months later "why did I think
this one fitted?" is exactly what the record is for. Entered by hand they are simply empty
unless Sina has something to put there -- and they are grouped and labelled as what they
are, so the window does not look like it is asking him to guess at Claude's own numbers.

A test holds this to it: a field added to `add_application` and not to FIELDS fails the
suite, because a record shape defined in two places drifts the first time one is changed --
which this project has already been bitten by, in that function's own curated dict.

THE JOB DESCRIPTION IS A PDF

"برای JobDescription به صورت PDF بگیر". The description is the one field nobody types: it is
pages long, and he already has it as a file. So it is chosen as a PDF (or Word) and its text
is read out on the spot, by the same reader the résumé uses, and shown back to him -- an
unreadable or scanned file is refused there and then, with the reason, rather than saved as
an empty description he discovers months later. Typing instead is allowed; the box is
editable, and a file simply fills it in.

WHY THIS BUILDS A JOB DICT INSTEAD OF AN APPLICATION RECORD

It hands `storage.add_application` an ordinary job-shaped dict, exactly as the Jobs page
does, rather than writing a record itself. One record shape, one code path: the status menu,
the documents folder, Remove, and the Excel export all work on a hand-entered row without
knowing it is one.

WHAT IS REQUIRED

Only the job title. The point is to capture an application Sina has ALREADY made, and
refusing it over a missing company name would make the feature useless at the moment it is
used -- on his recollection of a job he applied to last Tuesday. Fields left empty stay
empty in the table, exactly as they do for a listing a source never filled in.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app import doc_text
from app.pipeline import geo

# Every key this window fills in on the job dict it hands to add_application. Compared
# against that function in the tests, so a field added there and forgotten here is caught.
FIELDS = (
    'title', 'company', 'country', 'location', 'url', 'platform', 'Category',
    'Seniority',
    'sponsorship_visa', 'description', 'claude_match', 'apply_verdict', 'apply_note',
    'resume_strengths', 'resume_gaps', '_search_title', '_search_level',
)

# The same set the Jobs page shows in its Type column, so a hand-entered row is labelled the
# way every other row is.
CATEGORY_CHOICES = ['Full-Time', 'Part-Time', 'Internship', 'Thesis', 'PhD', 'Contract']

# The same six the Seniority column shows, in the same order -- Intern first, Unspecified
# last, because 'Unspecified' is the honest answer for a job he typed in from memory and
# it is what the column prints for a posting that never said.
SENIORITY_CHOICES = ['Unspecified', 'Intern', 'Junior', 'Mid', 'Senior', 'Lead']

# Matching the Sponsorship Visa column's own vocabulary rather than inventing a third one.
SPONSORSHIP_CHOICES = ['Unknown', 'Yes', "Employer's Discretion", 'No']

# What Claude's first pass answers with, plus the empty default for a row he never saw.
VERDICT_CHOICES = ['', 'Worth applying to', 'Not worth applying to']

# The Levels, as the Search wizard and the Filter window name them.
LEVEL_CHOICES = ['', 'thesis', 'internship', 'entry', 'junior', 'mid', 'senior']

_HINT = 'color: #6b7280; font-size: 12px;'


class ManualApplicationDialog(QDialog):
    """Collects one hand-entered application. `job` and `documents` are what the caller saves.

    Accepted means `job` is filled in and worth saving; Rejected means nothing happened.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add an application by hand')
        self.setMinimumWidth(620)
        self.setMinimumHeight(640)
        self.job: dict = {}
        self.documents: list[str] = []
        self._chosen_documents: list[str] = []
        self._description_source = ''

        outer = QVBoxLayout(self)

        head = QLabel('For a job you applied to somewhere else — on LinkedIn, or a '
                      'company’s own site. Only the job title is needed.')
        head.setWordWrap(True)
        head.setStyleSheet('font-size: 14px; font-weight: 600;')
        outer.addWidget(head)

        # Scrolled, because this is every field an application has and the window must still
        # open on a laptop screen without its buttons falling off the bottom.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setSpacing(14)
        form.addWidget(self._job_box())
        form.addWidget(self._application_box())
        form.addWidget(self._description_box())
        form.addWidget(self._claude_box())
        form.addWidget(self._search_box())
        form.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Add to my applications')
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------ the fields ----

    def _job_box(self) -> QWidget:
        box = QGroupBox('The job')
        lay = QFormLayout(box)
        lay.setSpacing(10)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText('Data Scientist')
        lay.addRow('Job title *', self.title_input)

        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText('e.g. Adyen')
        lay.addRow('Company', self.company_input)

        # Editable, because he applies to places this app does not search. The list is there
        # to save typing and keep the spelling consistent with every other row -- the country
        # is what the Filter and the export group by -- not to limit him to it.
        self.country_input = QComboBox()
        self.country_input.setEditable(True)
        self.country_input.addItem('')
        for name in geo.COUNTRIES:
            self.country_input.addItem(name)
        lay.addRow('Country', self.country_input)

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText('e.g. Amsterdam')
        lay.addRow('City', self.location_input)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('https://www.linkedin.com/jobs/view/…')
        lay.addRow('Link', self.url_input)
        note = QLabel('Clicking the row in the table opens this.')
        note.setStyleSheet(_HINT)
        lay.addRow('', note)

        self.platform_input = QLineEdit()
        self.platform_input.setPlaceholderText('e.g. LinkedIn')
        lay.addRow('Found on', self.platform_input)

        self.seniority_input = QComboBox()
        for label in SENIORITY_CHOICES:
            self.seniority_input.addItem(label)
        lay.addRow('Seniority', self.seniority_input)

        self.category_input = QComboBox()
        for label in CATEGORY_CHOICES:
            self.category_input.addItem(label)
        lay.addRow('Type', self.category_input)
        return box

    def _application_box(self) -> QWidget:
        box = QGroupBox('The application')
        lay = QFormLayout(box)
        lay.setSpacing(10)

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat('dd/MM/yyyy')
        self.date_input.setDate(QDate.currentDate())
        # An application cannot have been made tomorrow, and a mistyped year is the easiest
        # mistake there is to make in a date field.
        self.date_input.setMaximumDate(QDate.currentDate())
        lay.addRow('Applied on', self.date_input)
        note = QLabel('Defaults to today. An application entered by hand usually is not.')
        note.setStyleSheet(_HINT)
        lay.addRow('', note)

        self.sponsorship_input = QComboBox()
        for label in SPONSORSHIP_CHOICES:
            self.sponsorship_input.addItem(label)
        lay.addRow('Sponsorship Visa', self.sponsorship_input)

        # Copied into the application's own folder by add_application, the same as for an
        # application made through the app, so "Download" works on this row too.
        docs_row = QHBoxLayout()
        attach = QPushButton('Attach files…')
        attach.clicked.connect(self._choose_documents)
        docs_row.addWidget(attach)
        self.clear_docs_button = QPushButton('Remove all')
        self.clear_docs_button.clicked.connect(self._clear_documents)
        docs_row.addWidget(self.clear_docs_button)
        docs_row.addStretch(1)
        lay.addRow('Documents', docs_row)

        self.documents_list = QListWidget()
        self.documents_list.setFixedHeight(76)
        lay.addRow('', self.documents_list)
        self._show_documents()
        note = QLabel('The CV and cover letter you sent. Any file type; they are copied '
                      'into this application’s own folder.')
        note.setStyleSheet(_HINT)
        note.setWordWrap(True)
        lay.addRow('', note)
        return box

    def _description_box(self) -> QWidget:
        box = QGroupBox('Job description')
        lay = QVBoxLayout(box)

        row = QHBoxLayout()
        pick = QPushButton('Choose a PDF…')
        pick.clicked.connect(self._choose_description)
        row.addWidget(pick)
        self.description_source_label = QLabel('Nothing chosen — you can type it instead.')
        self.description_source_label.setStyleSheet(_HINT)
        self.description_source_label.setWordWrap(True)
        row.addWidget(self.description_source_label, 1)
        lay.addLayout(row)

        self.description_input = QPlainTextEdit()
        self.description_input.setPlaceholderText(
            'Choose a PDF above and its text appears here, or paste the advert yourself.')
        self.description_input.setFixedHeight(140)
        lay.addWidget(self.description_input)

        note = QLabel('PDF or Word (.docx). The text is read out of the file and kept with '
                      'the application — the file itself is not.')
        note.setStyleSheet(_HINT)
        note.setWordWrap(True)
        lay.addWidget(note)
        return box

    def _claude_box(self) -> QWidget:
        box = QGroupBox('What Claude said — leave empty unless you know')
        lay = QFormLayout(box)
        lay.setSpacing(10)

        note = QLabel('An application made through RoleHound carries these. One entered by '
                      'hand has no verdict unless you give it one, and empty is the honest '
                      'answer — nothing read this listing.')
        note.setStyleSheet(_HINT)
        note.setWordWrap(True)
        lay.addRow('', note)

        # -1 means "no score", which is not the same as 0%. A spin box cannot be left blank,
        # so its minimum is the empty value and is shown as such.
        self.match_input = QSpinBox()
        self.match_input.setRange(-1, 100)
        self.match_input.setValue(-1)
        self.match_input.setSpecialValueText('not scored')
        self.match_input.setSuffix('%')
        lay.addRow('Match', self.match_input)

        self.verdict_input = QComboBox()
        for label in VERDICT_CHOICES:
            self.verdict_input.addItem(label or '(none)', label)
        lay.addRow('Verdict', self.verdict_input)

        self.apply_note_input = QLineEdit()
        self.apply_note_input.setPlaceholderText('Why it was or was not worth applying to.')
        lay.addRow('Reason', self.apply_note_input)

        self.strengths_input = QPlainTextEdit()
        self.strengths_input.setPlaceholderText('What fits.')
        self.strengths_input.setFixedHeight(56)
        lay.addRow('Strengths', self.strengths_input)

        self.gaps_input = QPlainTextEdit()
        self.gaps_input.setPlaceholderText('What does not.')
        self.gaps_input.setFixedHeight(56)
        lay.addRow('Gaps', self.gaps_input)
        return box

    def _search_box(self) -> QWidget:
        box = QGroupBox('The search it came from — optional')
        lay = QFormLayout(box)
        lay.setSpacing(10)

        self.search_title_input = QLineEdit()
        self.search_title_input.setPlaceholderText('e.g. Data Science')
        lay.addRow('Searched as', self.search_title_input)

        self.search_level_input = QComboBox()
        for key in LEVEL_CHOICES:
            self.search_level_input.addItem(key.title() if key else '(none)', key)
        lay.addRow('Level', self.search_level_input)

        note = QLabel('Recorded on every application RoleHound makes, so the Excel export can '
                      'group by it. Fill it in if this job belongs with one of your searches.')
        note.setStyleSheet(_HINT)
        note.setWordWrap(True)
        lay.addRow('', note)
        return box

    # ------------------------------------------------------------------- documents ----

    def _choose_documents(self):
        paths, _filter = QFileDialog.getOpenFileNames(
            self, 'Attach the documents you sent', '', 'All files (*.*)')
        for path in paths:
            if path not in self._chosen_documents:
                self._chosen_documents.append(path)
        self._show_documents()

    def _clear_documents(self):
        self._chosen_documents = []
        self._show_documents()

    def _show_documents(self):
        self.documents_list.clear()
        for path in self._chosen_documents:
            self.documents_list.addItem(Path(path).name)
        if not self._chosen_documents:
            self.documents_list.addItem('No documents attached.')
        self.clear_docs_button.setEnabled(bool(self._chosen_documents))

    # ----------------------------------------------------------------- description ----

    def _choose_description(self):
        """Read the advert's text out of a PDF, and refuse a file that cannot give it up.

        Refusing here, with the reason, is the whole point: a scanned PDF is a picture of a
        page and yields nothing, and saving that silently would leave an application whose
        description is empty for a reason discovered months later.
        """
        path, _filter = QFileDialog.getOpenFileName(
            self, 'Choose the job description',
            '', 'Job description (PDF or Word) (*.pdf *.docx)')
        if not path:
            return
        try:
            _kind, text = doc_text.read_document_text(path)
        except doc_text.DocumentError as exc:
            QMessageBox.warning(self, 'That file could not be read', str(exc))
            return
        except Exception as exc:                                       # noqa: BLE001
            QMessageBox.warning(self, 'That file could not be read',
                                'The file could not be read: %s' % exc)
            return
        if not text.strip():
            QMessageBox.warning(
                self, 'Nothing could be read from that file',
                'No text came out of "%s". This is usually a scanned PDF — a picture of '
                'the page rather than words. Paste the description in instead.'
                % Path(path).name)
            return
        self.description_input.setPlainText(text)
        self._description_source = path
        self.description_source_label.setText(
            'Read from %s — %s characters.' % (Path(path).name, '{:,}'.format(len(text))))

    # ---------------------------------------------------------------------- saving ----

    def _on_accept(self):
        if not ' '.join(self.title_input.text().split()):
            QMessageBox.warning(self, 'Job title needed',
                                'An application needs at least the job title, so the row '
                                'says what it was for.')
            self.title_input.setFocus()
            return
        self.job = self.entered()
        self.documents = list(self._chosen_documents)
        self.accept()

    def entered(self) -> dict:
        """The application as a job dict, in the shape add_application expects.

        `Category` is capitalised and the search keys carry their leading underscore because
        those are the names add_application reads -- `job.get('Category')`,
        `job.get('_search_title')`. Spelling either of them the natural way would leave the
        column empty with nothing on screen to say why.
        """
        match = self.match_input.value()
        return {
            'title': ' '.join(self.title_input.text().split()),
            'company': self.company_input.text().strip(),
            'country': self.country_input.currentText().strip(),
            'location': self.location_input.text().strip(),
            'url': self.url_input.text().strip(),
            # Never blank: a row that says nothing about where it came from is the one row
            # in the table with no answer to "where did this come from".
            'platform': self.platform_input.text().strip() or 'Added by hand',
            'Category': self.category_input.currentText(),
            # Capitalised, like 'Category': add_application reads job.get('Seniority')
            # and renames it to 'seniority' on the record.
            'Seniority': self.seniority_input.currentText(),
            'sponsorship_visa': self.sponsorship_input.currentText(),
            'description': self.description_input.toPlainText().strip(),
            # None rather than -1: an absent score must read as absent everywhere that
            # renders it, and -1% would be printed.
            'claude_match': match if match >= 0 else None,
            'apply_verdict': self.verdict_input.currentData() or '',
            'apply_note': self.apply_note_input.text().strip(),
            'resume_strengths': self.strengths_input.toPlainText().strip(),
            'resume_gaps': self.gaps_input.toPlainText().strip(),
            '_search_title': self.search_title_input.text().strip(),
            '_search_level': self.search_level_input.currentData() or '',
            'added_by_hand': True,
        }

    def apply_date(self) -> str:
        """dd/mm/yyyy, the format the Applications page reads."""
        chosen = self.date_input.date()
        return date(chosen.year(), chosen.month(), chosen.day()).strftime('%d/%m/%Y')
