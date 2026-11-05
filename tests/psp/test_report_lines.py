"""New measurement records must fit the actual 256-byte sa1_log buffer."""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[2]
formats = []
for rel in ('backend/psp/draw_gu.c', 'backend/psp/audio_psp.c'):
    source = (root / rel).read_text(encoding='utf-8')
    for fmt in re.findall(r'sa1_log\("([^"\n]+)"', source):
        if not fmt.startswith(('display:', 'display-state:', 'audio-output:', 'audio-wait:')):
            continue
        # Counters are uint32_t/uint64_t; the %d values here are boolean.
        largest = re.sub(r'%llu', '9' * 20, fmt)
        largest = re.sub(r'%u', '9' * 10, largest)
        largest = re.sub(r'%d', '1', largest)
        assert '%' not in largest, fmt
        formats.append((rel, fmt.split(':')[0], len(largest)))
        assert len(largest) < 256, (rel, len(largest), fmt)
assert len(formats) == 4, formats
print('measurement log record bounds PASS:', formats)
