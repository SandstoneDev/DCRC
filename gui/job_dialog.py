"""Owned job progress; closing requests cancellation and waits for cleanup."""
from PySide6 import QtCore, QtWidgets as W


class JobDialog(W.QDialog):
    def __init__(self, title, cancel, parent=None, translate=lambda text:text):
        super().__init__(parent)
        self.tr_text=translate
        self.setWindowTitle(title)
        self.resize(540,200)
        self.running=True
        self.cancel_job=cancel
        layout=W.QVBoxLayout(self)
        self.label=W.QLabel(title+'…');self.label.setWordWrap(True)
        self.label.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.label)
        self.bar=W.QProgressBar();self.bar.setRange(0,0);layout.addWidget(self.bar)
        self.detail=W.QLabel();self.detail.setWordWrap(True);self.detail.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.detail)
        self.button=W.QPushButton(translate('Cancel job'))
        self.button.clicked.connect(self.request_close);layout.addWidget(self.button)

    def update_event(self,event):
        if event.get('message'):self.label.setText(str(event['message']))
        progress=event.get('progress')
        if type(progress) in (int,float):
            self.bar.setRange(0,100)
            self.bar.setValue(max(0,min(100,round(progress*100))))

    def finish(self,message,ok):
        self.running=False
        self.label.setText(message)
        self.bar.setRange(0,100);self.bar.setValue(100 if ok else 0)
        self.button.setEnabled(True);self.button.setText(self.tr_text('Close'))

    def request_close(self):
        if self.running:
            self.cancel_job();self.button.setEnabled(False)
            self.label.setText(self.tr_text('Cancelling — waiting for owned processes and cleanup…'))
        else:self.accept()

    def reject(self):
        # QDialog routes Escape here directly, bypassing closeEvent.
        if self.running:self.request_close()
        else:super().reject()

    def closeEvent(self,event):
        if self.running:
            self.request_close();event.ignore()
        else:event.accept()
