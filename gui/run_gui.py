"""Entry point works from source and an isolated portable Python ._pth."""
from pathlib import Path
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.path.insert(0, str(ROOT))
for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
    os.environ.pop(key, None)


def main():
    from gui.session_log import start_app_log
    session_log=start_app_log()
    try:
        from gui.app import main as start
        return start(session_log=session_log)
    except Exception:
        log=session_log.path
        session_log.write(traceback.format_exc())
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'DCRC Converter could not start.\n\n' + str(log),
                                            'DCRC Converter', 0x10)
        else:
            sys.stderr.write(log.read_text(encoding='utf8'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
