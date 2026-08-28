#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

import gnuradio
import numpy
import pmt

# GR_ADD_TEST places the source package under test_modules/gnuradio, while the
# system GNU Radio package is a regular package. Put that generated test path
# first so this QA actually exercises the just-built Python blocks rather than
# an older installed gr-doa module.
for search_path in sys.path:
    test_gnuradio = os.path.join(search_path, "gnuradio")
    if os.path.isfile(os.path.join(test_gnuradio, "doa", "cross_sdr_cfo_corrector.py")):
        gnuradio.__path__.insert(0, test_gnuradio)
        break

from gnuradio import blocks
from gnuradio import doa
from gnuradio import filter as gr_filter
from gnuradio import gr
from gnuradio import gr_unittest


def _pilot_channels(sample_rate, sample_count, bravo_cfo_hz, phases=None):
    if phases is None:
        phases = (0.0, 0.31, -1.17, 2.08)
    sample_index = numpy.arange(sample_count, dtype=numpy.float64)
    pilot = numpy.exp(1j * (2.0 * numpy.pi * 4100.0 / sample_rate * sample_index))
    alpha0 = numpy.exp(1j * phases[0]) * pilot
    alpha1 = 0.83 * numpy.exp(1j * phases[1]) * pilot
    bravo_cfo = numpy.asarray(bravo_cfo_hz, dtype=numpy.float64)
    if bravo_cfo.ndim == 0:
        bravo_phase = 2.0 * numpy.pi * bravo_cfo / sample_rate * sample_index
    else:
        if bravo_cfo.size != sample_count:
            raise ValueError("Per-sample CFO array must match sample_count")
        bravo_phase = numpy.empty(sample_count, dtype=numpy.float64)
        bravo_phase[0] = 0.0
        bravo_phase[1:] = numpy.cumsum(
            2.0 * numpy.pi * bravo_cfo[:-1] / sample_rate
        )
    bravo_rotator = numpy.exp(1j * bravo_phase)
    bravo2 = 1.12 * numpy.exp(1j * phases[2]) * pilot * bravo_rotator
    bravo3 = 0.91 * numpy.exp(1j * phases[3]) * pilot * bravo_rotator
    return [
        channel.astype(numpy.complex64)
        for channel in (alpha0, alpha1, bravo2, bravo3)
    ]


def _run_block(block, inputs, max_noutput_items=257):
    flowgraph = gr.top_block()
    sources = [blocks.vector_source_c(channel, False) for channel in inputs]
    sinks = [blocks.vector_sink_c() for _ in inputs]
    for channel in range(len(inputs)):
        flowgraph.connect(sources[channel], (block, channel))
        flowgraph.connect((block, channel), sinks[channel])
    flowgraph.run(max_noutput_items=max_noutput_items)
    return [numpy.asarray(sink.data(), dtype=numpy.complex64) for sink in sinks], sinks


