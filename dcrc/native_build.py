"""Own shell-free PSP build adapter for the Sonic runtime's CMake contract.

Runtime sources remain under their upstream MIT licence. This module does not
ship generated game code or copy the PS2RC converter implementation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import struct

from .errors import ConverterError
from .storage import windows_native_path_too_long
from .toolchain import resolve

BACKEND = ('platform_psp.c', 'coro_psp.c', 'draw_gu.c', 'crash_psp.c', 'main_psp.c',
           'chain_psp.c', 'savestate_psp.c', 'vmu_store_psp.c', 'audio_psp.c', 'debug_psp.c', 'movie_psp.c')
HOT_CHUNKS = {'game_001', 'game_002', 'game_003', 'game_004', 'game_005', 'game_007',
              'game_008', 'game_015', 'game_030'}
WRAPS = ('8c037350', '8c0376d0', '8c028d0a', '8c028ec2', '8c02d2e0',
         '8c029b00', '8c029400', '8c091380')
SUPPORT = Path(__file__).resolve().parents[1]/'converter'/'support'


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.part')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    temp.replace(path)


def wrap_defines(header):
    result = ['SA1_WRAP_' + a.upper() for a in WRAPS if 'fn_' + a + '_orig' in header]
    if all('fn_' + a + '_orig' in header for a in ('8c011060', '8c011a84')):
        result.append('SA1_WRAP_DLC')
    if 'fn_8c051e56_orig' in header:
        result.append('SA1_WRAP_LAND_DISTANCE')
    return result


def link_order(text):
    """Preserve CMake's hot placement and five 8KB data alignment clauses."""
    hot, game, end = '', '', ''
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        pad = lambda a: '    . = . + ((' + a + ' - .) & 0x3fff);\n'
        if m := re.fullmatch(r'=@(0x[0-9a-fA-F]+)', line):
            end = pad(m[1]) + '    sa1_obj_end = .;\n'
        elif m := re.fullmatch(r'=([^ ]+)(?: +@(0x[0-9a-fA-F]+))?', line):
            sym = re.sub(r'[^A-Za-z0-9_]', '_', m[1])
            if sym[0].isdigit():
                sym = '_' + sym
            game += (pad(m[2]) if m[2] else '')
            game += '    sa1_obj_' + sym + ' = .;\n    *sa1_game_psp.dir/*/' + m[1] + '.o*(.text .text.*)\n'
        elif m := re.fullmatch(r'@(0x[0-9a-fA-F]+)', line):
            hot += pad(m[1])
        elif m := re.fullmatch(r'([^:]+\.a):([^:]+)', line):
            hot += '    *' + m[1] + ':' + m[2] + '(.text .text.*)\n'
        elif m := re.fullmatch(r'([^:]+):([^:]+)', line):
            hot += '    */' + m[1] + '.o*(.text.' + m[2] + ')\n'
        else:
            hot += '    *(EXCLUDE_FILE(*seam_stubs.c.o*) .text.' + line + ')\n'
    order = ''
    if text:
        order = ('.text : {\n    . = ALIGN(64);\n' + hot + '    . = ALIGN(64);\n'
                 '    *.a:*(.text .text.*)\n' + game +
                 '    *sa1_game_psp.dir/*(.text .text.*)\n' +
                 (end or ('    sa1_obj_end = .;\n' if game else '')) + '}\n')
    ro = '.rodata .rodata.[!sc]* .rodata.s[!t]* .rodata.st[!r]* .rodata.c[!s]* .rodata.cs[!t]*'
    for name, inputs in (('.rodata', ro), ('.data', '.data .data.*'), ('.sdata', '.sdata .sdata.*'),
                         ('.sbss', '.sbss .sbss.* .scommon'), ('.bss', '.bss .bss.* COMMON')):
        order += (name + ' : {\n    . = ALIGN(0x2000);\n    *sa1_game_psp.dir/*(' + inputs + ')\n'
                  '    *.a:*(' + inputs + ')\n    *(' + inputs + ')\n}\n')
    return order


