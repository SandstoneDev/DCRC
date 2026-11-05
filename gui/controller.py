"""Qt-independent GUI boundary: typed settings and an owned cooperative worker."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import threading
import traceback
from dcrc.models import STAGES, CHARACTERS

DEFAULTS = dict(world_textures=64, land_distance=100, aspect='wide', frame_skip='auto',
                mip_levels=8, show_fps=True, audio=True, voice='en',
                startup_stage='normal', startup_character='sonic', startup_act=1,
                title='DCRC Port', jobs=max(1, min(8, (os.cpu_count() or 2)-1)))


def settings_values(data):
    values = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    for key, choices in dict(world_textures=(0, 64, 128), aspect=('wide', '4:3'),
                             voice=('game', 'en', 'ja')).items():
        if values[key] not in choices:
            raise ValueError(f'Invalid {key}: {values[key]}')
    if type(values['world_textures']) is not int:
        raise ValueError('world_textures must be 0, 64 or 128')
    for key, low, high in (('land_distance', 100, 100), ('mip_levels', 1, 8),
                           ('startup_act', 1, 8), ('jobs', 1, 64)):
        if type(values[key]) is not int or not low <= values[key] <= high:
            raise ValueError(f'{key} must be {low}..{high}')
    for key in ('audio', 'show_fps'):
        if type(values[key]) is not bool:
            raise ValueError(f'{key} must be true or false')
    skip = str(values['frame_skip'])
    if skip not in ('auto', 'off') and skip not in tuple(map(str, range(2, 61))):
        raise ValueError('frame_skip must be auto, off or 2..60')
    values['frame_skip'] = skip
    if values['startup_stage'] not in STAGES:
        raise ValueError('Unsupported startup stage')
    if values['startup_character'] not in CHARACTERS:
        raise ValueError('Unsupported character')
    if not isinstance(values['title'], str) or not values['title'].strip():
        raise ValueError('Title must not be empty')
    return values


def load_settings(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class Task:
    """One non-daemon job. The UI must wait for cleanup before closing."""
    def __init__(self):
        self.thread = None
        self.cancel_event = threading.Event()
        self.messages = queue.Queue()

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, operation):
        if self.running:
            raise RuntimeError('A job is still running')
        self.cancel_event = threading.Event()
        def run():
            try:
                result = operation(self.post, self.cancel_event)
                self.post({'type': 'cancelled'} if self.cancel_event.is_set()
                          else {'type': 'finished', 'result': result})
            except Exception as error:
                self.post(dict(type='cancelled' if self.cancel_event.is_set() else 'error',
                               message=str(error), detail=traceback.format_exc()))
        self.thread = threading.Thread(target=run, name='DCRC converter worker', daemon=False)
        self.thread.start()

    def post(self, event):
        self.messages.put(dict(event) if isinstance(event, dict)
                          else {'type': 'log', 'message': str(event)})

    def cancel(self):
        self.cancel_event.set()

    def drain(self, maximum=200):
        rows = []
        for _ in range(maximum):
            try:
                rows.append(self.messages.get_nowait())
            except queue.Empty:
                break
        return rows
