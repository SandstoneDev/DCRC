"""A single, automatically saved UTF-8 log for a converter session."""
from datetime import datetime
import os
from pathlib import Path
import sys
import threading
import uuid


class SessionLog:
    def __init__(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.path = folder / f'DCRC_{stamp}_{os.getpid()}_{uuid.uuid4().hex[:6]}.log'
        self.path.touch(exist_ok=False)
        self.lock = threading.Lock()
        self.write('DCRC Converter session started')
        self.write('Log file: ' + str(self.path.resolve()))

    def write(self, message):
        stamp = datetime.now().isoformat(timespec='seconds')
        text = str(message).rstrip()
        with self.lock, self.path.open('a', encoding='utf8', newline='\n') as stream:
            stream.write(f'[{stamp}] {text}\n')

    def event(self, event):
        # CommandRunner already appended these bytes to this exact session file.
        if event.get('log_path') == str(self.path):
            return
        kind = event.get('type', 'log')
        message = event.get('message') or event.get('stage')
        if message:
            self.write(message)
        detail = event.get('detail')
        if detail and detail != message:
            self.write(detail)
        if kind in ('finished', 'cancelled'):
            # Results may include image/audio bytes. Only record status here.
            self.write(kind)


def start_app_log(settings_path=None):
    """Keep portable logs beside the app; explicit settings remain isolated."""
    if settings_path is not None:
        return SessionLog(Path(settings_path).parent/'logs')
    bundle = Path(sys.executable).resolve().parent.parent
    if (Path(__file__).resolve()==bundle/'app/gui/session_log.py'
            and (bundle/'BUNDLE_MANIFEST.json').is_file() and (bundle/'app/gui/run_gui.py').is_file()):
        try:
            return SessionLog(bundle/'logs')
        except OSError:
            pass
    folder = Path(os.environ.get('APPDATA', str(Path.home()/'.config')))/'DCRC Converter'/'logs'
    return SessionLog(folder)
