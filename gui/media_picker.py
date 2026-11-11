"""Reusable catalog picker; previews remain in memory until explicitly exported."""
from PySide6 import QtCore,QtGui,QtWidgets as W

class ImagePicker(W.QDialog):
    def __init__(self,images,parent=None,*,title='Game images',selected_id=None):
        super().__init__(parent);self.setWindowTitle(title);self.resize(820,570);self.selected_id=None
        layout=W.QVBoxLayout(self);self.search=W.QLineEdit();self.search.setPlaceholderText('Filter images / archive');layout.addWidget(self.search)
        row=W.QHBoxLayout();layout.addLayout(row,1)
        self.list=W.QListWidget();self.list.setViewMode(W.QListView.IconMode);self.list.setIconSize(QtCore.QSize(128,90));self.list.setResizeMode(W.QListView.Adjust);self.list.setWordWrap(True);row.addWidget(self.list,2)
        self.preview=W.QLabel();self.preview.setMinimumWidth(260);self.preview.setAlignment(QtCore.Qt.AlignCenter);self.preview.setWordWrap(True);row.addWidget(self.preview,1)
        self.images={item['id']:item for item in images};self.pixmaps={}
        for image in images:
            pix=QtGui.QPixmap();pix.loadFromData(image.get('preview_png',b''),'PNG');self.pixmaps[image['id']]=pix
            item=W.QListWidgetItem(QtGui.QIcon(pix),image.get('label',image['id']));item.setData(QtCore.Qt.UserRole,image['id']);item.setToolTip(image['id']);self.list.addItem(item)
            if image['id']==selected_id:self.list.setCurrentItem(item)
        self.buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel);layout.addWidget(self.buttons);self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        self.search.textChanged.connect(self._filter);self.list.currentItemChanged.connect(self._select);self.list.itemDoubleClicked.connect(lambda _:self.accept());self._select(self.list.currentItem())
    def _filter(self,text):
        for i in range(self.list.count()):
            item=self.list.item(i);item.setHidden(text.casefold() not in (item.text()+' '+item.toolTip()).casefold())
        if self.list.currentItem() and self.list.currentItem().isHidden():self.list.setCurrentItem(None)
    def _select(self,item,*_):
        self.selected_id=item.data(QtCore.Qt.UserRole) if item else None
        self.buttons.button(W.QDialogButtonBox.Ok).setEnabled(bool(self.selected_id))
        if item:
            pix=self.pixmaps[self.selected_id];self.preview.setPixmap(pix.scaled(290,310,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation));self.preview.setToolTip(self.selected_id)
        else:self.preview.clear()
    def accept(self):
        if self.selected_id:super().accept()

_player=None

def stop_audio():
    global _player
    import sys
    if sys.platform=='win32':
        import winsound
        winsound.PlaySound(None,0)
    elif _player is not None:_player.stop()

def play_wav(path,parent=None):
    """Windows stdlib playback works in portable builds without QtMultimedia."""
    global _player
    import sys
    stop_audio()
    if sys.platform=='win32':
        import winsound
        winsound.PlaySound(str(path),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
    else:
        from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
        _player=QMediaPlayer(parent);output=QAudioOutput(_player);_player.setAudioOutput(output);_player._output=output
        _player.setSource(QtCore.QUrl.fromLocalFile(str(path)));_player.play()
