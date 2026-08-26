/* -*- c++ -*- */
/*
 * Copyright 2026
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include "MUSIC_uca_impl.h"
#include <gnuradio/io_signature.h>
#include <cmath>

#define COPY_MEM false // Do not copy matrices into separate memory
#define FIX_SIZE true  // Keep dimensions of matrices constant

namespace gr {
namespace doa {

using input_type = gr_complex;
using output_type = float;

MUSIC_uca::sptr MUSIC_uca::make(float norm_radius,
                                int num_targets,
                                int inputs,
                                int pspectrum_len,
                                float element0_angle_deg,
                                float element_angle_step_deg)
{
    return gnuradio::make_block_sptr<MUSIC_uca_impl>(norm_radius,
                                                     num_targets,
                                                     inputs,
                                                     pspectrum_len,
                                                     element0_angle_deg,
                                                     element_angle_step_deg);
}

MUSIC_uca_impl::MUSIC_uca_impl(float norm_radius,
                               int num_targets,
                               int inputs,
                               int pspectrum_len,
                               float element0_angle_deg,
                               float element_angle_step_deg)
    : gr::sync_block("MUSIC_uca",
                     gr::io_signature::make(
                         1, 1, sizeof(input_type) * inputs * inputs),
                     gr::io_signature::make(
                         1, 1, sizeof(output_type) * pspectrum_len)),
      d_norm_radius(norm_radius),
      d_num_targets(num_targets),
      d_num_ant_ele(inputs),
      d_pspectrum_len(pspectrum_len),
      d_element0_angle_deg(element0_angle_deg),
      d_element_angle_step_deg(element_angle_step_deg)
{
    // UCA geometry is the only intentional algorithmic difference from the
    // Ettus MUSIC_lin_array constructor.  Positions are expressed in
    // wavelengths and projected onto each candidate bearing.
    const float pi = static_cast<float>(arma::datum::pi);
    const float degrees_to_radians = pi / 180.0F;
    const gr_complex j(0.0F, 1.0F);
    d_manifold.set_size(d_num_ant_ele, d_pspectrum_len);

    for (int angle_index = 0; angle_index < d_pspectrum_len; ++angle_index) {
        const float theta = 2.0F * pi * angle_index /
                            static_cast<float>(d_pspectrum_len);
        for (int element = 0; element < d_num_ant_ele; ++element) {
            const float beta = (d_element0_angle_deg +
                                element * d_element_angle_step_deg) *
                               degrees_to_radians;
            const float projected_position = d_norm_radius * std::cos(theta - beta);
            d_manifold(element, angle_index) =
                std::exp(j * (-2.0F * pi * projected_position));
        }
    }
    d_manifold_h = arma::trans(d_manifold);
}

int MUSIC_uca_impl::work(int noutput_items,
                         gr_vector_const_void_star& input_items,
                         gr_vector_void_star& output_items)
{
    const auto* in = static_cast<const input_type*>(input_items[0]);
    auto* out = static_cast<output_type*>(output_items[0]);

    arma::fvec eigenvalues;
    arma::cx_fmat eigenvectors;
    arma::cx_fmat noise_subspace;
    arma::cx_fmat noise_projector;

    for (int item = 0; item < noutput_items; ++item) {
        arma::cx_fmat covariance(
            const_cast<input_type*>(in + item * d_num_ant_ele * d_num_ant_ele),
            d_num_ant_ele,
            d_num_ant_ele);
        arma::fvec spectrum(out + item * d_pspectrum_len,
                            d_pspectrum_len,
                            COPY_MEM,
                            FIX_SIZE);

        // Preserve Ettus eigendecomposition and ascending eigenvector order.
        arma::eig_sym(eigenvalues, eigenvectors, covariance);

        noise_subspace = eigenvectors.cols(0, d_num_ant_ele - d_num_targets - 1);
        noise_projector = noise_subspace * arma::trans(noise_subspace);

        gr_complex denominator;
        for (int angle_index = 0; angle_index < d_pspectrum_len; ++angle_index) {
            denominator = arma::as_scalar(
                d_manifold_h.row(angle_index) * noise_projector *
                d_manifold.col(angle_index));
            spectrum(angle_index) = 1.0F / denominator.real();
        }

        // Preserve Ettus pseudo-spectrum normalization.
        spectrum = 10.0F * arma::log10(spectrum / spectrum.max());
    }

    return noutput_items;
}

} // namespace doa
} // namespace gr
