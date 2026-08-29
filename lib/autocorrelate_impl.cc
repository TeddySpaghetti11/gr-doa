/* -*- c++ -*- */
/*
 * Copyright 2025 Ettus Research LLC.
 * Travis F. Collins <travisfcollins@gmail.com>
 * Srikanth Pagadarai <srikanth.pagadarai@gmail.com>
 *
 * This is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 *
 * This software is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this software; see the file COPYING.  If not, write to
 * the Free Software Foundation, Inc., 51 Franklin Street,
 * Boston, MA 02110-1301, USA.
 */


#include "autocorrelate_impl.h"
#include <gnuradio/io_signature.h>
#include <armadillo>
#include <algorithm>
#include <stdexcept>
#include <vector>

#define COPY_MEM false  // Do not copy matrices into separate memory
#define FIX_SIZE true   // Keep dimensions of matrices constant

namespace gr {
    namespace doa {

        using input_type = gr_complex;
        using output_type = gr_complex;

        autocorrelate::sptr
        autocorrelate::make(int inputs,
                            int snapshot_size,
                            int overlap_size,
                            int avg_method)
        {
            return autocorrelate::make(
                inputs, snapshot_size, overlap_size, avg_method, "", "", "doa_valid");
        }

        autocorrelate::sptr
        autocorrelate::make(int inputs,
                            int snapshot_size,
                            int overlap_size,
                            int avg_method,
                            const std::string& valid_tag_key,
                            const std::string& invalid_tag_key,
                            const std::string& output_valid_tag_key)
        {
            return gnuradio::make_block_sptr<autocorrelate_impl>(
                inputs,
                snapshot_size,
                overlap_size,
                avg_method,
                valid_tag_key,
                invalid_tag_key,
                output_valid_tag_key);
        }

        /*
        * The private constructor
        */
        autocorrelate_impl::autocorrelate_impl(
            int inputs,
            int snapshot_size,
            int overlap_size,
            int avg_method,
            const std::string& valid_tag_key,
            const std::string& invalid_tag_key,
            const std::string& output_valid_tag_key)
            : gr::block("autocorrelate",
                    gr::io_signature::make(inputs, inputs, sizeof(input_type)),
                    gr::io_signature::make(1, 1, sizeof(output_type)*inputs*inputs)),
            d_num_inputs(inputs),
            d_snapshot_size(snapshot_size),
            d_overlap_size(overlap_size),
            d_avg_method(avg_method),
            d_valid_tag_key(valid_tag_key),
            d_invalid_tag_key(invalid_tag_key),
            d_output_valid_tag_key(output_valid_tag_key),
            d_validity_gating(!valid_tag_key.empty() || !invalid_tag_key.empty()),
            // A valid tag arms an initially invalid stream. With an
            // invalid-only configuration, preserve the legacy assumption that
            // samples are valid until the first invalidation arrives.
            d_stream_valid(!d_validity_gating || valid_tag_key.empty()),
            d_valid_key(valid_tag_key.empty() ? pmt::PMT_NIL
                                              : pmt::intern(valid_tag_key)),
            d_invalid_key(invalid_tag_key.empty() ? pmt::PMT_NIL
                                                  : pmt::intern(invalid_tag_key)),
            d_output_valid_key(output_valid_tag_key.empty()
                                   ? pmt::PMT_NIL
                                   : pmt::intern(output_valid_tag_key))
        {
            if (d_validity_gating && d_overlap_size != 0) {
                throw std::invalid_argument(
                    "validity-gated autocorrelation currently requires zero overlap");
            }
            d_nonoverlap_size = d_snapshot_size-d_overlap_size;
            set_history(d_overlap_size+1);

            // Create container for temporary matrix
            d_input_matrix = arma::cx_fmat(snapshot_size,inputs);

            // initialize the reflection matrix
            // creates an identity matrix 
            d_J.eye(d_num_inputs, d_num_inputs);
            // flips the matrix into a reflection matrix
            d_J = fliplr(d_J);
        }

        /*
        * Our virtual destructor.
        */
        autocorrelate_impl::~autocorrelate_impl() 
        {
        }
        
