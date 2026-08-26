/* -*- c++ -*- */
/*
 * Copyright 2026
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef INCLUDED_DOA_MUSIC_UCA_H
#define INCLUDED_DOA_MUSIC_UCA_H

#include <gnuradio/doa/api.h>
#include <gnuradio/sync_block.h>

namespace gr {
namespace doa {

/*!
 * \brief MUSIC pseudo-spectrum estimator for a uniform circular array.
 * \ingroup doa
 *
 * Angles are scanned over [0, 360) degrees. Element zero is placed at
 * element0_angle_deg and subsequent element bearings are separated by
 * element_angle_step_deg. Use a negative step when the channel order runs in
 * the opposite direction to the chosen bearing convention.
 */
class DOA_API MUSIC_uca : virtual public gr::sync_block
{
public:
    typedef std::shared_ptr<MUSIC_uca> sptr;

    static sptr make(float norm_radius,
                     int num_targets,
                     int inputs,
                     int pspectrum_len,
                     float element0_angle_deg,
                     float element_angle_step_deg);
};

} // namespace doa
} // namespace gr

#endif /* INCLUDED_DOA_MUSIC_UCA_H */
