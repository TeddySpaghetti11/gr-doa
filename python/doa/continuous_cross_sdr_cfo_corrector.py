#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Continuously qualified cross-SDR carrier-frequency-offset correction."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import threading

from .cross_sdr_cfo_corrector import cross_sdr_cfo_corrector as _tracker


class continuous_cross_sdr_cfo_corrector(_tracker):
    """Delay lock until the base continuous tracker proves it is stable.

    ``cross_sdr_cfo_corrector`` owns the signal path. It leaves Alpha
    unchanged, applies one phase-continuous rotator to both Bravo channels,
    follows common frequency-state changes, detects structural phase jumps,
    and emits unlock/relock tags while reacquiring after a discontinuity.

    This subclass adds a lock-qualification policy. The parent's initial
    acquisition may enable correction, but ``cfo_locked`` is withheld until a
    configured number of consecutive accepted tracking windows have a small,
    mutually agreeing residual. Absolute Alpha-vs-Bravo phase is never forced
    to zero, so the fixed geometric/hardware phase remains available to the
    downstream OTA calibration block.
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

        # Apply the full measured frequency residual; use tracking_gain only
        # for the slow phase-error servo. This follows the LibreSDR's observed
        # 50--100 Hz common states without erasing fixed absolute phase.
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
            tracking_window_samples=tracking_window_samples,
            tracking_phase_gain=tracking_gain,
            phase_jump_threshold_rad=2.0,
            tracking_bad_window_grace=1,
        )

        self.tracking_warmup_samples = int(tracking_warmup_samples)
        self.tracking_lock_tolerance_hz = float(tracking_lock_tolerance_hz)
        self.tracking_agreement_tolerance_hz = float(
            tracking_agreement_tolerance_hz
        )
        self.tracking_max_residual_hz = float(tracking_max_residual_hz)
        self.tracking_gain = float(tracking_gain)
        self.tracking_lock_windows = int(tracking_lock_windows)
        self.tracking_min_coherence = float(tracking_min_coherence)
        self.tracking_log_every = int(tracking_log_every)

        self._qualification_lock = threading.RLock()
        self._qualification_started = False
        self._qualification_ready = False
        self._qualification_warmup_remaining = self.tracking_warmup_samples
        self._qualification_stable_windows = 0
        self._qualification_window_rejected = False
        self._qualification_update_count = 0
        self._qualification_rejection_count = 0
        self._qualification_last_residual_hz = None
        self._qualification_last_estimates_hz = None
        self._qualification_last_coherences = None

        print(
            "Cross-SDR continuous lock qualification: "
            f"residual <= {self.tracking_lock_tolerance_hz:.6f} Hz for "
            f"{self.tracking_lock_windows} consecutive accepted windows; "
            "frequency-state tracking and discontinuity reacquisition remain "
            "active after cfo_locked."
        )

    def locked(self):
        with self._qualification_lock:
            qualified = self._qualification_ready
        with self._lock:
            tracked = self._locked
        return bool(tracked and qualified)

    def tracking_residual_hz(self):
        with self._qualification_lock:
            return self._qualification_last_residual_hz

    def tracking_estimates_hz(self):
        with self._qualification_lock:
            if self._qualification_last_estimates_hz is None:
                return None
            return tuple(self._qualification_last_estimates_hz)

    def tracking_coherences(self):
        with self._qualification_lock:
            if self._qualification_last_coherences is None:
                return None
            return tuple(self._qualification_last_coherences)

    def tracking_update_count(self):
        with self._qualification_lock:
            return self._qualification_update_count

    def tracking_rejection_count(self):
        with self._qualification_lock:
            return self._qualification_rejection_count

    def _reset_qualification(self):
        with self._qualification_lock:
            self._qualification_started = False
            self._qualification_ready = False
            self._qualification_warmup_remaining = self.tracking_warmup_samples
            self._qualification_stable_windows = 0
            self._qualification_window_rejected = False

    def _start_qualification(self):
        with self._qualification_lock:
            if self._qualification_started:
                return
            self._qualification_started = True
            self._qualification_ready = False
            self._qualification_warmup_remaining = self.tracking_warmup_samples
            self._qualification_stable_windows = 0
        print(
            "Cross-SDR acquisition passed. cfo_locked is withheld until the "
            "continuous tracker demonstrates a stationary residual phase slope."
        )

    def _emit_lock_tags(self, relative_offset):
        with self._qualification_lock:
            ready = self._qualification_ready
        if ready:
            super()._emit_lock_tags(relative_offset)

    def _handle_bad_tracking_window(self, reason):
        with self._qualification_lock:
            self._qualification_window_rejected = True
            self._qualification_rejection_count += 1
            self._qualification_stable_windows = 0
        super()._handle_bad_tracking_window(reason)

    def _start_reacquire(self, reason):
        super()._start_reacquire(reason)
        self._reset_qualification()

    def _finish_tracking(self):
        self._start_qualification()
        with self._qualification_lock:
            self._qualification_window_rejected = False

        # Parent performs the actual update, phase-continuity checks,
        # structural-jump detection, and reacquire transition.
        super()._finish_tracking()

        with self._lock:
            still_locked = self._locked
            estimates = self._estimates_hz
            coherences = self._coherences
        with self._qualification_lock:
            rejected = self._qualification_window_rejected
        if not still_locked or rejected or estimates is None or coherences is None:
            return

        estimates = tuple(float(value) for value in estimates)
        coherences = tuple(float(value) for value in coherences)
        residual_hz = 0.5 * (estimates[0] + estimates[1])
        disagreement_hz = abs(estimates[0] - estimates[1])

        with self._qualification_lock:
            self._qualification_update_count += 1
            update_count = self._qualification_update_count
            self._qualification_last_residual_hz = residual_hz
            self._qualification_last_estimates_hz = estimates
            self._qualification_last_coherences = coherences

            if self._qualification_warmup_remaining > 0:
                self._qualification_warmup_remaining = max(
                    0,
                    self._qualification_warmup_remaining
                    - self.tracking_window_samples,
                )
                stable = 0
            else:
                acceptable = (
                    abs(residual_hz) <= self.tracking_lock_tolerance_hz
                    and abs(residual_hz) <= self.tracking_max_residual_hz
                    and disagreement_hz
                    <= self.tracking_agreement_tolerance_hz
                    and min(coherences) >= self.tracking_min_coherence
                )
                if acceptable:
                    self._qualification_stable_windows += 1
                else:
                    self._qualification_stable_windows = 0
                stable = self._qualification_stable_windows

            became_ready = (
                not self._qualification_ready
                and stable >= self.tracking_lock_windows
            )
            if became_ready:
                self._qualification_ready = True

        if (
                update_count == 1
                or update_count % self.tracking_log_every == 0
                or abs(residual_hz) > self.tracking_lock_tolerance_hz
                or became_ready):
            print(
                f"Cross-SDR qualification {update_count}: ch2/ch0 "
                f"{estimates[0]:+.6f} Hz, ch3/ch0 {estimates[1]:+.6f} Hz, "
                f"avg {residual_hz:+.6f} Hz; coherence "
                f"{coherences[0]:.5f}/{coherences[1]:.5f}; stable "
                f"{stable}/{self.tracking_lock_windows}"
            )
        if became_ready:
            print(
                "Cross-SDR CONTINUOUS LOCK QUALIFIED. cfo_locked will be "
                "emitted on the next output sample; tracking and reacquisition "
                "remain active."
            )

    def work(self, input_items, output_items):
        produced = super().work(input_items, output_items)
        with self._lock:
            tracked = self._locked
        with self._qualification_lock:
            started = self._qualification_started
        if tracked and not started:
            self._start_qualification()
        return produced