def make_pbp(elf, title='DCRC Port', icon=b'', *, pic1=b'', snd0=b''):
    """Encode public PBP/SFO layouts; no external packer or game artwork."""
    if not isinstance(title, str) or not title or '\0' in title or len(title.encode('utf8')) > 127:
        raise ConverterError('title', 'The PSP title must contain 1..127 UTF-8 bytes without NUL.')
    fields = {'APP_VER': '00.04', 'BOOTABLE': 1, 'CATEGORY': 'MG', 'DISC_ID': 'DCRC00001',
              'DISC_VERSION': '1.00', 'MEMSIZE': 1, 'PARENTAL_LEVEL': 1,
              'PSP_SYSTEM_VER': '6.60', 'REGION': 0x8000, 'TITLE': title}
    keys, values, records = bytearray(), bytearray(), []
    for key, value in sorted(fields.items()):
        ko = len(keys)
        keys.extend(key.encode('ascii') + b'\0')
        raw = struct.pack('<I', value) if isinstance(value, int) else value.encode('utf8') + b'\0'
        capacity = (len(raw) + 3) & ~3
        records.append(struct.pack('<HHIII', ko, 0x404 if isinstance(value, int) else 0x204,
                                   len(raw), capacity, len(values)))
        values.extend(raw + bytes(capacity - len(raw)))
    key_offset = 20 + 16 * len(records)
    value_offset = (key_offset + len(keys) + 3) & ~3
    sfo = (struct.pack('<5I', 0x46535000, 0x101, key_offset, value_offset, len(records)) +
           b''.join(records) + keys + bytes(value_offset - key_offset - len(keys)) + values)
    parts = (bytes(sfo), bytes(icon), b'', b'', bytes(pic1), bytes(snd0), bytes(elf), b'')
    offsets, cursor = [], 40
    for part in parts:
        offsets.append(cursor)
        cursor += len(part)
    return b'\0PBP' + struct.pack('<9I', 0x10000, *offsets) + b''.join(parts)


def inspect_elf(data):
    """Validate ELF32 MIPS ranges and report actual import descriptors/NIDs."""
    def require(ok, message):
        if not ok:
            raise ConverterError('native-artifact', message)
    require(len(data) >= 52 and data[:6] == b'\x7fELF\x01\x01', 'Not a little-endian ELF32 artifact.')
    kind, machine = struct.unpack_from('<HH', data, 16)
    require(machine == 8 and kind in (2, 0xFFA0), 'Artifact is not an executable PSP MIPS ELF.')
    entry, phoff, shoff = struct.unpack_from('<III', data, 24)
    phsize, phcount, shsize, shcount, names = struct.unpack_from('<5H', data, 42)
    require(shsize == 40 and shcount > 0 and shoff + shsize*shcount <= len(data), 'Invalid ELF section table.')
    require(phsize in (0, 32) and phoff + phsize*phcount <= len(data), 'Invalid ELF program table.')
    rows = [struct.unpack_from('<10I', data, shoff+i*40) for i in range(shcount)]
    require(names < shcount, 'Invalid ELF section-name table.')
    for row in rows:
        require(row[1] == 8 or row[4] + row[5] <= len(data), 'ELF section exceeds artifact.')
    n = rows[names]
    strings = data[n[4]:n[4]+n[5]]
    def string(raw, offset):
        require(offset < len(raw), 'ELF string outside table.')
        stop = raw.find(b'\0', offset)
        require(stop >= 0, 'Unterminated ELF string.')
        return raw[offset:stop].decode('ascii', errors='strict')
    sections = {string(strings, row[0]): row for row in rows}
    def memory(addr, size):
        for row in rows:
            if row[1] != 8 and row[3] <= addr and addr + size <= row[3] + row[5]:
                off = row[4] + addr - row[3]
                return data[off:off+size]
        raise ConverterError('native-artifact', 'Import pointer outside ELF sections.')
    imports = []
    if stub := sections.get('.lib.stub'):
        pos, end = stub[4], stub[4]+stub[5]
        while pos < end:
            require(pos+20 <= end, 'Truncated PSP import record.')
            name, flags, length_count, nid, functions = struct.unpack_from('<5I', data, pos)
            words, count = length_count & 255, length_count >> 16
            require(words >= 5 and pos + words*4 <= end, 'Invalid PSP import record length.')
            library = bytearray()
            for i in range(256):
                c = memory(name+i, 1)
                if c == b'\0':
                    break
                library.extend(c)
            else:
                raise ConverterError('native-artifact', 'Unterminated PSP import library.')
            ids = struct.unpack('<' + 'I'*count, memory(nid, count*4)) if count else ()
            memory(functions, count*8) if count else None
            imports.append({'library': library.decode('ascii'), 'flags_version': flags,
                            'nids': ['%08X' % v for v in ids]})
            pos += words*4
    return {'machine': machine, 'type': kind, 'entry': entry, 'sections': len(rows), 'imports': imports}


