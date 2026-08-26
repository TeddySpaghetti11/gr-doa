/* -*- c++ -*- */
/*
 * Copyright 2026
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef INCLUDED_DOA_MUSIC_UCA_IMPL_H
#define INCLUDED_DOA_MUSIC_UCA_IMPL_H

#include <gnuradio/doa/MUSIC_uca.h>
#include <armadillo>

namespace gr {
namespace doa {

class MUSIC_uca_impl : public MUSIC_uca
{
private:
    float d_norm_radius;
    int d_num_targets;
    int d_num_ant_ele;
    int d_pspectrum_len;
    float d_element0_angle_deg;
    float d_element_angle_step_deg;
    arma::cx_fmat d_manifold;
    arma::cx_fmat d_manifold_h;

public:
    MUSIC_uca_impl(float norm_radius,
                   int num_targets,
                   int inputs,
                   int pspectrum_len,
                   float element0_angle_deg,
                   float element_angle_step_deg);
    ~MUSIC_uca_impl() override = default;

    int work(int noutput_items,
             gr_vector_const_void_star& input_items,
             gr_vector_void_star& output_items) override;
};

} // namespace doa
} // namespace gr

#endif /* INCLUDED_DOA_MUSIC_UCA_IMPL_H */
