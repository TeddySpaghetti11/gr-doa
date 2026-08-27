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

    @staticmethod
    def _source_steering(norm_radius, bearing_deg, element0_deg, step_deg, count):
        element_bearings = numpy.deg2rad(
            element0_deg + numpy.arange(count) * step_deg
        )
        return numpy.exp(
            1j * 2.0 * numpy.pi * norm_radius
            * numpy.cos(numpy.deg2rad(bearing_deg) - element_bearings)
        )

    def test_physical_channel_order_source_bearing(self):
        """Exercise the real LibreSDR channel order and source-bearing convention."""
        num_elements = 4
        norm_radius = 0.353265327
        element0_deg = 225.0
        element_step_deg = -90.0
        expected_bearings = numpy.asarray(
            [17.0, 45.0, 73.0, 123.0, 225.0, 311.0]
        )
        spectrum_length = 720

        covariance_items = []
        for expected_bearing in expected_bearings:
            steering = self._source_steering(
                norm_radius,
                expected_bearing,
                element0_deg,
                element_step_deg,
                num_elements,
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
            element0_deg,
            element_step_deg,
        )
        sink = blocks.vector_sink_f(spectrum_length)
        self.tb.connect(source, music, sink)
        self.tb.run()

        spectra = numpy.asarray(sink.data()).reshape(-1, spectrum_length)
        estimated_bearings = (
            360.0 * numpy.argmax(spectra, axis=1) / spectrum_length
        )
        numpy.testing.assert_allclose(
            estimated_bearings, expected_bearings, rtol=0.0, atol=0.5
        )

    def test_upstream_covariance_to_uca_music(self):
        """Verify unchanged Ettus covariance layout feeds the physical UCA model."""
        num_elements = 4
        norm_radius = 0.353265327
        element0_deg = 225.0
        element_step_deg = -90.0
        expected_bearing = 73.0
        spectrum_length = 720
        snapshot_size = 2048
        overlap_size = 1024
        sample_count = 8192

        steering = self._source_steering(
            norm_radius,
            expected_bearing,
            element0_deg,
            element_step_deg,
            num_elements,
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
            element0_deg,
            element_step_deg,
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
        self.assertGreater(len(spectra), 1)
        # autocorrelate can emit one scheduler warm-up vector before its first
        # complete covariance snapshot. Depending on chunking it may look flat
        # or contain a partial covariance, so discard that one warm-up result
        # and validate every subsequent meaningful spectrum.
        spectra = spectra[1:]
        valid = (
            numpy.all(numpy.isfinite(spectra), axis=1)
            & (numpy.max(numpy.abs(spectra), axis=1) > numpy.finfo(numpy.float32).eps)
            & (numpy.ptp(spectra, axis=1) > numpy.finfo(numpy.float32).eps)
        )
        self.assertGreater(numpy.count_nonzero(valid), 0)
        spectra = spectra[valid]
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
