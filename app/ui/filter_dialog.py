# -*- coding: utf-8 -*-
"""The Filter window: every choice in one place, and a way to take them all off again.

Sina asked for this directly -- click Filter, see every option there is, press Submit and the
filtering starts; click Filter again and one button clears everything and shows the whole
Bank. And: a Filter already run with exactly these choices must not be run again.

Two things about the design are deliberate.

**Nothing here filters anything.** The dialog collects choices and hands them back; the
caller decides whether they are new. That keeps the expensive, money-spending path out of a
widget and testable on its own -- the same reason the search phases were pulled out of
run_search.

**The buttons say what will happen, not what they are.** "Filter" and "Clear" are what a
control is; "Filter 5,442 listings" and "Show all 5,442" are what pressing it does, and the
counts come from the real pool so the window cannot promise something the Bank cannot give.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFormLayout,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QRadioButton, QScrollArea, QSlider,
                               QVBoxLayout, QWidget)

from app import pipeline
from app.pipeline import geo

# The levels, in the order the wizard offers them, with what each one means to Sina rather
# than its internal key -- "Junior" alone never said whether a thesis counted.
LEVEL_LABELS = [
    ('any', 'Any — jobs, internships and theses; Seniority and Type are columns'),
    ('thesis', 'Thesis — a final-year or master thesis placement'),
    ('internship', 'Internship — Praktikum, stage, working student'),
]

DATE_LABELS = [
    ('anyTime', 'Any time'),
    ('pastMonth', 'Posted in the last month'),
    ('pastWeek', 'Posted in the last week'),
    ('past24Hours', 'Posted in the last 24 hours'),
]

CATEGORY_LABELS = ['Full-Time', 'Part-Time', 'Internship', 'Thesis', 'PhD', 'Contract']

SPONSORSHIP_LABELS = [
    ('', 'Any'),
    ('Yes', 'Only employers known to sponsor a visa'),
    ("Employer's Discretion", "Employer's discretion"),
]


class FilterDialog(QDialog):
    """Collects every filter choice. `chosen` is what the caller acts on.

    Ends in one of three states, and the caller must handle all three:
        Accepted  + cleared=False -> filter with `chosen`
        Accepted  + cleared=True  -> take every filter off and show the whole pool
        Rejected                  -> the window was closed; change nothing
    """

    def __init__(self, settings: dict, pool_size: int, last_run: str = '', parent=None,
                 field_counts=None):
        super().__init__(parent)
        self.setWindowTitle('Filter')
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)
        self.chosen: dict = {}
        self.cleared = False
        self._settings = settings or {}
        # The job titles this search actually asked for: the one Sina typed, then each other
        # name for the same work, as [(title, similarity)]. It comes from what was SEARCHED --
        # title_equivalents' cached answer -- and not from reading the pool.
        #
        # An earlier draft counted how many listings each title had found, which meant
        # scanning every row to open this window. Sina stopped it: "نباید بره تمام آگهی هارو
        # بخونه بگه این Title های کاری هست ها / فقط همون هایی که Search شده اند رو باید بهم
        # نشون بده". He is choosing among what was asked for, which is a list already known.
        self._searched_titles = list(field_counts or [])

        outer = QVBoxLayout(self)

        head = QLabel('Choose what to keep. %s listing%s in the Bank.'
                      % ('{:,}'.format(pool_size), '' if pool_size == 1 else 's'))
        head.setStyleSheet('font-size: 15px; font-weight: 600;')
        outer.addWidget(head)

        if last_run:
            # What the last Filter was run with, so pressing Submit unchanged is visibly a
            # no-op rather than a gamble on whether it will cost anything.
            was = QLabel('Last run: %s' % last_run)
            was.setWordWrap(True)
            was.setStyleSheet('color: #6b7280;')
            outer.addWidget(was)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setSpacing(14)

        form.addWidget(self._field_box())
        form.addWidget(self._which_fields_box())
        form.addWidget(self._level_box())
        form.addWidget(self._work_mode_box())
        # Thesis and Internship are never remote-only: the Remote radio is greyed and Not Remote
        # is chosen, exactly as in the Search window.
        self.level_group.buttonClicked.connect(lambda _b: self._lock_remote_for_type())
        self._lock_remote_for_type()
        form.addWidget(self._where_box())
        form.addWidget(self._when_box())
        form.addWidget(self._resume_box())
        form.addWidget(self._match_box())
        form.addWidget(self._kind_box())
        form.addWidget(self._claude_box())
        form.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        outer.addLayout(self._buttons(pool_size))

    # ---------------------------------------------------------------- the choices ----

    def _field_box(self) -> QWidget:
        box = QGroupBox('Job title')
        lay = QFormLayout(box)
        self.title_input = QLineEdit(str(self._settings.get('search_title') or ''))
        self.title_input.setPlaceholderText('Data Science')
        lay.addRow('Field', self.title_input)
        note = QLabel('The rules judge every listing against this title. '
                      'Changing it re-runs everything.')
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        note.setWordWrap(True)
        lay.addRow('', note)
        return box

    def _which_fields_box(self) -> QWidget:
        """Which job titles in the pool are worth reading -- the one choice that saves money.

        Sina asked for it here rather than in the table: "قبل از Filter ... بگه در اون Search
        کلی ای که انجام شد این Field ها جستجو شد / به صورت Dropdown بگه میخوای کدوم Field ها
        نمایش داده بشه و بقیه حذف بشن".

        The difference from the table's own column filters is the whole point of having both.
        Unticking a title HERE removes those listings before Claude reads anything -- 512
        listings for "AI Engineer" on his own pool, which is real money. Unticking it in the
        table only hides them, after the reading is paid for. So this window is where he
        decides what to spend on, and the table is where he decides what to look at.

        The percentage beside each one is how close that title is to the one he typed, which
        is what the search already recorded; the typed title itself is 100%.
        """
        box = QGroupBox('Which job titles to read')
        lay = QVBoxLayout(box)

        if not self._searched_titles:
            note = QLabel('Only the title above was searched for, so every listing in the '
                          'pool will be read. Other names for the same work appear here once '
                          'a search has asked for them.')
            note.setStyleSheet('color: #6b7280; font-size: 12px;')
            note.setWordWrap(True)
            lay.addWidget(note)
            self.field_boxes: dict = {}
            return box

        note = QLabel('These are the job titles this search asked for. Anything unticked is '
                      'removed before Claude reads it — this is where the cost of a run is '
                      'decided. Nothing ticked means all of them.')
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        note.setWordWrap(True)
        lay.addWidget(note)

        # Previously chosen fields, or nothing -- and nothing means all, so a first run reads
        # everything rather than silently narrowing to whatever happened to be ticked.
        chosen = {str(f) for f in (self._settings.get('fields') or [])}
        self.field_boxes = {}
        for name, similarity in self._searched_titles:
            tick = QCheckBox('%s   —   %d%% the same work' % (name, similarity))
            tick.setChecked(name in chosen)
            self.field_boxes[name] = tick
            lay.addWidget(tick)

        buttons = QHBoxLayout()
        all_btn = QPushButton('All')
        all_btn.clicked.connect(lambda: self._set_all_fields(True))
        buttons.addWidget(all_btn)
        none_btn = QPushButton('Only the title I searched')
        none_btn.setToolTip('Untick every other name for the job.')
        none_btn.clicked.connect(self._only_searched_field)
        buttons.addWidget(none_btn)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        return box

    def _set_all_fields(self, on: bool) -> None:
        for tick in getattr(self, 'field_boxes', {}).values():
            tick.setChecked(on)

    def _only_searched_field(self) -> None:
        """Tick only the title in the box above -- the cheapest useful run."""
        typed = pipeline.clean_title(self.title_input.text()).lower()
        for name, tick in getattr(self, 'field_boxes', {}).items():
            tick.setChecked(name.lower() == typed)

    def _level_box(self) -> QWidget:
        """The Level -- which no longer removes anything.

        It used to drive `profile.is_wrong_level`, which deleted every listing whose level
        did not match. It now picks only the word lists the Work Location rule reads, so it
        is still a real choice; the seniority of each listing is reported in the Seniority
        column and narrowed there, in the table, where changing his mind is free.
        """
        box = QGroupBox('Type')
        lay = QVBoxLayout(box)
        self.level_group = QButtonGroup(self)
        current = pipeline.clean_search_type(self._settings.get('search_level'))
        for key, label in LEVEL_LABELS:
            button = QRadioButton(label)
            button.setProperty('level_key', key)
            if key == current:
                button.setChecked(True)
            self.level_group.addButton(button)
            lay.addWidget(button)
        if not self.level_group.checkedButton():
            self.level_group.buttons()[0].setChecked(True)
        return box

    def _lock_remote_for_type(self) -> None:
        """Remote unclickable for Thesis and Internship -- Sina's rule, the same as in Search."""
        level = self.level_group.checkedButton()
        locked = bool(level) and level.property('level_key') in ('thesis', 'internship')
        for button in self.mode_group.buttons():
            if button.property('mode_key') == 'remote':
                button.setEnabled(not locked)
                button.setToolTip('Not available for Thesis and Internship' if locked else '')
            elif locked:
                button.setChecked(True)   # Any

    def _work_mode_box(self) -> QWidget:
        box = QGroupBox('Where the work happens')
        lay = QVBoxLayout(box)
        self.mode_group = QButtonGroup(self)
        current = pipeline.clean_work_mode(self._settings.get('search_work_mode'))
        current = 'remote' if current == 'remote' else 'any'   # a saved Not Remote opens as Any
        for key, label in (('remote', 'Remote — the posting says it can be done away '
                                      'from an office'),
                           ('any', 'Any — remote, hybrid, on-site, everything')):
            button = QRadioButton(label)
            button.setProperty('mode_key', key)
            if key == current:
                button.setChecked(True)
            self.mode_group.addButton(button)
            lay.addWidget(button)
        if not self.mode_group.checkedButton():
            self.mode_group.buttons()[0].setChecked(True)
        return box

    def _where_box(self) -> QWidget:
        box = QGroupBox('Where')
        lay = QVBoxLayout(box)
        note = QLabel('Leave everything unticked to keep listings from anywhere.')
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        lay.addWidget(note)

        chosen_countries = {str(c) for c in (self._settings.get('countries') or [])}
        chosen_cities = {str(c) for c in (self._settings.get('cities') or [])}

        grid = QGridLayout()
        self.country_boxes = {}
        for i, country in enumerate(geo.COUNTRIES):
            tick = QCheckBox(country)
            tick.setChecked(country in chosen_countries)
            self.country_boxes[country] = tick
            grid.addWidget(tick, i // 3, i % 3)
        lay.addLayout(grid)

        cities = QGridLayout()
        self.city_boxes = {}
        for i, city in enumerate(geo.CITIES):
            tick = QCheckBox(city)
            tick.setChecked(city in chosen_cities)
            self.city_boxes[city] = tick
            cities.addWidget(tick, i // 4, i % 4)
        lay.addWidget(QLabel('Cities'))
        lay.addLayout(cities)
        return box

    def _when_box(self) -> QWidget:
        box = QGroupBox('When it was posted')
        lay = QVBoxLayout(box)
        self.date_input = QComboBox()
        for key, label in DATE_LABELS:
            self.date_input.addItem(label, key)
        current = str(self._settings.get('date_range') or 'anyTime')
        index = self.date_input.findData(current)
        self.date_input.setCurrentIndex(index if index >= 0 else 0)
        lay.addWidget(self.date_input)
        note = QLabel('A listing that gives no date is always kept — not knowing when '
                      'something was posted is not evidence that it is old.')
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        note.setWordWrap(True)
        lay.addWidget(note)
        return box

    def _resume_box(self) -> QWidget:
        """Choose the résumé, here rather than in the Search wizard.

        It moved because this is where it is used. The search does not read the résumé at
        all -- it collects postings. The Filter is what sends them to Claude to be scored
        against it, so choosing the résumé beside the match slider is choosing it at the
        moment it matters, and a wrong one is noticed before a run is paid for instead of
        after. Sina found this out the hard way: he uploaded someone else's résumé, from a
        different field entirely, and the low match scores were the first he heard of it.

        Changing the résumé changes the run's signature -- filter_signature hashes its
        fingerprint -- so a new résumé always re-filters, and never silently reuses verdicts
        scored against the old one.
        """
        from app import resume

        box = QGroupBox('Résumé')
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self.resume_label = QLabel()
        self.resume_label.setWordWrap(True)
        choose = QPushButton('Choose résumé…')
        choose.clicked.connect(self._choose_resume)
        self.resume_preview_button = QPushButton('Preview')
        self.resume_preview_button.setToolTip(
            'Show the text Claude will read from your résumé.')
        self.resume_preview_button.clicked.connect(self._preview_resume)
        row.addWidget(self.resume_label, 1)
        row.addWidget(choose)
        row.addWidget(self.resume_preview_button)
        lay.addLayout(row)
        note = QLabel('PDF or Word (.docx) only. Claude reads every fact about you from it. '
                      'Changing it re-scores everything.')
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        note.setWordWrap(True)
        lay.addWidget(note)
        self._resume_name = resume.resume_name()
        self._show_resume_state()
        return box

    def _show_resume_state(self):
        self.resume_label.setText(self._resume_name or 'No résumé chosen yet')
        self.resume_preview_button.setEnabled(bool(self._resume_name))

    def _choose_resume(self):
        """Pick a résumé. Checked by what is inside the file, not by its name -- anything
        that is not a readable PDF or Word document is refused with the reason, and the
        résumé already saved stays as it was."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        from app import resume

        path, _filter = QFileDialog.getOpenFileName(
            self, 'Choose your résumé', '', resume.FILE_DIALOG_FILTER)
        if not path:
            return
        try:
            info = resume.save_resume(path)
        except resume.ResumeError as exc:
            QMessageBox.warning(self, 'Résumé not accepted', str(exc))
            return
        except Exception as exc:                                      # noqa: BLE001
            QMessageBox.warning(self, 'Résumé not accepted',
                                'The file could not be read: %s' % exc)
            return
        self._resume_name = info['name']
        self._show_resume_state()
        self._preview_resume()

    def _preview_resume(self):
        """The text Claude will actually read -- so a résumé that came out garbled, or one
        belonging to somebody else, is seen before a Filter run pays to score against it."""
        from PySide6.QtWidgets import QDialogButtonBox, QPlainTextEdit

        from app import resume

        dialog = QDialog(self)
        dialog.setWindowTitle('Résumé — what Claude will read')
        dialog.resize(640, 640)
        lay = QVBoxLayout(dialog)
        viewer = QPlainTextEdit(resume.load_resume_text() or 'No résumé has been saved.')
        viewer.setReadOnly(True)
        lay.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        lay.addWidget(buttons)
        dialog.exec()

    def _match_box(self) -> QWidget:
        box = QGroupBox('Résumé match')
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self.match_slider = QSlider(Qt.Horizontal)
        self.match_slider.setRange(0, 95)
        self.match_slider.setSingleStep(5)
        self.match_slider.setPageStep(5)
        self.match_slider.setValue(int(self._settings.get('min_match_percent') or 0))
        self.match_value = QLabel()
        self.match_value.setMinimumWidth(96)
        self.match_slider.valueChanged.connect(self._show_match)
        row.addWidget(self.match_slider, 1)
        row.addWidget(self.match_value)
        lay.addLayout(row)
        self._show_match(self.match_slider.value())
        note = QLabel('Claude scores each survivor against the résumé you uploaded. '
                      'Anything below this is flagged, never deleted outright.')
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        note.setWordWrap(True)
        lay.addWidget(note)
        return box

    def _show_match(self, value: int):
        self.match_value.setText('no minimum' if value <= 0 else '%d%% and above' % value)

    def _kind_box(self) -> QWidget:
        box = QGroupBox('Visa')
        lay = QVBoxLayout(box)
        # THE TYPE TICK BOXES USED TO BE HERE AND THEY DELETED.
        #
        # Six of them -- Full-Time, Part-Time, Internship, Thesis, PhD, Contract -- and
        # `filter_by_category` removed everything unticked. Measured on the real
        # Netherlands run: ticking Part-Time removed 295 of the 321 listings that had
        # survived every other rule, because 295 of them were full-time. He was left with
        # four, and no way to see what had gone without re-running the whole Filter.
        #
        # The Type column in the Jobs table has had its own Excel-style filter button for
        # a while, so the choice already existed in the one place where making it is free.
        # `self.category_boxes` is kept as an empty dict so _build_result_settings reads
        # the same shape it always did and an older settings.json still loads.
        # Empty, and typed so mypy can see what it is: the Type tick boxes that used to
        # fill it are gone (see the note above), but _build_result_settings still reads
        # the same shape so an older settings.json loads unchanged.
        self.category_boxes: dict[str, QCheckBox] = {}
        note = QLabel('The kind of role — Full-Time, Part-Time, Internship, Thesis, PhD, '
                      'Contract — is no longer filtered here. Every kind comes through and '
                      'is labelled in the Type column; pick the ones you want there, next '
                      'to Seniority.')
        note.setWordWrap(True)
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        lay.addWidget(note)

        self.sponsorship_input = QComboBox()
        for key, label in SPONSORSHIP_LABELS:
            self.sponsorship_input.addItem(label, key)
        index = self.sponsorship_input.findData(
            str(self._settings.get('sponsorship') or ''))
        self.sponsorship_input.setCurrentIndex(index if index >= 0 else 0)
        lay.addWidget(QLabel('Sponsorship'))
        lay.addWidget(self.sponsorship_input)
        return box

    def _claude_box(self) -> QWidget:
        box = QGroupBox('Claude')
        lay = QVBoxLayout(box)
        self.claude_tick = QCheckBox('Read every survivor with Claude '
                                     '(the slow, accurate pass)')
        self.claude_tick.setChecked(bool(self._settings.get('use_claude', True)))
        lay.addWidget(self.claude_tick)
        note = QLabel('Unticked, only the keyword rules run: instant and free, but nothing '
                      'is read for meaning and there is no résumé match.')
        note.setStyleSheet('color: #6b7280; font-size: 12px;')
        note.setWordWrap(True)
        lay.addWidget(note)
        return box

    # ---------------------------------------------------------------- the buttons ----

    def _buttons(self, pool_size: int) -> QHBoxLayout:
        row = QHBoxLayout()
        self.clear_button = QPushButton('Show all %s — no filters'
                                        % '{:,}'.format(pool_size))
        self.clear_button.clicked.connect(self._on_clear)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.submit_button = QPushButton('Filter %s listing%s'
                                         % ('{:,}'.format(pool_size),
                                            '' if pool_size == 1 else 's'))
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self._on_submit)
        row.addWidget(self.submit_button)
        return row

    def _on_clear(self):
        self.cleared = True
        self.chosen = {}
        self.accept()

    def _on_submit(self):
        # Claude reads every fact about Sina from the résumé, so ticking Claude with no
        # résumé means part two -- the whole match score -- silently does nothing. This is
        # the check the Search wizard used to make; it belongs here, where the résumé is
        # chosen and where the run that needs it is about to start.
        if self.claude_tick.isChecked() and not self._resume_name:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 'Résumé needed',
                'Claude reads every fact about you from your résumé, and scores each '
                'listing against it. Choose your résumé (PDF or Word) first, or untick '
                'Claude to run the keyword rules only.')
            return
        self.cleared = False
        self.chosen = self.selections()
        self.accept()

    def selections(self) -> dict:
        """Everything the window is currently showing, in settings shape."""
        level = self.level_group.checkedButton()
        mode = self.mode_group.checkedButton()
        return {
            'search_title': self.title_input.text().strip(),
            'search_level': level.property('level_key') if level else 'any',
            'search_work_mode': mode.property('mode_key') if mode else 'remote',
            'countries': [name for name, tick in self.country_boxes.items()
                          if tick.isChecked()],
            'cities': [name for name, tick in self.city_boxes.items() if tick.isChecked()],
            'date_range': self.date_input.currentData(),
            'min_match_percent': int(self.match_slider.value()),
            'categories': [name for name, tick in self.category_boxes.items()
                           if tick.isChecked()],
            'sponsorship': self.sponsorship_input.currentData(),
            # Which of the searched job titles to read. Empty means all of them -- the same
            # rule as every other choice in this window, and the one that makes a first run
            # complete rather than silently narrow.
            'fields': [name for name, tick in getattr(self, 'field_boxes', {}).items()
                       if tick.isChecked()],
            'use_claude': bool(self.claude_tick.isChecked()),
        }
