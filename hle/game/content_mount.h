/* Opaque user-local VMU events. Own container/mount adapter, MIT. */
#pragma once
/* Call on the owning guest thread. Catalog is loaded by hle_dlc_start.
 * data/dlc/events.txt: label|data-relative.vmi|data-relative.vms
 * At most32 entries/64 physical lines; ASCII labels1..63, paths1..255.
 * Comments begin # after whitespace. Duplicate labels reject the catalog.
 * No payload decoding or internal section validation is performed here. */
int hle_content_count(void);
const char *hle_content_label(int index); /* NULL if out of range */
int hle_content_select(int index);       /* -1 off;0 success,-1 declined */
int hle_content_selected(void);          /* -1 when nothing is mounted */
const char *hle_content_status(void);
/* Backend must set before hle_init for --load; a resume always unmounts. */
void hle_content_set_resuming(int resuming);
/* Selection changes VMU visibility; guest activation is NEXT ordinary level
 * load, after normal VMU/file selection. This never edits the no-save flag,
 * calls a guest decoder, reloads a scene, or destroys already spawned tasks. */
