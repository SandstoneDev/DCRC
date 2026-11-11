"""Own 480x272 XMB composition preview. Game previews stay in memory."""
from PySide6 import QtCore, QtGui, QtWidgets


def file_image(path):
    reader = QtGui.QImageReader(path)
    size = reader.size()
    if not size.isValid() or size.width()*size.height() > 16000000:
        return QtGui.QImage()
    reader.setAutoTransform(True)
    reader.setScaledSize(size.scaled(480, 272, QtCore.Qt.KeepAspectRatio))
    return reader.read()


def _draw_fit(painter,target,image):
    """Center crop source geometry like leaf ImageOps.fit(centering=(.5,.5)).

    Preview resampling uses Qt; this promises the same crop/framing, not
    bit-exact agreement between Qt filtering and Pillow's Lanczos kernel.
    """
    target=QtCore.QRectF(target)
    scale=max(target.width()/image.width(),target.height()/image.height())
    width,height=target.width()/scale,target.height()/scale
    source=QtCore.QRectF((image.width()-width)*.5,(image.height()-height)*.5,width,height)
    painter.drawImage(target,image,source)


class Preview(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(480, 272)
        self.background = QtGui.QImage()
        self.icon = QtGui.QImage()
        self.title = 'DCRC Port'
        self.border = False

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform,True)
        p.fillRect(self.rect(), QtGui.QColor('#17273b'))
        if not self.background.isNull():
            p.fillRect(self.rect(),QtGui.QColor('black'))
            if self.border:
                # DBR1 encoding resizes the whole image, unlike XMB slot crop.
                p.drawImage(self.rect(),self.background)
            else:_draw_fit(p,self.rect(),self.background)
        if self.border:
            p.fillRect(60,0,360,272,QtGui.QColor('#080a0d'))
            p.setPen(QtGui.QColor('white'))
            p.drawText(QtCore.QRect(60,0,360,272),QtCore.Qt.AlignCenter,'4:3 · 360 × 272')
            p.end()
            return
        p.fillRect(0, 0, 480, 40, QtGui.QColor(0, 0, 0, 120))
        p.setPen(QtGui.QColor('white'))
        p.drawText(20, 27, 'PSP  /  Game')
        if not self.icon.isNull():
            target=QtCore.QRect(35,89,144,80)
            p.fillRect(target,QtGui.QColor('black'))
            _draw_fit(p,target,self.icon)
        else:
            p.setPen(QtGui.QColor('#b6cde6'))
            p.drawRect(35, 89, 144, 80)
        p.setPen(QtGui.QColor('white'))
        p.drawText(QtCore.QRect(198, 92, 263, 80), QtCore.Qt.TextWordWrap, self.title)
        p.end()
