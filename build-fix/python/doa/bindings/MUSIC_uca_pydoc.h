/*
 * Copyright 2026
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#pragma once
#include "pydoc_macros.h"

#define D(...) DOC(gr, doa, __VA_ARGS__)

static const char* __doc_gr_doa_MUSIC_uca = R"doc(MUSIC pseudo-spectrum estimator for a uniform circular array.

Angles are scanned over [0, 360) degrees. Element zero is placed at element0_angle_deg and subsequent element bearings are separated by element_angle_step_deg. Use a negative step when the channel order runs in the opposite direction to the chosen bearing convention.

Constructor Specific Documentation:



Args:
    norm_radius : 
    num_targets : 
    inputs : 
    pspectrum_len : 
    element0_angle_deg : 
    element_angle_step_deg : )doc";
static const char* __doc_gr_doa_MUSIC_uca_MUSIC_uca_0 = R"doc()doc";
static const char* __doc_gr_doa_MUSIC_uca_make = R"doc(MUSIC pseudo-spectrum estimator for a uniform circular array.

Angles are scanned over [0, 360) degrees. Element zero is placed at element0_angle_deg and subsequent element bearings are separated by element_angle_step_deg. Use a negative step when the channel order runs in the opposite direction to the chosen bearing convention.

Constructor Specific Documentation:



Args:
    norm_radius : 
    num_targets : 
    inputs : 
    pspectrum_len : 
    element0_angle_deg : 
    element_angle_step_deg : )doc";
