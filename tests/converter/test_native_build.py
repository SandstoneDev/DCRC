"""Tests the native build contract; actual compiler proof lives in ignored work."""
import importlib
import os
from pathlib import Path
import struct
import tempfile
import unittest


class NativeBuildTest(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module('dcrc.native_build')
        except ImportError:
            self.fail('native build is not implemented')

    def test_pbp_contains_elf_memsize_one_neutral_id_and_utf8_title(self):
        api = self.api()
        elf = b'\x7fELF' + bytes(range(64))
        data = api.make_pbp(elf, 'DCRC Тест')
        self.assertEqual(data[:8], b'\x00PBP\x00\x00\x01\x00')
        offsets = struct.unpack_from('<8I', data, 8)
        self.assertEqual(data[offsets[6]:offsets[7]], elf)
        sfo = data[offsets[0]:offsets[1]]
        self.assertEqual(sfo[:4], b'\x00PSF')
        keys, values, count = struct.unpack_from('<III', sfo, 8)
        parsed = {}
        for i in range(count):
            ko, fmt, length, capacity, vo = struct.unpack_from('<HHIII', sfo, 20 + i * 16)
            key = sfo[keys + ko:].split(b'\0', 1)[0].decode('ascii')
            raw = sfo[values + vo:values + vo + length]
            parsed[key] = struct.unpack('<I', raw)[0] if fmt == 0x404 else raw.rstrip(b'\0').decode('utf8')
            self.assertLessEqual(length, capacity)
        self.assertEqual(parsed['MEMSIZE'], 1)
        self.assertEqual(parsed['TITLE'], 'DCRC Тест')
        self.assertEqual(parsed['DISC_ID'], 'DCRC00001')
        self.assertEqual(parsed['CATEGORY'], 'MG')

    def test_no_game_is_error_before_commands_or_output(self):
        api = self.api()
        class Runner:
            def run(self, *a, **kw):
                raise AssertionError('must not build hello')
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with self.assertRaises(Exception) as caught:
                api.build(base, base/'missing', base/'output', base/'sdk', Runner())
            self.assertNotIsInstance(caught.exception, AssertionError)
            self.assertFalse((base/'output').exists())

    def test_wrapper_gates_require_actual_generated_orig(self):
        api = self.api()
        self.assertEqual(api.wrap_defines(''), [])
        result = api.wrap_defines('fn_8c037350_orig fn_8c011060_orig')
        self.assertIn('SA1_WRAP_8C037350', result)
        self.assertNotIn('SA1_WRAP_DLC', result)
        self.assertIn('SA1_WRAP_DLC', api.wrap_defines('fn_8c011060_orig fn_8c011a84_orig'))

    def test_link_order_pins_chunks_and_aligns_all_data_sections(self):
        api = self.api()
        result = api.link_order('@0x100\nfoo\na.c:bar\nlibx.a:m.o\n=game_001.c @0x200\n=@0x300\n')
        self.assertIn('(0x100 - .) & 0x3fff', result)
        self.assertIn('*sa1_game_psp.dir/*/game_001.c.o*', result)
        self.assertIn('sa1_obj_end', result)
        self.assertIn('*libx.a:m.o', result)
        for section in ['.rodata', '.data', '.sdata', '.sbss', '.bss']:
            self.assertIn(section + ' : {\n    . = ALIGN(0x2000);', result)

    def test_elf_parser_rejects_wrong_arch_and_truncation(self):
        api = self.api()
        with self.assertRaises(Exception):
            api.inspect_elf(b'\x7fELF')
        header = bytearray(52)
        header[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<HHI', header, 16, 2, 62, 1)
        with self.assertRaises(Exception):
            api.inspect_elf(header)

    def test_elf_import_pointer_and_count_bounds_are_checked(self):
        api = self.api()
        names = b'\0.shstrtab\0.rodata\0.lib.stub\0.sceStub.text\0'
        ro = b'KUBridge\0' + b'\0'*3 + struct.pack('<I',0x4C25EA72)
        stub = struct.pack('<5I',0x1000,0x40090000,0x00010005,0x100C,0x3000)
        body = bytearray(52) + names + ro + stub + bytes(8)
        shoff = len(body)
        offsets = [52,52+len(names),52+len(names)+len(ro),52+len(names)+len(ro)+20]
        rows = [(0,0,0,0,0,0,0,0,0,0),
                (1,3,0,0,offsets[0],len(names),0,0,1,0),
                (11,1,2,0x1000,offsets[1],len(ro),0,0,4,0),
                (19,1,2,0x2000,offsets[2],20,0,0,4,0),
                (29,1,6,0x3000,offsets[3],8,0,0,4,0)]
        for row in rows:
            body.extend(struct.pack('<10I',*row))
        body[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<HHI',body,16,2,8,1)
        struct.pack_into('<III',body,24,0x3000,0,shoff)
        struct.pack_into('<6H',body,40,52,0,0,40,5,1)
        info = api.inspect_elf(body)
        self.assertEqual(info['imports'],[{'library':'KUBridge','flags_version':0x40090000,'nids':['4C25EA72']}])
        struct.pack_into('<I',body,offsets[2]+12,0xFFFFFFFC)
        with self.assertRaises(Exception):
            api.inspect_elf(body)

    def test_native_plan_preserves_runtime_overrides_and_hot_chunk_opt(self):
        api = self.api()
        tcapi = importlib.import_module('dcrc.toolchain')
        with tempfile.TemporaryDirectory(prefix='DCRC space ю ') as d:
            base = Path(d)
            src, gen, sdk = base/'source', base/'generated', base/'sdk'
            for rel in tcapi.REQUIRED:
                file = sdk/rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'fixture')
            for rel in ['hle/bios/syscalls.c','hle/shinobi/cfg.c','hle/sound/sd.c',
                        'recomp/emitter/runtime/sh4_rt.c','recomp/emitter/runtime/sh4_rt.h',
                        'backend/desktop/input_tape.c','backend/desktop/sha256.c','backend/texpool.c',
                        'backend/debug_menu.c','backend/debug_config.c','backend/movie_wav.c']:
                file = src/rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('/* own fixture */')
            for name in api.BACKEND:
                file = src/'backend'/'psp'/name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('/* own fixture */')
            for rel in ['emitter/game_001.c','emitter/game_009.c','emitter/game_table.c',
                        'overlays/emitter/one/ovl_000.c']:
                file = gen/rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('/* own fixture */')
            (gen/'emitter/game.h').write_text('fn_8c037350_orig')
            (src/'tools').mkdir()
            (src/'tools/psp_hot_order.txt').write_text('foo\n')
            result = api.plan(src,gen,base/'build',sdk)
            units = {u['source'].name:u for u in result['units']}
            self.assertEqual(result['counts']['overlays'],1)
            self.assertEqual(result['counts']['game'],2)
            self.assertIn('-DSA1_WRAP_8C037350',units['syscalls.c']['flags'])
            self.assertIn('-DSA1_OFF_FULL',units['sd.c']['flags'])
            self.assertNotIn('-DSA1_OFF_FULL',units['sh4_rt.c']['flags'])
            self.assertNotIn('-DSA1_OFF_AREA_TEST_ONLY',units['draw_gu.c']['flags'])
            self.assertNotIn('-DSA1_WRAP_8C037350',units['draw_gu.c']['flags'])
            self.assertEqual(units['game_001.c']['flags'][-1],'-O2')
            self.assertIn('-Os',units['game_009.c']['flags'])
            self.assertNotIn('-O2',units['game_009.c']['flags'])
            self.assertIn('-include',units['game_009.c']['flags'])
            self.assertIn((src/'recomp/emitter/runtime/sh4_rt.h').as_posix(),units['game_009.c']['flags'])
            self.assertTrue(all('hello' not in str(u['source']) for u in result['units']))
            self.assertFalse((base/'build').exists())
            if os.name == 'nt':
                deep = gen / 'overlays' / 'emitter' / ('long_' * 38) / 'ovl_long.c'
                deep.parent.mkdir()
                deep.write_text('/* own fixture */')
                self.assertGreaterEqual(len(str(deep)), 260)
                with self.assertRaisesRegex(api.ConverterError, 'Choose a short work folder') as failure:
                    api.plan(src,gen,base/'build',sdk)
                self.assertEqual(failure.exception.code,'native-work-path')
                self.assertFalse((base/'build').exists())

    @unittest.skipUnless(os.name == 'nt','MinGW response files use the Windows ANSI codepage')
    def test_response_file_uses_native_codepage_instead_of_utf8_mojibake(self):
        api = self.api()
        try:
            expected = '"path ю space/file.o"\n'.encode('mbcs')
        except UnicodeEncodeError:
            self.skipTest('Cyrillic is outside this machine codepage')
        with tempfile.TemporaryDirectory() as d:
            response = Path(d)/'link.rsp'
            api._rsp(response,['path ю space/file.o'])
            self.assertEqual(response.read_bytes(),expected)


if __name__ == '__main__':
    unittest.main()
