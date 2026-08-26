#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import numpy
import os
import tempfile
from gnuradio import doa
from gnuradio import gr_unittest


class qa_uca_pilot_calibration(gr_unittest.TestCase):
    def test_geometry_preserved_and_hardware_removed(self):
        num_elements = 4
        norm_radius = 0.346379923
        pilot_bearing = 37.0
        sample_count = 4096

        element_bearings = numpy.deg2rad(numpy.arange(num_elements) * 90.0)
        steering = numpy.exp(
            -1j * 2.0 * numpy.pi * norm_radius
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
            element0_angle=0.0,
            element_angle_step=90.0,
            skip_samples=0,
            calibration_samples=sample_count,
            config_filename="",
        )
        discarded = [numpy.empty(sample_count, dtype=numpy.complex64)
                     for _ in range(num_elements)]
        calibration.work(inputs, discarded)
        self.assertTrue(calibration.calibrated())

        corrected = [numpy.empty(sample_count, dtype=numpy.complex64)
                     for _ in range(num_elements)]
        calibration.work(inputs, corrected)
        for channel in range(num_elements):
            # This stage is deliberately phase-only, like Ettus's relative
            # phase correction.  Channel amplitudes are not equalized.
            expected = abs(hardware[channel]) * steering[channel] * tone
            numpy.testing.assert_allclose(
                corrected[channel], expected, rtol=2e-5, atol=2e-5
            )

    def test_saved_phases_match_ettus_phase_correct_format(self):
        num_elements = 4
        sample_count = 256
        hardware_phases = numpy.asarray([0.0, 0.4, -1.1, 2.2])
        tone = numpy.ones(sample_count, dtype=numpy.complex64)
        inputs = [
            (numpy.exp(1j * phase) * tone).astype(numpy.complex64)
            for phase in hardware_phases
        ]

        with tempfile.TemporaryDirectory() as directory:
            config_filename = os.path.join(directory, "phase_offsets.cfg")
            calibration = doa.uca_pilot_calibration(
                num_inputs=num_elements,
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
