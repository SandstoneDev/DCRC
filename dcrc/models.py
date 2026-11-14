"""Validated public conversion options; no dependency on GUI or private data."""
from dataclasses import dataclass, asdict, field
from pathlib import Path
import os
import math
import re
from .errors import ConverterError
from .storage import plain_path, windows_native_path_too_long
from .capabilities import PROFILE_CAPABILITIES

STAGES=('normal','emerald_coast','station_square','windy_valley','twinkle_park',
 'speed_highway','red_mountain','sky_deck','lost_world','ice_cap','casinopolis',
 'final_egg','chaos0','chaos4','chaos6','egg_hornet','egg_viper','mystic_ruins',
 'egg_carrier_outside','egg_carrier_inside','sky_chase1','sky_chase2')
CHARACTERS=('sonic','tails','knuckles','amy','gamma','big')

# Reserve space for the deepest build file, including the temporary stamp
# extension and both the stage digest and run ID.
_BUILD_STAMP = (Path('stages/build') / ('0' * 64) / ('run_' + '0' * 32) /
                'build/obj/sa1_game_psp.dir/generated/overlays/emitter/al_garden00' /
                'ovl_al_garden00_table.c.o.json.part')


def default_work_folder(output):
    adjacent = output.parent / '.dcrc-work'
    if not windows_native_path_too_long(adjacent / _BUILD_STAMP):
        return adjacent
    home = Path.home()
    local = Path(os.environ.get('LOCALAPPDATA') or home / 'AppData' / 'Local') / 'DCRC' / 'work'
    for fallback in (local, home / '.dcrc-work'):
        if not windows_native_path_too_long(fallback / _BUILD_STAMP):
            work = plain_path(fallback)
            if not windows_native_path_too_long(work / _BUILD_STAMP):
                return work
    raise ConverterError('native-work-path',
        'The build files would exceed the Windows path limit. Choose a short work folder near the drive root.',
        'Use Output > Advanced build options > Work folder, or set --work in the CLI.')

