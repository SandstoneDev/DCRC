"""Own palette-based Fusion themes; no fixed background images or external assets."""
from PySide6 import QtGui, QtWidgets

_system_palette = None


def apply_theme(choice):
    global _system_palette
    app = QtWidgets.QApplication.instance()
    if _system_palette is None:
        _system_palette = QtGui.QPalette(app.palette())
    app.setStyle('Fusion')
    p = QtGui.QPalette(_system_palette)
    if choice == 'dark':
        colors = dict(Window='#20242b', WindowText='#edf0f6', Base='#151920',
                      AlternateBase='#272d36', Text='#edf0f6', Button='#303844',
                      ButtonText='#edf0f6', Highlight='#337fc1', HighlightedText='#ffffff',
                      ToolTipBase='#edf0f6', ToolTipText='#151920', PlaceholderText='#aeb8c8')
    elif choice == 'light':
        colors = dict(Window='#f2f4f7', WindowText='#192332', Base='#ffffff',
                      AlternateBase='#e8edf4', Text='#192332', Button='#e2e8f0',
                      ButtonText='#192332', Highlight='#246ab0', HighlightedText='#ffffff',
                      ToolTipBase='#ffffff', ToolTipText='#192332', PlaceholderText='#58677b')
    else:
        colors = {}
    for role, color in colors.items():
        p.setColor(getattr(QtGui.QPalette.ColorRole, role), QtGui.QColor(color))
    if colors:
        muted = QtGui.QColor('#8e9aab' if choice == 'dark' else '#677487')
        for role in (p.ColorRole.Text, p.ColorRole.WindowText, p.ColorRole.ButtonText):
            p.setColor(p.ColorGroup.Disabled, role, muted)
    app.setPalette(p)
    app.setStyleSheet('QGroupBox{font-weight:600;margin-top:8px;padding-top:8px}'
                      'QPushButton{padding:5px 9px} QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox{padding:3px}'
                      'QPushButton[stepCurrent="true"]{background:#286fa8;color:white;font-weight:600}'
                      'QPushButton[stepDone="true"]{border-bottom:2px solid #479d70}')
