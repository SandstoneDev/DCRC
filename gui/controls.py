"""Editable guest bindings; system controls stay raw."""
from PySide6 import QtCore,QtGui,QtWidgets as W
from dcrc.controls import BUTTONS, ACTIONS, validate_control_map

BUTTON_LABELS=dict(zip(BUTTONS,('Cross ×','Circle ○','Square □','Triangle △','L','R','Start','Select','D-pad Up','D-pad Down','D-pad Left','D-pad Right')))
ACTION_LABELS=dict(zip(ACTIONS,('Disabled','A · jump / confirm','B · action / cancel','X · action','Y','L trigger','R trigger','Start','D-pad Up','D-pad Down','D-pad Left','D-pad Right')))

class ControlsEditor(W.QWidget):
    def __init__(self, mapping=None, translate=None, parent=None):
        super().__init__(parent)
        self.tr_text=translate or (lambda text:text)
        layout=W.QFormLayout(self)
        heading=W.QLabel('Dreamcast button → PSP buttons')
        layout.addRow(heading)
        self.bindings={};self.action_labels={};self.options={}
        for action in ACTIONS[1:]:
            button=W.QPushButton();menu=W.QMenu(button);button.setMenu(menu)
            self.bindings[action]=button
            label=W.QLabel();self.action_labels[action]=label
            for physical in BUTTONS:
                option=menu.addAction(BUTTON_LABELS[physical]);option.setCheckable(True)
                option.toggled.connect(lambda checked,a=action,p=physical:self.assign(a,p,checked))
                self.options[action,physical]=option
            layout.addRow(label,button)
        reset=W.QPushButton('Reset controls')
        reset.clicked.connect(lambda: self.set_value(None))
        layout.addRow(reset)
        note=W.QLabel('Choose which PSP buttons activate each Dreamcast button. One PSP button has one assignment; several PSP buttons may share a Dreamcast button.')
        note.setWordWrap(True)
        layout.addRow(note)
        self.set_value(mapping)
    def value(self):
        return self.mapping.copy()

    def assign(self,action,physical,checked=True):
        if checked:self.mapping[physical]=action
        elif self.mapping[physical]==action:self.mapping[physical]='disabled'
        self.refresh()

    def retranslate(self,translate):
        self.tr_text=translate
        self.refresh()

    def refresh(self):
        tr=self.tr_text
        for action,button in self.bindings.items():
            self.action_labels[action].setText('Dreamcast '+tr(ACTION_LABELS[action]))
            selected=[tr(BUTTON_LABELS[physical]) for physical in BUTTONS if self.mapping[physical]==action]
            button.setText('PSP '+ ' / '.join(selected) if selected else tr('Disabled'))
            for physical in BUTTONS:
                option=self.options[action,physical]
                blocker=QtCore.QSignalBlocker(option)
                option.setText('PSP '+tr(BUTTON_LABELS[physical]))
                option.setChecked(self.mapping[physical]==action)

    def set_value(self,mapping):
        self.mapping=validate_control_map(mapping)
        self.refresh()
    set_mapping=set_value
