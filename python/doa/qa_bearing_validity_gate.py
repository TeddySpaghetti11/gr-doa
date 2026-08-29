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
    candidate = os.path.join(test_gnuradio, "doa", "bearing_validity_gate.py")
    if os.path.isfile(candidate):
        gnuradio.__path__.insert(0, test_gnuradio)
        break

from gnuradio import blocks
from gnuradio import doa
from gnuradio import gr
from gnuradio import gr_unittest


def _tag(offset, valid):
    tag = gr.tag_t()
    tag.offset = offset
    tag.key = pmt.intern("doa_valid")
    tag.value = pmt.from_bool(valid)
    tag.srcid = pmt.intern("qa")
    return tag


def _state_tag(offset, key):
    tag = gr.tag_t()
    tag.offset = offset
    tag.key = pmt.intern(key)
    tag.value = pmt.PMT_T
    tag.srcid = pmt.intern("qa")
    return tag


class qa_bearing_validity_gate(gr_unittest.TestCase):
    def test_invalid_intervals_hold_last_valid_value(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
        source = blocks.vector_source_f(
            values,
            False,
            1,
            [_tag(1, True), _tag(3, False), _tag(5, True)],
        )
        gate = doa.bearing_validity_gate(1, "doa_valid")
        sink = blocks.vector_sink_f(1)
        flowgraph = gr.top_block()
        flowgraph.connect(source, gate, sink)
        flowgraph.run()

        observed = numpy.asarray(sink.data(), dtype=numpy.float32)
        numpy.testing.assert_allclose(
            observed,
            [0.0, 20.0, 30.0, 30.0, 30.0, 60.0],
        )

    def test_invalid_covariance_holds_bearing_through_music_chain(self):
        snapshot_size = 64
        snapshot_count = 3
        sample_count = snapshot_size * snapshot_count
        bearing_deg = 70.0
        norm_radius = 0.25
        element_angles = numpy.deg2rad(numpy.arange(4) * 90.0)
        steering = numpy.exp(
            1j * 2.0 * numpy.pi * norm_radius
            * numpy.cos(numpy.deg2rad(bearing_deg) - element_angles)
        )
        tone = numpy.exp(1j * 0.13 * numpy.arange(sample_count))
        channels = [
            (steering[channel] * tone).astype(numpy.complex64)
            for channel in range(4)
        ]

        covariance = doa.autocorrelate(
            4,
            snapshot_size,
            0,
            0,
            "calibration_valid",
            "calibration_invalid",
            "doa_valid",
        )
        music = doa.MUSIC_uca(norm_radius, 1, 4, 360, 0.0, 90.0)
        peaks = doa.find_local_max(1, 360, 0.0, 360.0)
        gate = doa.bearing_validity_gate(1, "doa_valid")
        sink = blocks.vector_sink_f(1)
        flowgraph = gr.top_block()

        for channel, samples in enumerate(channels):
            tags = []
            if channel == 0:
                tags = [
                    _state_tag(snapshot_size, "calibration_valid"),
                    _state_tag(2 * snapshot_size, "calibration_invalid"),
                ]
            source = blocks.vector_source_c(samples, False, 1, tags)
            flowgraph.connect(source, (covariance, channel))
        flowgraph.connect(covariance, music, peaks)
        flowgraph.connect((peaks, 1), gate, sink)
        flowgraph.connect((peaks, 0), blocks.null_sink(gr.sizeof_float))
        flowgraph.run()

        observed = numpy.asarray(sink.data(), dtype=numpy.float32)
        self.assertEqual(observed.size, snapshot_count)
        self.assertEqual(observed[0], 0.0)
        self.assertAlmostEqual(observed[1], bearing_deg, delta=1.0)
        self.assertEqual(observed[2], observed[1])


if __name__ == "__main__":
    gr_unittest.run(qa_bearing_validity_gate)
