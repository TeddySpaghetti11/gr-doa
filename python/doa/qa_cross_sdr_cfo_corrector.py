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


if __name__ == "__main__":
    gr_unittest.run(qa_cross_sdr_cfo_corrector)
