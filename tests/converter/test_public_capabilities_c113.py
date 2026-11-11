"""Public profile capabilities must remain honest while the frontend evolves."""
from pathlib import Path
import unittest
from unittest.mock import patch
from dcrc.models import ConversionOptions
from dcrc.errors import ConverterError

class PublicCapabilitiesTests(unittest.TestCase):
    def test_explicit_capabilities(self):
        from dcrc.capabilities import PROFILE_CAPABILITIES
        self.assertEqual(PROFILE_CAPABILITIES['renderer'], 'ta')
        self.assertEqual(PROFILE_CAPABILITIES['static_distance'], [100])
        for feature in ('movie_playback','custom_border','configurable_dither'):
            self.assertTrue(PROFILE_CAPABILITIES[feature])
        self.assertFalse(PROFILE_CAPABILITIES['dlc_gameplay_verified'])
        self.assertFalse(PROFILE_CAPABILITIES['dlc_decoder'])
    def test_unsupported_runtime_options_decline(self):
        for kw in ({'land_distance':60},{'movies':'yes'},{'border_mode':'orbit'},{'dither':'invalid'}):
            with self.subTest(kw=kw), self.assertRaises(ConverterError):
                ConversionOptions(Path('.'),Path('out'),**kw).validate(check_paths=False)
    def test_enabled_generic_features_validate_without_enabling_defaults(self):
        from dcrc.package import runtime_text
        defaults=ConversionOptions(Path('.'),Path('out')).validate(check_paths=False)
        self.assertFalse(defaults.movies)
        self.assertEqual(defaults.border_mode,'none')
        self.assertEqual(defaults.dither,'on')
        for dither in ('on','opaque','off'):
            options=ConversionOptions(Path('.'),Path('out'),movies=True,
                border_mode='custom',border_image=Path('own.png'),dither=dither).validate(check_paths=False)
            args,ini=runtime_text(options)
            self.assertIn('movies = on',ini)
            self.assertIn('dither = '+dither,ini)
            self.assertIn('renderer = ta',ini)
            self.assertEqual(options.land_distance,100)

    def test_disabled_capabilities_still_decline_options(self):
        from dcrc.capabilities import PROFILE_CAPABILITIES
        with patch.dict(PROFILE_CAPABILITIES,movie_playback=False,custom_border=False,configurable_dither=False):
            for kw in ({'movies':True},{'border_mode':'custom','border_image':Path('own.png')},{'dither':'off'}):
                with self.subTest(kw=kw),self.assertRaises(ConverterError):
                    ConversionOptions(Path('.'),Path('out'),**kw).validate(check_paths=False)

    def test_xmb_and_controls_are_real_options(self):
        options=ConversionOptions(Path('.'),Path('out'),xmb_music_mode='none',control_map={'cross':'b'}).validate(check_paths=False)
        from dcrc.package import runtime_text
        args,ini=runtime_text(options)
        self.assertIn('renderer = ta',ini)
        self.assertIn('control_cross = b',ini)
        self.assertNotIn('renderer = native',ini)
        self.assertEqual(options.land_distance,100)
