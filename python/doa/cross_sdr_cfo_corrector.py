#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Automatic cross-SDR carrier-frequency-offset estimation and correction."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import threading

import numpy
import pmt
from gnuradio import gr


class cross_sdr_cfo_corrector(gr.sync_block):
    """Freeze one Bravo-vs-Alpha CFO correction from an OTA pilot.

    Inputs and outputs use the LibreSDR array order: ch0 Alpha RX1 reference,
    ch1 Alpha RX2, ch2 Bravo RX2, and ch3 Bravo RX1. Both Alpha channels pass
    through bit-for-bit. Before lock, both Bravo channels also pass through
    without correction. After the independent Bravo/reference estimates pass
    the configured checks, exactly one rotator is applied to both Bravo streams.
    """

    _LOCK_TAG = "cfo_locked"

    def __init__(self,
                 samp_rate=2.8e6,
                 settling_samples=65536,
                 estimation_samples=262144,
                 retry_delay_samples=1048576,
                 agreement_tolerance_hz=10.0,
                 max_abs_cfo_hz=20000.0,
                 min_coherence=0.5):
        if samp_rate <= 0.0:
            raise ValueError("Sample rate must be positive")
        if settling_samples < 0:
            raise ValueError("CFO settling length must be non-negative")
        if estimation_samples < 2:
            raise ValueError("CFO estimation window must contain at least two samples")
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
        self.settling_remaining = int(settling_samples)
        self.estimation_samples = int(estimation_samples)
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
        self._locked = False
        self._failed = False
        self._rejection_count = 0
        self._last_failure_reason = ""
        self._lock_tag_pending = False
        self._lock = threading.Lock()

        print(
            "Cross-SDR CFO: settling for "
            f"{self.settling_remaining} samples, then estimating over "
            f"{self.estimation_samples} pilot samples"
        )
        print(
            "Cross-SDR CFO acceptance limits: disagreement <= "
            f"{self.agreement_tolerance_hz:.6f} Hz, |CFO| <= "
            f"{self.max_abs_cfo_hz:.6f} Hz, coherence >= {self.min_coherence:.6f}"
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
        """Return the frozen Bravo-minus-Alpha CFO, or None before lock."""
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

    def _finish_estimation(self):
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
        print(
            f"Cross-SDR CFO ch2/ch0 estimate: {estimates[0]:+.6f} Hz "
            f"(coherence {coherences[0]:.6f}, valid "
            f"{valid_counts[0]}/{self.estimation_samples}, used {used_counts[0]})"
        )
        print(
            f"Cross-SDR CFO ch3/ch0 estimate: {estimates[1]:+.6f} Hz "
            f"(coherence {coherences[1]:.6f}, valid "
            f"{valid_counts[1]}/{self.estimation_samples}, used {used_counts[1]})"
        )
        print(
            f"Cross-SDR CFO estimate disagreement: {disagreement:.6f} Hz "
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
            self._reject("; ".join(rejection_reasons))
            return

        accepted = 0.5 * (estimates[0] + estimates[1])
        correction_step = -2.0 * numpy.pi * accepted / self.samp_rate
        with self._lock:
            self._accepted_cfo_hz = accepted
            self._correction_step = correction_step
            # Zero phase at lock preserves the instantaneous constant phase for
            # the downstream phase-only calibration rather than absorbing it here.
            self._correction_phase = 0.0
            self._locked = True
            self._failed = False
            self._lock_tag_pending = True

        print(f"Cross-SDR CFO accepted average: {accepted:+.6f} Hz")
        print(
            f"Cross-SDR CFO frozen correction: {-accepted:+.6f} Hz, "
            f"phase step {correction_step:+.12g} rad/sample, identically on ch2 and ch3"
        )
        print(
            "Cross-SDR CFO lock established. Downstream constant phase "
            "calibration may now begin."
        )

    def _reject(self, reason):
        with self._lock:
            self._failed = True
            self._rejection_count += 1
            rejection_count = self._rejection_count
            self._last_failure_reason = reason
        self._samples_accumulated = 0
        self._relative_samples = [[], []]
        self.retry_remaining = self.retry_delay_samples
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
                self.settling_remaining -= skipped
                cursor += skipped
                continue

            if self.retry_remaining:
                skipped = min(self.retry_remaining, item_count - cursor)
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
            reference = input_items[0][cursor:cursor + used]
            for relative_index, bravo_channel in enumerate((2, 3)):
                relative = (
                    input_items[bravo_channel][cursor:cursor + used]
                    * numpy.conj(reference)
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
