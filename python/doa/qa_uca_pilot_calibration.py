#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import tempfile

import gnuradio
import numpy

# Ensure GR_ADD_TEST exercises the source package copied under
# test_modules/gnuradio, not an older system-installed gr-doa package.
for search_path in sys.path:
    test_gnuradio = os.path.join(search_path, "gnuradio")
    if os.path.isfile(os.path.join(test_gnuradio, "doa", "uca_pilot_calibration.py")):
        gnuradio.__path__.insert(0, test_gnuradio)
        break

from gnuradio import doa
from gnuradio import gr_unittest


class qa_uca_pilot_calibration(gr_unittest.TestCase):
    def test_pilot_coefficients_are_applied_to_separate_target(self):
        num_elements = 4
        norm_radius = 0.26857
        pilot_bearing = 0.0
        target_bearing = 117.0
        element0_deg = 225.0
        element_step_deg = -90.0
        sample_count = 2048

        element_bearings = numpy.deg2rad(
            element0_deg + numpy.arange(num_elements) * element_step_deg
        )
        pilot_steering = numpy.exp(
            1j * 2.0 * numpy.pi * norm_radius
            * numpy.cos(numpy.deg2rad(pilot_bearing) - element_bearings)
        )
        target_steering = numpy.exp(
            1j * 2.0 * numpy.pi * norm_radius
            * numpy.cos(numpy.deg2rad(target_bearing) - element_bearings)
        )
        hardware = numpy.exp(1j * numpy.asarray([0.0, 0.43, -1.17, 2.08]))
        pilot_tone = numpy.exp(1j * 0.031 * numpy.arange(sample_count))
        target_tone = numpy.exp(1j * 0.083 * numpy.arange(sample_count))
        pilot_inputs = [
            (hardware[channel] * pilot_steering[channel] * pilot_tone).astype(
                numpy.complex64
            )
            for channel in range(num_elements)
        ]
        target_inputs = [
            (hardware[channel] * target_steering[channel] * target_tone).astype(
                numpy.complex64
            )
            for channel in range(num_elements)
        ]

        calibration = doa.uca_pilot_calibration(
            num_inputs=num_elements,
            norm_radius=norm_radius,
            pilot_angle=pilot_bearing,
            element0_angle=element0_deg,
            element_angle_step=element_step_deg,
            skip_samples=0,
            calibration_samples=sample_count,
            config_filename="",
            separate_data_inputs=True,
        )
        outputs = [
            numpy.empty(sample_count, dtype=numpy.complex64)
            for _ in range(num_elements)
        ]
        calibration.work(pilot_inputs + target_inputs, outputs)
        self.assertTrue(calibration.calibrated())

        calibration.work(pilot_inputs + target_inputs, outputs)
        for channel in range(num_elements):
            expected = target_steering[channel] * target_tone
            numpy.testing.assert_allclose(
                outputs[channel], expected, rtol=2e-5, atol=2e-5
            )

        # The target output must retain its own bearing manifold, not the known
        # calibration-pilot manifold.
        target_ratio = outputs[1][0] / outputs[0][0]
        expected_target_ratio = target_steering[1] / target_steering[0]
        pilot_ratio = pilot_steering[1] / pilot_steering[0]
        self.assertAlmostEqual(abs(target_ratio - expected_target_ratio), 0.0, 5)
        self.assertGreater(abs(target_ratio - pilot_ratio), 0.25)

    def test_geometry_preserved_and_hardware_removed(self):
        num_elements = 4
        norm_radius = 0.353265327
        pilot_bearing = 37.0
        element0_deg = 225.0
        element_step_deg = -90.0
        sample_count = 4096

        element_bearings = numpy.deg2rad(
            element0_deg + numpy.arange(num_elements) * element_step_deg
        )
        steering = numpy.exp(
            1j * 2.0 * numpy.pi * norm_radius
            * numpy.cos(numpy.deg2rad(pilot_bearing) - element_bearings)
        )
        hardware = numpy.asarray(
            [
                1.0 + 0.0j,
                0.72 * numpy.exp(0.61j),
                1.21 * numpy.exp(-1.08j),
                0.91 * numpy.exp(2.14j),
            ],
            dtype=numpy.complex64,
        )
        tone = numpy.exp(1j * 0.07 * numpy.arange(sample_count)).astype(
            numpy.complex64
        )
        inputs = [
            (hardware[channel] * steering[channel] * tone).astype(numpy.complex64)
            for channel in range(num_elements)
        ]

        calibration = doa.uca_pilot_calibration(
            num_inputs=num_elements,
            norm_radius=norm_radius,
            pilot_angle=pilot_bearing,
            element0_angle=element0_deg,
            element_angle_step=element_step_deg,
            skip_samples=0,
            calibration_samples=sample_count,
            config_filename="",
        )
        discarded = [
            numpy.empty(sample_count, dtype=numpy.complex64)
            for _ in range(num_elements)
        ]
        calibration.work(inputs, discarded)
        self.assertTrue(calibration.calibrated())
        numpy.testing.assert_allclose(
            calibration.coherences(), numpy.ones(num_elements), rtol=0.0, atol=2e-6
        )

        corrected = [
            numpy.empty(sample_count, dtype=numpy.complex64)
            for _ in range(num_elements)
        ]
        calibration.work(inputs, corrected)
        for channel in range(num_elements):
            # Phase-only correction: keep the channel amplitude but remove the
            # fixed hardware phase, leaving the physical source-bearing manifold.
            expected = abs(hardware[channel]) * steering[channel] * tone
            numpy.testing.assert_allclose(
                corrected[channel], expected, rtol=2e-5, atol=2e-5
            )

    def test_coherence_reports_decorrelated_channel(self):
        sample_count = 4096
        random = numpy.random.default_rng(20260826)
        tone = numpy.exp(1j * 0.043 * numpy.arange(sample_count)).astype(
            numpy.complex64
        )
        inputs = [
            tone,
            (0.8 * numpy.exp(0.4j) * tone).astype(numpy.complex64),
            (1.1 * numpy.exp(-0.7j) * tone).astype(numpy.complex64),
            (
                random.standard_normal(sample_count)
                + 1j * random.standard_normal(sample_count)
            ).astype(numpy.complex64),
        ]
        calibration = doa.uca_pilot_calibration(
            num_inputs=4,
            norm_radius=0.25,
            pilot_angle=0.0,
            element0_angle=0.0,
            element_angle_step=90.0,
            skip_samples=0,
            calibration_samples=sample_count,
            config_filename="",
        )
        outputs = [numpy.empty(sample_count, dtype=numpy.complex64) for _ in range(4)]
        calibration.work(inputs, outputs)
        coherences = calibration.coherences()
        self.assertFalse(calibration.calibrated())
        self.assertTrue(calibration.calibration_failed())
        self.assertEqual(calibration.status(), "failed")
        self.assertIn("ch3/ch0 coherence", calibration.failure_reason())
        self.assertGreater(coherences[1], 0.999)
        self.assertGreater(coherences[2], 0.999)
        self.assertLess(coherences[3], 0.1)
        numpy.testing.assert_array_equal(
            calibration.coefficients(), numpy.ones(4, dtype=numpy.complex64)
        )

        bypassed = [
            numpy.empty(sample_count, dtype=numpy.complex64) for _ in range(4)
        ]
        calibration.work(inputs, bypassed)
        for channel in range(4):
            numpy.testing.assert_array_equal(bypassed[channel], inputs[channel])

    def test_failed_calibration_does_not_write_coefficients(self):
        sample_count = 512
        tone = numpy.ones(sample_count, dtype=numpy.complex64)
        inputs = [tone, tone, tone, numpy.zeros_like(tone)]

        with tempfile.TemporaryDirectory() as directory:
            config_filename = os.path.join(directory, "invalid.cfg")
            calibration = doa.uca_pilot_calibration(
                num_inputs=4,
                norm_radius=0.25,
                pilot_angle=0.0,
                element0_angle=0.0,
                element_angle_step=90.0,
                skip_samples=0,
                calibration_samples=sample_count,
                config_filename=config_filename,
            )
            outputs = [
                numpy.empty(sample_count, dtype=numpy.complex64)
                for _ in range(4)
            ]
            calibration.work(inputs, outputs)

            self.assertTrue(calibration.calibration_failed())
            self.assertFalse(os.path.exists(config_filename))

    def test_saved_phases_match_ettus_phase_correct_format(self):
        num_elements = 4
        sample_count = 256
        hardware_phases = numpy.asarray([0.0, 0.4, -1.1, 2.2])
        tone = numpy.ones(sample_count, dtype=numpy.complex64)

        norm_radius = 0.25
        pilot_bearing = 0.0
        element_bearings = numpy.deg2rad(numpy.arange(num_elements) * 90.0)
        steering = numpy.exp(
            1j * 2.0 * numpy.pi * norm_radius
            * numpy.cos(numpy.deg2rad(pilot_bearing) - element_bearings)
        )
        inputs = [
            (numpy.exp(1j * phase) * steering[channel] * tone).astype(numpy.complex64)
            for channel, phase in enumerate(hardware_phases)
        ]

        with tempfile.TemporaryDirectory() as directory:
            config_filename = os.path.join(directory, "phase_offsets.cfg")
            calibration = doa.uca_pilot_calibration(
                num_inputs=num_elements,
                norm_radius=norm_radius,
                pilot_angle=pilot_bearing,
                element0_angle=0.0,
                element_angle_step=90.0,
                skip_samples=0,
                calibration_samples=sample_count,
                config_filename=config_filename,
            )
            outputs = [
                numpy.empty(sample_count, dtype=numpy.complex64)
                for _ in range(num_elements)
            ]
            calibration.work(inputs, outputs)

            with open(config_filename, "r", encoding="utf-8") as config_file:
                saved_phases = [
                    float(line)
                    for line in config_file
                    if not line.lstrip().startswith("#")
                ]

        self.assertEqual(len(saved_phases), num_elements - 1)
        numpy.testing.assert_allclose(
            numpy.exp(1j * numpy.asarray(saved_phases)),
            calibration.coefficients()[1:],
            rtol=0.0,
            atol=1e-6,
        )


if __name__ == "__main__":
    gr_unittest.run(qa_uca_pilot_calibration)