@dataclass
class ConversionOptions:
    source: Path
    output: Path
    work: Path | None = None
    toolchain: Path | None = None
    profile: str = 'sa1_us_1005'
    world_textures: int = 64
    land_distance: int = 100
    aspect: str = '16:9'
    frame_skip: str = 'auto'
    mip_levels: int = 8
    show_fps: bool = True
    audio: bool = True
    voice: str = 'en'
    startup_stage: str = 'normal'
    startup_character: str = 'sonic'
    startup_act: int = 1
    title: str = 'DCRC Port'
    jobs: int = min(8,max(1,(os.cpu_count() or 2)-1))
    dlc_dir: Path | None = None
    border_image: Path | None = None
    movies: bool = False
    ffmpeg: Path | None = None
    border_mode: str | None = None
    xmb_icon_mode: str = 'none'
    xmb_icon_art: str = 'title'
    xmb_icon_file: Path | None = None
    xmb_background_mode: str = 'none'
    xmb_background_art: str = 'title'
    xmb_background_file: Path | None = None
    xmb_music_mode: str = 'none'
    xmb_music_file: Path | None = None
    xmb_track: str = 'TITLE.ADX'
    xmb_music_start: float = 0.0
    xmb_music_seconds: float = 6.0
    xmb_encoder: Path | None = None
    control_map: dict = field(default_factory=dict)
    dither: str = 'on'

    def validate(self, *, check_paths=True):
        from .controls import validate_control_map
        self.control_map=validate_control_map(self.control_map)
        self.source=plain_path(self.source)
        self.output=plain_path(self.output)
        if check_paths:
            self.work=plain_path(self.work) if self.work else default_work_folder(self.output)
        self.toolchain=Path(self.toolchain).expanduser().resolve() if self.toolchain else None
        self.dlc_dir=plain_path(self.dlc_dir) if self.dlc_dir else None
        self.border_image=plain_path(self.border_image) if self.border_image and self.border_mode not in ('default','orbit') else None
        self.ffmpeg=plain_path(self.ffmpeg) if self.ffmpeg else None
        for kind in ('icon','background','music'):
            name='xmb_'+kind+'_file'
            value=getattr(self,name)
            setattr(self,name,plain_path(value) if value and getattr(self,'xmb_'+kind+'_mode')=='file' else None)
        needs_encoder=self.xmb_music_mode=='game' or (self.xmb_music_mode=='file' and self.xmb_music_file is not None and self.xmb_music_file.suffix.lower()!='.at3')
        self.xmb_encoder=plain_path(self.xmb_encoder) if self.xmb_encoder and needs_encoder else None
        def require(ok, message):
            if not ok: raise ConverterError('options',message)
        if check_paths:require(self.source.exists(),'The disc image or extracted folder does not exist.')
        require(self.profile=='sa1_us_1005','This converter supports the sa1_us_1005 profile only.')
        require(self.world_textures in (0,64,128),'World texture size must be original (0),64 or128.')
        require(type(self.land_distance) is int and self.land_distance==100,'This reviewed TA source profile supports full static distance100 only.')
        if self.aspect=='wide':self.aspect='16:9' # Existing player settings remain readable.
        require(self.aspect in ('16:9','4:3'),'Aspect must be16:9 or4:3.')
        if self.border_mode is None:self.border_mode='custom' if self.border_image else 'none'
        require(self.border_mode in ('none','custom') and (self.border_mode=='none' and self.border_image is None or PROFILE_CAPABILITIES['custom_border'] and self.border_mode=='custom'),'Custom borders are unavailable or invalid for this public TA runtime.')
        require(self.dither in ('on','opaque','off') and (self.dither=='on' or PROFILE_CAPABILITIES['configurable_dither']),'Configurable dithering is unavailable or invalid for this public TA runtime.')
        for name in ('xmb_icon_mode','xmb_background_mode','xmb_music_mode'):
            require(getattr(self,name) in ('game','file','none'),'XMB source must be game, file or none.')
        for name in ('xmb_icon_art','xmb_background_art'):
            from .media import valid_artwork_id
            require(valid_artwork_id(getattr(self,name)),'Choose a known game artwork ID.')
        for name,lo,hi in (('xmb_music_start',0,7200),('xmb_music_seconds',1,10)):
            value=getattr(self,name)
            require(type(value) in (int,float) and math.isfinite(value) and lo<=value<=hi,'Invalid XMB music time range.')
            setattr(self,name,float(value))
        require(isinstance(self.xmb_track,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]+\.ADX',self.xmb_track,re.I)),
                'Choose an ADX filename from the game music catalog.')
        self.frame_skip=str(self.frame_skip)
        require(self.frame_skip in ('auto','off') or self.frame_skip.isascii() and self.frame_skip.isdecimal() and 2<=int(self.frame_skip)<=60,'Frame skip must be auto, off, or2..60.')
        require(type(self.mip_levels) is int and 1<=self.mip_levels<=8,'Mip levels must be1..8.')
        require(type(self.show_fps) is bool and type(self.audio) is bool,'FPS and audio options must be booleans.')
        require(type(self.movies) is bool and (not self.movies or PROFILE_CAPABILITIES['movie_playback']),'FMV playback is unavailable or invalid for this public TA runtime.')
        require(self.voice in ('en','ja','game'),'Voice must be en, ja or game.')
        require(self.startup_stage in STAGES,'Unsupported startup stage.')
        require(self.startup_character in CHARACTERS,'Unsupported startup character.')
        require(type(self.startup_act) is int and 1<=self.startup_act<=8,'Startup act must be1..8.')
        require(type(self.jobs) is int and 1<=self.jobs<=64,'Parallel jobs must be1..64.')
        require(isinstance(self.title,str) and 1<=len(self.title.encode('utf-8'))<=127 and not any(ord(c)<32 for c in self.title),'Invalid PSP menu title.')
        if check_paths:
            for kind in ('icon','background','music'):
                path=getattr(self,'xmb_'+kind+'_file')
                if getattr(self,'xmb_'+kind+'_mode')=='file':
                    require(path is not None and path.is_file(),'Choose an existing XMB '+kind+' file.')
                if path is not None:
                    require(not path.is_relative_to(self.output) and not path.is_relative_to(self.work),
                            'Read-only XMB inputs must be outside output and work folders.')
            require(self.xmb_encoder is None or self.xmb_encoder.is_file(),'The external ATRAC encoder does not exist.')
            require(self.border_mode!='custom' or self.border_image is not None,'Choose a custom4:3 border image.')
            require(self.border_image is None or self.border_image.is_file(),'The optional border image does not exist.')
            if self.border_image:
                require(not self.border_image.is_relative_to(self.output) and not self.border_image.is_relative_to(self.work),
                        'The read-only border image must be outside output and work folders.')
            require(self.dlc_dir is None or self.dlc_dir.is_dir(),'The optional DLC folder does not exist.')
            if self.dlc_dir:
                require(not self.output.is_relative_to(self.dlc_dir) and not self.work.is_relative_to(self.dlc_dir),
                        'Output/work must be outside the read-only DLC source folder.')
                require(not self.dlc_dir.is_relative_to(self.output),'DLC input must be outside the output folder.')
            require(self.output!=self.work and not self.work.is_relative_to(self.output),'The work directory must be outside the PSP output folder.')
            require(not self.source.is_relative_to(self.output),'The input must not be inside the output folder.')
            require(not self.source.is_dir() or not self.output.is_relative_to(self.source),'The output must not be inside the input folder.')
            require(not self.source.is_dir() or not self.work.is_relative_to(self.source),'The work directory must not be inside the input folder.')
            require(self.output.parent!=self.output,'A drive root is not a PSP game folder.')
        return self

    def to_dict(self):
        return {k:str(v) if isinstance(v,Path) else v for k,v in asdict(self).items()}
