/* Optional opaque-content settings. No external payload decoder is shipped. MIT. */
#pragma once
/* dlc_event=off, zero-based catalog index, or exact label; CLI owns precedence.
 * Legacy dlc_vms/dlc_vmi only accept off/none. Invalid explicit CLI blocks INI. */
int hle_dlc_setting(const char *key, const char *value, int cli);
void hle_dlc_start(void); /* after base VMU init/settings; loads catalog, mounts */
