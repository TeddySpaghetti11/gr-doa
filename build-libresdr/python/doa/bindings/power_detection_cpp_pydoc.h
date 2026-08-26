/*
 * Copyright 2025 Free Software Foundation, Inc.
 *
 * This file is part of GNU Radio
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 */
#include "pydoc_macros.h"
#define D(...) DOC(gr, doa, __VA_ARGS__)
/*
  This file contains placeholders for docstrings for the Python bindings.
  Do not edit! These were automatically extracted during the binding process
  and will be overwritten during the build process
 */


static const char* __doc_gr_doa_power_detection_cpp = R"doc(Power detection block with buffer capture and replay.

Detects signal power on the first input channel. When power exceeds threshold, captures signal to buffer. During silence, replays captured signal.

Constructor Specific Documentation:

Create a power detection block.

Args:
    num_inputs : Number of input channels
    sample_rate : Sample rate in Hz
    buffer_size : Size of capture/playback buffer in samples
    threshold_multiplier : Multiplier for power threshold detection)doc";


static const char* __doc_gr_doa_power_detection_cpp_power_detection_cpp_0 = R"doc()doc";


static const char* __doc_gr_doa_power_detection_cpp_make = R"doc(Power detection block with buffer capture and replay.

Detects signal power on the first input channel. When power exceeds threshold, captures signal to buffer. During silence, replays captured signal.

Constructor Specific Documentation:

Create a power detection block.

Args:
    num_inputs : Number of input channels
    sample_rate : Sample rate in Hz
    buffer_size : Size of capture/playback buffer in samples
    threshold_multiplier : Multiplier for power threshold detection)doc";
