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


static const char* __doc_gr_doa_rootMUSIC_linear_array = R"doc(<+description of block+>

This block takes a correlation matrix of size (number of antenna elements x number of antenna elements) as input and generates a complex vector of size (pseudo-spectrum length x 1) whose arg-max values represent the estimated DoAs.

Constructor Specific Documentation:

Return a shared_ptr to a new instance of doa::rootMUSIC_linear_array.

Args:
    norm_spacing : Normalized spacing between antenna elements
    num_targets : Known number of targets
    num_ant_ele : Number of antenna elements)doc";


static const char* __doc_gr_doa_rootMUSIC_linear_array_rootMUSIC_linear_array_0 =
    R"doc()doc";


static const char* __doc_gr_doa_rootMUSIC_linear_array_make = R"doc(<+description of block+>

This block takes a correlation matrix of size (number of antenna elements x number of antenna elements) as input and generates a complex vector of size (pseudo-spectrum length x 1) whose arg-max values represent the estimated DoAs.

Constructor Specific Documentation:

Return a shared_ptr to a new instance of doa::rootMUSIC_linear_array.

Args:
    norm_spacing : Normalized spacing between antenna elements
    num_targets : Known number of targets
    num_ant_ele : Number of antenna elements)doc";
