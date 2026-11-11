/* Supported-input filename and completion facts, not game function bodies.
 * Facts verified locally from the supported own US1.005 source. Converter
 * validates version/source table before staging PMF/WAV. No media bytes. */
#pragma once
#define DCRC_MOVIE_COUNT 10u
static const char *const dcrc_movie_names[DCRC_MOVIE_COUNT]={
 "SLH448_1","SAH448_6","SA1_600","SA2_600","SA3_600",
 "SA4_600","SA5_600","SA6_600","SA7_300","SA8_600"};
static const signed char dcrc_movie_completed[DCRC_MOVIE_COUNT]={1,0,0,0,0,0,0,0,0,0};
