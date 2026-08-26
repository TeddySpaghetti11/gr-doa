#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy
from gnuradio import blocks
from gnuradio import doa
from gnuradio import gr
from gnuradio import gr_unittest


class qa_MUSIC_uca(gr_unittest.TestCase):
    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def test_single_source_bearing(self):
        num_elements = 4
        norm_radius = 0.346379923
        expected_bearings = numpy.asarray(
            [0.0, 1.0, 45.0, 73.0, 179.0, 225.0, 359.0]
        )
        spectrum_length = 720

        element_bearings = numpy.deg2rad(numpy.arange(num_elements) * 90.0)
        covariance_items = []
        for expected_bearing in expected_bearings:
            steering = numpy.exp(
                -1j * 2.0 * numpy.pi * norm_radius
                * numpy.cos(numpy.deg2rad(expected_bearing) - element_bearings)
            )
            covariance = (
                numpy.outer(steering, numpy.conj(steering))
                + 0.05 * numpy.eye(num_elements)
            ).astype(numpy.complex64)
            covariance_items.extend(covariance.flatten(order="F"))

        source = blocks.vector_source_c(
            covariance_items, False, num_elements * num_elements
        )
        music = doa.MUSIC_uca(
            norm_radius,
            1,
            num_elements,
            spectrum_length,
            0.0,
            90.0,
        )
        sink = blocks.vector_sink_f(spectrum_length)
        self.tb.connect(source, music, sink)
        self.tb.run()

        spectra = numpy.asarray(sink.data()).reshape(-1, spectrum_length)
        estimated_bearings = (
            360.0 * numpy.argmax(spectra, axis=1) / spectrum_length
        )
        numpy.testing.assert_allclose(
            estimated_bearings, expected_bearings, rtol=0.0, atol=1e-6
        )

    def test_upstream_covariance_to_uca_music(self):
        """Verify the unchanged Ettus covariance layout feeds UCA MUSIC."""
        num_elements = 4
        norm_radius = 0.346379923
        expected_bearing = 73.0
        spectrum_length = 720
        snapshot_size = 2048
        overlap_size = 1024
        sample_count = 8192

        element_bearings = numpy.deg2rad(numpy.arange(num_elements) * 90.0)
        steering = numpy.exp(
            -1j * 2.0 * numpy.pi * norm_radius
            * numpy.cos(numpy.deg2rad(expected_bearing) - element_bearings)
        )
        tone = numpy.exp(1j * 0.071 * numpy.arange(sample_count))
        random = numpy.random.default_rng(20260826)

        covariance = doa.autocorrelate(
            num_elements, snapshot_size, overlap_size, 0
        )
        music = doa.MUSIC_uca(
            norm_radius,
            1,
            num_elements,
            spectrum_length,
            0.0,
            90.0,
        )
        sink = blocks.vector_sink_f(spectrum_length)

        for channel in range(num_elements):
            noise = 0.03 * (
                random.standard_normal(sample_count)
                + 1j * random.standard_normal(sample_count)
            )
            samples = (steering[channel] * tone + noise).astype(numpy.complex64)
            source = blocks.vector_source_c(samples, False)
            setattr(self, f"source_{channel}", source)
            self.tb.connect(source, (covariance, channel))

        self.tb.connect(covariance, music, sink)
        self.tb.run()

        spectra = numpy.asarray(sink.data()).reshape(-1, spectrum_length)
        self.assertGreater(len(spectra), 0)
        estimated_bearings = (
            360.0 * numpy.argmax(spectra, axis=1) / spectrum_length
        )
        numpy.testing.assert_allclose(
            estimated_bearings,
            expected_bearing,
            rtol=0.0,
            atol=0.5,
        )


if __name__ == "__main__":
    gr_unittest.run(qa_MUSIC_uca)