def plan(source_root, generated, build_dir, toolchain):
    """Build argv descriptions only; reject incomplete game inputs before writes."""
    src, gen, dest = (Path(p).resolve() for p in (source_root, generated, build_dir))
    games = sorted((gen/'emitter').glob('game_[0-9]*.c'))
    overlays = sorted((gen/'overlays'/'emitter').glob('*/ovl_*.c'))
    table, header = gen/'emitter'/'game_table.c', gen/'emitter'/'game.h'
    if not games or not table.is_file() or not header.is_file() or not overlays:
        raise ConverterError('generated', 'Missing generated game/table/header/overlay sources; refusing a hello-only build.')
    tc = resolve(toolchain)
    common = ['-DPSP', '-D__PSP__', '-D_PSP_FW_VERSION=600', '-std=gnu11', '-Umips', '-Wno-format']
    sdk_inc = ['-I' + (tc.root/p).as_posix() for p in ('psp/include', 'psp/sdk/include')]
    runtime = src/'recomp'/'emitter'/'runtime'
    includes = ['-I' + p.as_posix() for p in (src/'hle', runtime, src/'backend')]
    hot_path = src/'tools'/'psp_hot_order.txt'
    hot = hot_path.read_text(encoding='utf8') if hot_path.is_file() else ''
    hle = []
    for part in ('', 'bios', 'shinobi', 'game', 'ninja', 'sound', 'overlay'):
        hle.extend(sorted((src/'hle'/part).glob('*.c')))
    hle.sort()  # CMake file(GLOB ...) sorts the combined result, across patterns.
    hle.append(runtime/'sh4_rt.c')
    backend = [src/'backend'/'psp'/name for name in BACKEND]
    backend += [src/'backend'/'desktop'/'input_tape.c', src/'backend'/'desktop'/'sha256.c', src/'backend'/'texpool.c']
    backend += [src/'backend'/'debug_menu.c',src/'backend'/'debug_config.c',src/'backend'/'movie_wav.c']
    definitions = ['-DSA1_OFF_AREA_TEST_ONLY'] + ['-D'+s for s in wrap_defines(header.read_text(encoding='utf8'))]
    units = []
    for group, sources in (('hle', hle), ('backend', backend), ('game', games+[table]+overlays)):
        for path in sources:
            if not path.is_file():
                raise ConverterError('runtime', 'Required runtime source is missing: ' + str(path))
            if windows_native_path_too_long(path):
                raise ConverterError('native-work-path',
                    'The PSP compiler source path is too long. Choose a short work folder near the drive root.',
                    'Use Output > Advanced build options > Work folder, or set --work in the CLI.')
            rel = path.relative_to(gen if group == 'game' else src)
            obj = dest/'obj'/('sa1_' + group + '_psp.dir')/('generated' if group == 'game' else 'source')/rel.parent/(rel.name+'.o')
            flags = common + includes + sdk_inc
            if group == 'hle':
                flags += definitions + ['-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-Wall', '-g']
                if path in (src/'hle'/'shinobi'/'cfg.c', src/'hle'/'bios'/'syscalls.c', src/'hle'/'sound'/'sd.c'):
                    flags += ['-DSA1_OFF_FULL']
            elif group == 'backend':
                flags += ['-O2', '-fno-strict-aliasing', '-Wall', '-g', '-I'+SUPPORT.as_posix()]
            else:
                flags = common + ['-I'+runtime.as_posix(), '-I'+(gen/'emitter').as_posix()] + includes + sdk_inc
                flags += ['-include', (runtime/'sh4_rt.h').as_posix(), '-DSA1_OFF_AREA_TEST_ONLY', '-Os',
                          '-fno-strict-aliasing', '-ffp-contract=off', '-Wall', '-Wno-unused-label',
                          '-Wno-unused-variable', '-Wno-unused-but-set-variable', '-Wno-parentheses']
            if hot:
                flags += ['-ffunction-sections']
            if group == 'game' and path.stem in HOT_CHUNKS:
                flags += ['-O2']
            units.append({'group':group, 'source':path, 'object':obj, 'flags':flags})
    units.append({'group':'import', 'source':SUPPORT/'kubridge_import.S',
                  'object':dest/'obj'/'kubridge_import.o', 'flags':sdk_inc})
    return {'source':src, 'generated':gen, 'dest':dest, 'toolchain':tc, 'units':units,
            'link_order':link_order(hot), 'counts':{'game':len(games), 'overlays':len(overlays),
            'hle':len(hle), 'backend':len(backend), 'imports':1}}


def _rsp(path, args):
    # GCC response files have their own escaping; paths are normalized to '/'.
    content = '\n'.join('"'+str(a).replace('\\','\\\\').replace('"','\\"')+'"' for a in args)+'\n'
    try:
        path.write_text(content, encoding='mbcs' if os.name == 'nt' else 'utf8', newline='\n')
    except UnicodeEncodeError as error:
        raise ConverterError('native-path', 'Native linker cannot represent a build path in the Windows codepage.',
                             'Choose an ASCII-only work folder and portable application location.') from error


