#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Direct pilot-referenced phase correction for two coherent SDR pairs."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import threading

import numpy
import pmt
from gnuradio import gr


class cross_sdr_pilot_phase_corrector(gr.sync_block):
    """Remove common Alpha/Bravo phase motion using the filtered OTA pilot.

    Inputs 0--3 are filtered pilot streams in physical array order. Inputs
    4--7 are the corresponding filtered target streams. Alpha channels pass
    unchanged. One sample-by-sample correction derived independently from both
    Bravo pilot channels is applied identically to Bravo pilot and target
    channels, preserving each SDR's internal RX1/RX2 phase.
    """

    _LOCK_TAG = "cfo_locked"
    _DEGRADED_TAG = "cfo_tracking_degraded"
    _RECOVERED_TAG = "cfo_tracking_recovered"

    def __init__(self,
                 settling_samples=327680,
                 acquisition_samples=8192,
                 min_coherence=0.995,
                 max_differential_phase_rad=0.35,
                 min_valid_fraction=0.90,
                 max_alignment_lag=256,
                 phase_smoothing_samples=64):
        if settling_samples < 0:
            raise ValueError("Settling length must be non-negative")
        if acquisition_samples < 64:
            raise ValueError("Acquisition must contain at least 64 samples")
        if not 0.0 <= min_coherence <= 1.0:
            raise ValueError("Minimum coherence must be in [0, 1]")
        if not 0.0 < max_differential_phase_rad <= numpy.pi:
            raise ValueError("Differential phase limit must be in (0, pi]")
        if not 0.0 < min_valid_fraction <= 1.0:
            raise ValueError("Valid fraction must be in (0, 1]")
        if max_alignment_lag < 0:
            raise ValueError("Maximum alignment lag must be non-negative")
        if phase_smoothing_samples < 1:
            raise ValueError("Phase smoothing length must be positive")

        gr.sync_block.__init__(
            self,
            name="Cross-SDR Pilot Phase Corrector",
            in_sig=[numpy.complex64] * 8,
            out_sig=[numpy.complex64] * 8,
        )
        self.set_tag_propagation_policy(gr.TPP_DONT)

        self.settling_remaining = int(settling_samples)
        self.acquisition_samples = int(acquisition_samples)
        self.min_coherence = float(min_coherence)
        self.max_differential_phase_rad = float(max_differential_phase_rad)
        self.min_valid_fraction = float(min_valid_fraction)
        self.max_alignment_lag = int(max_alignment_lag)
        self.phase_smoothing_samples = int(phase_smoothing_samples)

        self._acquired = 0
        self._acquisition = numpy.empty(
            (4, self.acquisition_samples), dtype=numpy.complex64
        )
        self._reference_phasors = None
        self._alignment_lag = 0
        self._history_length = 2 * self.max_alignment_lag
        self._history = [
            numpy.zeros(self._history_length, dtype=numpy.complex64)
            for _ in range(8)
        ]
        self._last_correction = numpy.complex64(1.0 + 0.0j)
        self._phase_history = numpy.ones(
            max(0, self.phase_smoothing_samples - 1), dtype=numpy.complex64
        )
        self._locked = False
        self._degraded = False
        self._lock = threading.Lock()

        print(
            "Cross-SDR direct pilot phase correction: settling for "
            f"{self.settling_remaining} processed samples, acquiring over "
            f"{self.acquisition_samples} samples, minimum coherence "
            f"{self.min_coherence:.3f}, alignment search "
            f"+/-{self.max_alignment_lag} processed samples"
        )

    def locked(self):
        with self._lock:
            return self._locked

    def degraded(self):
        with self._lock:
            return self._degraded

    def _emit_tag(self, relative_offset, key_name, value):
        absolute_offset = self.nitems_written(0) + int(relative_offset)
        key = pmt.intern(key_name)
        # Emit one event on each four-channel bank's reference stream. Emitting
        # it on every channel would duplicate it when streams are vectorized.
        self.add_item_tag(0, absolute_offset, key, value)
        self.add_item_tag(4, absolute_offset, key, value)

    def _accumulate_acquisition(self, pilot, start, stop):
        count = stop - start
        destination = slice(self._acquired, self._acquired + count)
        for channel in range(4):
            self._acquisition[channel, destination] = pilot[channel][start:stop]

    @staticmethod
    def _lag_slices(length, lag):
        if lag >= 0:
            return slice(0, length - lag), slice(lag, length)
        return slice(-lag, length), slice(0, length + lag)

    def _estimate_alignment_lag(self):
        if self.max_alignment_lag == 0:
            return 0, 1.0
        envelopes = numpy.abs(self._acquisition[[0, 2, 3]]).astype(
            numpy.float64, copy=False
        )
        scores = []
        for lag in range(-self.max_alignment_lag,
                         self.max_alignment_lag + 1):
            alpha_slice, bravo_slice = self._lag_slices(
                self.acquisition_samples, lag
            )
            channel_scores = []
            for row in (1, 2):
                alpha = envelopes[0, alpha_slice]
                bravo = envelopes[row, bravo_slice]
                alpha = alpha - numpy.mean(alpha)
                bravo = bravo - numpy.mean(bravo)
                denominator = numpy.sqrt(
                    numpy.dot(alpha, alpha) * numpy.dot(bravo, bravo)
                )
                channel_scores.append(
                    float(numpy.dot(alpha, bravo) / denominator)
                    if denominator > numpy.finfo(numpy.float64).tiny else 0.0
                )
            scores.append(float(numpy.mean(channel_scores)))
        best_index = int(numpy.argmax(scores))
        return best_index - self.max_alignment_lag, scores[best_index]

    def _finish_acquisition(self, relative_offset):
        alignment_lag, alignment_score = self._estimate_alignment_lag()
        alpha_slice, bravo_slice = self._lag_slices(
            self.acquisition_samples, alignment_lag
        )
        reference = self._acquisition[0, alpha_slice].astype(
            numpy.complex128, copy=False
        )
        reference = reference[-64:]
        reference_power = float(numpy.sum(numpy.abs(reference) ** 2))
        cross_sum = numpy.zeros(2, dtype=numpy.complex128)
        bravo_power = numpy.zeros(2, dtype=numpy.float64)
        for index, channel in enumerate((2, 3)):
            bravo = self._acquisition[channel, bravo_slice].astype(
                numpy.complex128, copy=False
            )
            bravo = bravo[-64:]
            cross_sum[index] = numpy.sum(bravo * numpy.conj(reference))
            bravo_power[index] = float(numpy.sum(numpy.abs(bravo) ** 2))
        denominator = numpy.sqrt(reference_power * bravo_power)
        coherences = numpy.divide(
            numpy.abs(cross_sum), denominator,
            out=numpy.zeros(2, dtype=numpy.float64), where=denominator > 0.0
        )
        if (not numpy.all(numpy.isfinite(coherences))
                or numpy.min(coherences) < self.min_coherence
                or (self.max_alignment_lag and alignment_score < 0.25)
                or numpy.any(numpy.abs(cross_sum)
                             <= numpy.finfo(numpy.float64).tiny)):
            print(
                "Cross-SDR direct pilot acquisition rejected: coherence "
                f"{coherences[0]:.5f}/{coherences[1]:.5f}, alignment "
                f"lag {alignment_lag:+d}, score {alignment_score:.3f}; retrying"
            )
            self._acquired = 0
            return False

        references = cross_sum / numpy.abs(cross_sum)
        with self._lock:
            self._reference_phasors = references.astype(numpy.complex64)
            self._alignment_lag = int(alignment_lag)
            self._locked = True
            self._degraded = False
        self._last_correction = numpy.complex64(1.0 + 0.0j)
        self._phase_history.fill(1.0 + 0.0j)
        self._emit_tag(relative_offset, self._LOCK_TAG, pmt.from_double(0.0))
        print(
            "Cross-SDR DIRECT PILOT LOCKED: reference coherence "
            f"{coherences[0]:.5f}/{coherences[1]:.5f}; stream alignment lag "
            f"{alignment_lag:+d} processed samples (marker score "
            f"{alignment_score:.3f}); common phase is now corrected "
            "sample-by-sample on both Bravo channels"
        )
        return True

    def _aligned_segment(self, input_items, start, stop):
        if self._history_length == 0:
            return [items[start:stop] for items in input_items]
        latency = self.max_alignment_lag
        bravo_delay = latency - self._alignment_lag
        aligned = []
        for channel, items in enumerate(input_items):
            delay = bravo_delay if channel in (2, 3, 6, 7) else latency
            extended = numpy.concatenate((self._history[channel], items[:stop]))
            begin = self._history_length + start - delay
            aligned.append(extended[begin:begin + stop - start])
        return aligned

    @staticmethod
    def _forward_fill(values, valid, initial):
        if values.size == 0:
            return values
        indices = numpy.where(valid, numpy.arange(values.size), -1)
        numpy.maximum.accumulate(indices, out=indices)
        result = numpy.empty(values.size, dtype=numpy.complex64)
        before_first = indices < 0
        result[before_first] = initial
        usable = ~before_first
        result[usable] = values[indices[usable]]
        return result

    def _correct_segment(self, input_items, output_items, start, stop):
        aligned = self._aligned_segment(input_items, start, stop)
        for channel in range(8):
            output_items[channel][start:stop] = aligned[channel]
        reference = aligned[0]
        tiny = numpy.finfo(numpy.float32).tiny
        drifts = []
        powers_valid = []
        for ref_index, channel in enumerate((2, 3)):
            cross = aligned[channel] * numpy.conj(reference)
            magnitude = numpy.abs(cross)
            valid = numpy.isfinite(cross) & (magnitude > tiny)
            unit = numpy.ones(cross.size, dtype=numpy.complex64)
            numpy.divide(cross, magnitude, out=unit, where=valid)
            drifts.append(unit * numpy.conj(self._reference_phasors[ref_index]))
            powers_valid.append(valid)

        agreement = numpy.abs(numpy.angle(drifts[0] * numpy.conj(drifts[1])))
        valid = (
            powers_valid[0]
            & powers_valid[1]
            & numpy.isfinite(agreement)
            & (agreement <= self.max_differential_phase_rad)
        )
        common = drifts[0] + drifts[1]
        common_magnitude = numpy.abs(common)
        valid &= common_magnitude > tiny
        phase = numpy.ones(common.size, dtype=numpy.complex64)
        numpy.divide(
            common,
            common_magnitude,
            out=phase,
            where=valid,
        )
        phase = self._forward_fill(
            phase, valid, numpy.conj(self._last_correction)
        )
        if self.phase_smoothing_samples > 1:
            extended = numpy.concatenate((self._phase_history, phase))
            kernel = numpy.full(
                self.phase_smoothing_samples,
                1.0 / self.phase_smoothing_samples,
                dtype=numpy.float32,
            )
            phase = numpy.convolve(extended, kernel, mode="valid").astype(
                numpy.complex64, copy=False
            )
            self._phase_history = extended[
                -(self.phase_smoothing_samples - 1):
            ].copy()
        smoothed_magnitude = numpy.abs(phase)
        correction = numpy.ones(phase.size, dtype=numpy.complex64)
        numpy.divide(
            numpy.conj(phase), smoothed_magnitude,
            out=correction, where=smoothed_magnitude > tiny
        )
        if correction.size:
            self._last_correction = correction[-1]

        for channel in (2, 3, 6, 7):
            numpy.multiply(
                aligned[channel],
                correction,
                out=output_items[channel][start:stop],
            )

        valid_fraction = float(numpy.mean(valid)) if valid.size else 0.0
        with self._lock:
            was_degraded = self._degraded
            now_degraded = valid_fraction < self.min_valid_fraction
            self._degraded = now_degraded
        if now_degraded and not was_degraded:
            self._emit_tag(
                start,
                self._DEGRADED_TAG,
                pmt.intern(
                    f"direct pilot valid fraction {valid_fraction:.3f} is below "
                    f"{self.min_valid_fraction:.3f}"
                ),
            )
            print(
                "Cross-SDR DIRECT PILOT DEGRADED: holding the last valid phase "
                f"for bad samples; valid fraction {valid_fraction:.3f}"
            )
        elif was_degraded and not now_degraded:
            self._emit_tag(start, self._RECOVERED_TAG, pmt.from_double(0.0))
            print("Cross-SDR DIRECT PILOT RECOVERED")

    def work(self, input_items, output_items):
        item_count = min(
            min(len(items) for items in input_items),
            min(len(items) for items in output_items),
        )
        for channel in range(8):
            output_items[channel][:item_count] = input_items[channel][:item_count]

        cursor = 0
        while cursor < item_count:
            if self.settling_remaining:
                skipped = min(self.settling_remaining, item_count - cursor)
                self.settling_remaining -= skipped
                cursor += skipped
                continue

            with self._lock:
                locked = self._locked
            if not locked:
                needed = self.acquisition_samples - self._acquired
                used = min(needed, item_count - cursor)
                self._accumulate_acquisition(input_items, cursor, cursor + used)
                self._acquired += used
                cursor += used
                if self._acquired == self.acquisition_samples:
                    self._finish_acquisition(cursor)
                continue

            self._correct_segment(input_items, output_items, cursor, item_count)
            cursor = item_count

        if self._history_length:
            for channel in range(8):
                extended = numpy.concatenate(
                    (self._history[channel], input_items[channel][:item_count])
                )
                self._history[channel] = extended[-self._history_length:].copy()

        return item_count
