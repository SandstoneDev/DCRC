/* Movie ownership of the game's audio pause. MIT. */
#pragma once
int audio_psp_movie_pause(int on); /* pause ACK/drain, discard stale PCM; no channel handover */

/* Nonzero means worker/channel ownership retained: caller must exit safely. */
int audio_psp_shutdown_failed(void);
