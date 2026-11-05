"""Source contract: HOME callback only requests; owning frame hook performs exit."""
from pathlib import Path
import re
s = (Path(__file__).resolve().parents[2] / 'backend/psp/main_psp.c').read_text()
callback = re.search(r'static int exit_callback\([^)]*\)\s*\{(.*?)\n\}', s, re.S).group(1)
assert 'home_exit_requested = 1' in callback
assert not any(x in callback for x in ('sa1_log(', 'prof_stop(', 'plat_log_close(', 'sceKernelExitGame(', 'report_and_exit('))
on_frame = re.search(r'static void on_frame\([^)]*\)\s*\{(.*?)\n\}', s, re.S).group(1)
assert on_frame.index('home_exit_requested') < on_frame.index('pace(frame)')
assert 'report_and_exit(0)' in on_frame
worker = re.search(r'static int callback_thread\([^)]*\)\s*\{(.*?)\n\}', s, re.S).group(1)
assert 'sceKernelDelayThreadCB(100000)' in worker
assert 'deadline = sa1_plat_time_us() + 5000000u' in worker
assert 'sceKernelExitGame()' in worker
assert not any(x in worker for x in ('sa1_log(', 'plat_log_close(', 'report_and_exit(', 'audio_close(', 'draw_shutdown('))
print('HOME owning-thread source contract PASS')