def build_helpers(source_root, build_dir, toolchain, runner):
    src, dest, tc = Path(source_root).resolve(), Path(build_dir).resolve(), resolve(toolchain)
    dest.mkdir(parents=True, exist_ok=True)
    sdk = tc.root/'psp'/'sdk'
    includes = ['-I'+(tc.root/'psp'/'include').as_posix(), '-I'+(sdk/'include').as_posix()]
    libs = ['-nostdlib', '-lpspdebug', '-lpspdisplay_driver', '-lpspctrl_driver', '-lpspmodinfo', '-lpspsdk', '-lpspkernel']
    outputs = {}
    for part, filename, extra, fw in (('exc','sa1exc.c',['-lpspdebug','-lpspge_driver','-lgcc'],600),
                                     ('chain','chain_main.c',[],660), ('prof','sa1prof.c',[],600), ('me','sa1me.c',[],600)):
        name = 'sa1'+part
        folder = dest/name
        folder.mkdir(exist_ok=True)
        flags = includes + ['-I'+(src/'backend'/'psp').as_posix(), '-I'+(src/'backend'/'psp'/part).as_posix(),
                            '-D_PSP_FW_VERSION='+str(fw), '-O2', '-G0', '-Wall']
        if part == 'chain':
            flags += ['-fno-builtin']
        sources = [src/'backend'/'psp'/part/filename]
        if part != 'exc':
            sources.append(SUPPORT/(part+'_import.S'))
        objs = []
        for path in sources:
            obj = folder/(path.stem+'.o')
            runner.run([str(tc.tool('psp-gcc'))]+flags+['-c',path.as_posix(),'-o',obj.as_posix()], cwd=folder, env=tc.env(), label='Compile '+name)
            objs.append(obj.as_posix())
        elf, prx = folder/(name+'.elf'), dest/(name+'.prx')
        ld = ['-L'+(tc.root/'psp'/'lib').as_posix(), '-L'+(sdk/'lib').as_posix(),
              '-specs='+(sdk/'lib'/'prxspecs').as_posix(), '-Wl,-q,-T'+(sdk/'lib'/'linkfile.prx').as_posix(),
              '-Wl,-zmax-page-size=128']
        runner.run([str(tc.tool('psp-gcc'))]+flags+ld+objs+[(sdk/'lib'/'prxexports.o').as_posix()]+extra+libs+['-o',elf.as_posix()], cwd=folder, env=tc.env(),label='Link '+name)
        runner.run([str(tc.tool('psp-fixup-imports')),str(elf)],cwd=folder,env=tc.env(),label='Imports '+name)
        runner.run([str(tc.tool('psp-prxgen')),str(elf),str(prx)],cwd=folder,env=tc.env(),label='PRX '+name)
        info = inspect_elf(prx.read_bytes())
        required = {'chain':('SystemCtrlForKernel',{'2D10FB28'}),
                    'prof':('ThreadManForKernel',{'6652B8CA','7E65B999'}),
                    'me':('ThreadManForKernel',{'CEADEB47','369ED59D'}),
                    'exc':('ExceptionManagerForKernel',{'565C0B0E'})}[part]
        if not any(row['library']==required[0] and required[1] <= set(row['nids']) for row in info['imports']):
            raise ConverterError('native-artifact',name+' is missing its required kernel ABI imports.')
        outputs[name+'.prx'] = str(prx)
    return outputs


