#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

import gnuradio
import numpy
import pmt

for search_path in sys.path:
    test_gnuradio = os.path.join(search_path, "gnuradio")
    candidate = os.path.join(
        test_gnuradio, "doa", "cross_sdr_pilot_phase_corrector.py"
    )
    if os.path.isfile(candidate):
        gnuradio.__path__.insert(0, test_gnuradio)
        break

from gnuradio import blocks, doa, gr, gr_unittest


class qa_cross_sdr_pilot_phase_corrector(gr_unittest.TestCase):
    def test_nonlinear_common_phase_is_removed_from_pilot_and_target(self):
        sample_count = 8192
        acquisition = 512
        index = numpy.arange(sample_count, dtype=numpy.float64)
        pilot_tone = numpy.exp(1j * 0.071 * index)
        target_tone = numpy.exp(1j * 0.137 * index)
        hardware = numpy.exp(1j * numpy.asarray([0.0, 0.4, -1.1, 2.0]))
        pilot_steering = numpy.exp(
            1j * numpy.asarray([0.2, -0.3, 0.8, -1.4])
        )
        target_steering = numpy.exp(
            1j * numpy.asarray([-0.1, 0.7, -1.2, 1.1])
        )
        common_phase = 0.7 * numpy.sin(0.004 * index)
        common_phase[2500:] += 2.4
        common_phase[5000:] -= 1.7
        common = numpy.exp(1j * common_phase)

        pilots = []
        targets = []
        for channel in range(4):
            bravo_motion = common if channel >= 2 else 1.0
            pilots.append((
                hardware[channel] * pilot_steering[channel]
                * pilot_tone * bravo_motion
            ).astype(numpy.complex64))
            targets.append((
                hardware[channel] * target_steering[channel]
                * target_tone * bravo_motion
            ).astype(numpy.complex64))

        tracker = doa.cross_sdr_pilot_phase_corrector(
            settling_samples=0,
            acquisition_samples=acquisition,
            min_coherence=0.90,
            max_differential_phase_rad=0.2,
            max_alignment_lag=0,
            phase_smoothing_samples=1,
        )
        flowgraph = gr.top_block()
        sinks = []
        for channel, data in enumerate(pilots + targets):
            source = blocks.vector_source_c(data, False)
            sink = blocks.vector_sink_c()
            setattr(self, f"source_{channel}", source)
            sinks.append(sink)
            flowgraph.connect(source, (tracker, channel))
            flowgraph.connect((tracker, channel), sink)
        flowgraph.run(max_noutput_items=173)

        self.assertTrue(tracker.locked())
        output = [numpy.asarray(sink.data()) for sink in sinks]
        reference_common = numpy.sum(common[acquisition - 64:acquisition])
        reference_common /= abs(reference_common)
        comparison_start = acquisition + 32
        for channel in (2, 3):
            expected_pilot = (
                hardware[channel] * pilot_steering[channel]
                * pilot_tone * reference_common
            )
            expected_target = (
                hardware[channel] * target_steering[channel]
                * target_tone * reference_common
            )
            numpy.testing.assert_allclose(
                output[channel][comparison_start:],
                expected_pilot[comparison_start:],
                rtol=0.0,
                atol=3e-4,
            )
            numpy.testing.assert_allclose(
                output[channel + 4][comparison_start:],
                expected_target[comparison_start:],
                rtol=0.0,
                atol=3e-4,
            )

        lock_tags = [
            tag for tag in sinks[0].tags()
            if pmt.symbol_to_string(tag.key) == "cfo_locked"
        ]
        self.assertEqual(len(lock_tags), 1)
        self.assertEqual(lock_tags[0].offset, acquisition)

    def test_amplitude_marker_aligns_a_lagging_bravo_stream(self):
        sample_count = 12288
        acquisition = 2048
        lag = 5
        index = numpy.arange(sample_count + lag, dtype=numpy.float64)
        marker = 1.0 + 0.45 * numpy.cos(0.097 * index)
        pilot = marker * numpy.exp(1j * 0.031 * index)
        target = numpy.exp(1j * 0.083 * index)
        common = numpy.exp(1j * (0.4 * numpy.sin(0.0021 * index)))

        pilots = [pilot[:sample_count], pilot[:sample_count]]
        targets = [target[:sample_count], target[:sample_count]]
        # At a common GNU Radio item index, Bravo contains a signal sample that
        # is `lag` samples newer than Alpha, so the measured lag is negative.
        pilots.extend([
            pilot[lag:lag + sample_count] * common[lag:lag + sample_count],
            pilot[lag:lag + sample_count] * common[lag:lag + sample_count]
            * numpy.exp(0.2j),
        ])
        targets.extend([
            target[lag:lag + sample_count] * common[lag:lag + sample_count],
            target[lag:lag + sample_count] * common[lag:lag + sample_count]
            * numpy.exp(0.2j),
        ])

        tracker = doa.cross_sdr_pilot_phase_corrector(
            settling_samples=0,
            acquisition_samples=acquisition,
            min_coherence=0.90,
            max_differential_phase_rad=0.3,
            max_alignment_lag=8,
            phase_smoothing_samples=1,
        )
        flowgraph = gr.top_block()
        sinks = []
        for channel, data in enumerate(pilots + targets):
            source = blocks.vector_source_c(
                numpy.asarray(data, dtype=numpy.complex64), False
            )
            sink = blocks.vector_sink_c()
            sinks.append(sink)
            flowgraph.connect(source, (tracker, channel))
            flowgraph.connect((tracker, channel), sink)
        flowgraph.run(max_noutput_items=191)

        self.assertTrue(tracker.locked())
        self.assertEqual(tracker._alignment_lag, -lag)
        output = [numpy.asarray(sink.data()) for sink in sinks]
        start = acquisition + 128
        cross = output[4][start:] * numpy.conj(output[6][start:])
        self.assertGreater(abs(numpy.mean(cross / numpy.abs(cross))), 0.999)


if __name__ == "__main__":
    gr_unittest.run(qa_cross_sdr_pilot_phase_corrector)
