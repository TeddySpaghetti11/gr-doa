#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Same-session OTA phase calibration for a uniform circular array."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import threading

import numpy
import pmt
from gnuradio import gr


class uca_pilot_calibration(gr.sync_block):
    """Estimate and freeze per-channel phase corrections from a known pilot.

    The block deliberately emits zeros while skipping and calibrating. Once the
    requested pilot samples have been accumulated, it applies fixed phase
    coefficients and passes all channels through. If any channel fails the
    coherence threshold, it enters an explicit failed state and bypasses all
    inputs with unity coefficients instead of freezing an untrustworthy phase.
    Keeping this block and the two IIO sources alive avoids invalidating a valid
    calibration by reopening or retuning either AD9361.

    ``pilot_angle`` is the bearing from the array centre *towards the source*.
    With the usual analytic-signal convention the corresponding UCA manifold is
    exp(+j 2*pi*r/lambda*cos(theta-beta)).

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
                 config_filename="",
                 min_coherence=0.90,
                 start_tag_key=""):
        if num_inputs < 2:
            raise ValueError("UCA pilot calibration requires at least two inputs")
        if norm_radius <= 0.0:
            raise ValueError("Normalized UCA radius must be positive")
        if skip_samples < 0 or calibration_samples <= 0:
            raise ValueError("Skip must be non-negative and calibration length positive")
        if not 0.0 <= min_coherence <= 1.0:
            raise ValueError("Minimum coherence must be between 0 and 1")

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
        self._configured_skip_samples = int(skip_samples)
        self.skip_remaining = self._configured_skip_samples
        self.calibration_samples = int(calibration_samples)
        self.config_filename = str(config_filename)
        self.min_coherence = float(min_coherence)
        self.start_tag_key = str(start_tag_key)
        self._armed = not bool(self.start_tag_key)

        self._samples_accumulated = 0
        self._cross_sum = numpy.zeros(self.num_inputs, dtype=numpy.complex128)
        self._power_sum = numpy.zeros(self.num_inputs, dtype=numpy.float64)
        self._coefficients = numpy.ones(self.num_inputs, dtype=numpy.complex64)
        self._coherences = numpy.zeros(self.num_inputs, dtype=numpy.float64)
        self._state = "collecting"
        self._failure_reason = ""
        self._lock = threading.Lock()

        theta = numpy.deg2rad(self.pilot_angle)
        element_angles = numpy.deg2rad(
            self.element0_angle
            + numpy.arange(self.num_inputs) * self.element_angle_step
        )
        self._steering = numpy.exp(
            1j * 2.0 * numpy.pi * self.norm_radius
            * numpy.cos(theta - element_angles)
        )

        if self._armed:
            print(
                "UCA calibration: waiting for "
                f"{self.calibration_samples} pilot samples after skipping "
                f"{self.skip_remaining} samples; minimum coherence is "
                f"{self.min_coherence:.2f}"
            )
        else:
            print(
                f"UCA calibration: waiting for '{self.start_tag_key}' before "
                f"skipping {self.skip_remaining} samples and collecting "
                f"{self.calibration_samples} pilot samples; minimum coherence "
                f"is {self.min_coherence:.2f}"
            )

    def calibrated(self):
        """Return True after coefficients have been frozen."""
        with self._lock:
            return self._state == "calibrated"

    def calibration_failed(self):
        """Return True when validation rejected the collected coefficients."""
        with self._lock:
            return self._state == "failed"

    def status(self):
        """Return ``collecting``, ``calibrated``, or ``failed``."""
        with self._lock:
            return self._state

    def failure_reason(self):
        """Return the validation failure message, or an empty string."""
        with self._lock:
            return self._failure_reason

    def coefficients(self):
        """Return a copy of the current complex correction coefficients."""
        with self._lock:
            return self._coefficients.copy()

    def coherences(self):
        """Return normalized pilot coherence relative to channel 0."""
        with self._lock:
            return self._coherences.copy()

    def _fail_calibration(self, reason, coherences):
        with self._lock:
            self._coefficients = numpy.ones(
                self.num_inputs, dtype=numpy.complex64
            )
            self._coherences = coherences.copy()
            self._state = "failed"
            self._failure_reason = reason

        print("=" * 72)
        print(f"UCA CALIBRATION FAILED: {reason}")
        print(
            "No phase coefficients were frozen or written. The calibration "
            "block is now in UNITY/BYPASS mode so downstream diagnostics keep "
            "receiving uncalibrated samples. Do not trust the MUSIC bearing."
        )
        print("=" * 72)

    def _finish_calibration(self):
        eps = numpy.finfo(numpy.float64).eps
        reference_power = self._power_sum[0]
        coherences = numpy.zeros(self.num_inputs, dtype=numpy.float64)
        if reference_power <= eps:
            self._fail_calibration(
                "reference channel 0 has no measurable pilot power", coherences
            )
            return

        coefficients = numpy.ones(self.num_inputs, dtype=numpy.complex128)
        coherences[0] = 1.0
        steering_reference = self._steering[0]
        failures = []

        for channel in range(1, self.num_inputs):
            cross = self._cross_sum[channel]
            channel_power = self._power_sum[channel]
            denom = numpy.sqrt(reference_power * channel_power)
            if denom <= eps:
                failures.append(
                    f"channel {channel} has no measurable pilot power"
                )
                print(
                    f"UCA calibration ch{channel}/ch0: coherence=0.0000 "
                    "(no measurable channel power)"
                )
                continue

            coherence = float(numpy.clip(abs(cross) / denom, 0.0, 1.0))
            coherences[channel] = coherence
            if abs(cross) <= eps:
                failures.append(
                    f"channel {channel} has no coherent cross-correlation with ch0"
                )
                print(
                    f"UCA calibration ch{channel}/ch0: coherence={coherence:.4f} "
                    "(no usable phase estimate)"
                )
                continue

            # Same cross-product convention as Ettus phase_offset_est:
            # angle(x0 * conj(xi)).  Divide out the known array-manifold ratio
            # so the frozen coefficient removes only fixed channel/hardware phase.
            measured_ratio = cross / abs(cross)
            geometric_ratio = steering_reference * numpy.conj(
                self._steering[channel]
            )
            hardware_ratio = measured_ratio / geometric_ratio
            coefficients[channel] = hardware_ratio / abs(hardware_ratio)

            print(
                f"UCA calibration ch{channel}/ch0: "
                f"measured={numpy.angle(measured_ratio, deg=True):.3f} deg, "
                f"geometry={numpy.angle(geometric_ratio, deg=True):.3f} deg, "
                f"hardware correction={numpy.angle(coefficients[channel], deg=True):.3f} deg, "
                f"coherence={coherence:.4f}"
            )
            if coherence < self.min_coherence:
                failures.append(
                    f"ch{channel}/ch0 coherence {coherence:.4f} is below "
                    f"{self.min_coherence:.2f}"
                )

        if failures:
            self._fail_calibration("; ".join(failures), coherences)
            return

        with self._lock:
            self._coefficients = coefficients.astype(numpy.complex64)
            self._coherences = coherences
            self._state = "calibrated"

        for channel, coefficient in enumerate(coefficients):
            print(
                f"UCA calibration ch{channel}: magnitude={abs(coefficient):.6f}, "
                f"phase={numpy.angle(coefficient, deg=True):.3f} deg, "
                f"coherence={coherences[channel]:.4f}"
            )
        print(
            "UCA calibration complete. Coefficients are frozen; keep the pilot "
            "transmitting for continuous cross-SDR tracking."
        )
        self._write_config(coefficients)

    def _write_config(self, coefficients):
        if not self.config_filename:
            return
        directory = os.path.dirname(os.path.abspath(self.config_filename))
        os.makedirs(directory, exist_ok=True)
        with open(self.config_filename, "w", encoding="utf-8") as config_file:
            config_file.write("# UCA OTA phase corrections in radians\n")
            config_file.write("# Compatible with Ettus phase_correct_hier\n")
            config_file.write("# Channel 0 is the reference and is not listed\n")
            for channel, coefficient in enumerate(coefficients[1:], start=1):
                phase_radians = numpy.angle(coefficient)
                config_file.write(
                    f"# ch{channel}/ch0 correction: "
                    f"{numpy.rad2deg(phase_radians):.6f} degrees\n"
                )
                config_file.write(f"{phase_radians:.12g}\n")

    def _reset_calibration(self, armed):
        """Discard frozen/partial phase state after a tracker unlock or relock."""
        with self._lock:
            self.skip_remaining = self._configured_skip_samples
            self._samples_accumulated = 0
            self._cross_sum.fill(0.0)
            self._power_sum.fill(0.0)
            self._coefficients.fill(1.0)
            self._coherences.fill(0.0)
            self._state = "collecting"
            self._failure_reason = ""
            self._armed = bool(armed)

    def _process_segment(self, input_items, output_items, start, stop):
        """Process a tag-free half-open input range."""
        cursor = start
        if not self._armed:
            return stop

        if self.skip_remaining:
            skipped = min(self.skip_remaining, stop - cursor)
            self.skip_remaining -= skipped
            cursor += skipped

        if self.status() == "collecting" and cursor < stop:
            needed = self.calibration_samples - self._samples_accumulated
            used = min(needed, stop - cursor)
            reference = input_items[0][cursor:cursor + used].astype(
                numpy.complex128, copy=False
            )
            reference_power = float(numpy.vdot(reference, reference).real)
            self._cross_sum[0] += reference_power
            self._power_sum[0] += reference_power

            for channel in range(1, self.num_inputs):
                samples = input_items[channel][cursor:cursor + used].astype(
                    numpy.complex128, copy=False
                )
                self._cross_sum[channel] += numpy.sum(
                    reference * numpy.conj(samples)
                )
                self._power_sum[channel] += float(
                    numpy.vdot(samples, samples).real
                )

            self._samples_accumulated += used
            cursor += used
            if self._samples_accumulated == self.calibration_samples:
                self._finish_calibration()

        state = self.status()
        if state == "calibrated" and cursor < stop:
            for channel in range(self.num_inputs):
                output_items[channel][cursor:stop] = (
                    input_items[channel][cursor:stop]
                    * self._coefficients[channel]
                )
        elif state == "failed" and cursor < stop:
            for channel in range(self.num_inputs):
                output_items[channel][cursor:stop] = input_items[channel][
                    cursor:stop
                ]
        return stop

    def work(self, input_items, output_items):
        item_count = min(len(items) for items in input_items)
        for output in output_items:
            output[:item_count] = 0.0

        if not self.start_tag_key:
            self._process_segment(input_items, output_items, 0, item_count)
            return item_count

        absolute_start = self.nitems_read(0)
        absolute_stop = absolute_start + item_count
        control_tags = []
        event_keys = [(self.start_tag_key, "lock")]
        if self.start_tag_key == "cfo_locked":
            event_keys.append(("cfo_unlocked", "unlock"))
        for key, event_type in event_keys:
            for tag in self.get_tags_in_range(
                    0, absolute_start, absolute_stop, pmt.intern(key)):
                control_tags.append((int(tag.offset), event_type))
        control_tags.sort(key=lambda event: event[0])

        cursor = 0
        for absolute_offset, event_type in control_tags:
            event_cursor = max(cursor, absolute_offset - absolute_start)
            self._process_segment(
                input_items, output_items, cursor, event_cursor
            )
            cursor = event_cursor
            if event_type == "unlock":
                self._reset_calibration(armed=False)
                print(
                    f"UCA calibration: received 'cfo_unlocked' at input sample "
                    f"{absolute_offset}; frozen phase correction discarded"
                )
            else:
                self._reset_calibration(armed=True)
                print(
                    f"UCA calibration: received '{self.start_tag_key}' at input "
                    f"sample {absolute_offset}; post-lock settling begins"
                )

        self._process_segment(input_items, output_items, cursor, item_count)

        return item_count
