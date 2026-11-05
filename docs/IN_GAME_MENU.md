# PSP control menu

Open with **L + R + Cross + Down**. Release the entire chord before using
Start or Select: custom firmware also sees physical buttons and cannot be
filtered by a game. This matches the inspected PS2RC interaction; the menu
implementation is original DCRC code.

The owning game thread pauses at a completed rendering boundary. The menu uses
its own synchronous GE pass and the externally installed PSPSDK font. It does
not advance guest gameplay, write pixels through the CPU or count menu pictures
as game FPS. Menu-open/close logs identify pauses for hardware measurements.

- D-pad: choose/change; L/R: page; Cross: action; Circle: close/back.
- Start: save with byte readback; Select: restore the opening values for this
  session; Triangle: default the focused row; Square: help.
- Graphics: 4:3/16:9, FPS, frame skip and mip count. Mip count affects newly
  loaded textures. World texture resolution is selected during conversion.
- Audio: mixer on/off and voice language. The next voice starts in that language.
- Gameplay: stage/act/character and explicit save/restart. Ordinary resource and
  collision loading handles the new selection. Arbitrary character/stage routes
  are not all supported. Startup CLI overrides disable this restart action;
  remove them from args.txt if the INI/menu should control startup.
- Cheats: refill rings/lives to99 or keep them refilled, default off. The first
  supported admission is stable Sonic/Emerald Coast act1, ordinary play substate.
  Unknown/loading/menu states decline; no unproved invulnerability/noclip writes.
- DLC: one opaque event or off. See below; selection is not instant activation.

Settings are in `data/sa1psp.ini`, including `aspect = 4:3` or `aspect = 16:9`,
`fps_hud`, `frame_skip`, `mip_levels`, `audio`, `voice`, `start_stage`, `start_act`,
`start_character` and `dlc_event`. The converter keeps these out of its ordinary
args.txt so an explicit CLI flag is a real override. Unknown INI keys/comments
are retained by menu saves. A verified previous INI is kept in a transaction
backup. Failed save never uses an in-place fallback. Cheats do not persist.

Live aspect changes update only the known ordinary guest clip rectangle along
with the backend projection. A custom/uninitialized rectangle declines the live
change; use the INI before launch. Wide fills reviewed boot/frontend screens;
gameplay uses Hor+ while its HUD proportions remain unchanged. Frontend art/text
is expanded horizontally. 4:3 keeps the complete image with side pillars.

Menu restarts require a `DCRC_` app folder, an installed chain helper and no
active profiler/resident crash-screen module. Ordinary menu-enabled PSP runs
omit that kernel crash-screen module. Strict replays, headless/no-pad tests and
saved-state resume disable the menu. HOME retains the ordinary cleanup/exit.

## User-supplied download events

Pass `--dlc-dir "<own-extracted-events-folder>"` during conversion or select the
optional DLC folder in the converter window. No DLC is downloaded or bundled.
The US profile imports valid `SONICADV_5xx` VMI/VMS pairs, reports unsupported
files, keeps distinct variants and verifies copied files with SHA256 and size.

The local output has `data/dlc/events.txt`, with bounded ASCII lines:

```text
Event label|dlc/events/event00.vmi|dlc/events/event00.vms
```

Paths are relative to data. The mount validates outer VMI/VMS metadata and optional
container CRC. It does not decrypt or interpret the event payload. The original
game functions generated from the user's image do that locally. The selected
event is a read-only VMU overlay; ordinary player files remain in the base VMU.
At most32 catalogue entries and one mounted event are supported.

Activation requires normal boot and ordinary VMU/file selection, followed by
the game's next ordinary scene load. A fresh boot warp skips that selection;
the menu declines a direct warp while an event is selected. Choose normal boot,
select the VMU/save and play to the relevant scene. Off unmounts the event;
objects already spawned by it leave only when the game unloads the scene. Base
VMU files, including any independent existing event, are not deleted by off.
Strict/resumed runs do not mount it. Hardware activation/quality must be tested
separately; a selected/mounted file alone is not evidence of visible activation.

Event references: [Dreamcast Live's Sonic Adventure catalogue](https://dreamcastlive.net/sonic-adventure-dlc/)
and [Sonic Retro's Downloadable Events reference](https://info.sonicretro.org/Sonic_Adventure_Downloadable_Events).
They are credited references; event data is supplied by the user, not distributed
with this repository. Research maintainer sources when a reference is unavailable.
