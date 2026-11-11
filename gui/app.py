"""Offline DCRC wizard. All conversions run through the public core API."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import sys
import uuid
from dataclasses import replace

from .i18n import catalog
from .theme import apply_theme
from .art_preview import Preview, file_image

from PySide6 import QtCore, QtGui, QtWidgets as W
from .controller import Task, DEFAULTS, settings_values, load_settings, save_settings
from .session_log import start_app_log
from dcrc.models import STAGES, CHARACTERS
from dcrc.capabilities import PROFILE_CAPABILITIES


class Window(W.QMainWindow):
    def __init__(self, settings_path=None, session_log=None):
        super().__init__()
        self.setWindowTitle('DCRC Converter')
        self.setWindowIcon(QtGui.QIcon(str(Path(__file__).parent / 'assets' / 'dcrc.ico')))
        self.resize(1200, 760)
        self.setMinimumSize(860, 560)
        self.job = None
        self.job_dialog = None
        self.pending_picker = None
        self.pending_audio = False
        self.pending_border = False
        self.closing = False
        self.identity = None
        self.identity_source = None
        self.check_source = None
        self.convert_after_check = None
        self.start_after_check = False
        self.auto_check_due = False
        self.auto_check_timer = QtCore.QTimer(self)
        self.auto_check_timer.setSingleShot(True)
        self.auto_check_timer.setInterval(500)
        self.auto_check_timer.timeout.connect(self.auto_identify)
        self.settings_path = Path(settings_path) if settings_path else Path(
            os.environ.get('APPDATA', str(Path.home()/'.config')))/'DCRC Converter'/'gui.json'
        self.session_log = session_log or start_app_log(settings_path)
        self.task = Task(self.session_log)
        self.saved = load_settings(self.settings_path)
        # Migrating preferences never enables capabilities absent from this runtime.
        self.saved['land_distance']=100
        if self.saved.get('border_mode','none') not in ('none','custom'):self.saved.update(border_mode='none',border_image='')
        if not PROFILE_CAPABILITIES['movie_playback']:self.saved['movies']=False
        if not PROFILE_CAPABILITIES['custom_border']:self.saved.update(border_mode='none',border_image='')
        if not PROFILE_CAPABILITIES['configurable_dither']:self.saved['dither']='on'
        self.media = None
        self.dlc_catalog = None
        self._translations = []
        self.language_choice = self.saved.get("language", "system")
        self.theme_choice = self.saved.get("theme", "dark")
        outer = W.QWidget()
        self.setCentralWidget(outer)
        layout = W.QVBoxLayout(outer)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)
        header = W.QHBoxLayout()
        heading = W.QLabel('DCRC Converter')
        heading.setStyleSheet('font-size:21px;font-weight:600')
        header.addWidget(heading)
        header.addStretch()
        self.language_box = W.QComboBox()
        for label, value in [('System language','system'),('English','en'),('Русский','ru')]:
            self.language_box.addItem(label,value)
        self.language_box.setCurrentIndex(max(0,self.language_box.findData(self.language_choice)))
        self.theme_box = W.QComboBox()
        for label, value in [('Dark','dark'),('Light','light'),('System theme','system')]:
            self.theme_box.addItem(label,value)
        self.theme_box.setCurrentIndex(max(0,self.theme_box.findData(self.theme_choice)))
        header.addWidget(self.language_box)
        header.addWidget(self.theme_box)
        layout.addLayout(header)
        self.tabs = W.QTabWidget()
        self.tabs.tabBar().hide()
        self.controls = {}
        self._source_page()
        self._output_page()
        self._appearance_page()
        self._settings_page()
        self._controls_page()
        self._progress_page()
        steps = W.QHBoxLayout()
        self.step_buttons = []
        for i, label in enumerate(('Disc','Output','Appearance','Settings','Controls','Convert')):
            button = W.QPushButton(f'{i+1}  {label}')
            self._translations.append((button.setText, f'{i+1}  {label}'))
            button.clicked.connect(lambda checked=False,index=i:self.tabs.setCurrentIndex(index))
            self.step_buttons.append(button)
            steps.addWidget(button)
        layout.addLayout(steps)
        layout.addWidget(self.tabs,1)
        self.inline_status = W.QLabel()
        self.inline_status.setWordWrap(True)
        layout.addWidget(self.inline_status)
        self.inline_bar = W.QProgressBar()
        self.inline_bar.setMaximumHeight(8)
        self.inline_bar.hide()
        layout.addWidget(self.inline_bar)
        nav = W.QHBoxLayout()
        self.back = W.QPushButton('Back')
        self.next = W.QPushButton('Next')
        self.start = W.QPushButton('Convert / resume')
        self.cancel = W.QPushButton('Cancel job')
        self.cancel.setEnabled(False)
        self.back.clicked.connect(lambda:self.tabs.setCurrentIndex(max(0,self.tabs.currentIndex()-1)))
        self.next.clicked.connect(self.advance)
        self.start.clicked.connect(self.convert)
        self.cancel.clicked.connect(self.stop)
        nav.addWidget(self.back);nav.addWidget(self.next);nav.addStretch()
        nav.addWidget(self.start);nav.addWidget(self.cancel)
        self.start.hide()
        layout.addLayout(nav)
        self.tabs.currentChanged.connect(self._step_state)
        self.language_box.currentIndexChanged.connect(lambda:self.set_language(self.language_box.currentData()))
        self.theme_box.currentIndexChanged.connect(lambda:self.set_theme(self.theme_box.currentData()))
        self._collect_texts()
        self.set_language(self.language_choice)
        self.set_theme(self.theme_choice)
        self._step_state()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(75)
        self.statusBar().showMessage(self.tr('Choose a disc; its version is checked automatically.'))
        if self.controls['source'].text().strip():self.auto_check_timer.start()

    def _collect_texts(self):
        """Bind static labels once; retranslation never rebuilds live controls."""
        for widget in self.findChildren(W.QWidget):
            if isinstance(widget,(W.QComboBox,W.QAbstractSpinBox)):
                widget.setFocusPolicy(QtCore.Qt.StrongFocus)
                widget.installEventFilter(self)
            if isinstance(widget, (W.QLabel, W.QPushButton, W.QCheckBox)) and widget.text():
                if widget not in (self.version, self.stage, self.log_path):
                    self._translations.append((widget.setText, widget.text()))
            elif isinstance(widget, W.QComboBox) and widget not in (self.language_box,self.theme_box):
                for index in range(widget.count()):
                    text = widget.itemText(index)
                    self._translations.append((lambda value,c=widget,i=index:c.setItemText(i,value),text))
            elif isinstance(widget,W.QTabWidget):
                for index in range(widget.count()):
                    text=widget.tabText(index)
                    self._translations.append((lambda value,c=widget,i=index:c.setTabText(i,value),text))
        self._dynamic_labels={widget:widget.text() for widget in (self.version,self.stage,self.log_path)}

    def eventFilter(self,widget,event):
        if event.type()==QtCore.QEvent.Wheel and isinstance(widget,(W.QComboBox,W.QAbstractSpinBox)) and not widget.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(widget,event)

    def tr(self,text):
        return catalog(self.language_choice).get(text,text)

    def set_language(self, choice):
        previous=catalog(self.language_choice)
        self.language_choice = choice if choice in ('system','en','ru') else 'system'
        translations = catalog(self.language_choice)
        for setter, text in self._translations:
            setter(translations.get(text,text))
        self.controls_editor.retranslate(self.tr)
        for widget,text in self._dynamic_labels.items():
            if widget.text() in (text,previous.get(text,text)):
                widget.setText(translations.get(text,text))
        for index,text in enumerate(('Dark','Light','System theme')):
            self.theme_box.setItemText(index,translations.get(text,text))
        self.dlc_list.setHeaderLabels([translations.get(text,text) for text in ('Event','Region / support')])
        status='Choose a disc; its version is checked automatically.'
        if self.statusBar().currentMessage() in (status,previous.get(status,status)):
            self.statusBar().showMessage(translations.get(status,status))
        at = self.language_box.findData(self.language_choice)
        if self.language_box.currentIndex()!=at:
            self.language_box.setCurrentIndex(at)
        self._step_state()

    def set_theme(self, choice):
        self.theme_choice = choice if choice in ('system','dark','light') else 'dark'
        apply_theme(self.theme_choice)
        at = self.theme_box.findData(self.theme_choice)
        if self.theme_box.currentIndex()!=at:
            self.theme_box.setCurrentIndex(at)

    def _step_state(self):
        index = self.tabs.currentIndex()
        busy = self.task.pending
        self.back.setEnabled(index>0)
        last=index==self.tabs.count()-1
        self.inline_status.setVisible(bool(self.inline_status.text()) and not last and
                                      not (self.job=='Download DLC' and busy))
        self.next.setText(self.tr('Convert') if last else self.tr('Next'))
        self.next.setEnabled(not last or not busy or self.job=='Check version')
        for i, button in enumerate(self.step_buttons):
            button.setProperty('stepCurrent',i==index)
            button.setProperty('stepDone',i<index)
            button.style().unpolish(button);button.style().polish(button)

    def advance(self):
        if self.tabs.currentIndex()==self.tabs.count()-1:self.convert()
        else:self.tabs.setCurrentIndex(self.tabs.currentIndex()+1)

    def _appearance_page(self):
        page = W.QWidget()
        layout = W.QVBoxLayout(page)
        note = W.QLabel('Choose your game title, artwork and menu music. Convert / resume applies this appearance to the PSP game folder.')
        note.setWordWrap(True);layout.addWidget(note)
        body = W.QHBoxLayout();layout.addLayout(body)
        art_tabs = W.QTabWidget();body.addWidget(art_tabs,1)
        self.art_tabs = art_tabs
        def form_page(title):
            widget=W.QWidget();form=W.QFormLayout(widget)
            form.setFieldGrowthPolicy(W.QFormLayout.AllNonFixedFieldsGrow)
            scroll=W.QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget)
            art_tabs.addTab(scroll,title)
            return form
        choices=[('Game artwork','game'),('Own file','file'),('None','none')]
        f=form_page('Icon & title')
        title = W.QLineEdit(self.saved.get('title', DEFAULTS['title']))
        self.controls['title'] = title
        f.addRow('PSP menu title', title)
        self.combo(f,'Icon','xmb_icon_mode',choices)
        game_art=[('Title screen','title'),('Sega tile (partial)','sega')]
        self.art_choice=self.combo(f,'Game icon artwork','xmb_icon_art',game_art)
        self.add_gallery_button(f, 'icon')
        self.path(f,'Icon image','xmb_icon_file',file=True,file_filter='Images (*.png *.jpg *.jpeg *.bmp)')
        self.media_button=W.QPushButton('Inspect disc artwork / music')
        self.media_button.clicked.connect(self.inspect_media)
        f.addRow(self.media_button)
        f=form_page('Background')
        self.combo(f,'Background','xmb_background_mode',choices)
        self.combo(f,'Game background artwork','xmb_background_art',game_art)
        self.add_gallery_button(f, 'background')
        self.path(f,'Background image','xmb_background_file',file=True,file_filter='Images (*.png *.jpg *.jpeg *.bmp)')
        f=form_page('Music')
        self.combo(f,'XMB music','xmb_music_mode',[('None','none'),('Game music','game'),('Own file','file')])
        tracks=[('TITLE.ADX','TITLE.ADX')]
        saved_track=self.saved.get('xmb_track')
        if isinstance(saved_track,str) and saved_track!='TITLE.ADX' and re.fullmatch(r'[A-Za-z0-9_-]+\.ADX',saved_track,re.I):
            tracks.append((saved_track,saved_track))
        self.combo(f,'Game track','xmb_track',tracks)
        self.path(f,'Music file','xmb_music_file',file=True,file_filter='Audio (*.wav *.mp3 *.ogg *.flac *.adx *.at3);;All files (*)')
        scan_music=W.QPushButton('Browse music from the game')
        scan_music.clicked.connect(self.browse_game_music);f.addRow(scan_music)
        for label,key,lo,hi in [('Start (seconds)','xmb_music_start',0,7200),('Length (seconds)','xmb_music_seconds',1,10)]:
            spin=W.QDoubleSpinBox();spin.setRange(lo,hi);spin.setDecimals(2)
            value=self.saved.get(key,DEFAULTS[key])
            spin.setValue(float(value) if type(value) in (int,float) else DEFAULTS[key])
            self.controls[key]=spin;f.addRow(label,spin)
        self.music_position=W.QSlider(QtCore.Qt.Horizontal)
        self.music_position.setRange(0,720000)
        self.music_position.valueChanged.connect(lambda value:self.controls['xmb_music_start'].setValue(value/100))
        self.controls['xmb_music_start'].valueChanged.connect(lambda value:self.music_position.setValue(round(value*100)))
        self.music_position.setValue(round(self.controls['xmb_music_start'].value()*100))
        self.controls['xmb_track'].currentIndexChanged.connect(self.music_track_changed)
        self.controls['xmb_music_mode'].currentIndexChanged.connect(self.music_track_changed)
        f.addRow('Start position',self.music_position)
        music_actions=W.QWidget();music_row=W.QHBoxLayout(music_actions);music_row.setContentsMargins(0,0,0,0)
        self.listen_button=W.QPushButton('Listen to selected clip')
        self.listen_button.clicked.connect(self.preview_audio)
        stop_music=W.QPushButton('Stop');stop_music.clicked.connect(self.stop_audio)
        music_row.addWidget(self.listen_button);music_row.addWidget(stop_music);f.addRow(music_actions)
        note=W.QLabel('Choose any start point. PSP menu music supports clips up to 10 seconds. The preview plays the selected cut.')
        note.setWordWrap(True);f.addRow(note)
        f=form_page('4:3 border')
        self.combo(f,'Border','border_mode',[('Keep existing border (if present)','none'),('Own image','custom')] if PROFILE_CAPABILITIES['custom_border'] else [('Unavailable in public TA runtime','none')])
        self.path(f,'Border image','border_image',file=True,file_filter='Images (*.png *.jpg *.jpeg *.bmp)')
        self.controls['border_mode'].setEnabled(PROFILE_CAPABILITIES['custom_border'])
        self.controls['border_image'].parentWidget().setEnabled(PROFILE_CAPABILITIES['custom_border'])
        if PROFILE_CAPABILITIES['custom_border']:self.add_gallery_button(f,'border')
        default=Path(__file__).parent/'assets'/'default_border.png'
        note=W.QLabel('Choose your own 4:3 border image. No stock artwork is bundled.' if PROFILE_CAPABILITIES['custom_border'] else 'Custom 4:3 borders require a runtime feature not included in this public profile.')
        note.setWordWrap(True);f.addRow(note)
        right=W.QVBoxLayout();body.addLayout(right)
        self.preview=Preview();right.addWidget(self.preview)
        caption=W.QLabel('PSP XMB preview · 480 × 272');caption.setAlignment(QtCore.Qt.AlignCenter)
        right.addWidget(caption);right.addStretch()
        self.tabs.addTab(page,'3 · Appearance')
        for key in ('xmb_icon_mode','xmb_background_mode','xmb_icon_art','xmb_background_art','border_mode'):
            self.controls[key].currentIndexChanged.connect(self.update_preview)
        for key in ('xmb_icon_file','xmb_background_file','title','border_image'):
            self.controls[key].textChanged.connect(self.update_preview)
        self.art_tabs.currentChanged.connect(self.update_preview)
        self.update_preview()

    def update_preview(self):
        if not hasattr(self,'preview'):return
        values=self.values()
        images=self.media.get('images',[]) if self.media else []
        def selected(kind):
            mode=values['xmb_'+kind+'_mode']
            if mode=='file':return file_image(values['xmb_'+kind+'_file'])
            if mode=='game':
                entry=next((entry for entry in images if entry['id']==values['xmb_'+kind+'_art']),None)
                return QtGui.QImage.fromData(entry['preview_png']) if entry else QtGui.QImage()
            return QtGui.QImage()
        self.preview.icon=selected('icon')
        self.preview.background=selected('background')
        self.preview.title=values['title']
        self.preview.border=self.art_tabs.currentIndex()==3
        if self.preview.border:
            path=(values['border_image'] if values['border_mode']=='custom' else
                  str(Path(__file__).parent/'assets'/('orbit_border.png' if values['border_mode']=='orbit' else 'default_border.png')))
            self.preview.background=file_image(path)
        self.preview.update()

    def inspect_media(self):
        name=self.controls['source'].text().strip()
        if not name:self.show_error('Choose your own disc first.');return
        def operation(event,cancel):
            from dcrc.xmb import inspect_source_media
            return inspect_source_media(Path(name),event=event,cancel=cancel)
        self.begin('Inspect media',operation)

    def _apply_media(self):
        for key in ('xmb_icon_art','xmb_background_art'):
            widget=self.controls[key];selected=widget.currentData();blocker=QtCore.QSignalBlocker(widget);widget.clear()
            for image in self.media.get('images',[]):widget.addItem(image['label'],image['id'])
            if not widget.count():widget.addItem('Title screen','title')
            if widget.findData(selected)<0:widget.addItem(selected,selected)
            widget.setCurrentIndex(max(0,widget.findData(selected)));del blocker
        combo=self.controls['xmb_track'];selected=combo.currentData()
        blocker=QtCore.QSignalBlocker(combo)
        combo.clear()
        for track in self.media.get('tracks',[]):
            combo.addItem(f"{track.get('label',track['id'])} · {track.get('seconds',0):.1f}s",track['id'])
        if not combo.count():combo.addItem('TITLE.ADX','TITLE.ADX')
        combo.setCurrentIndex(max(0,combo.findData(selected)))
        del blocker
        self.music_track_changed()
        self.update_preview()

    def add_gallery_button(self, form, target):
        button=W.QPushButton('Choose image from the game…')
        button.clicked.connect(lambda:self.choose_game_image(target))
        form.addRow(button)

    def choose_game_image(self, target):
        if target=='border' and not PROFILE_CAPABILITIES['custom_border']:
            self.show_error('Custom borders are unavailable in this public TA runtime.');return
        if self.task.running:return
        if self.media is None:
            self.pending_picker=target
            self.inspect_media()
            return
        from .media_picker import ImagePicker
        selected=self.values().get('xmb_'+target+'_art')
        picker=ImagePicker(self.media.get('images',[]),self,title=self.tr('Choose image from the game…'),selected_id=selected)
        if picker.exec()!=W.QDialog.Accepted:return
        if target=='border':
            source=Path(self.controls['source'].text())
            destination=self.settings_path.parent/'media'/('border_'+uuid.uuid4().hex+'.png')
            destination.parent.mkdir(parents=True,exist_ok=True)
            from dcrc.media import export_source_image
            self.begin('Prepare border',lambda event,cancel:export_source_image(source,picker.selected_id,destination,event=event,cancel=cancel))
            return
        combo=self.controls['xmb_'+target+'_art']
        combo.setCurrentIndex(combo.findData(picker.selected_id))
        mode=self.controls['xmb_'+target+'_mode'];mode.setCurrentIndex(mode.findData('game'))
        self.update_preview()

    def stop_audio(self):
        from .media_picker import stop_audio
        stop_audio()

    def browse_game_music(self):
        combo=self.controls['xmb_music_mode'];combo.setCurrentIndex(combo.findData('game'))
        self.inspect_media()

    def music_track_changed(self):
        if not hasattr(self,'music_position'):return
        if not self.media or self.controls['xmb_music_mode'].currentData()!='game':
            self.music_position.setMaximum(720000)
            self.controls['xmb_music_start'].setMaximum(7200)
            return
        selected=self.controls['xmb_track'].currentData()
        entry=next((entry for entry in self.media.get('tracks',[]) if entry['id']==selected),None)
        if entry:
            maximum=max(0,min(7200,entry.get('seconds',7200)-1))
            self.music_position.setMaximum(round(maximum*100))
            self.controls['xmb_music_start'].setMaximum(maximum)

    def preview_audio(self):
        if self.task.running:return
        values=self.values();mode=values['xmb_music_mode']
        if mode=='none':self.show_error('Choose game music or an audio file first.');return
        if mode=='game' and self.media is None:
            self.pending_audio=True;self.inspect_media();return
        source=values['source'] if mode=='game' else values['xmb_music_file']
        if not source:self.show_error('Choose game music or an audio file first.');return
        self.stop_audio()
        from dcrc.media import preview_source_audio
        destination=self.settings_path.parent/'media'/('preview_'+uuid.uuid4().hex+'.wav')
        destination.parent.mkdir(parents=True,exist_ok=True)
        self.begin('Prepare music preview',lambda event,cancel:preview_source_audio(
            Path(source),values['xmb_track'] if mode=='game' else None,
            values['xmb_music_start'],values['xmb_music_seconds'],destination,
            ffmpeg=Path(values['ffmpeg']) if self.advanced.isChecked() and values['ffmpeg'] else None,event=event,cancel=cancel))

    def _dlc_widgets(self,form):
        self.catalog_button=W.QPushButton('Find downloadable DLC (network)')
        self.catalog_button.clicked.connect(self.discover_dlc);form.addRow(self.catalog_button)
        self.dlc_list=W.QTreeWidget();self.dlc_list.setHeaderLabels(['Event','Region / support'])
        self.dlc_list.header().setSectionResizeMode(0,W.QHeaderView.Stretch)
        self.dlc_list.header().setSectionResizeMode(1,W.QHeaderView.ResizeToContents)
        self.dlc_list.setMinimumHeight(120);form.addRow(self.dlc_list)
        self.path(form,'DLC download parent folder','dlc_download_root',str(Path.home()/'Downloads'/'DCRC DLC'))
        self.download_button=W.QPushButton('Download selected DLC')
        self.download_button.clicked.connect(self.download_dlc);form.addRow(self.download_button)
        from dcrc.capabilities import DLC_NOTICE
        note=W.QLabel(DLC_NOTICE + ' Checked events take precedence over the local DLC folder when converting.')
        note.setWordWrap(True);form.addRow(note)

    def discover_dlc(self):
        def operation(event,cancel):
            from dcrc.dlc_download import discover_catalog
            return discover_catalog(event=event,cancel=cancel,preflight=True)
        self.begin('DLC catalog',operation)

    def _apply_catalog(self):
        self.dlc_list.clear()
        for entry in self.dlc_catalog.get('entries',[]):
            reasons={'guest_validation_required':'Needs an in-game check',
                     'guest_compatibility_unknown':'Compatibility unknown',
                     'region_not_supported':'Region not supported','voice_unsupported':'Voice pack not supported',
                     'unsupported_us_name_family':'Not supported by this US game profile',
                     'invalid_metadata':'Invalid event metadata','metadata_unavailable':'Event server unavailable'}
            status=entry['region']+' · '+self.tr(reasons.get(entry.get('reason'),entry.get('reason','').replace('_',' ')))
            item=W.QTreeWidgetItem([entry['label'],status]);item.setData(0,QtCore.Qt.UserRole,entry['id'])
            item.setToolTip(0,status);item.setToolTip(1,status)
            if entry.get('supported'):
                item.setFlags(item.flags()|QtCore.Qt.ItemIsUserCheckable);item.setCheckState(0,QtCore.Qt.Unchecked)
            else:item.setFlags(item.flags()&~QtCore.Qt.ItemIsEnabled)
            self.dlc_list.addTopLevelItem(item)

    def _selected_dlc_ids(self):
        return [self.dlc_list.topLevelItem(i).data(0,QtCore.Qt.UserRole)
                for i in range(self.dlc_list.topLevelItemCount())
                if self.dlc_list.topLevelItem(i).checkState(0)==QtCore.Qt.Checked]

    def download_dlc(self):
        if not self.dlc_catalog:self.show_error('Find the DLC catalog first.');return
        ids=self._selected_dlc_ids()
        name=self.controls['dlc_download_root'].text().strip()
        if not ids or not name:self.show_error('Choose supported events and a download parent folder.');return
        destination=Path(name)/('events_'+uuid.uuid4().hex)
        catalog_value=self.dlc_catalog
        def operation(event,cancel):
            from dcrc.dlc_download import download_events
            return download_events(catalog_value,ids,destination,
                expected_fingerprint=catalog_value['fingerprint'],event=event,cancel=cancel)
        self.begin('Download DLC',operation)

    def _controls_page(self):
        form=self.page('5 · Controls')
        from .controls import ControlsEditor
        self.controls_editor=ControlsEditor(self.saved.get('control_map'))
        form.addRow(self.controls_editor)
        note=W.QLabel('Analog stick: move. DCRC menu: L + R + Cross + Down (physical buttons). HOME and menu controls stay available with any game mapping.')
        note.setWordWrap(True);form.addRow(note)

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

    def path(self, form, label, key, default='', file=False, file_filter='Dreamcast GDI (*.gdi);;All files (*)'):
        row = W.QWidget()
        box = W.QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        edit = W.QLineEdit(str(self.saved.get(key, default)))
        button = W.QPushButton('Browse…')
        def choose():
            selected = (W.QFileDialog.getOpenFileName(self, label, edit.text(),
                         file_filter)[0] if file else
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
        if key == 'aspect' and wanted == 'wide': wanted = '16:9'
        at = combo.findData(wanted)
        if at<0 and key in ('xmb_icon_art','xmb_background_art'):
            from dcrc.media import valid_artwork_id
            if valid_artwork_id(wanted):combo.addItem(wanted,wanted);at=combo.count()-1
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
        self._dlc_widgets(form)
        folder = W.QPushButton('Use an extracted folder (advanced)…')
        def pick_folder():
            value = W.QFileDialog.getExistingDirectory(self, 'Extracted disc folder')
            if value:
                self.controls['source'].setText(value)
        folder.clicked.connect(pick_folder)
        form.addRow(folder)
        self.identify_button = W.QPushButton('Check supported version')
        self.identify_button.clicked.connect(self.identify)
        form.addRow(self.identify_button)
        self.identify_button.hide()
        self.version = W.QLabel('Choose your own disc. Its version is checked automatically.')
        self.version.setWordWrap(True)
        self.version.setTextFormat(QtCore.Qt.PlainText)
        form.addRow('Compatibility', self.version)

    def _settings_page(self):
        form = self.page('2 · Graphics & start')
        quality = W.QLabel('Quality changes apply to selected Emerald Coast world assets. '
                          '64/128 reduce texture detail. This public TA profile keeps full distance100. '
                          'These choices are not lossless optimizations or hardware speed guarantees.')
        quality.setWordWrap(True)
        form.addRow(quality)
        self.combo(form, 'EC world textures (PSP preset initially selected)', 'world_textures',
                   [('Original', 0), ('Maximum 128', 128), ('Maximum 64', 64)])
        distance=W.QWidget();distance_row=W.QHBoxLayout(distance);distance_row.setContentsMargins(0,0,0,0)
        self.distance_slider=W.QSlider(QtCore.Qt.Horizontal);self.distance_slider.setRange(100,100)
        self.distance_slider.setValue(self.saved.get('land_distance',DEFAULTS['land_distance']))
        number=W.QSpinBox();number.setRange(100,100);number.setSuffix(' %');number.setValue(self.distance_slider.value())
        self.controls['land_distance']=number
        self.distance_slider.valueChanged.connect(number.setValue);number.valueChanged.connect(self.distance_slider.setValue)
        distance_row.addWidget(self.distance_slider,1);distance_row.addWidget(number)
        form.addRow('Draw distance (static scenery)',distance)
        distance.setEnabled(False)
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
        self.combo(form, 'Aspect ratio', 'aspect', [('16:9', '16:9'), ('4:3', '4:3')])
        self.combo(form, 'Frame skip', 'frame_skip', [('Automatic', 'auto'), ('Off', 'off')] +
                   [(str(i), str(i)) for i in range(2, 61)])
        self.spin(form, 'Mip levels', 'mip_levels', 1, 8)
        mip_note=W.QLabel('Mip count includes the base level (maximum 8), stops at 8 × 8, and applies to new texture loads.')
        mip_note.setWordWrap(True);form.addRow(mip_note)
        self.combo(form,'Dithering','dither',[('On','on'),('Opaque only','opaque'),('Off','off')] if PROFILE_CAPABILITIES['configurable_dither'] else [('Fixed by public runtime','on')])
        self.check(form, 'FPS display', 'show_fps')
        self.check(form, 'Audio', 'audio')
        self.controls['dither'].setEnabled(PROFILE_CAPABILITIES['configurable_dither'])
        self.check(form, 'Convert / play FMV movies' if PROFILE_CAPABILITIES['movie_playback'] else 'FMV playback unavailable in this public runtime', 'movies')
        self.controls['movies'].setEnabled(PROFILE_CAPABILITIES['movie_playback'])
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
        self.advanced=W.QGroupBox('Advanced build options')
        self.advanced.setCheckable(True);self.advanced.setChecked(False)
        advanced_form=W.QFormLayout(self.advanced)
        self.path(advanced_form, 'Work folder (optional)', 'work')
        self.path(advanced_form, 'Native toolchain (optional)', 'toolchain')
        self.path(advanced_form, 'FFmpeg override (optional)', 'ffmpeg', file=True,file_filter='Programs (*.exe);;All files (*)')
        self.path(advanced_form, 'ATRAC encoder override (optional)', 'xmb_encoder', file=True,file_filter='Programs (*.exe);;All files (*)')
        self.spin(advanced_form, 'Compiler jobs', 'jobs', 1, 64)
        for i in range(advanced_form.rowCount()):
            for role in (W.QFormLayout.LabelRole,W.QFormLayout.FieldRole):
                item=advanced_form.itemAt(i,role)
                if item and item.widget():item.widget().hide()
        def toggle_advanced(visible):
            for i in range(advanced_form.rowCount()):
                for role in (W.QFormLayout.LabelRole,W.QFormLayout.FieldRole):
                    item=advanced_form.itemAt(i,role)
                    if item and item.widget():item.widget().setVisible(visible)
        self.advanced.toggled.connect(toggle_advanced)
        form.addRow(self.advanced)
        note = W.QLabel('Choose where to save your PSP game folder. Select a separately installed SDK in Advanced options or use a separately audited portable dependency package. Conversion saves locally; copy to your PSP after testing.')
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
        self.log_path = W.QLabel('Log is saved automatically.')
        self.log_path.setWordWrap(True)
        self.log_path.setToolTip(str(self.session_log.path))
        form.addRow(self.log_path)
        buttons = W.QWidget()
        row = W.QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        work = W.QPushButton('Open logs folder')
        work.clicked.connect(self.open_logs)
        row.addWidget(work)
        form.addRow(buttons)

    def values(self):
        result = {}
        for key, widget in self.controls.items():
            if isinstance(widget, W.QComboBox): result[key] = widget.currentData()
            elif isinstance(widget, (W.QSpinBox, W.QDoubleSpinBox)): result[key] = widget.value()
            elif isinstance(widget, W.QCheckBox): result[key] = widget.isChecked()
            else: result[key] = widget.text().strip()
        if hasattr(self,'controls_editor'):result['control_map']=self.controls_editor.value()
        return result

    def reset_identity(self):
        self.identity = None
        self.identity_source = None
        self.convert_after_check = None
        self.start_after_check = False
        self.media = None
        self.auto_check_due = False
        self.auto_check_timer.stop()
        if self.controls['source'].text().strip():self.auto_check_timer.start()
        self.music_track_changed()
        if hasattr(self, "preview"): self.update_preview()
        if hasattr(self, 'version'):
            self.version.setText(self.tr('The disc will be checked automatically…'))

    def auto_identify(self):
        if self.closing:return
        source=self.controls['source'].text().strip()
        if not source or not Path(source).exists():return
        path=Path(source)
        if path.is_dir() and not ((path/'1ST_READ.BIN').is_file() or (path/'data/1ST_READ.BIN').is_file()):return
        if self.task.pending:
            self.auto_check_due=True
            return
        if self.identity_source==source and self.identity is not None:return
        self.identify()

    def begin(self, name, operation):
        if self.task.pending:
            return
        self.job = name
        self._record_session(name + ' started')
        self.stage.setText(self.tr(name) + '…')
        self.inline_status.setText(self.tr(name) + '…')
        self.inline_status.setVisible(name!='Download DLC')
        self.inline_bar.setRange(0,0);self.inline_bar.setVisible(name not in ('Download DLC','Convert'))
        self.bar.setRange(0, 0)
        self.bar.setVisible(name=='Convert')
        if name=='Convert':self.tabs.setCurrentIndex(self.tabs.count()-1)
        if name=='Download DLC':
            from .job_dialog import JobDialog
            if self.job_dialog:self.job_dialog.close()
            self.job_dialog=JobDialog(self.tr(name),self.stop,parent=self,translate=self.tr)
            self.job_dialog.show()
        if name=='Check version':self.version.setText(self.tr('Checking the selected disc…'))
        self.task.start(operation)
        self._busy(True)

    def _busy(self, busy):
        for i in range(self.tabs.count()-1):
            self.tabs.widget(i).setEnabled(not busy or (self.job=='Check version' and i!=0))
        for button in self.step_buttons: button.setEnabled(True)
        for button in (self.start,self.identify_button,self.verify_button,self.configure_button,
                       self.media_button,self.catalog_button,self.download_button,
                       self.language_box,self.theme_box):
            button.setEnabled(not busy)
        self.cancel.setEnabled(busy)
        self.cancel.setVisible(not busy or self.job!='Download DLC')
        self._step_state()

    def identify(self):
        if self.task.pending:return
        source = self.controls['source'].text().strip()
        if not source:
            self.show_error('Choose your own GDI image or extracted folder first.')
            return
        self.auto_check_timer.stop();self.auto_check_due=False
        self.check_source=source
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
            if self.task.pending:
                if self.job=='Check version':
                    self.convert_after_check=values['source']
                    self.inline_status.setText(self.tr('Checking the disc; conversion will start when it is ready.'))
                return
            if not self.identity or self.identity.get('ok') is not True or (self.identity_source and self.identity_source!=values['source']):
                self.convert_after_check=values['source']
                self.identify()
                return
            from dcrc.models import ConversionOptions
            from dcrc.pipeline import convert
            dlc_ids=self._selected_dlc_ids()
            dlc_catalog=self.dlc_catalog
            dlc_parent=values['dlc_download_root']
            if dlc_ids and (not dlc_catalog or not dlc_parent):
                raise ValueError('Choose supported events and a download parent folder.')
            options = ConversionOptions(source=Path(values['source']), output=Path(values['output']),
                work=Path(values['work']) if self.advanced.isChecked() and values['work'] else None,
                toolchain=Path(values['toolchain']) if self.advanced.isChecked() and values['toolchain'] else None,
                dlc_dir=Path(values['dlc_dir']) if values.get('dlc_dir') else None,
                border_image=Path(values['border_image']) if typed['border_mode']=='custom' and values.get('border_image') else None,
                ffmpeg=Path(values['ffmpeg']) if self.advanced.isChecked() and values.get('ffmpeg') else None,
                profile=self.identity.get('profile', 'sa1_us_1005'),
                **{key:Path(values[key]) if values.get(key) and (key!='xmb_encoder' or self.advanced.isChecked()) else None for key in
                   ('xmb_icon_file','xmb_background_file','xmb_music_file','xmb_encoder')}, **typed)
            self.persist(values)
            def operation(event,cancel):
                selected_options=options
                if dlc_ids:
                    from dcrc.dlc_download import download_events
                    from dcrc.errors import Cancelled
                    destination=Path(dlc_parent)/('events_'+uuid.uuid4().hex)
                    ready=download_events(dlc_catalog,dlc_ids,destination,
                        expected_fingerprint=dlc_catalog['fingerprint'],event=event,cancel=cancel)
                    if cancel.is_set():raise Cancelled()
                    selected_options=replace(options,dlc_dir=Path(ready['source_dir']))
                    event({'type':'dlc_ready','source_dir':str(selected_options.dlc_dir),
                           'message':'Selected DLC verified: '+str(selected_options.dlc_dir)})
                return convert(selected_options,event=event,cancel_event=cancel,log_path=self.session_log.path)
            self.begin('Convert',operation)
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
            from dcrc.package import RUNTIME_KEYS
            options = {key:value for key,value in options.items() if key in RUNTIME_KEYS}
            self.persist(values)
            self.begin('Apply runtime settings', lambda event, cancel:
                       configure_folder(Path(values['output']), **options))
        except ImportError:
            self.show_error('This core does not yet support changing an existing folder. Reconvert to apply settings.')
        except Exception as error:
            self.show_error(str(error))

    def persist(self, values):
        try:
            save_settings(self.settings_path, dict(values,language=self.language_choice,theme=self.theme_choice))
        except OSError as error:
            self.log.appendPlainText('Settings could not be saved: ' + str(error))
            self._record_session('Settings could not be saved: '+str(error))

    def stop(self):
        self.auto_check_timer.stop();self.auto_check_due=False
        self.convert_after_check=None;self.start_after_check=False
        self.task.cancel()
        self.cancel.setEnabled(False)
        self.stage.setText(self.tr('Cancelling — waiting for owned processes and cleanup…'))
        self.inline_status.setText(self.stage.text())

    def identity_summary(self,result):
        if result.get('ok'):
            return '\n'.join((self.tr('Supported version — ready to convert.'),
                f"{result.get('title','Sonic Adventure')} · {result.get('region','USA')} · {result.get('version','V1.005')}"))
        return '\n'.join(filter(None,(self.tr('This version is not supported.'),
                                     result.get('message'),result.get('hint'))))

    def _log_unavailable(self):
        # Do not expose filesystem exception details or replace the job result.
        if not getattr(self, '_log_failure_shown', False):
            self._log_failure_shown = True
            self.log.appendPlainText(self.tr('Session log is unavailable; see the on-screen log.'))

    def _record_session(self, value):
        try:
            if isinstance(value, dict):self.session_log.event(value)
            else:self.session_log.write(value)
        except OSError:
            self._log_unavailable()

    def poll(self):
        log_revision = self.log.document().revision()
        for event in self.task.drain():
            kind = event.get('type', 'log')
            message = str(event.get('message', ''))
            if event.get('log_error'):self._log_unavailable()
            if kind=='dlc_ready' and self.job=='Convert':
                self.controls['dlc_dir'].setText(event['source_dir'])
            if kind=='finished' and self.job=='Prepare music preview':
                from .media_picker import play_wav
                try:play_wav(event['result'],parent=self)
                except (OSError,RuntimeError) as error:
                    kind='error';message=self.tr('Audio playback failed: ')+str(error)
                    event={'type':'error','message':message}
                    self._record_session(event)
            if kind in ('finished', 'cancelled', 'error'):
                self.bar.setRange(0, 100)
                if kind == 'finished':
                    result = event.get('result')
                    ok = not isinstance(result, dict) or result.get('ok', True) is True
                    if self.job == 'Inspect media':
                        self.media = result
                        self._apply_media()
                    elif self.job == 'DLC catalog':
                        self.dlc_catalog = result
                        self._apply_catalog()
                    elif self.job == 'Download DLC':
                        self.controls['dlc_dir'].setText(result['source_dir'])
                    elif self.job=='Prepare border':
                        self.controls['border_image'].setText(str(result))
                        self.controls['border_mode'].setCurrentIndex(self.controls['border_mode'].findData('custom'))
                    if self.job == 'Check version':
                        if self.check_source==self.controls['source'].text().strip():
                            self.identity = result;self.identity_source=self.check_source
                            self.version.setText(self.identity_summary(result))
                            if self.convert_after_check==self.check_source:
                                self.start_after_check=ok;self.convert_after_check=None
                        else:self.auto_check_due=True
                    text = ('Complete' if ok else 'Not supported / verification failed')
                    self.stage.setText(self.tr(text))
                    self.bar.setValue(100 if ok else 0)
                    if hasattr(result, 'folder'):
                        self.log.appendPlainText('Output: ' + str(result.folder))
                        self._record_session('Output: '+str(result.folder))
                    else:
                        shown = self.result_summary(result)
                        self.log.appendPlainText(shown)
                        self._record_session(shown)
                else:
                    self.stage.setText(self.tr('Cancelled — partial output is not ready.') if kind == 'cancelled' else self.tr('Failed: ') + message)
                    self.log.appendPlainText(event.get('detail', message))
                    if self.job=='Check version':self.version.setText(self.stage.text())
                    self.convert_after_check=None;self.start_after_check=False
                    self.pending_picker=None;self.pending_audio=False
                self.inline_status.setText(self.stage.text())
                self.inline_bar.hide()
                if self.job_dialog and self.job=='Download DLC':
                    self.job_dialog.finish(self.result_summary(event.get('result')) if kind=='finished' else self.stage.text(),kind=='finished')
            else:
                if message: self.log.appendPlainText(message)
                if event.get('stage'):
                    self.stage.setText(str(event['stage']))
                    self.inline_status.setText(self.stage.text())
                if self.job_dialog and self.job=='Download DLC':self.job_dialog.update_event(event)
                value = event.get('progress')
                if isinstance(value, (int, float)):
                    self.bar.setRange(0, 100)
                    self.bar.setValue(max(0, min(100, round(value*100 if 0 <= value <= 1 else value))))
                    self.inline_bar.setRange(0,100);self.inline_bar.setValue(self.bar.value())
                elif event.get('state')=='running':
                    self.bar.setRange(0,0)
        if not self.task.pending:
            self._busy(False)
            if self.closing:
                self.close()
            elif self.start_after_check:
                self.start_after_check=False;self.convert()
            elif self.auto_check_due:
                self.auto_check_due=False;self.auto_identify()
            elif self.pending_picker and self.media is not None:
                target=self.pending_picker;self.pending_picker=None
                self.choose_game_image(target)
            elif self.pending_audio and self.media is not None:
                self.pending_audio=False;self.preview_audio()
        if self.log.document().revision()!=log_revision:
            self._scroll_log_to_end()
            QtCore.QTimer.singleShot(0, self._scroll_log_to_end)

    def _scroll_log_to_end(self):
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def result_summary(self,result):
        if self.job=='Check version':return self.identity_summary(result)
        if self.job=='DLC catalog':
            entries=result.get('entries',[])
            return self.tr('Available to download: {available} of {count} events. Select events, then download.').format(available=sum(bool(e.get('supported')) for e in entries),count=len(entries))
        if self.job=='Download DLC':
            return self.tr('DLC downloaded and verified. Folder: {folder}').format(folder=result['source_dir'])
        if self.job=='Inspect media':
            text=self.tr('Found {images} images and {tracks} music tracks.').format(images=len(result.get('images',[])),tracks=len(result.get('tracks',[])))
            if result.get('images_truncated'):text+=' '+self.tr('The gallery is bounded; remaining or unsupported archives are omitted.')
            return text
        if self.job=='Prepare music preview':return self.tr('Playing the selected music clip.')
        if self.job=='Prepare border':return self.tr('Game image selected as 4:3 border.')
        if isinstance(result,dict):
            return self.tr('Complete') if result.get('ok',True) else str(result.get('message',self.tr('Verification failed.')))
        return self.tr('Complete')

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

    def open_logs(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.session_log.path.parent.resolve())))

    def show_error(self, message):
        self.stage.setText(self.tr(message))
        self.log.appendPlainText(message)
        self._record_session(message)
        self.inline_status.setText(self.tr(message))

    def closeEvent(self, event):
        self.auto_check_timer.stop()
        if self.task.pending:
            self.closing = True
            self.stop()
            event.ignore()
            return
        self.persist(self.values())
        self.stop_audio()
        if self.job_dialog:self.job_dialog.close()
        event.accept()


def main(session_log=None):
    application = W.QApplication(sys.argv)
    application.setStyle('Fusion')
    application.setApplicationName('DCRC Converter')
    application.setOrganizationName('DCRC')
    window = Window(session_log=session_log)
    window.show()
    return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
