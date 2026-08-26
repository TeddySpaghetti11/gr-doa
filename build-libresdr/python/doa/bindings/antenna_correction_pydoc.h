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


static const char* __doc_gr_doa_antenna_correction = R"doc(<+description of block+>

This block takes a correlation matrix of size (number of antenna elements x number of antenna elements) as input and multiplies it with a diagonal matrix of size (number of antenna elements x number of antenna elements) using calibration values retrieved from a config file.

Constructor Specific Documentation:

Return a shared_ptr to a new instance of doa::antenna_correction.

Args:
    num_ant_ele : Number of antenna elements
    config_filename : Config file consisting of antenna calibration values)doc";


static const char* __doc_gr_doa_antenna_correction_antenna_correction_0 = R"doc()doc";


static const char* __doc_gr_doa_antenna_correction_make = R"doc(<+description of block+>

This block takes a correlation matrix of size (number of antenna elements x number of antenna elements) as input and multiplies it with a diagonal matrix of size (number of antenna elements x number of antenna elements) using calibration values retrieved from a config file.

Constructor Specific Documentation:

Return a shared_ptr to a new instance of doa::antenna_correction.

Args:
    num_ant_ele : Number of antenna elements
    config_filename : Config file consisting of antenna calibration values)doc";
