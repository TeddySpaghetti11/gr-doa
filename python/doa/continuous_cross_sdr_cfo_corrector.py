#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Continuously tracked cross-SDR carrier-frequency-offset correction."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import threading

import numpy
from scipy import signal

from .cross_sdr_cfo_corrector import cross_sdr_cfo_corrector as _initial_corrector


class continuous_cross_sdr_cfo_corrector(_initial_corrector):
    """Keep the Bravo-vs-Alpha pilot phase slope locked for the whole run.

    The parent class performs the existing coarse acquisition and residual
    refinement. After that succeeds, this class keeps measuring the residual
    phase slope of the filtered OTA pilot and continuously updates the one
    common Bravo rotator frequency. It intentionally does not force absolute
    phase to zero, so fixed hardware/geometric phase remains available to the
    downstream OTA phase calibration and MUSIC processing.

    ``cfo_locked`` is withheld until the continuous tracker has observed the
    configured number of stable residual windows. Tracking then continues for
    the lifetime of the flowgraph instead of freezing the CFO estimate.
    """

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
                 min_coherence=0.90,
                 tracking_window_samples=262144,
                 tracking_warmup_samples=4096,
                 tracking_lock_tolerance_hz=0.05,
                 tracking_agreement_tolerance_hz=0.25,
                 tracking_max_residual_hz=20.0,
                 tracking_gain=1.0,
                 tracking_lock_windows=2,
                 tracking_min_coherence=None,
                 tracking_log_every=8):
        super().__init__(
            samp_rate=samp_rate,
            pilot_offset_hz=pilot_offset_hz,
            pilot_bandwidth_hz=pilot_bandwidth_hz,
            settling_samples=settling_samples,
            estimation_samples=estimation_samples,
            validation_settling_samples=validation_settling_samples,
            residual_tolerance_hz=residual_tolerance_hz,
            max_refinement_rounds=max_refinement_rounds,
            retry_delay_samples=retry_delay_samples,
            agreement_tolerance_hz=agreement_tolerance_hz,
            max_abs_cfo_hz=max_abs_cfo_hz,
            min_coherence=min_coherence,
        )

        if tracking_window_samples < 64:
            raise ValueError("Tracking window must contain at least 64 samples")
        if tracking_warmup_samples < 0:
            raise ValueError("Tracking warm-up must be non-negative")
        if tracking_lock_tolerance_hz < 0.0:
            raise ValueError("Tracking lock tolerance must be non-negative")
        if tracking_agreement_tolerance_hz < 0.0:
            raise ValueError("Tracking agreement tolerance must be non-negative")
        if tracking_max_residual_hz <= 0.0:
            raise ValueError("Tracking maximum residual must be positive")
        if not 0.0 < tracking_gain <= 1.0:
            raise ValueError("Tracking gain must be in (0, 1]")
        if tracking_lock_windows < 1:
            raise ValueError("Tracking lock windows must be at least one")
        if tracking_min_coherence is None:
            tracking_min_coherence = min_coherence
        if not 0.0 <= tracking_min_coherence <= 1.0:
            raise ValueError("Tracking minimum coherence must be in [0, 1]")
        if tracking_log_every < 1:
            raise ValueError("Tracking log interval must be at least one")

        self.tracking_window_samples = int(tracking_window_samples)
        self.tracking_warmup_samples = int(tracking_warmup_samples)
        self.tracking_lock_tolerance_hz = float(tracking_lock_tolerance_hz)
        self.tracking_agreement_tolerance_hz = float(tracking_agreement_tolerance_hz)
        self.tracking_max_residual_hz = float(tracking_max_residual_hz)
        self.tracking_gain = float(tracking_gain)
        self.tracking_lock_windows = int(tracking_lock_windows)
        self.tracking_min_coherence = float(tracking_min_coherence)
        self.tracking_log_every = int(tracking_log_every)

        self._tracking_started = False
        self._tracking_ready = False
        self._tracking_warmup_remaining = self.tracking_warmup_samples
        self._tracking_relative_samples = [[], []]
        self._tracking_samples_accumulated = 0
        self._tracking_filter_states = None
        self._tracking_mix_phase = 0.0
        self._tracking_stable_windows = 0
        self._tracking_update_count = 0
        self._tracking_rejection_count = 0
        self._tracking_last_residual_hz = None
        self._tracking_last_estimates_hz = None
        self._tracking_last_coherences = None
        self._tracking_lock = threading.Lock()
        self._reset_tracking_filters()

        print(
            "Cross-SDR continuous tracker: "
            f"{self.tracking_window_samples} samples/window, lock residual <= "
            f"{self.tracking_lock_tolerance_hz:.6f} Hz for "
            f"{self.tracking_lock_windows} consecutive windows; tracking "
            "continues after cfo_locked."
        )

    def locked(self):
        """True only when acquisition and continuous residual tracking are stable."""
        with self._tracking_lock:
            ready = self._tracking_ready
        with self._lock:
            acquired = self._locked
        return bool(acquired and ready)

    def tracking_residual_hz(self):
        with self._tracking_lock:
            return self._tracking_last_residual_hz

    def tracking_estimates_hz(self):
        with self._tracking_lock:
            if self._tracking_last_estimates_hz is None:
                return None
            return tuple(self._tracking_last_estimates_hz)

    def tracking_coherences(self):
        with self._tracking_lock:
            if self._tracking_last_coherences is None:
                return None
            return tuple(self._tracking_last_coherences)

    def tracking_update_count(self):
        with self._tracking_lock:
            return self._tracking_update_count

    def tracking_rejection_count(self):
        with self._tracking_lock:
            return self._tracking_rejection_count

    def _emit_lock_tags(self, relative_offset):
        # Parent sets _locked after its one-shot residual check. Delay the
        # downstream calibration tag until the tracker proves the slope stays flat.
        with self._tracking_lock:
            ready = self._tracking_ready
        if ready:
            super()._emit_lock_tags(relative_offset)

    def _reset_tracking_filters(self):
        shape = (self._pilot_sos.shape[0], 2)
        self._tracking_filter_states = [
            numpy.zeros(shape, dtype=numpy.complex128) for _ in range(3)
        ]
        self._tracking_mix_phase = 0.0

    def _start_tracking(self):
        self._tracking_started = True
        self._tracking_ready = False
        self._tracking_warmup_remaining = self.tracking_warmup_samples
        self._tracking_relative_samples = [[], []]
        self._tracking_samples_accumulated = 0
        self._tracking_stable_windows = 0
        self._reset_tracking_filters()
        print(
            "Cross-SDR acquisition passed. cfo_locked is withheld until the "
            "continuous tracker demonstrates a stationary residual phase slope."
        )

    def _filter_tracking_segment(self, output_items, start, stop):
        count = stop - start
        phases = self._tracking_mix_phase + self._pilot_mix_step * numpy.arange(count)
        mixer = numpy.exp(1j * phases)
        selected = (
            output_items[0][start:stop],
            output_items[2][start:stop],
            output_items[3][start:stop],
        )
        filtered = []
        for index, samples in enumerate(selected):
            pilot, state = signal.sosfilt(
                self._pilot_sos,
                samples * mixer,
                zi=self._tracking_filter_states[index],
            )
            self._tracking_filter_states[index] = state
            filtered.append(pilot)
        self._tracking_mix_phase = float(
            numpy.remainder(
                self._tracking_mix_phase + self._pilot_mix_step * count + numpy.pi,
                2.0 * numpy.pi,
            ) - numpy.pi
        )
        return filtered

    def _reject_tracking_window(self, reason):
        self._tracking_relative_samples = [[], []]
        self._tracking_samples_accumulated = 0
        with self._tracking_lock:
            self._tracking_rejection_count += 1
            count = self._tracking_rejection_count
            self._tracking_stable_windows = 0
        print(
            f"Cross-SDR tracking window rejected ({count}): {reason}. "
            "Keeping the last valid correction and continuing to track."
        )

    def _finish_tracking_window(self):
        estimates = []
        coherences = []
        try:
            for chunks in self._tracking_relative_samples:
                relative = numpy.concatenate(chunks)
                estimate, coherence, *_ = self._fit_cfo(relative)
                estimates.append(estimate)
                coherences.append(coherence)
        except ValueError as error:
            self._reject_tracking_window(str(error))
            return
        finally:
            self._tracking_relative_samples = [[], []]
            self._tracking_samples_accumulated = 0

        disagreement = abs(estimates[0] - estimates[1])
        reasons = []
        for channel, (estimate, coherence) in enumerate(
                zip(estimates, coherences), start=2):
            if not numpy.isfinite(estimate):
                reasons.append(f"ch{channel}/ch0 residual is not finite")
            elif abs(estimate) > self.tracking_max_residual_hz:
                reasons.append(
                    f"ch{channel}/ch0 residual {estimate:+.6f} Hz exceeds "
                    f"{self.tracking_max_residual_hz:.6f} Hz"
                )
            if not numpy.isfinite(coherence) or coherence < self.tracking_min_coherence:
                reasons.append(
                    f"ch{channel}/ch0 coherence {coherence:.6f} is below "
                    f"{self.tracking_min_coherence:.6f}"
                )
        if disagreement > self.tracking_agreement_tolerance_hz:
            reasons.append(
                f"the two residual estimates disagree by {disagreement:.6f} Hz"
            )
        if reasons:
            self._reject_tracking_window("; ".join(reasons))
            return

        residual_hz = 0.5 * (estimates[0] + estimates[1])
        applied_hz = self.tracking_gain * residual_hz

        # Frequency only: retain instantaneous rotator phase. This removes
        # continuing phase ramp without erasing the absolute spatial phase.
        with self._lock:
            self._accepted_cfo_hz += applied_hz
            total_cfo_hz = self._accepted_cfo_hz
            self._set_correction_frequency(total_cfo_hz, reset_phase=False)

        with self._tracking_lock:
            self._tracking_update_count += 1
            update_count = self._tracking_update_count
            self._tracking_last_residual_hz = float(residual_hz)
            self._tracking_last_estimates_hz = tuple(estimates)
            self._tracking_last_coherences = tuple(coherences)
            if abs(residual_hz) <= self.tracking_lock_tolerance_hz:
                self._tracking_stable_windows += 1
            else:
                self._tracking_stable_windows = 0
            stable = self._tracking_stable_windows
            became_ready = (
                not self._tracking_ready and stable >= self.tracking_lock_windows
            )
            if became_ready:
                self._tracking_ready = True

        if (
                update_count == 1
                or update_count % self.tracking_log_every == 0
                or abs(residual_hz) > self.tracking_lock_tolerance_hz
                or became_ready):
            print(
                f"Cross-SDR tracking {update_count}: ch2/ch0 "
                f"{estimates[0]:+.6f} Hz, ch3/ch0 {estimates[1]:+.6f} Hz, "
                f"avg {residual_hz:+.6f} Hz; applied {applied_hz:+.6f} Hz; "
                f"total {total_cfo_hz:+.6f} Hz; coherence "
                f"{coherences[0]:.5f}/{coherences[1]:.5f}; "
                f"stable {stable}/{self.tracking_lock_windows}"
            )
        if became_ready:
            print(
                "Cross-SDR CONTINUOUS LOCK QUALIFIED. cfo_locked will be emitted "
                "on the next output sample; residual tracking remains active."
            )

    def _track_output_segment(self, output_items, start, stop):
        cursor = start
        while cursor < stop:
            if self._tracking_warmup_remaining:
                used = min(self._tracking_warmup_remaining, stop - cursor)
                self._filter_tracking_segment(output_items, cursor, cursor + used)
                self._tracking_warmup_remaining -= used
                cursor += used
                continue

            needed = self.tracking_window_samples - self._tracking_samples_accumulated
            used = min(needed, stop - cursor)
            pilots = self._filter_tracking_segment(output_items, cursor, cursor + used)
            reference = pilots[0]
            for index, bravo in enumerate(pilots[1:]):
                relative = (bravo * numpy.conj(reference)).astype(
                    numpy.complex64, copy=False
                )
                self._tracking_relative_samples[index].append(relative.copy())
            self._tracking_samples_accumulated += used
            cursor += used
            if self._tracking_samples_accumulated == self.tracking_window_samples:
                self._finish_tracking_window()

    def work(self, input_items, output_items):
        if not self._locked:
            produced = super().work(input_items, output_items)
            if self._locked and not self._tracking_started:
                self._start_tracking()
            return produced

        if not self._tracking_started:
            self._start_tracking()

        item_count = min(len(items) for items in input_items)
        output_items[0][:item_count] = input_items[0][:item_count]
        output_items[1][:item_count] = input_items[1][:item_count]

        with self._tracking_lock:
            ready = self._tracking_ready
        if ready and self._lock_tag_pending:
            super()._emit_lock_tags(0)

        self._apply_correction(input_items, output_items, 0, item_count)
        self._track_output_segment(output_items, 0, item_count)
        return item_count