def build(source_root, generated, build_dir, toolchain, runner, jobs=1, title='DCRC Port'):
    if not isinstance(jobs, int) or isinstance(jobs, bool) or not 1 <= jobs <= 64:
        raise ConverterError('jobs', 'Build jobs must be an integer from 1 to 64.')
    make_pbp(b'', title)  # validate title before writes or compiler invocation
    p = plan(source_root, generated, build_dir, toolchain)
    dest, tc = p['dest'], p['toolchain']
    dest.mkdir(parents=True, exist_ok=True)
    sdk = tc.root/'psp'/'sdk'
    fingerprint = tc.fingerprint()
    manifest = dest/'native_build.json'
    _json(manifest,{'status':'INCOMPLETE','toolchain':fingerprint,'source_root':str(p['source']),
                    'generated':str(p['generated'])})
    # Every header participates, including nested generated overlay headers.
    headers = sorted(set(path for root in (p['source']/'hle',p['source']/'backend',p['source']/'recomp'/'emitter'/'runtime',p['generated'],SUPPORT)
                         for path in root.rglob('*') if path.is_file() and path.suffix in ('.h','.inc','.s')))
    header_hash = hashlib.sha256(''.join(str(f)+_hash(f) for f in headers).encode('utf8')).hexdigest()
    records = []
    def compile_one(unit):
        obj, source = unit['object'], unit['source']
        obj.parent.mkdir(parents=True, exist_ok=True)
        args = [str(tc.tool('psp-gcc'))]+unit['flags']+['-c',source.as_posix(),'-o',obj.as_posix()]
        key = hashlib.sha256(json.dumps([args,_hash(source),header_hash,fingerprint]).encode('utf8')).hexdigest()
        stamp = obj.with_suffix(obj.suffix+'.json')
        try:
            saved = json.loads(stamp.read_text(encoding='utf8'))
            cached = saved.get('key') == key and obj.is_file() and saved.get('sha256') == _hash(obj)
        except (OSError, ValueError):
            cached = False
        if not cached:
            runner.run(args,cwd=dest,env=tc.env(),label='Compile '+source.name)
            if not obj.is_file():
                raise ConverterError('compile', 'Compiler produced no object: '+str(obj))
            _json(stamp,{'key':key,'sha256':_hash(obj)})
        return {'source':str(source),'object':str(obj),'key':key,'sha256':_hash(obj),'cached':cached,'argv':args}
    with ThreadPoolExecutor(max_workers=min(jobs,8)) as pool:
        records = list(pool.map(compile_one,p['units']))
    order = dest/'sa1_hot_order.ld'
    order.write_text(p['link_order'],encoding='utf8')
    elf, stripped = dest/'sa1psp.elf', dest/'sa1psp_stripped.elf'
    ld = ['-L'+(tc.root/'lib').as_posix(),'-L'+(tc.root/'psp'/'lib').as_posix(),'-L'+(sdk/'lib').as_posix(),
          '-Wl,-zmax-page-size=128','-Wl,--wrap=sceGeListUpdateStallAddr,--wrap=sceGuGetMemory,--wrap=sceDisplaySetFrameBuf',
          '-Wl,--section-ordering-file=sa1_hot_order.ld','-Wl,-Map=sa1psp.map']
    libraries = ['-l'+name for name in ('pspgu','pspge','pspdisplay','pspctrl','psppower','psprtc','pspdebug','pspaudio','pspmpeg','psputility')]
    # MinGW GCC/collect2 do not agree on non-ASCII paths read from response
    # files. Relative build-owned paths keep those arguments ASCII even when
    # the working directory itself contains Unicode. Python sets cwd via Win32.
    args = ld + [u['object'].relative_to(dest).as_posix() for u in p['units']] + libraries + ['-o',elf.name]
    response = dest/'link.rsp'
    _rsp(response,args)
    runner.run([str(tc.tool('psp-gcc')),'@'+response.as_posix()],cwd=dest,env=tc.env(),label='Link game')
    runner.run([str(tc.tool('psp-fixup-imports')),str(elf)],cwd=dest,env=tc.env(),label='Fix game imports')
    main_validation = inspect_elf(elf.read_bytes())
    if not any(i['library']=='KUBridge' and '4C25EA72' in i['nids'] for i in main_validation['imports']):
        raise ConverterError('native-artifact','Game image has no kuKernelLoadModule import.')
    runner.run([str(tc.tool('psp-strip')),str(elf),'-o',str(stripped)],cwd=dest,env=tc.env(),label='Strip game')
    inspect_elf(stripped.read_bytes())
    icon = p['source']/'backend'/'psp'/'icon0.png'
    pbp = dest/'EBOOT.PBP'
    pbp.write_bytes(make_pbp(stripped.read_bytes(),title,icon.read_bytes() if icon.is_file() else b''))
    artifacts = {'EBOOT.PBP':str(pbp),'sa1psp.elf':str(elf)}
    artifacts.update(build_helpers(p['source'],dest,tc,runner))
    validation = {'memsize':1,'unit_counts':p['counts'],'game_elf':main_validation,
                  'helpers':{name:inspect_elf(Path(path).read_bytes()) for name,path in artifacts.items() if name.endswith('.prx')}}
    files = {name:{'bytes':Path(path).stat().st_size,'sha256':_hash(path)} for name,path in artifacts.items()}
    _json(manifest,{'status':'PASS','toolchain':fingerprint,'source_root':str(p['source']),
                    'generated':str(p['generated']),'units':records,'artifacts':files,'validation':validation})
    return {'artifacts':artifacts,'validation':validation,'manifest':str(manifest)}
