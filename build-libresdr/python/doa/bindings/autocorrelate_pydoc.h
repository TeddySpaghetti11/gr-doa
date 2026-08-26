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


static const char* __doc_gr_doa_autocorrelate = R"doc(<+description of block+>

This block collects a certain number of samples over each of the input streams and forms a (number of inputs x snap shot size) matrix. Then, it produces a correlation matrix of size (number of inputs x number of inputs) using either Forward Averaging method or Forward-Backward Averaging method.

Constructor Specific Documentation:

Return a shared_ptr to a new instance of doa::autocorrelate.

Args:
    inputs : Number of input streams
    snapshot_size : Size of each snapshot
    overlap_size : Size of the overlap between successive snapshots
    avg_method : Use Forward Averaging or Forward-Backward Averaging)doc";


static const char* __doc_gr_doa_autocorrelate_autocorrelate_0 = R"doc()doc";


static const char* __doc_gr_doa_autocorrelate_make = R"doc(<+description of block+>

This block collects a certain number of samples over each of the input streams and forms a (number of inputs x snap shot size) matrix. Then, it produces a correlation matrix of size (number of inputs x number of inputs) using either Forward Averaging method or Forward-Backward Averaging method.

Constructor Specific Documentation:

Return a shared_ptr to a new instance of doa::autocorrelate.

Args:
    inputs : Number of input streams
    snapshot_size : Size of each snapshot
    overlap_size : Size of the overlap between successive snapshots
    avg_method : Use Forward Averaging or Forward-Backward Averaging)doc";
