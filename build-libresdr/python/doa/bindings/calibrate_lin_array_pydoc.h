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


static const char* __doc_gr_doa_calibrate_lin_array = R"doc(<+description of block+>

This block takes a correlation matrix of size (number of antenna elements x number of antenna elements) as input and generates a complex vector of size (number of antenna elements x 1) which can be utilized to calibrate a linear array.

Constructor Specific Documentation:

Make a block to calibrate linear arrays.

Args:
    norm_spacing : Normalized spacing between antenna elements
    num_ant_ele : Number of antenna elements
    pilot_angle : Known angle of a pilot transmitter used for calibration)doc";


static const char* __doc_gr_doa_calibrate_lin_array_calibrate_lin_array_0 = R"doc()doc";


static const char* __doc_gr_doa_calibrate_lin_array_make = R"doc(<+description of block+>

This block takes a correlation matrix of size (number of antenna elements x number of antenna elements) as input and generates a complex vector of size (number of antenna elements x 1) which can be utilized to calibrate a linear array.

Constructor Specific Documentation:

Make a block to calibrate linear arrays.

Args:
    norm_spacing : Normalized spacing between antenna elements
    num_ant_ele : Number of antenna elements
    pilot_angle : Known angle of a pilot transmitter used for calibration)doc";
