#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Automatic cross-SDR carrier-frequency-offset estimation and correction."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import threading

import numpy
import pmt
from scipy import signal
from gnuradio import gr


class cross_sdr_cfo_corrector(gr.sync_block):
    """Freeze one Bravo-vs-Alpha CFO correction from an OTA pilot.

    Inputs and outputs use the LibreSDR array order: ch0 Alpha RX1 reference,
    ch1 Alpha RX2, ch2 Bravo RX2, and ch3 Bravo RX1. Both Alpha channels pass
    through bit-for-bit. Both Bravo channels pass through unchanged during the
    coarse estimate. A common provisional correction is then applied while its
    post-correction residual is measured and refined. No lock tag is emitted
    until the residual passes. Exactly one rotator is always shared by Bravo.
    """

    _LOCK_TAG = "cfo_locked"

    def __init__(self,
                 samp_rate=2.8e6,
                 pilot_offset_hz=50e3,
                 pilot_bandwidth_hz=10e3,
                 settling_samples=65536,
                 estimation_samples=262144,
                 validation_settling_samples=65536,
                 residual_tolerance_hz=1.0,
                 max_refinement_rounds=3,
                 retry_delay_samples=1048576,
                 agreement_tolerance_hz=10.0,
                 max_abs_cfo_hz=20000.0,
                 min_coherence=0.90):
        if samp_rate <= 0.0:
            raise ValueError("Sample rate must be positive")
        if pilot_bandwidth_hz <= 0.0:
            raise ValueError("Pilot bandwidth must be positive")
        if abs(pilot_offset_hz) + pilot_bandwidth_hz >= samp_rate / 2.0:
            raise ValueError("Pilot passband must remain inside Nyquist")
        if settling_samples < 0:
            raise ValueError("CFO settling length must be non-negative")
        if estimation_samples < 2:
            raise ValueError("CFO estimation window must contain at least two samples")
        if validation_settling_samples < 0:
            raise ValueError("CFO validation settling length must be non-negative")
        if residual_tolerance_hz < 0.0:
            raise ValueError("Residual CFO tolerance must be non-negative")
        if max_refinement_rounds < 1:
            raise ValueError("At least one residual validation round is required")
        if retry_delay_samples < 0:
            raise ValueError("CFO retry delay must be non-negative")
        if agreement_tolerance_hz < 0.0:
            raise ValueError("CFO agreement tolerance must be non-negative")
        if max_abs_cfo_hz <= 0.0 or max_abs_cfo_hz >= samp_rate / 2.0:
            raise ValueError("Maximum CFO must be between zero and Nyquist")
        if min_coherence < 0.0 or min_coherence > 1.0:
            raise ValueError("Minimum coherence must be in [0, 1]")

        gr.sync_block.__init__(
            self,
            name="Cross-SDR CFO Corrector",
            in_sig=[numpy.complex64] * 4,
            out_sig=[numpy.complex64] * 4,
        )

        self.samp_rate = float(samp_rate)
        self.pilot_offset_hz = float(pilot_offset_hz)
        self.pilot_bandwidth_hz = float(pilot_bandwidth_hz)
        self.settling_remaining = int(settling_samples)
        self.estimation_samples = int(estimation_samples)
        self.validation_settling_samples = int(validation_settling_samples)
        self.residual_tolerance_hz = float(residual_tolerance_hz)
        self.max_refinement_rounds = int(max_refinement_rounds)
        self.retry_delay_samples = int(retry_delay_samples)
        self.retry_remaining = 0
        self.agreement_tolerance_hz = float(agreement_tolerance_hz)
        self.max_abs_cfo_hz = float(max_abs_cfo_hz)
        self.min_coherence = float(min_coherence)

        self._relative_samples = [[], []]
        self._samples_accumulated = 0
        self._estimates_hz = None
        self._coherences = None
        self._accepted_cfo_hz = None
        self._correction_phase = 0.0
        self._correction_step = 0.0
        self._correction_active = False
        self._estimating_residual = False
        self._refinement_round = 0
        self._locked = False
        self._failed = False
        self._rejection_count = 0
        self._last_failure_reason = ""
        self._lock_tag_pending = False
        self._lock = threading.Lock()

        # Estimate from the configured OTA pilot only. The earlier full-band
        # cross product could fit other strong tones visible in the raw FFT and
        # falsely declare a flat residual while the selected pilot still ramped.
        self._pilot_sos = signal.butter(
            4,
            self.pilot_bandwidth_hz,
            btype="lowpass",
            fs=self.samp_rate,
            output="sos",
        )
        self._pilot_mix_step = -2.0 * numpy.pi * self.pilot_offset_hz / self.samp_rate
        self._pilot_mix_phase = 0.0
        self._pilot_filter_states = None
        self._reset_pilot_filters()

        print(
            "Cross-SDR CFO: settling for "
            f"{self.settling_remaining} samples, then estimating over "
            f"{self.estimation_samples} pilot samples"
        )
        print(
            "Cross-SDR CFO pilot selector: complex mix at "
            f"{self.pilot_offset_hz:+.6f} Hz, low-pass bandwidth "
            f"{self.pilot_bandwidth_hz:.6f} Hz"
        )
        print(
            "Cross-SDR CFO acceptance limits: disagreement <= "
            f"{self.agreement_tolerance_hz:.6f} Hz, |CFO| <= "
            f"{self.max_abs_cfo_hz:.6f} Hz, coherence >= {self.min_coherence:.6f}"
        )
        print(
            "Cross-SDR CFO post-correction validation: residual <= "
            f"{self.residual_tolerance_hz:.6f} Hz after "
            f"{self.validation_settling_samples} settling samples, up to "
            f"{self.max_refinement_rounds} refinement rounds"
        )

    def locked(self):
        """Return True once the common correction has been accepted and frozen."""
        with self._lock:
            return self._locked

    def failed(self):
        """Return True while waiting to retry a rejected estimate."""
        with self._lock:
            return self._failed

    def estimates_hz(self):
        """Return the two most recent independent estimates, or None."""
        with self._lock:
            return None if self._estimates_hz is None else tuple(self._estimates_hz)

    def accepted_cfo_hz(self):
        """Return the current accepted total CFO, or None before a coarse fit."""
        with self._lock:
            return self._accepted_cfo_hz

    def rejection_count(self):
        """Return the number of rejected estimation windows."""
        with self._lock:
            return self._rejection_count

    def last_failure_reason(self):
        """Return the most recent rejection diagnostic."""
        with self._lock:
            return self._last_failure_reason

    def _fit_cfo(self, relative_samples):
        magnitudes = numpy.abs(relative_samples)
        finite = numpy.isfinite(relative_samples)
        positive = finite & (magnitudes > numpy.finfo(numpy.float32).tiny)
        if not numpy.any(positive):
            raise ValueError("relative pilot product has no finite power")

        # Use the median non-zero level instead of the maximum. A single IIO
        # transient can be orders of magnitude larger than the steady pilot and
        # must not cause an otherwise good window to be classified as zero.
        typical_magnitude = float(numpy.median(magnitudes[positive]))
        amplitude_floor = max(
            numpy.finfo(numpy.float32).tiny,
            typical_magnitude * 1e-6,
        )
        valid = finite & (magnitudes > amplitude_floor)
        valid_count = int(numpy.count_nonzero(valid))
        minimum_valid = max(64, relative_samples.size // 2)
        if valid_count < minimum_valid:
            raise ValueError(
                f"only {valid_count}/{relative_samples.size} relative pilot "
                f"samples are finite/non-zero (need at least {minimum_valid})"
            )

        valid_indices = numpy.flatnonzero(valid)
        # Missing samples can interrupt phase unwrapping. Split at any gap large
        # enough that a CFO within the configured range could rotate by pi, fit
        # one common slope with a separate phase intercept for every segment.
        max_unambiguous_gap = max(
            1,
            int(self.samp_rate / (2.0 * self.max_abs_cfo_hz)) - 1,
        )
        split_points = numpy.flatnonzero(
            numpy.diff(valid_indices) > max_unambiguous_gap
        ) + 1
        index_segments = numpy.split(valid_indices, split_points)
        fit_segments = []
        numerator = 0.0
        denominator = 0.0
        used_count = 0
        for indices in index_segments:
            if indices.size < 16:
                continue
            sample_index = indices.astype(numpy.float64)
            phase = numpy.unwrap(numpy.angle(relative_samples[indices])).astype(
                numpy.float64, copy=False
            )
            centered_index = sample_index - numpy.mean(sample_index)
            centered_phase = phase - numpy.mean(phase)
            numerator += float(numpy.dot(centered_index, centered_phase))
            denominator += float(numpy.dot(centered_index, centered_index))
            used_count += int(indices.size)
            fit_segments.append((sample_index, phase))

        if denominator <= numpy.finfo(numpy.float64).eps:
            raise ValueError(
                f"valid pilot samples form no usable phase-continuous segment "
                f"(valid {valid_count}/{relative_samples.size})"
            )

        slope = numerator / denominator
        residual_sum = 0.0j
        for sample_index, phase in fit_segments:
            fitted = numpy.mean(phase) + slope * (
                sample_index - numpy.mean(sample_index)
            )
            residual_sum += numpy.sum(numpy.exp(1j * (phase - fitted)))
        coherence = float(abs(residual_sum) / used_count)
        estimate_hz = float(slope * self.samp_rate / (2.0 * numpy.pi))
        return estimate_hz, coherence, valid_count, used_count

    def _reset_pilot_filters(self):
        state_shape = (self._pilot_sos.shape[0], 2)
        self._pilot_filter_states = [
            numpy.zeros(state_shape, dtype=numpy.complex128)
            for _ in range(3)
        ]

    def _filter_pilot_segment(self, input_items, output_items, start, stop):
        """Select the OTA pilot from Alpha RX1 and both Bravo channels."""
        count = stop - start
        if count <= 0:
            return None
        phases = self._pilot_mix_phase + self._pilot_mix_step * numpy.arange(count)
        mixer = numpy.exp(1j * phases)
        selected = [input_items[0][start:stop]]
        for channel in (2, 3):
            selected.append(
                output_items[channel][start:stop]
                if self._correction_active
                else input_items[channel][start:stop]
            )

        filtered = []
        for index, samples in enumerate(selected):
            pilot, state = signal.sosfilt(
                self._pilot_sos,
                samples * mixer,
                zi=self._pilot_filter_states[index],
            )
            self._pilot_filter_states[index] = state
            filtered.append(pilot)

        self._pilot_mix_phase = float(
            numpy.remainder(
                self._pilot_mix_phase + self._pilot_mix_step * count + numpy.pi,
                2.0 * numpy.pi,
            ) - numpy.pi
        )
        return filtered

    def _finish_estimation(self):
        estimating_residual = self._estimating_residual
        refinement_round = self._refinement_round
        estimates = []
        coherences = []
        valid_counts = []
        used_counts = []
        try:
            for chunks in self._relative_samples:
                relative = numpy.concatenate(chunks)
                estimate, coherence, valid_count, used_count = self._fit_cfo(
                    relative
                )
                estimates.append(estimate)
                coherences.append(coherence)
                valid_counts.append(valid_count)
                used_counts.append(used_count)
        except ValueError as error:
            self._reject(str(error))
            return
        finally:
            self._relative_samples = [[], []]

        disagreement = abs(estimates[0] - estimates[1])
        label = (
            f"residual round {refinement_round}"
            if estimating_residual else "coarse"
        )
        print(
            f"Cross-SDR CFO {label} ch2/ch0 estimate: {estimates[0]:+.6f} Hz "
            f"(coherence {coherences[0]:.6f}, valid "
            f"{valid_counts[0]}/{self.estimation_samples}, used {used_counts[0]})"
        )
        print(
            f"Cross-SDR CFO {label} ch3/ch0 estimate: {estimates[1]:+.6f} Hz "
            f"(coherence {coherences[1]:.6f}, valid "
            f"{valid_counts[1]}/{self.estimation_samples}, used {used_counts[1]})"
        )
        print(
            f"Cross-SDR CFO {label} estimate disagreement: {disagreement:.6f} Hz "
            f"(limit {self.agreement_tolerance_hz:.6f} Hz)"
        )

        with self._lock:
            self._estimates_hz = tuple(estimates)
            self._coherences = tuple(coherences)

        rejection_reasons = []
        for channel, (estimate, coherence) in enumerate(
                zip(estimates, coherences), start=2):
            if not numpy.isfinite(estimate):
                rejection_reasons.append(f"ch{channel}/ch0 estimate is not finite")
            elif abs(estimate) > self.max_abs_cfo_hz:
                rejection_reasons.append(
                    f"ch{channel}/ch0 magnitude {abs(estimate):.6f} Hz exceeds "
                    f"{self.max_abs_cfo_hz:.6f} Hz"
                )
            if not numpy.isfinite(coherence) or coherence < self.min_coherence:
                rejection_reasons.append(
                    f"ch{channel}/ch0 coherence {coherence:.6f} is below "
                    f"{self.min_coherence:.6f}"
                )
        if disagreement > self.agreement_tolerance_hz:
            rejection_reasons.append(
                f"the two estimates disagree by {disagreement:.6f} Hz"
            )
        if rejection_reasons:
            self._reject(f"{label}: " + "; ".join(rejection_reasons))
            return

        accepted = 0.5 * (estimates[0] + estimates[1])
        if estimating_residual:
            self._finish_residual_validation(accepted)
        else:
            self._start_provisional_correction(accepted)

    def _set_correction_frequency(self, cfo_hz, reset_phase=False):
        self._correction_step = -2.0 * numpy.pi * cfo_hz / self.samp_rate
        if reset_phase:
            self._correction_phase = 0.0

    def _start_provisional_correction(self, accepted):
        with self._lock:
            self._accepted_cfo_hz = accepted
            self._set_correction_frequency(accepted, reset_phase=True)
            self._correction_active = True
            self._estimating_residual = True
            self._refinement_round = 1
            self._failed = False
        self._samples_accumulated = 0
        self.settling_remaining = self.validation_settling_samples
        self._reset_pilot_filters()

        print(f"Cross-SDR CFO coarse accepted average: {accepted:+.6f} Hz")
        print(
            f"Cross-SDR CFO provisional correction: {-accepted:+.6f} Hz, "
            f"phase step {self._correction_step:+.12g} rad/sample, identically "
            "on ch2 and ch3"
        )
        print(
            "Cross-SDR CFO: correction is active but NOT locked; post-correction "
            f"residual validation round 1 begins after "
            f"{self.validation_settling_samples} samples"
        )

    def _finish_residual_validation(self, residual_hz):
        print(
            f"Cross-SDR CFO residual round {self._refinement_round} accepted "
            f"average: {residual_hz:+.6f} Hz"
        )
        if abs(residual_hz) <= self.residual_tolerance_hz:
            with self._lock:
                # The tolerance is an acceptance bound, not a reason to leave
                # a known residual unapplied. Fold the final measured residual
                # into the frozen total while retaining instantaneous phase.
                self._accepted_cfo_hz += residual_hz
                self._set_correction_frequency(
                    self._accepted_cfo_hz, reset_phase=False
                )
                self._locked = True
                self._failed = False
                self._lock_tag_pending = True
                accepted = self._accepted_cfo_hz
                correction_step = self._correction_step
            print(f"Cross-SDR CFO final accepted CFO: {accepted:+.6f} Hz")
            print(
                f"Cross-SDR CFO frozen correction: {-accepted:+.6f} Hz, "
                f"phase step {correction_step:+.12g} rad/sample, identically "
                "on ch2 and ch3"
            )
            print(
                "Cross-SDR CFO lock established after post-correction residual "
                "validation. Downstream constant phase calibration may now begin."
            )
            return

        if self._refinement_round >= self.max_refinement_rounds:
            self._reject(
                f"post-correction residual {residual_hz:+.6f} Hz exceeds "
                f"{self.residual_tolerance_hz:.6f} Hz after "
                f"{self.max_refinement_rounds} refinement rounds"
            )
            return

        with self._lock:
            self._accepted_cfo_hz += residual_hz
            accepted = self._accepted_cfo_hz
            # Retain the current rotator phase when changing its frequency so
            # both Bravo streams remain phase-continuous across refinements.
            self._set_correction_frequency(accepted, reset_phase=False)
            self._refinement_round += 1
            refinement_round = self._refinement_round
            correction_step = self._correction_step
        self._samples_accumulated = 0
        self.settling_remaining = self.validation_settling_samples
        self._reset_pilot_filters()
        print(
            f"Cross-SDR CFO refinement: total estimate {accepted:+.6f} Hz; "
            f"common correction {-accepted:+.6f} Hz, phase step "
            f"{correction_step:+.12g} rad/sample"
        )
        print(
            f"Cross-SDR CFO: residual validation round {refinement_round} begins "
            f"after {self.validation_settling_samples} samples"
        )

    def _reject(self, reason):
        with self._lock:
            self._failed = True
            self._rejection_count += 1
            rejection_count = self._rejection_count
            self._last_failure_reason = reason
            self._accepted_cfo_hz = None
            self._correction_active = False
            self._estimating_residual = False
            self._refinement_round = 0
            self._correction_phase = 0.0
            self._correction_step = 0.0
        self._samples_accumulated = 0
        self._relative_samples = [[], []]
        self.retry_remaining = self.retry_delay_samples
        self._reset_pilot_filters()
        print(f"Cross-SDR CFO REJECTED: {reason}")
        print(
            f"Cross-SDR CFO correction remains disabled; retry {rejection_count + 1} "
            f"will start after {self.retry_delay_samples} samples. No cfo_locked "
            "tag is emitted until an estimate passes every check."
        )

    def _emit_lock_tags(self, relative_offset):
        absolute_offset = self.nitems_written(0) + int(relative_offset)
        value = pmt.from_double(float(self._accepted_cfo_hz))
        key = pmt.intern(self._LOCK_TAG)
        for port in range(4):
            self.add_item_tag(port, absolute_offset, key, value)
        self._lock_tag_pending = False

    def _apply_correction(self, input_items, output_items, start, stop):
        count = stop - start
        if count <= 0:
            return
        phases = self._correction_phase + self._correction_step * numpy.arange(count)
        rotator = numpy.exp(1j * phases).astype(numpy.complex64)
        output_items[2][start:stop] = input_items[2][start:stop] * rotator
        output_items[3][start:stop] = input_items[3][start:stop] * rotator
        self._correction_phase = float(
            numpy.remainder(
                self._correction_phase + self._correction_step * count + numpy.pi,
                2.0 * numpy.pi,
            ) - numpy.pi
        )

    def work(self, input_items, output_items):
        item_count = min(len(items) for items in input_items)
        for channel in range(4):
            output_items[channel][:item_count] = input_items[channel][:item_count]

        if self._locked:
            if self._lock_tag_pending:
                self._emit_lock_tags(0)
            self._apply_correction(input_items, output_items, 0, item_count)
            return item_count

        cursor = 0
        while cursor < item_count and not self._locked:
            if self.settling_remaining:
                skipped = min(self.settling_remaining, item_count - cursor)
                if self._correction_active:
                    self._apply_correction(
                        input_items, output_items, cursor, cursor + skipped
                    )
                self._filter_pilot_segment(
                    input_items, output_items, cursor, cursor + skipped
                )
                self.settling_remaining -= skipped
                cursor += skipped
                continue

            if self.retry_remaining:
                skipped = min(self.retry_remaining, item_count - cursor)
                self._filter_pilot_segment(
                    input_items, output_items, cursor, cursor + skipped
                )
                self.retry_remaining -= skipped
                cursor += skipped
                if self.retry_remaining == 0:
                    with self._lock:
                        self._failed = False
                        attempt = self._rejection_count + 1
                    print(f"Cross-SDR CFO: starting estimation attempt {attempt}")
                continue

            needed = self.estimation_samples - self._samples_accumulated
            used = min(needed, item_count - cursor)
            if self._correction_active:
                self._apply_correction(
                    input_items, output_items, cursor, cursor + used
                )
            pilots = self._filter_pilot_segment(
                input_items, output_items, cursor, cursor + used
            )
            reference = pilots[0]
            for relative_index, bravo_samples in enumerate(pilots[1:]):
                relative = (
                    bravo_samples * numpy.conj(reference)
                ).astype(numpy.complex64, copy=False)
                self._relative_samples[relative_index].append(relative.copy())
            self._samples_accumulated += used
            cursor += used
            if self._samples_accumulated == self.estimation_samples:
                self._finish_estimation()

        if self._locked and cursor < item_count:
            self._emit_lock_tags(cursor)
            self._apply_correction(input_items, output_items, cursor, item_count)
        # If the window ends exactly at a scheduler boundary, the lock tag and
        # first corrected sample are both deferred to the next work call.

        return item_count
