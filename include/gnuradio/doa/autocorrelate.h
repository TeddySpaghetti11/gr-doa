/* -*- c++ -*- */
/*
 * Copyright 2025 Ettus Research LLC.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#ifndef INCLUDED_DOA_AUTOCORRELATE_H
#define INCLUDED_DOA_AUTOCORRELATE_H

#include <gnuradio/block.h>
#include <gnuradio/doa/api.h>
#include <string>

namespace gr {
namespace doa {

/*!
 * \brief <+description of block+>
 * \ingroup doa
 *
 * \details
 * This block collects a certain number of samples over each of the input streams
 * and forms a (number of inputs x snap shot size) matrix. Then, it produces 
 * a correlation matrix of size (number of inputs x number of inputs) using 
 * either Forward Averaging method or Forward-Backward Averaging method. 
 */
class DOA_API autocorrelate : virtual public gr::block
{
public:
    typedef std::shared_ptr<autocorrelate> sptr;

    /*!
     * \brief Return a shared_ptr to a new instance of doa::autocorrelate.
     *
     * \param inputs          Number of input streams
     * \param snapshot_size   Size of each snapshot
     * \param overlap_size    Size of the overlap between successive snapshots
     * \param avg_method      Use Forward Averaging or Forward-Backward Averaging
     */
    // Preserve the original four-argument factory ABI for existing compiled
    // callers while exposing validity gating to new flowgraphs.
    static sptr make(int inputs,
                     int snapshot_size,
                     int overlap_size,
                     int avg_method);

    /*!
     * \brief Create a validity-gated autocorrelation block.
     *
     * The first four parameters have the same meaning as the legacy factory.
     * \param valid_tag_key   Optional tag that starts a valid input interval
     * \param invalid_tag_key Optional tag that ends a valid input interval
     * \param output_valid_tag_key Boolean validity tag for each output matrix
     */
    static sptr make(int inputs,
                     int snapshot_size,
                     int overlap_size,
                     int avg_method,
                     const std::string& valid_tag_key,
                     const std::string& invalid_tag_key,
                     const std::string& output_valid_tag_key);
};

} // namespace doa
} // namespace gr

#endif /* INCLUDED_DOA_AUTOCORRELATE_H */