class qa_cross_sdr_cfo_corrector(gr_unittest.TestCase):
    def test_long_settling_filters_only_the_final_warmup_tail(self):
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=100000.0,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=10000,
            estimation_samples=4096,
            max_abs_cfo_hz=1000.0,
        )
        input_items = [numpy.ones(1024, dtype=numpy.complex64) for _ in range(4)]
        output_items = [numpy.empty(1024, dtype=numpy.complex64) for _ in range(4)]
        filtered_counts = []
        original_filter = corrector._filter_pilot_segment

        def recording_filter(inputs, outputs, start, stop):
            filtered_counts.append(stop - start)
            return original_filter(inputs, outputs, start, stop)

        corrector._filter_pilot_segment = recording_filter
        self.assertEqual(corrector.work(input_items, output_items), 1024)
        self.assertEqual(filtered_counts, [])
        self.assertEqual(corrector.settling_remaining, 8976)

        corrector.settling_remaining = corrector._pilot_filter_warmup_samples
        self.assertEqual(corrector.work(input_items, output_items), 1024)
        self.assertEqual(filtered_counts, [1024])

    def test_common_rotator_preserves_alpha_phase_and_chunk_continuity(self):
        sample_rate = 100000.0
        settling_samples = 37
        estimation_samples = 4096
        correction_start = settling_samples + estimation_samples
        lock_offset = correction_start + estimation_samples
        inputs = _pilot_channels(sample_rate, lock_offset + 5000, 123.75)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=settling_samples,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )

        outputs, sinks = _run_block(corrector, inputs)
        self.assertTrue(corrector.locked())
        self.assertFalse(corrector.failed())
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 123.75, places=3)
        numpy.testing.assert_array_equal(outputs[0], inputs[0])
        numpy.testing.assert_array_equal(outputs[1], inputs[1])
        numpy.testing.assert_array_equal(
            outputs[2][:correction_start], inputs[2][:correction_start]
        )
        numpy.testing.assert_array_equal(
            outputs[3][:correction_start], inputs[3][:correction_start]
        )

        correction2 = outputs[2][correction_start:] / inputs[2][correction_start:]
        correction3 = outputs[3][correction_start:] / inputs[3][correction_start:]
        numpy.testing.assert_allclose(correction2, correction3, rtol=2e-6, atol=2e-6)
        correction_steps = numpy.angle(
            correction2[1:] * numpy.conj(correction2[:-1])
        )
        validation_end = estimation_samples
        numpy.testing.assert_allclose(
            correction_steps[:validation_end - 1],
            correction_steps[0],
            rtol=0.0,
            atol=2e-6,
        )
        numpy.testing.assert_allclose(
            correction_steps[validation_end:],
            -2.0 * numpy.pi * corrector.accepted_cfo_hz() / sample_rate,
            rtol=0.0,
            atol=2e-6,
        )
        # The first sample after changing the frozen frequency continues from
        # the prior phase; only subsequent phase increments use the new step.
        self.assertAlmostEqual(
            correction_steps[validation_end - 1], correction_steps[0], places=6
        )

        relative_phase = numpy.unwrap(
            numpy.angle(
                outputs[2][correction_start:]
                * numpy.conj(outputs[0][correction_start:])
            )
        )
        fitted_slope = numpy.polyfit(numpy.arange(relative_phase.size), relative_phase, 1)[0]
        self.assertAlmostEqual(fitted_slope, 0.0, places=6)

        lock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        self.assertEqual(len(lock_tags), 1)
        self.assertEqual(lock_tags[0].offset, lock_offset)

    def test_disagreeing_estimates_are_rejected_without_modifying_streams(self):
        sample_rate = 100000.0
        sample_count = 5000
        inputs = _pilot_channels(sample_rate, sample_count, 100.0)
        sample_index = numpy.arange(sample_count, dtype=numpy.float64)
        inputs[3] *= numpy.exp(
            1j * 2.0 * numpy.pi * 25.0 / sample_rate * sample_index
        ).astype(numpy.complex64)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=4096,
            validation_settling_samples=0,
            agreement_tolerance_hz=5.0,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )

        outputs, sinks = _run_block(corrector, inputs)
        self.assertFalse(corrector.locked())
        self.assertTrue(corrector.failed())
        for output, expected in zip(outputs, inputs):
            numpy.testing.assert_array_equal(output, expected)
        for sink in sinks:
            self.assertFalse(any(
                pmt.symbol_to_string(tag.key) == "cfo_locked"
                for tag in sink.tags()
            ))

    def test_sparse_zero_samples_do_not_poison_an_otherwise_valid_window(self):
        sample_rate = 100000.0
        estimation_samples = 4096
        inputs = _pilot_channels(sample_rate, 2 * estimation_samples + 1000, 64.25)
        # Model intermittent source zeros while retaining 80% of the defined
        # time window. The old maximum-based validity test rejected this case.
        for channel in (0, 2, 3):
            inputs[channel][::5] = 0.0
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )

        _run_block(corrector, inputs)
        self.assertTrue(corrector.locked())
        self.assertEqual(corrector.rejection_count(), 0)
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 64.25, places=3)

    def test_invalid_first_window_retries_and_locks_without_restart(self):
        sample_rate = 100000.0
        estimation_samples = 1024
        retry_delay = 128
        second_window_start = estimation_samples + retry_delay
        sample_count = second_window_start + 2 * estimation_samples + 1000
        inputs = _pilot_channels(sample_rate, sample_count, 51.5)
        for channel in range(4):
            inputs[channel][:estimation_samples] = 0.0
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            retry_delay_samples=retry_delay,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )

        outputs, sinks = _run_block(corrector, inputs, max_noutput_items=97)
        self.assertTrue(corrector.locked())
        self.assertFalse(corrector.failed())
        self.assertEqual(corrector.rejection_count(), 1)
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 51.5, places=3)
        lock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        self.assertEqual(len(lock_tags), 1)
        self.assertEqual(
            lock_tags[0].offset,
            second_window_start + 2 * estimation_samples,
        )
        numpy.testing.assert_array_equal(outputs[0], inputs[0])
        numpy.testing.assert_array_equal(outputs[1], inputs[1])

    def test_lock_tag_gates_downstream_phase_calibration(self):
        sample_rate = 100000.0
        cfo_settling = 41
        cfo_samples = 2048
        phase_settling = 73
        phase_samples = 2048
        sample_count = (
            cfo_settling + 2 * cfo_samples
            + phase_settling + phase_samples + 500
        )
        inputs = _pilot_channels(sample_rate, sample_count, 87.5)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=cfo_settling,
            estimation_samples=cfo_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )
        calibration = doa.uca_pilot_calibration(
            num_inputs=4,
            norm_radius=0.1,
            pilot_angle=0.0,
            element0_angle=0.0,
            element_angle_step=90.0,
            skip_samples=phase_settling,
            calibration_samples=phase_samples,
            config_filename="",
            start_tag_key="cfo_locked",
        )

        flowgraph = gr.top_block()
        sources = [blocks.vector_source_c(channel, False) for channel in inputs]
        sinks = [blocks.vector_sink_c() for _ in inputs]
        for channel in range(4):
            flowgraph.connect(sources[channel], (corrector, channel))
            flowgraph.connect((corrector, channel), (calibration, channel))
            flowgraph.connect((calibration, channel), sinks[channel])
        flowgraph.run(max_noutput_items=193)

        self.assertTrue(corrector.locked())
        self.assertTrue(calibration.calibrated())
        calibration_start = cfo_settling + 2 * cfo_samples
        calibration_end = calibration_start + phase_settling + phase_samples
        for sink in sinks:
            output = numpy.asarray(sink.data(), dtype=numpy.complex64)
            numpy.testing.assert_array_equal(
                output[:calibration_end],
                numpy.zeros(calibration_end, dtype=numpy.complex64),
            )
            self.assertGreater(numpy.max(numpy.abs(output[calibration_end:])), 0.1)

    def test_lock_tag_survives_existing_decimating_filter_stage(self):
        sample_rate = 100000.0
        decimation = 4
        cfo_samples = 1024
        phase_samples = 256
        sample_count = 3 * cfo_samples + decimation * (phase_samples + 128)
        inputs = _pilot_channels(sample_rate, sample_count, 42.0)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=cfo_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )
        calibration = doa.uca_pilot_calibration(
            num_inputs=4,
            norm_radius=0.1,
            pilot_angle=0.0,
            element0_angle=0.0,
            element_angle_step=90.0,
            skip_samples=16,
            calibration_samples=phase_samples,
            config_filename="",
            min_coherence=0.99,
            start_tag_key="cfo_locked",
        )

        flowgraph = gr.top_block()
        sources = [blocks.vector_source_c(channel, False) for channel in inputs]
        filters = [
            gr_filter.freq_xlating_fir_filter_ccc(
                decimation, [1.0], 0.0, sample_rate
            )
            for _ in range(4)
        ]
        sinks = [blocks.vector_sink_c() for _ in inputs]
        for channel in range(4):
            flowgraph.connect(sources[channel], (corrector, channel))
            flowgraph.connect((corrector, channel), filters[channel])
            flowgraph.connect(filters[channel], (calibration, channel))
            flowgraph.connect((calibration, channel), sinks[channel])
        flowgraph.run(max_noutput_items=113)

        self.assertTrue(corrector.locked())
        self.assertTrue(calibration.calibrated())

    def test_residual_validation_refines_a_changed_cfo_before_lock(self):
        sample_rate = 100000.0
        estimation_samples = 2048
        coarse_cfo_hz = 100.0
        final_cfo_hz = 112.5
        lock_offset = 3 * estimation_samples
        cfo = numpy.full(lock_offset + 1000, final_cfo_hz, dtype=numpy.float64)
        cfo[:estimation_samples] = coarse_cfo_hz
        inputs = _pilot_channels(sample_rate, cfo.size, cfo)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            max_refinement_rounds=2,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )

        outputs, sinks = _run_block(corrector, inputs, max_noutput_items=131)
        self.assertTrue(corrector.locked())
        self.assertFalse(corrector.failed())
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), final_cfo_hz, places=3)
        lock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        self.assertEqual(len(lock_tags), 1)
        self.assertEqual(lock_tags[0].offset, lock_offset)

        # The rotator frequency changes after round one without a phase jump,
        # then the final corrected relative phase is flat before lock is emitted.
        correction = outputs[2][estimation_samples:] / inputs[2][estimation_samples:]
        phase_step = numpy.angle(correction[1:] * numpy.conj(correction[:-1]))
        boundary = estimation_samples
        self.assertLess(
            abs(numpy.angle(correction[boundary] * numpy.conj(correction[boundary - 1]))),
            0.02,
        )
        numpy.testing.assert_allclose(
            phase_step[boundary + 1:],
            -2.0 * numpy.pi * final_cfo_hz / sample_rate,
            rtol=0.0,
            atol=2e-6,
        )
        relative_phase = numpy.unwrap(
            numpy.angle(outputs[2][2 * estimation_samples:] * numpy.conj(
                outputs[0][2 * estimation_samples:]
            ))
        )
        fitted_slope = numpy.polyfit(
            numpy.arange(relative_phase.size), relative_phase, 1
        )[0]
        self.assertLess(abs(fitted_slope), 1e-6)

    def test_nonconvergent_residual_is_rejected_without_lock_tag(self):
        sample_rate = 100000.0
        estimation_samples = 2048
        sample_count = 3 * estimation_samples + 500
        cfo = numpy.full(sample_count, 137.5, dtype=numpy.float64)
        cfo[:estimation_samples] = 100.0
        cfo[estimation_samples:2 * estimation_samples] = 112.5
        inputs = _pilot_channels(sample_rate, sample_count, cfo)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.01,
            max_refinement_rounds=2,
            retry_delay_samples=10000,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )

        outputs, sinks = _run_block(corrector, inputs, max_noutput_items=127)
        self.assertFalse(corrector.locked())
        self.assertTrue(corrector.failed())
        self.assertEqual(corrector.rejection_count(), 1)
        self.assertIn("post-correction residual", corrector.last_failure_reason())
        numpy.testing.assert_array_equal(outputs[0], inputs[0])
        numpy.testing.assert_array_equal(outputs[1], inputs[1])
        for sink in sinks:
            self.assertFalse(any(
                pmt.symbol_to_string(tag.key) == "cfo_locked"
                for tag in sink.tags()
            ))

    def test_pilot_selector_rejects_a_stronger_off_frequency_tone(self):
        sample_rate = 100000.0
        settling_samples = 256
        estimation_samples = 4096
        validation_settling = 256
        sample_count = (
            settling_samples + estimation_samples
            + validation_settling + estimation_samples + 1000
        )
        pilot_cfo_hz = 73.25
        inputs = _pilot_channels(sample_rate, sample_count, pilot_cfo_hz)

        # Model the hardware screenshots: the selected OTA pilot is accompanied
        # by another, stronger tone whose Alpha-vs-Bravo slope is different. A
        # full-band cross product follows this interferer; the pilot selector
        # must continue to estimate the +4.1 kHz pilot itself.
        sample_index = numpy.arange(sample_count, dtype=numpy.float64)
        alpha_interferer = 4.0 * numpy.exp(
            1j * 2.0 * numpy.pi * 15000.0 / sample_rate * sample_index
        )
        bravo_interferer = 4.0 * numpy.exp(
            1j * (
                2.0 * numpy.pi * (15000.0 - 300.0) / sample_rate * sample_index
                + 0.7
            )
        )
        inputs[0] += alpha_interferer.astype(numpy.complex64)
        inputs[2] += bravo_interferer.astype(numpy.complex64)
        inputs[3] += (0.8 * bravo_interferer).astype(numpy.complex64)

        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=settling_samples,
            estimation_samples=estimation_samples,
            validation_settling_samples=validation_settling,
            residual_tolerance_hz=0.05,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
        )

        _run_block(corrector, inputs, max_noutput_items=137)
        self.assertTrue(corrector.locked())
        self.assertFalse(corrector.failed())
        self.assertAlmostEqual(
            corrector.accepted_cfo_hz(), pilot_cfo_hz, places=2
        )

    def test_slowly_drifting_cfo_after_initial_lock_is_tracked(self):
        sample_rate = 100000.0
        estimation_samples = 2048
        tracking_samples = 1024
        lock_offset = 2 * estimation_samples
        sample_count = lock_offset + 24 * tracking_samples
        cfo = numpy.full(sample_count, 60.0, dtype=numpy.float64)
        cfo[lock_offset:] = numpy.linspace(
            60.0, 66.0, sample_count - lock_offset
        )
        inputs = _pilot_channels(sample_rate, sample_count, cfo)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.1,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
            tracking_window_samples=tracking_samples,
            tracking_phase_gain=0.25,
            phase_jump_threshold_rad=1.5,
        )

        outputs, _ = _run_block(corrector, inputs, max_noutput_items=173)
        self.assertTrue(corrector.locked())
        self.assertEqual(corrector.discontinuity_count(), 0)
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 66.0, delta=0.8)
        final = slice(sample_count - 4 * tracking_samples, sample_count)
        relative_phase = numpy.unwrap(numpy.angle(
            outputs[2][final] * numpy.conj(outputs[0][final])
        ))
        slope_hz = numpy.polyfit(
            numpy.arange(relative_phase.size), relative_phase, 1
        )[0] * sample_rate / (2.0 * numpy.pi)
        self.assertAlmostEqual(slope_hz, 0.0, delta=0.8)

    def test_bravo_internal_phase_is_preserved_during_continuous_tracking(self):
        sample_rate = 100000.0
        estimation_samples = 1024
        tracking_samples = 512
        sample_count = 2 * estimation_samples + 12 * tracking_samples
        cfo = numpy.linspace(80.0, 83.0, sample_count)
        inputs = _pilot_channels(sample_rate, sample_count, cfo)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=1.0,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
            tracking_window_samples=tracking_samples,
            phase_jump_threshold_rad=1.5,
        )

        outputs, _ = _run_block(corrector, inputs, max_noutput_items=89)
        correction_start = estimation_samples
        correction2 = outputs[2][correction_start:] / inputs[2][correction_start:]
        correction3 = outputs[3][correction_start:] / inputs[3][correction_start:]
        numpy.testing.assert_allclose(correction2, correction3, atol=2e-6, rtol=2e-6)
        input_internal = inputs[3] * numpy.conj(inputs[2])
        output_internal = outputs[3] * numpy.conj(outputs[2])
        numpy.testing.assert_allclose(
            output_internal[correction_start:],
            input_internal[correction_start:],
            atol=3e-6,
            rtol=3e-6,
        )

    def test_tracking_updates_are_phase_continuous_across_chunk_boundaries(self):
        sample_rate = 100000.0
        estimation_samples = 1024
        tracking_samples = 256
        sample_count = 2 * estimation_samples + 16 * tracking_samples
        cfo = numpy.full(sample_count, 95.0)
        cfo[2 * estimation_samples:] = 98.0
        inputs = _pilot_channels(sample_rate, sample_count, cfo)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
            tracking_window_samples=tracking_samples,
            phase_jump_threshold_rad=1.5,
        )

        outputs, _ = _run_block(corrector, inputs, max_noutput_items=73)
        correction_start = estimation_samples
        correction = outputs[2][correction_start:] / inputs[2][correction_start:]
        phase_steps = numpy.angle(correction[1:] * numpy.conj(correction[:-1]))
        # A frequency update changes the next increment, never the accumulated
        # rotator phase. No scheduler or tracking boundary can create a phase step.
        self.assertLess(numpy.max(numpy.abs(phase_steps)), 0.02)
        self.assertTrue(numpy.all(numpy.isfinite(phase_steps)))

    def test_continuous_tracker_preserves_fixed_nonzero_phase(self):
        sample_rate = 100000.0
        estimation_samples = 2048
        tracking_samples = 512
        lock_offset = 2 * estimation_samples
        sample_count = lock_offset + 16 * tracking_samples
        inputs = _pilot_channels(
            sample_rate, sample_count, 71.0,
            phases=(0.2, -0.1, 1.35, -2.0),
        )
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=0.05,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.99,
            tracking_window_samples=tracking_samples,
            phase_jump_threshold_rad=1.5,
        )

        outputs, _ = _run_block(corrector, inputs, max_noutput_items=101)
        phase = numpy.angle(outputs[2] * numpy.conj(outputs[0]))
        captured = numpy.angle(numpy.mean(numpy.exp(
            1j * phase[lock_offset:lock_offset + tracking_samples]
        )))
        final = numpy.angle(numpy.mean(numpy.exp(
            1j * phase[-tracking_samples:]
        )))
        self.assertGreater(abs(captured), 0.25)
        self.assertAlmostEqual(
            numpy.angle(numpy.exp(1j * (final - captured))), 0.0, delta=0.05
        )

    def test_abrupt_phase_discontinuity_emits_unlock_and_relocks(self):
        sample_rate = 100000.0
        estimation_samples = 1024
        tracking_samples = 256
        lock_offset = 2 * estimation_samples
        jump_offset = lock_offset + 3 * tracking_samples + 51
        sample_count = jump_offset + 4 * estimation_samples
        inputs = _pilot_channels(sample_rate, sample_count, 55.0)
        jump = numpy.complex64(numpy.exp(1j * 1.4))
        inputs[2][jump_offset:] *= jump
        inputs[3][jump_offset:] *= jump
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=1.0,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.95,
            tracking_window_samples=tracking_samples,
            tracking_phase_gain=0.25,
            phase_jump_threshold_rad=0.6,
        )

        outputs, sinks = _run_block(corrector, inputs, max_noutput_items=79)
        self.assertTrue(corrector.locked())
        self.assertEqual(corrector.discontinuity_count(), 1)
        self.assertEqual(corrector.relock_count(), 1)
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
        numpy.testing.assert_array_equal(outputs[0], inputs[0])
        numpy.testing.assert_array_equal(outputs[1], inputs[1])
        internal_error = numpy.max(numpy.abs(
            outputs[3][estimation_samples:] * numpy.conj(outputs[2][estimation_samples:])
            - inputs[3][estimation_samples:] * numpy.conj(inputs[2][estimation_samples:])
        ))
        self.assertLess(internal_error, 5e-6)

    def test_abrupt_common_cfo_step_retains_lock_and_phase_reference(self):
        sample_rate = 100000.0
        estimation_samples = 4096
        tracking_samples = 512
        validation_settling = 2048
        lock_offset = 2 * estimation_samples + validation_settling
        step_offset = lock_offset + 3 * tracking_samples + 79
        sample_count = step_offset + 12 * tracking_samples
        cfo = numpy.full(sample_count, 60.0, dtype=numpy.float64)
        cfo[step_offset:] = 310.0
        inputs = _pilot_channels(sample_rate, sample_count, cfo)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=validation_settling,
            residual_tolerance_hz=1.0,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.95,
            tracking_window_samples=tracking_samples,
            phase_jump_threshold_rad=0.6,
        )

        _, sinks = _run_block(corrector, inputs, max_noutput_items=83)
        self.assertTrue(corrector.locked())
        self.assertEqual(corrector.discontinuity_count(), 0)
        self.assertEqual(corrector.relock_count(), 0)
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 310.0, delta=1.0)
        lock_offsets = [
            tag.offset for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        unlock_offsets = [
            tag.offset for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_unlocked"
        ]
        self.assertEqual(len(lock_offsets), 1)
        self.assertEqual(unlock_offsets, [])

    def test_recurring_common_cfo_state_changes_do_not_cycle_lock(self):
        sample_rate = 100000.0
        estimation_samples = 4096
        tracking_samples = 512
        validation_settling = 2048
        lock_offset = 2 * estimation_samples + validation_settling
        first_transition = lock_offset + 3 * tracking_samples + 79
        transition_spacing = 5 * tracking_samples
        transition_values = (310.0, -140.0, 310.0, 60.0)
        sample_count = (
            first_transition
            + len(transition_values) * transition_spacing
            + 6 * tracking_samples
        )
        cfo = numpy.full(sample_count, 60.0, dtype=numpy.float64)
        for index, value in enumerate(transition_values):
            offset = first_transition + index * transition_spacing
            cfo[offset:] = value
        inputs = _pilot_channels(sample_rate, sample_count, cfo)
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=validation_settling,
            residual_tolerance_hz=1.0,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.95,
            tracking_window_samples=tracking_samples,
            phase_jump_threshold_rad=2.0,
        )

        outputs, sinks = _run_block(corrector, inputs, max_noutput_items=83)
        self.assertTrue(corrector.locked())
        self.assertEqual(corrector.discontinuity_count(), 0)
        self.assertEqual(corrector.relock_count(), 0)
        self.assertAlmostEqual(corrector.accepted_cfo_hz(), 60.0, delta=2.0)
        lock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        unlock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_unlocked"
        ]
        self.assertEqual(len(lock_tags), 1)
        self.assertEqual(unlock_tags, [])
        numpy.testing.assert_array_equal(outputs[0], inputs[0])
        numpy.testing.assert_array_equal(outputs[1], inputs[1])

    def test_tracker_relock_restarts_downstream_ota_calibration(self):
        sample_rate = 100000.0
        estimation_samples = 1024
        tracking_samples = 256
        calibration_samples = 128
        initial_lock = 2 * estimation_samples
        jump_offset = initial_lock + 4 * tracking_samples + 37
        sample_count = jump_offset + 4 * estimation_samples
        inputs = _pilot_channels(sample_rate, sample_count, 44.0)
        common_jump = numpy.complex64(numpy.exp(1j * 1.3))
        inputs[2][jump_offset:] *= common_jump
        inputs[3][jump_offset:] *= common_jump
        corrector = doa.cross_sdr_cfo_corrector(
            samp_rate=sample_rate,
            pilot_offset_hz=4100.0,
            pilot_bandwidth_hz=1000.0,
            settling_samples=0,
            estimation_samples=estimation_samples,
            validation_settling_samples=0,
            residual_tolerance_hz=1.0,
            agreement_tolerance_hz=0.1,
            max_abs_cfo_hz=1000.0,
            min_coherence=0.95,
            tracking_window_samples=tracking_samples,
            phase_jump_threshold_rad=0.6,
        )
        calibration = doa.uca_pilot_calibration(
            num_inputs=4,
            norm_radius=0.1,
            pilot_angle=0.0,
            element0_angle=0.0,
            element_angle_step=90.0,
            skip_samples=0,
            calibration_samples=calibration_samples,
            config_filename="",
            min_coherence=0.90,
            start_tag_key="cfo_locked",
        )

        flowgraph = gr.top_block()
        sources = [blocks.vector_source_c(channel, False) for channel in inputs]
        sinks = [blocks.vector_sink_c() for _ in inputs]
        for channel in range(4):
            flowgraph.connect(sources[channel], (corrector, channel))
            flowgraph.connect((corrector, channel), (calibration, channel))
            flowgraph.connect((calibration, channel), sinks[channel])
        flowgraph.run(max_noutput_items=83)

        self.assertTrue(corrector.locked())
        self.assertEqual(corrector.relock_count(), 1)
        self.assertTrue(calibration.calibrated())
        sink_tags = sinks[0].tags()
        unlock_offset = next(
            tag.offset for tag in sink_tags
            if pmt.symbol_to_string(tag.key) == "cfo_unlocked"
        )
        # GNU Radio's default all-to-all propagation repeats the same tag from
        # each of the four calibration inputs on every output; offsets identify
        # the two distinct lock events.
        lock_offsets = sorted(set(
            tag.offset for tag in sink_tags
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ))
        self.assertEqual(len(lock_offsets), 2)
        output = numpy.asarray(sinks[0].data(), dtype=numpy.complex64)
        numpy.testing.assert_array_equal(
            output[unlock_offset:lock_offsets[1] + calibration_samples],
            numpy.zeros(
                lock_offsets[1] + calibration_samples - unlock_offset,
                dtype=numpy.complex64,
            ),
        )
        self.assertGreater(
            numpy.max(numpy.abs(output[lock_offsets[1] + calibration_samples:])),
            0.1,
        )


if __name__ == "__main__":
    gr_unittest.run(qa_cross_sdr_cfo_corrector)
