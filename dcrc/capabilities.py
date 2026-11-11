"""Reviewed public profile limits. Runtime features require a separate source audit."""
PROFILE_CAPABILITIES = {
    'renderer': 'ta', 'static_distance': [100],
    'movie_playback': True, 'custom_border': True, 'configurable_dither': True,
    'guest_control_mapping': True, 'dlc_import': True, 'dlc_decoder': False,
    'dlc_gameplay_verified': False,
}
DLC_NOTICE = ('Downloads are optional user-local inputs. This public profile imports opaque events, '
              'but excludes the private DLC decoder. Gameplay compatibility is unverified; '
              'downloaded or imported does not mean playable. Normal boot / VMU selection is required.')
