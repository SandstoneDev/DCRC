"""Validated public conversion options; no dependency on GUI or private data."""
from dataclasses import dataclass, asdict
from pathlib import Path
import os
from .errors import ConverterError
from .storage import plain_path

STAGES=('normal','emerald_coast','station_square','windy_valley','twinkle_park',
 'speed_highway','red_mountain','sky_deck','lost_world','ice_cap','casinopolis',
 'final_egg','chaos0','chaos4','chaos6','egg_hornet','egg_viper','mystic_ruins',
 'egg_carrier_outside','egg_carrier_inside','sky_chase1','sky_chase2')
CHARACTERS=('sonic','tails','knuckles','amy','gamma','big')

@dataclass
class ConversionOptions:
    source: Path
    output: Path
    work: Path | None = None
    toolchain: Path | None = None
    profile: str = 'sa1_us_1005'
    world_textures: int = 64
    land_distance: int = 100
    aspect: str = 'wide'
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

    def validate(self, *, check_paths=True):
        self.source=plain_path(self.source)
        self.output=plain_path(self.output)
        self.work=plain_path(self.work) if self.work else self.output.parent/'.dcrc-work'
        self.toolchain=Path(self.toolchain).expanduser().resolve() if self.toolchain else None
        self.dlc_dir=plain_path(self.dlc_dir) if self.dlc_dir else None
        def require(ok, message):
            if not ok: raise ConverterError('options',message)
        if check_paths:require(self.source.exists(),'The disc image or extracted folder does not exist.')
        require(self.profile=='sa1_us_1005','This converter supports the sa1_us_1005 profile only.')
        require(self.world_textures in (0,64,128),'World texture size must be original (0),64 or128.')
        require(type(self.land_distance) is int and self.land_distance==100,'This reviewed TA source profile supports full static distance100 only.')
        require(self.aspect in ('wide','4:3'),'Aspect must be wide or4:3.')
        self.frame_skip=str(self.frame_skip)
        require(self.frame_skip in ('auto','off') or self.frame_skip.isascii() and self.frame_skip.isdecimal() and 2<=int(self.frame_skip)<=60,'Frame skip must be auto, off, or2..60.')
        require(type(self.mip_levels) is int and 1<=self.mip_levels<=8,'Mip levels must be1..8.')
        require(type(self.show_fps) is bool and type(self.audio) is bool,'FPS and audio options must be booleans.')
        require(self.voice in ('en','ja','game'),'Voice must be en, ja or game.')
        require(self.startup_stage in STAGES,'Unsupported startup stage.')
        require(self.startup_character in CHARACTERS,'Unsupported startup character.')
        require(type(self.startup_act) is int and 1<=self.startup_act<=8,'Startup act must be1..8.')
        require(type(self.jobs) is int and 1<=self.jobs<=64,'Parallel jobs must be1..64.')
        require(isinstance(self.title,str) and 1<=len(self.title.encode('utf-8'))<=127 and not any(ord(c)<32 for c in self.title),'Invalid PSP menu title.')
        if check_paths:
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
