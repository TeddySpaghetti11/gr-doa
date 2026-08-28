#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

import gnuradio
import numpy
import pmt

# GR_ADD_TEST places the source package under test_modules/gnuradio. Prefer
# that generated package so the QA exercises the just-built Python sources.
for search_path in sys.path:
    test_gnuradio = os.path.join(search_path, "gnuradio")
    candidate = os.path.join(
        test_gnuradio, "doa", "continuous_cross_sdr_cfo_corrector.py"
    )
    if os.path.isfile(candidate):
        gnuradio.__path__.insert(0, test_gnuradio)
        break

from gnuradio import blocks
from gnuradio import doa
from gnuradio import gr
from gnuradio import gr_unittest


def _pilot_channels(sample_rate, sample_count, bravo_cfo_hz):
    sample_index = numpy.arange(sample_count, dtype=numpy.float64)
    pilot = numpy.exp(
        1j * 2.0 * numpy.pi * 4100.0 / sample_rate * sample_index
    )
    alpha0 = pilot
    alpha1 = 0.83 * numpy.exp(1j * 0.31) * pilot

    cfo = numpy.asarray(bravo_cfo_hz, dtype=numpy.float64)
    if cfo.ndim == 0:
        bravo_phase = 2.0 * numpy.pi * cfo / sample_rate * sample_index
    else:
        if cfo.size != sample_count:
            raise ValueError("Per-sample CFO array must match sample_count")
        bravo_phase = numpy.empty(sample_count, dtype=numpy.float64)
        bravo_phase[0] = 0.0
        bravo_phase[1:] = numpy.cumsum(2.0 * numpy.pi * cfo[:-1] / sample_rate)

    rotator = numpy.exp(1j * bravo_phase)
    bravo2 = 1.12 * numpy.exp(-1j * 1.17) * pilot * rotator
    bravo3 = 0.91 * numpy.exp(1j * 2.08) * pilot * rotator
    return [
        channel.astype(numpy.complex64)
        for channel in (alpha0, alpha1, bravo2, bravo3)
    ]


def _run_block(block, inputs, max_noutput_items=127):
    flowgraph = gr.top_block()
    sources = [blocks.vector_source_c(channel, False) for channel in inputs]
    sinks = [blocks.vector_sink_c() for _ in inputs]
    for channel in range(4):
        flowgraph.connect(sources[channel], (block, channel))
        flowgraph.connect((block, channel), sinks[channel])
    flowgraph.run(max_noutput_items=max_noutput_items)
    return [
        numpy.asarray(sink.data(), dtype=numpy.complex64) for sink in sinks
    ], sinks


