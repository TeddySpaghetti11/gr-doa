#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Same-session OTA calibration for a uniform circular array."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import threading

import numpy
from gnuradio import gr


class uca_pilot_calibration(gr.sync_block):
    """Estimate and freeze per-channel complex corrections from a known pilot.

    The block deliberately emits zeros while skipping and calibrating. Once the
    requested pilot samples have been accumulated, it applies fixed gain/phase
    coefficients and passes all channels through. Keeping this block and the two
    IIO sources alive avoids invalidating the calibration by reopening or
    retuning either AD9361.

    This corrects a fixed inter-radio delay at the pilot frequency. It does not
    provide wideband sample-time alignment.
    """

    def __init__(self,
                 num_inputs=4,
                 norm_radius=0.34638,
                 pilot_angle=0.0,
                 element0_angle=0.0,
                 element_angle_step=90.0,
                 skip_samples=8192,
                 calibration_samples=32768,
                 config_filename=""):
        if num_inputs < 2:
            raise ValueError("UCA pilot calibration requires at least two inputs")
        if norm_radius <= 0.0:
            raise ValueError("Normalized UCA radius must be positive")
        if skip_samples < 0 or calibration_samples <= 0:
            raise ValueError("Skip must be non-negative and calibration length positive")

        gr.sync_block.__init__(
            self,
            name="UCA OTA Pilot Calibration",
            in_sig=[numpy.complex64] * num_inputs,
            out_sig=[numpy.complex64] * num_inputs,
        )

        self.num_inputs = int(num_inputs)
        self.norm_radius = float(norm_radius)
        self.pilot_angle = float(pilot_angle)
        self.element0_angle = float(element0_angle)
        self.element_angle_step = float(element_angle_step)
        self.skip_remaining = int(skip_samples)
        self.calibration_samples = int(calibration_samples)
        self.config_filename = str(config_filename)

        self._samples_accumulated = 0
        self._cross_sum = numpy.zeros(self.num_inputs, dtype=numpy.complex128)
        self._power_sum = numpy.zeros(self.num_inputs, dtype=numpy.float64)
        self._coefficients = numpy.ones(self.num_inputs, dtype=numpy.complex64)
        self._calibrated = False
        self._lock = threading.Lock()

        theta = numpy.deg2rad(self.pilot_angle)
        element_angles = numpy.deg2rad(
            self.element0_angle
            + numpy.arange(self.num_inputs) * self.element_angle_step
        )
        self._steering = numpy.exp(
            -1j * 2.0 * numpy.pi * self.norm_radius
            * numpy.cos(theta - element_angles)
        )

        print(
            "UCA calibration: waiting for "
            f"{self.calibration_samples} pilot samples after skipping "
            f"{self.skip_remaining} samples"
        )

    def calibrated(self):
        """Return True after coefficients have been frozen."""
        with self._lock:
            return self._calibrated

    def coefficients(self):
        """Return a copy of the current complex correction coefficients."""
        with self._lock:
            return self._coefficients.copy()

    def _finish_calibration(self):
        reference_power = self._power_sum[0]
        if reference_power <= numpy.finfo(numpy.float64).eps:
            raise RuntimeError("Pilot calibration failed: reference channel has no power")

        coefficients = numpy.ones(self.num_inputs, dtype=numpy.complex128)
        steering_reference = self._steering[0]
        for channel in range(1, self.num_inputs):
            power = self._power_sum[channel]
            if power <= numpy.finfo(numpy.float64).eps:
                raise RuntimeError(
                    f"Pilot calibration failed: channel {channel} has no power"
                )
            measured_ratio = self._cross_sum[channel] / power
            geometric_ratio = steering_reference * numpy.conj(
                self._steering[channel]
            )
            coefficients[channel] = measured_ratio / geometric_ratio

        with self._lock:
            self._coefficients = coefficients.astype(numpy.complex64)
            self._calibrated = True

        for channel, coefficient in enumerate(coefficients):
            print(
                f"UCA calibration ch{channel}: magnitude={abs(coefficient):.6f}, "
                f"phase={numpy.angle(coefficient, deg=True):.3f} deg"
            )
        print(
            "UCA calibration complete. Coefficients are frozen; the pilot may now "
            "be switched off without stopping this flowgraph."
        )
        self._write_config(coefficients)

    def _write_config(self, coefficients):
        if not self.config_filename:
            return
        directory = os.path.dirname(os.path.abspath(self.config_filename))
        os.makedirs(directory, exist_ok=True)
        with open(self.config_filename, "w", encoding="utf-8") as config_file:
            config_file.write("# UCA OTA complex correction coefficients\n")
            config_file.write(
                "# channel real imag magnitude phase_degrees\n"
            )
            for channel, coefficient in enumerate(coefficients):
                config_file.write(
                    f"{channel} {coefficient.real:.12g} {coefficient.imag:.12g} "
                    f"{abs(coefficient):.12g} "
                    f"{numpy.angle(coefficient, deg=True):.12g}\n"
                )

    def work(self, input_items, output_items):
        item_count = min(len(items) for items in input_items)
        for output in output_items:
            output[:item_count] = 0.0

        cursor = 0
        if self.skip_remaining:
            skipped = min(self.skip_remaining, item_count)
            self.skip_remaining -= skipped
            cursor += skipped

        if not self._calibrated and cursor < item_count:
            needed = self.calibration_samples - self._samples_accumulated
            used = min(needed, item_count - cursor)
            reference = input_items[0][cursor:cursor + used].astype(
                numpy.complex128, copy=False
            )
            self._power_sum[0] += numpy.vdot(reference, reference).real
            for channel in range(1, self.num_inputs):
                samples = input_items[channel][cursor:cursor + used].astype(
                    numpy.complex128, copy=False
                )
                self._cross_sum[channel] += numpy.sum(reference * numpy.conj(samples))
                self._power_sum[channel] += numpy.vdot(samples, samples).real

            self._samples_accumulated += used
            cursor += used
            if self._samples_accumulated == self.calibration_samples:
                self._finish_calibration()

        if self._calibrated and cursor < item_count:
            for channel in range(self.num_inputs):
                output_items[channel][cursor:item_count] = (
                    input_items[channel][cursor:item_count]
                    * self._coefficients[channel]
                )

        return item_count