        // This function is called to forecast the number of input items required
        void autocorrelate_impl::forecast(int noutput_items, gr_vector_int& ninput_items_required)
        {
            for (size_t i=0; i < ninput_items_required.size(); i++){
                ninput_items_required[i] = d_nonoverlap_size*noutput_items;
            }
        }

        int autocorrelate_impl::general_work(int output_matrices,
                                            gr_vector_int &ninput_items,
                                            gr_vector_const_void_star &input_items,
                                            gr_vector_void_star &output_items)
        {
            // Cast pointer
            gr_complex *out = (gr_complex *) output_items[0];

            struct validity_event {
                uint64_t offset;
                bool valid;
            };
            std::vector<validity_event> validity_events;
            if (d_validity_gating) {
                const uint64_t range_start = nitems_read(0);
                const uint64_t range_stop = range_start
                    + static_cast<uint64_t>(d_nonoverlap_size * output_matrices);
                std::vector<tag_t> tags;
                if (!pmt::is_null(d_valid_key)) {
                    get_tags_in_range(tags, 0, range_start, range_stop, d_valid_key);
                    for (const auto& tag : tags) {
                        validity_events.push_back({tag.offset, true});
                    }
                }
                tags.clear();
                if (!pmt::is_null(d_invalid_key)) {
                    get_tags_in_range(tags, 0, range_start, range_stop, d_invalid_key);
                    for (const auto& tag : tags) {
                        validity_events.push_back({tag.offset, false});
                    }
                }
                std::sort(validity_events.begin(),
                          validity_events.end(),
                          [](const validity_event& lhs, const validity_event& rhs) {
                              return lhs.offset < rhs.offset;
                          });
            }
            size_t next_event = 0;

            // Create each output matrix
            for (int i=0; i < output_matrices; i++)
            {
                bool snapshot_valid = !d_validity_gating || d_stream_valid;
                if (d_validity_gating) {
                    const uint64_t window_start = nitems_read(0)
                        + static_cast<uint64_t>(i * d_nonoverlap_size);
                    const uint64_t window_stop = window_start
                        + static_cast<uint64_t>(d_snapshot_size);
                    while (next_event < validity_events.size()
                           && validity_events[next_event].offset <= window_start) {
                        d_stream_valid = validity_events[next_event].valid;
                        ++next_event;
                    }
                    snapshot_valid = d_stream_valid;
                    while (next_event < validity_events.size()
                           && validity_events[next_event].offset < window_stop) {
                        snapshot_valid = false;
                        d_stream_valid = validity_events[next_event].valid;
                        ++next_event;
                    }
                }

                // Form input matrix
                for(int k=0; k < d_num_inputs; k++) 
                {
                    const gr_complex* in_ptr = static_cast<const gr_complex*>(input_items[k]);
                    memcpy((void*)d_input_matrix.colptr(k),
                    &in_ptr[i*d_nonoverlap_size],
                    sizeof(gr_complex)*d_snapshot_size);
                }
                
                // Make output pointer into matrix pointer
                arma::cx_fmat out_matrix(out+d_num_inputs*d_num_inputs*i,d_num_inputs,d_num_inputs,COPY_MEM,FIX_SIZE);

                // Do autocorrelation only for a complete, explicitly valid
                // phase/calibration epoch. Invalid matrices remain zero and
                // carry a one-item validity tag for downstream display gating.
                if (snapshot_valid) {
                    out_matrix = (1.0/d_snapshot_size)*d_input_matrix.st()*conj(d_input_matrix);
                    if (d_avg_method == 1) {
                        out_matrix = 0.5*out_matrix+(0.5/d_snapshot_size)*d_J*conj(out_matrix)*d_J;
                    }
                } else {
                    out_matrix.zeros();
                }
                if (d_validity_gating && !pmt::is_null(d_output_valid_key)) {
                    add_item_tag(
                        0,
                        nitems_written(0) + static_cast<uint64_t>(i),
                        d_output_valid_key,
                        pmt::from_bool(snapshot_valid));
                }
            }
            // Tell runtime system how many input items we consumed on
            // each input stream.
            consume_each (d_nonoverlap_size * output_matrices);			

            // Tell runtime system how many output items we produced.
            return output_matrices;
        }
    } /* namespace doa */
} /* namespace gr */