class qa_continuous_cross_sdr_cfo_corrector(gr_unittest.TestCase):
    def test_post_lock_cfo_change_is_tracked_and_tag_is_delayed_until_stable(self):
        sample_rate = 100000.0
        estimation_samples = 2048
        tracking_window = 2048
        # Leave enough constant-CFO input for coarse acquisition plus both
        # possible residual-refinement windows.  The CFO change must begin only
        # after the parent corrector has actually had an opportunity to lock;
        # otherwise this is an acquisition-rejection test, not a post-lock
        # continuous-tracking test.
        acquisition_end = 4 * estimation_samples
        sample_count = acquisition_end + 5 * tracking_window + 2000

        # Acquisition sees +100 Hz and would have frozen there in the old block.
        # Immediately afterwards Bravo moves to +100.4 Hz. A frozen rotator
        # leaves a 0.4-Hz phase ramp; the continuous tracker must remove it.
        cfo = numpy.full(sample_count, 100.4, dtype=numpy.float64)
        cfo[:acquisition_end] = 100.0
        inputs = _pilot_channels(sample_rate, sample_count, cfo)

        corrector = doa.continuous_cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            max_refinement_rounds=2,
            retry_delay_samples=10000,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
            tracking_window_samples=tracking_window,
            tracking_warmup_samples=128,
            tracking_lock_tolerance_hz=0.03,
            tracking_agreement_tolerance_hz=0.05,
            tracking_max_residual_hz=5.0,
            tracking_gain=1.0,
            tracking_lock_windows=2,
            tracking_min_coherence=0.99,
            tracking_log_every=100,
        )

        outputs, sinks = _run_block(corrector, inputs)

        self.assertTrue(corrector.locked())
        self.assertGreaterEqual(corrector.tracking_update_count(), 3)
        self.assertEqual(corrector.tracking_rejection_count(), 0)
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 100.4, places=2)
        self.assertLess(abs(corrector.tracking_residual_hz()), 0.03)

        numpy.testing.assert_array_equal(outputs[0], inputs[0])
        numpy.testing.assert_array_equal(outputs[1], inputs[1])
        correction2 = outputs[2][acquisition_end:] / inputs[2][acquisition_end:]
        correction3 = outputs[3][acquisition_end:] / inputs[3][acquisition_end:]
        numpy.testing.assert_allclose(correction2, correction3, rtol=2e-6, atol=2e-6)

        tail = 2500
        relative_phase = numpy.unwrap(
            numpy.angle(outputs[2][-tail:] * numpy.conj(outputs[0][-tail:]))
        )
        slope = numpy.polyfit(numpy.arange(tail), relative_phase, 1)[0]
        residual_hz = slope * sample_rate / (2.0 * numpy.pi)
        self.assertLess(abs(residual_hz), 0.03)

        lock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        self.assertEqual(len(lock_tags), 1)
        self.assertGreater(lock_tags[0].offset, acquisition_end)

    def test_large_common_frequency_state_change_reacquires(self):
        sample_rate = 100000.0
        window = 2048
        acquisition_end = 4 * window
        transition_at = acquisition_end + 4 * window
        sample_count = transition_at + 10 * window

        # A large common slope can be genuine hardware drift, but it can also
        # be a stream/state discontinuity whose fitted slope looks coherent.
        # Above the configured post-lock limit it must disarm downstream
        # calibration and reacquire instead of silently changing the rotator.
        cfo = numpy.full(sample_count, 180.0, dtype=numpy.float64)
        cfo[:transition_at] = 100.0
        inputs = _pilot_channels(sample_rate, sample_count, cfo)

        corrector = doa.continuous_cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=window,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            max_refinement_rounds=3,
            retry_delay_samples=10000,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
            tracking_window_samples=window,
            post_lock_tracking_window_samples=128,
            tracking_warmup_samples=0,
            tracking_lock_tolerance_hz=0.03,
            tracking_agreement_tolerance_hz=0.05,
            # Deliberately below the later +80 Hz state change.
            tracking_max_residual_hz=5.0,
            tracking_gain=1.0,
            tracking_lock_windows=2,
            tracking_min_coherence=0.99,
            tracking_log_every=100,
        )

        outputs, sinks = _run_block(corrector, inputs)

        self.assertTrue(corrector.locked())
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 180.0, places=1)
        self.assertEqual(corrector.discontinuity_count(), 1)
        self.assertEqual(corrector.relock_count(), 1)
        self.assertGreaterEqual(corrector.tracking_rejection_count(), 2)
        self.assertEqual(corrector.tracking_window_samples, 128)
        numpy.testing.assert_array_equal(outputs[0], inputs[0])
        numpy.testing.assert_array_equal(outputs[1], inputs[1])

        lock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        unlock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_unlocked"
        ]
        self.assertEqual(len(lock_tags), 2)
        self.assertEqual(len(unlock_tags), 1)
        self.assertLess(lock_tags[0].offset, unlock_tags[0].offset)
        self.assertLess(unlock_tags[0].offset, lock_tags[1].offset)


if __name__ == "__main__":
    gr_unittest.run(qa_continuous_cross_sdr_cfo_corrector)
