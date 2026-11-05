"""Offline DCRC wizard. All conversions run through the public core API."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from PySide6 import QtCore, QtGui, QtWidgets as W
from .controller import Task, DEFAULTS, settings_values, load_settings, save_settings
from dcrc.models import STAGES, CHARACTERS


class Window(W.QMainWindow):
    def __init__(self, settings_path=None):
        super().__init__()
        self.setWindowTitle('DCRC Converter')
        self.resize(940, 760)
        self.task = Task()
        self.job = None
        self.closing = False
        self.identity = None
        self.settings_path = Path(settings_path) if settings_path else Path(
            os.environ.get('APPDATA', str(Path.home()/'.config')))/'DCRC Converter'/'gui.json'
        self.saved = load_settings(self.settings_path)
        outer = W.QWidget()
        self.setCentralWidget(outer)
        layout = W.QVBoxLayout(outer)
        heading = W.QLabel('DCRC Converter')
        heading.setStyleSheet('font-size:26px; font-weight:600; margin:8px 0')
        layout.addWidget(heading)
        note = W.QLabel('Your own supported Dreamcast disc → a locally built PSP folder. '
                        'No game data is included. Windows native build; no WSL required.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = W.QTabWidget()
        layout.addWidget(self.tabs)
        self.controls = {}
        self._source_page()
        self._settings_page()
        self._output_page()
        self._progress_page()
        nav = W.QHBoxLayout()
        self.back = W.QPushButton('Back')
        self.next = W.QPushButton('Next')
        self.start = W.QPushButton('Convert / resume')
        self.cancel = W.QPushButton('Cancel job')
        self.cancel.setEnabled(False)
        self.back.clicked.connect(lambda: self.tabs.setCurrentIndex(max(0, self.tabs.currentIndex()-1)))
        self.next.clicked.connect(lambda: self.tabs.setCurrentIndex(min(3, self.tabs.currentIndex()+1)))
        self.start.clicked.connect(self.convert)
        self.cancel.clicked.connect(self.stop)
        for widget in (self.back, self.next, self.start, self.cancel):
            nav.addWidget(widget)
        layout.addLayout(nav)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(75)
        self.statusBar().showMessage('Choose a GDI image and check its supported version.')

    def page(self, title):
        page = W.QWidget()
        form = W.QFormLayout(page)
        form.setFieldGrowthPolicy(W.QFormLayout.AllNonFixedFieldsGrow)
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(W.QFrame.NoFrame)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)
        return form

    def path(self, form, label, key, default='', file=False):
        row = W.QWidget()
        box = W.QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        edit = W.QLineEdit(str(self.saved.get(key, default)))
        button = W.QPushButton('Browse…')
        def choose():
            selected = (W.QFileDialog.getOpenFileName(self, label, edit.text(),
                         'Dreamcast GDI (*.gdi);;All files (*)')[0] if file else
                        W.QFileDialog.getExistingDirectory(self, label, edit.text()))
            if selected:
                edit.setText(selected)
        button.clicked.connect(choose)
        box.addWidget(edit)
        box.addWidget(button)
        form.addRow(label, row)
        self.controls[key] = edit
        return edit

    def combo(self, form, label, key, choices):
        combo = W.QComboBox()
        for text, value in choices:
            combo.addItem(text, value)
        wanted = self.saved.get(key, DEFAULTS.get(key))
        at = combo.findData(wanted)
        combo.setCurrentIndex(max(0, at))
        self.controls[key] = combo
        form.addRow(label, combo)
        return combo

    def spin(self, form, label, key, lo, hi):
        spin = W.QSpinBox()
        spin.setRange(lo, hi)
        value = self.saved.get(key, DEFAULTS[key])
        spin.setValue(value if type(value) is int else DEFAULTS[key])
        self.controls[key] = spin
        form.addRow(label, spin)

    def check(self, form, label, key):
        box = W.QCheckBox()
        box.setChecked(self.saved.get(key, DEFAULTS[key]) is True)
        form.addRow(label, box)
        self.controls[key] = box

    def _source_page(self):
        form = self.page('1 · Disc & version')
        self.path(form, 'Own GDI image', 'source', file=True).textChanged.connect(self.reset_identity)
        self.path(form,'Own DLC folder (optional)','dlc_dir')
        folder = W.QPushButton('Use an extracted folder (advanced)…')
        def pick_folder():
            value = W.QFileDialog.getExistingDirectory(self, 'Extracted disc folder')
            if value:
                self.controls['source'].setText(value)
        folder.clicked.connect(pick_folder)
        form.addRow('', folder)
        self.identify_button = W.QPushButton('Check supported version')
        self.identify_button.clicked.connect(self.identify)
        form.addRow('', self.identify_button)
        self.version = W.QLabel('Not checked. First supported profile: Sonic Adventure US v1.005. '
                                'Other versions and input formats are not supported.')
        self.version.setWordWrap(True)
        form.addRow('Compatibility', self.version)

    def _settings_page(self):
        form = self.page('2 · Graphics & start')
        quality = W.QLabel('Quality changes apply to selected Emerald Coast world assets. '
                          '64/128 reduce texture detail. This TA source profile currently keeps full static distance. '
                          'These choices are not lossless optimizations or hardware speed guarantees.')
        quality.setWordWrap(True)
        form.addRow(quality)
        self.combo(form, 'EC world textures (PSP preset initially selected)', 'world_textures',
                   [('Original', 0), ('Maximum 128', 128), ('Maximum 64', 64)])
        self.spin(form, 'Static distance (TA profile)', 'land_distance', 100, 100)
        preset = W.QPushButton('PSP preset: EC world64 / full distance100')
        def apply_preset():
            self.controls['world_textures'].setCurrentIndex(self.controls['world_textures'].findData(64))
            self.controls['land_distance'].setValue(100)
        preset.clicked.connect(apply_preset)
        form.addRow('', preset)
        original = W.QPushButton('Original preset: original textures / full distance100')
        def apply_original():
            self.controls['world_textures'].setCurrentIndex(self.controls['world_textures'].findData(0))
            self.controls['land_distance'].setValue(100)
        original.clicked.connect(apply_original)
        form.addRow('', original)
        self.combo(form, 'Aspect ratio', 'aspect', [('Wide', 'wide'), ('4:3', '4:3')])
        self.combo(form, 'Frame skip', 'frame_skip', [('Automatic', 'auto'), ('Off', 'off')] +
                   [(str(i), str(i)) for i in range(2, 61)])
        self.spin(form, 'Mip levels', 'mip_levels', 1, 8)
        self.check(form, 'FPS display', 'show_fps')
        self.check(form, 'Audio', 'audio')
        self.combo(form, 'Voice language', 'voice', [('Game default', 'game'), ('English', 'en'), ('Japanese', 'ja')])
        self.combo(form, 'Startup', 'startup_stage', [('Normal game boot', 'normal')] +
                   [(s.replace('_', ' ').title(), s) for s in STAGES if s != 'normal'])
        self.combo(form, 'Character (warp only)', 'startup_character',
                   [(s.title(), s) for s in CHARACTERS])
        self.spin(form, 'Act (warp only, 1-based)', 'startup_act', 1, 8)
        self.controls['startup_stage'].currentIndexChanged.connect(self._warp_state)
        self._warp_state()
        warp_note = W.QLabel('Advanced warp overrides normal startup. Stage/act/character combinations '
                             'do not all represent a normal playable route.')
        warp_note.setWordWrap(True)
        form.addRow(warp_note)

    def _warp_state(self):
        enabled = self.controls['startup_stage'].currentData() != 'normal'
        self.controls['startup_character'].setEnabled(enabled)
        self.controls['startup_act'].setEnabled(enabled)

    def _output_page(self):
        form = self.page('3 · Output folder')
        default = Path.home()/'Documents'/'DCRC Output'/'DCRC_SA1_US1005'
        self.path(form, 'Exact PSP game folder', 'output', str(default))
        self.path(form, 'Work folder (optional)', 'work')
        self.path(form, 'Native toolchain (optional)', 'toolchain')
        title = W.QLineEdit(self.saved.get('title', DEFAULTS['title']))
        self.controls['title'] = title
        form.addRow('PSP menu title', title)
        self.spin(form, 'Compiler jobs', 'jobs', 1, 64)
        note = W.QLabel('The output is the game folder itself. A foreign nonempty folder is rejected. '
                        'Work stays outside it. Resume uses validated content receipts. '
                        'Conversion writes locally and does not deploy to a memory card.')
        note.setWordWrap(True)
        form.addRow(note)
        self.verify_button = W.QPushButton('Verify existing output')
        self.verify_button.clicked.connect(self.verify)
        form.addRow('', self.verify_button)
        self.configure_button = W.QPushButton('Apply runtime settings to existing output')
        self.configure_button.clicked.connect(self.configure)
        form.addRow('', self.configure_button)
        open_button = W.QPushButton('Open output folder')
        open_button.clicked.connect(self.open_output)
        form.addRow('', open_button)

    def _progress_page(self):
        form = self.page('4 · Progress & log')
        self.stage = W.QLabel('Idle — no conversion has started.')
        self.stage.setWordWrap(True)
        self.bar = W.QProgressBar()
        self.bar.setRange(0, 100)
        self.log = W.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)
        form.addRow(self.stage)
        form.addRow(self.bar)
        form.addRow(self.log)
        self.log_path = W.QLabel('Diagnostics remain in the work folder after cancellation or failure.')
        self.log_path.setWordWrap(True)
        form.addRow(self.log_path)
        buttons = W.QWidget()
        row = W.QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        work = W.QPushButton('Open work / diagnostics')
        work.clicked.connect(self.open_work)
        save = W.QPushButton('Save visible log…')
        save.clicked.connect(self.save_log)
        row.addWidget(work)
        row.addWidget(save)
        form.addRow(buttons)

    def values(self):
        result = {}
        for key, widget in self.controls.items():
            if isinstance(widget, W.QComboBox): result[key] = widget.currentData()
            elif isinstance(widget, W.QSpinBox): result[key] = widget.value()
            elif isinstance(widget, W.QCheckBox): result[key] = widget.isChecked()
            else: result[key] = widget.text().strip()
        return result

    def reset_identity(self):
        self.identity = None
        if hasattr(self, 'version'):
            self.version.setText('Not checked. Check the supported version before converting.')

    def begin(self, name, operation):
        if self.task.running:
            return
        self.job = name
        self.stage.setText(name + '…')
        self.bar.setRange(0, 0)
        self.tabs.setCurrentIndex(3)
        self.task.start(operation)
        self._busy(True)

    def _busy(self, busy):
        for i in range(3): self.tabs.setTabEnabled(i, not busy)
        for b in (self.start, self.back, self.next, self.identify_button, self.verify_button,
                  self.configure_button): b.setEnabled(not busy)
        self.cancel.setEnabled(busy)

    def identify(self):
        source = self.controls['source'].text().strip()
        if not source:
            self.show_error('Choose your own GDI image or extracted folder first.')
            return
        def operation(event, cancel):
            from dcrc.pipeline import identify
            return identify(Path(source), event=event, cancel_event=cancel)
        self.begin('Check version', operation)

    def convert(self):
        try:
            values = self.values()
            typed = settings_values(values)
            if not values['source'] or not values['output']:
                raise ValueError('Input and exact output folder are required.')
            if not self.identity or self.identity.get('ok') is not True:
                raise ValueError('Check a supported disc version first.')
            from dcrc.models import ConversionOptions
            from dcrc.pipeline import convert
            options = ConversionOptions(source=Path(values['source']), output=Path(values['output']),
                work=Path(values['work']) if values['work'] else None,
                toolchain=Path(values['toolchain']) if values['toolchain'] else None,
                dlc_dir=Path(values['dlc_dir']) if values.get('dlc_dir') else None,
                profile=self.identity.get('profile', 'sa1_us_1005'), **typed)
            self.persist(values)
            self.begin('Convert', lambda event, cancel: convert(options, event=event, cancel_event=cancel))
        except Exception as error:
            self.show_error(str(error))

    def verify(self):
        name = self.controls['output'].text().strip()
        if not name:
            self.show_error('Choose the existing output folder first.')
            return
        folder = Path(name)
        def operation(event, cancel):
            from dcrc.pipeline import verify_folder
            return verify_folder(folder)
        self.begin('Verify output', operation)

    def configure(self):
        try:
            from dcrc.pipeline import configure_folder
            values = self.values()
            if not values['output']:
                raise ValueError('Choose the existing output folder first.')
            options = settings_values(values)
            for key in ('world_textures', 'title', 'jobs'): options.pop(key)
            self.persist(values)
            self.begin('Apply runtime settings', lambda event, cancel:
                       configure_folder(Path(values['output']), **options))
        except ImportError:
            self.show_error('This core does not yet support changing an existing folder. Reconvert to apply settings.')
        except Exception as error:
            self.show_error(str(error))

    def persist(self, values):
        try:
            save_settings(self.settings_path, values)
        except OSError as error:
            self.log.appendPlainText('Settings could not be saved: ' + str(error))

    def stop(self):
        self.task.cancel()
        self.cancel.setEnabled(False)
        self.stage.setText('Cancelling — waiting for owned processes and cleanup…')

    def poll(self):
        for event in self.task.drain():
            kind = event.get('type', 'log')
            message = str(event.get('message', ''))
            if kind in ('finished', 'cancelled', 'error'):
                self.bar.setRange(0, 100)
                if kind == 'finished':
                    result = event.get('result')
                    ok = not isinstance(result, dict) or result.get('ok', True) is True
                    if self.job == 'Check version':
                        self.identity = result
                        summary = {key: result[key] for key in ('ok', 'message', 'title', 'profile',
                                   'region', 'version', 'boot', 'code', 'hint') if key in result}
                        self.version.setText(json.dumps(summary, ensure_ascii=False, indent=2))
                    text = ('Complete' if ok else 'Not supported / verification failed')
                    self.stage.setText(text)
                    self.bar.setValue(100 if ok else 0)
                    if hasattr(result, 'folder'):
                        self.log.appendPlainText('Output: ' + str(result.folder))
                        self.log_path.setText('Work: ' + str(result.work) + '\nManifest: ' + str(result.manifest))
                    else:
                        shown = summary if self.job == 'Check version' else result
                        self.log.appendPlainText(json.dumps(shown, ensure_ascii=False, indent=2, default=str))
                else:
                    self.stage.setText('Cancelled — partial output is not ready.' if kind == 'cancelled' else 'Failed: ' + message)
                    self.log.appendPlainText(event.get('detail', message))
            else:
                if message: self.log.appendPlainText(message)
                if event.get('stage'): self.stage.setText(str(event['stage']))
                value = event.get('progress')
                if isinstance(value, (int, float)):
                    self.bar.setRange(0, 100)
                    self.bar.setValue(max(0, min(100, round(value*100 if 0 <= value <= 1 else value))))
        if not self.task.running:
            self._busy(False)
            if self.closing:
                self.close()

    def open_output(self):
        name = self.controls['output'].text().strip()
        path = Path(name)
        if name and path.is_dir():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path.resolve())))
        else:
            self.show_error('Output folder does not exist yet.')

    def open_work(self):
        values = self.values()
        path = Path(values['work']) if values['work'] else Path(values['output']).parent/'.dcrc-work'
        if path.is_dir():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path.resolve())))
        else:
            self.show_error('Work folder does not exist yet.')

    def save_log(self):
        name = W.QFileDialog.getSaveFileName(self, 'Save visible converter log', 'dcrc-log.txt',
                                            'Text (*.txt)')[0]
        if name:
            try:
                Path(name).write_text(self.log.toPlainText()+'\n', encoding='utf8')
            except OSError as error:
                self.show_error(str(error))

    def show_error(self, message):
        self.stage.setText(message)
        self.log.appendPlainText(message)
        self.tabs.setCurrentIndex(3)

    def closeEvent(self, event):
        if self.task.running:
            self.closing = True
            self.stop()
            event.ignore()
            return
        self.persist(self.values())
        event.accept()


def main():
    application = W.QApplication(sys.argv)
    application.setApplicationName('DCRC Converter')
    application.setOrganizationName('DCRC')
    window = Window()
    window.show()
    return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
