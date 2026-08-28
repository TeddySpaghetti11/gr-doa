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
    """Continuously track Bravo-vs-Alpha frequency drift from an OTA pilot.

    Inputs and outputs use the LibreSDR array order: ch0 Alpha RX1 reference,
    ch1 Alpha RX2, ch2 Bravo RX2, and ch3 Bravo RX1. Both Alpha channels pass
    through bit-for-bit. Both Bravo channels pass through unchanged during the
    coarse estimate. A common provisional correction is then applied while its
    post-correction residual is measured and refined. After lock, short pilot
    windows keep updating the common correction frequency and return the pilot
    to its captured non-zero lock-time phase. Phase feedback is applied only to
    the one rotator shared by both Bravo inputs, so Bravo's internal phase and
    the captured fixed propagation/hardware phase remain available to
    downstream calibration.
    """

    _LOCK_TAG = "cfo_locked"
    _UNLOCK_TAG = "cfo_unlocked"

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
                 tracking_window_samples=16384,
                 tracking_phase_gain=0.25,
                 phase_jump_threshold_rad=2.0,
                 tracking_bad_window_grace=1,
                 tracking_agreement_tolerance_hz=None,
                 tracking_max_residual_hz=None,
                 tracking_min_coherence=None):
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
        if tracking_window_samples < 64:
            raise ValueError("Tracking window must contain at least 64 samples")
        if tracking_phase_gain < 0.0 or tracking_phase_gain > 1.0:
            raise ValueError("Tracking phase gain must be in [0, 1]")
        if phase_jump_threshold_rad <= 0.0 or phase_jump_threshold_rad > numpy.pi:
            raise ValueError("Phase-jump threshold must be in (0, pi]")
        if tracking_bad_window_grace < 0:
            raise ValueError("Tracking bad-window grace must be non-negative")
        if tracking_agreement_tolerance_hz is None:
            tracking_agreement_tolerance_hz = agreement_tolerance_hz
        if tracking_agreement_tolerance_hz < 0.0:
            raise ValueError(
                "Tracking CFO agreement tolerance must be non-negative"
            )
        if tracking_max_residual_hz is None:
            tracking_max_residual_hz = max_abs_cfo_hz
        if (tracking_max_residual_hz <= 0.0
                or tracking_max_residual_hz > max_abs_cfo_hz):
            raise ValueError(
                "Tracking maximum residual must be positive and no greater "
                "than the acquisition CFO limit"
            )
        if tracking_min_coherence is None:
            tracking_min_coherence = min_coherence
        if tracking_min_coherence < 0.0 or tracking_min_coherence > 1.0:
            raise ValueError("Tracking minimum coherence must be in [0, 1]")

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
        self.tracking_window_samples = int(tracking_window_samples)
        self.tracking_phase_gain = float(tracking_phase_gain)
        self.phase_jump_threshold_rad = float(phase_jump_threshold_rad)
        self.tracking_bad_window_grace = int(tracking_bad_window_grace)
        self.tracking_agreement_tolerance_hz = float(
            tracking_agreement_tolerance_hz
        )
        self.tracking_max_residual_hz = float(tracking_max_residual_hz)
        self.tracking_min_coherence = float(tracking_min_coherence)

        self._relative_samples = [[], []]
        self._samples_accumulated = 0
        self._estimates_hz = None
        self._coherences = None
        self._accepted_cfo_hz = None
        self._correction_phase = 0.0
        self._correction_step = 0.0
        self._rotator_cache = numpy.empty(0, dtype=numpy.complex64)
        self._rotator_work = numpy.empty(0, dtype=numpy.complex64)
        self._rotator_cache_step = None
        self._correction_active = False
        self._estimating_residual = False
        self._refinement_round = 0
        self._locked = False
        self._reacquiring = False
        self._phase_references = None
        self._last_tracked_phase = None
        self._last_tracked_tail_samples = None
        self._tracking_bad_windows = 0
        self._relock_count = 0
        self._discontinuity_count = 0
        self._failed = False
        self._rejection_count = 0
        self._last_failure_reason = ""
        self._lock_tag_pending = False
        self._unlock_tag_pending = False
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
        # Long RF/PLL settling and retry delays must not run three full-rate
        # scipy filters over samples that will never enter an estimate. The
        # fourth-order pilot filter reaches steady state comfortably inside
        # this short tail immediately preceding each measurement window.
        self._pilot_filter_warmup_samples = 4096
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
        print(
            "Cross-SDR CFO continuous tracking: "
            f"{self.tracking_window_samples} samples/window, phase gain "
            f"{self.tracking_phase_gain:.3f}, discontinuity threshold "
            f"{self.phase_jump_threshold_rad:.3f} rad, bad-window grace "
            f"{self.tracking_bad_window_grace}"
        )

    def locked(self):
        """Return True while the continuous pilot tracker is in lock."""
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

    def relock_count(self):
        """Return the number of successful locks after the initial lock."""
        with self._lock:
            return self._relock_count

    def discontinuity_count(self):
        """Return the number of phase discontinuities that caused reacquisition."""
        with self._lock:
            return self._discontinuity_count

    def last_failure_reason(self):
        """Return the most recent rejection diagnostic."""
        with self._lock:
            return self._last_failure_reason

    def _fit_cfo(self, relative_samples):
        # Fitting every raw point causes a long scheduler pause at multi-MS/s
        # rates. Retain the full time span while fitting a safely decimated set
        # of points. The stride is capped so even max_abs_cfo_hz advances by
        # less than pi between fitted samples and phase unwrapping is unique.
        raw_sample_count = int(relative_samples.size)
        max_unambiguous_stride = max(
            1,
            int(self.samp_rate / (2.0 * self.max_abs_cfo_hz)) - 1,
        )
        fit_stride = min(8, max_unambiguous_stride)
        relative_samples = relative_samples[::fit_stride]
        fit_sample_rate = self.samp_rate / fit_stride
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
        # Tracking windows may intentionally decimate to only a few dozen fit
        # points; 16 phase-continuous points still provide a well-conditioned
        # slope while retaining the half-window corruption guard.
        minimum_valid = max(16, relative_samples.size // 2)
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
            int(fit_sample_rate / (2.0 * self.max_abs_cfo_hz)) - 1,
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
        residual_angles = []
        for sample_index, phase in fit_segments:
            fitted = numpy.mean(phase) + slope * (
                sample_index - numpy.mean(sample_index)
            )
            residual = numpy.angle(numpy.exp(1j * (phase - fitted)))
            residual_angles.append(residual)
            residual_sum += numpy.sum(numpy.exp(1j * residual))
        coherence = float(abs(residual_sum) / used_count)
        estimate_hz = float(slope * fit_sample_rate / (2.0 * numpy.pi))

        # The fitted endpoint phase is used as the non-zero phase reference for
        # the tracking loop. The robust residual span flags phase steps that a
        # single straight-line CFO fit can otherwise partially absorb.
        first_index, first_phase_values = fit_segments[0]
        start_phase = float(numpy.angle(numpy.exp(1j * (
            numpy.mean(first_phase_values)
            + slope * (first_index[0] - numpy.mean(first_index))
        ))))
        last_index, last_phase = fit_segments[-1]
        endpoint_phase = float(numpy.angle(numpy.exp(1j * (
            numpy.mean(last_phase)
            + slope * (last_index[-1] - numpy.mean(last_index))
        ))))
        first_raw_index = int(first_index[0]) * fit_stride
        endpoint_tail_samples = (
            raw_sample_count - 1 - int(last_index[-1]) * fit_stride
        )
        residual_angles = numpy.concatenate(residual_angles)
        residual_span = float(
            numpy.percentile(residual_angles, 95.0)
            - numpy.percentile(residual_angles, 5.0)
        )
        return (
            estimate_hz,
            coherence,
            valid_count,
            used_count,
            int(relative_samples.size),
            raw_sample_count,
            fit_stride,
            endpoint_phase,
            residual_span,
            start_phase,
            first_raw_index,
            endpoint_tail_samples,
        )

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

    def _warm_pilot_filter_tail(
            self, input_items, output_items, start, count, remaining_before):
        """Filter only the final warm-up tail of a discard interval."""
        remaining_after = remaining_before - count
        warm_count = max(
            0,
            min(
                count,
                self._pilot_filter_warmup_samples - remaining_after,
            ),
        )
        if warm_count:
            warm_start = start + count - warm_count
            self._filter_pilot_segment(
                input_items,
                output_items,
                warm_start,
                start + count,
            )

    def _finish_estimation(self):
        estimating_residual = self._estimating_residual
        refinement_round = self._refinement_round
        estimates = []
        coherences = []
        valid_counts = []
        used_counts = []
        fit_counts = []
        raw_counts = []
        fit_strides = []
        endpoint_phases = []
        endpoint_tail_samples = []
        residual_spans = []
        try:
            for chunks in self._relative_samples:
                relative = numpy.concatenate(chunks)
                (
                    estimate,
                    coherence,
                    valid_count,
                    used_count,
                    fit_count,
                    raw_count,
                    fit_stride,
                    endpoint_phase,
                    residual_span,
                    _start_phase,
                    _first_raw_index,
                    endpoint_tail,
                ) = self._fit_cfo(relative)
                estimates.append(estimate)
                coherences.append(coherence)
                valid_counts.append(valid_count)
                used_counts.append(used_count)
                fit_counts.append(fit_count)
                raw_counts.append(raw_count)
                fit_strides.append(fit_stride)
                endpoint_phases.append(endpoint_phase)
                endpoint_tail_samples.append(endpoint_tail)
                residual_spans.append(residual_span)
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
            f"{valid_counts[0]}/{fit_counts[0]} fit points, used "
            f"{used_counts[0]}, stride {fit_strides[0]} over "
            f"{raw_counts[0]} raw samples)"
        )
        print(
            f"Cross-SDR CFO {label} ch3/ch0 estimate: {estimates[1]:+.6f} Hz "
            f"(coherence {coherences[1]:.6f}, valid "
            f"{valid_counts[1]}/{fit_counts[1]} fit points, used "
            f"{used_counts[1]}, stride {fit_strides[1]} over "
            f"{raw_counts[1]} raw samples)"
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
            self._finish_residual_validation(
                accepted,
                endpoint_phases,
                endpoint_tail_samples,
            )
        else:
            self._start_provisional_correction(accepted)

    def _set_correction_frequency(self, cfo_hz, reset_phase=False):
        self._correction_step = -2.0 * numpy.pi * cfo_hz / self.samp_rate
        self._rotator_cache_step = None
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

    def _finish_residual_validation(
            self, residual_hz, endpoint_phases, endpoint_tail_samples):
        print(
            f"Cross-SDR CFO residual round {self._refinement_round} accepted "
            f"average: {residual_hz:+.6f} Hz"
        )
        if abs(residual_hz) <= self.residual_tolerance_hz:
            with self._lock:
                # The tolerance is an acceptance bound, not a reason to leave
                # a known residual unapplied. Fold the final measured residual
                # into the tracked total while retaining instantaneous phase.
                self._accepted_cfo_hz += residual_hz
                self._set_correction_frequency(
                    self._accepted_cfo_hz, reset_phase=False
                )
                self._locked = True
                was_reacquiring = self._reacquiring
                self._reacquiring = False
                self._phase_references = tuple(endpoint_phases)
                self._last_tracked_phase = tuple(endpoint_phases)
                self._last_tracked_tail_samples = tuple(endpoint_tail_samples)
                self._tracking_bad_windows = 0
                self._failed = False
                self._lock_tag_pending = True
                if was_reacquiring:
                    self._relock_count += 1
                accepted = self._accepted_cfo_hz
                correction_step = self._correction_step
            self._samples_accumulated = 0
            print(f"Cross-SDR CFO final accepted CFO: {accepted:+.6f} Hz")
            print(
                f"Cross-SDR CFO tracked correction: {-accepted:+.6f} Hz, "
                f"phase step {correction_step:+.12g} rad/sample, identically "
                "on ch2 and ch3"
            )
            print(
                "Cross-SDR CFO lock established; continuous pilot tracking is "
                "active. Downstream constant phase calibration may now begin."
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
        self.settling_remaining = self._next_validation_settling_samples()
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

    @staticmethod
    def _wrapped_phase(value):
        return float(numpy.angle(numpy.exp(1j * value)))

    def _next_validation_settling_samples(self):
        """Use a short filter warm-up while recovering from a stream slip.

        A full initial validation window is useful after applying a coarse CFO
        estimate. During reacquisition the existing correction remains active,
        so waiting that long can miss the next stable hardware interval. The
        pilot IIR only needs its bounded warm-up tail before another short fit.
        """
        if self._reacquiring:
            return min(
                self.validation_settling_samples,
                self._pilot_filter_warmup_samples,
            )
        return self.validation_settling_samples

    def _finish_tracking(self):
        """Update frequency from one locked pilot window without zeroing phase."""
        estimates = []
        coherences = []
        start_phases = []
        first_raw_indices = []
        endpoint_phases = []
        endpoint_tail_samples = []
        residual_spans = []
        try:
            for chunks in self._relative_samples:
                relative = numpy.concatenate(chunks)
                fit = self._fit_cfo(relative)
                estimates.append(fit[0])
                coherences.append(fit[1])
                endpoint_phases.append(fit[7])
                residual_spans.append(fit[8])
                start_phases.append(fit[9])
                first_raw_indices.append(fit[10])
                endpoint_tail_samples.append(fit[11])
        except ValueError as error:
            self._handle_bad_tracking_window(f"tracking pilot invalid: {error}")
            return
        finally:
            self._relative_samples = [[], []]
            self._samples_accumulated = 0

        disagreement = abs(estimates[0] - estimates[1])
        quality_failures = []
        for channel, (estimate, coherence) in enumerate(
                zip(estimates, coherences), start=2):
            if (not numpy.isfinite(estimate)
                    or abs(estimate) > self.tracking_max_residual_hz):
                quality_failures.append(
                    f"ch{channel}/ch0 residual {estimate:+.6f} Hz exceeds "
                    f"the tracking limit {self.tracking_max_residual_hz:.6f} Hz"
                )
            if (not numpy.isfinite(coherence)
                    or coherence < self.tracking_min_coherence):
                quality_failures.append(
                    f"ch{channel}/ch0 coherence {coherence:.6f} is below "
                    f"{self.tracking_min_coherence:.6f}"
                )
        if disagreement > self.tracking_agreement_tolerance_hz:
            quality_failures.append(
                f"the two tracking estimates disagree by {disagreement:.6f} "
                f"Hz, above the tracking limit "
                f"{self.tracking_agreement_tolerance_hz:.6f} Hz"
            )
        if quality_failures:
            self._handle_bad_tracking_window("; ".join(quality_failures))
            return

        residual_hz = 0.5 * (estimates[0] + estimates[1])
        phase_errors = [
            self._wrapped_phase(phase - reference)
            for phase, reference in zip(endpoint_phases, self._phase_references)
        ]
        common_phase_error = float(numpy.angle(numpy.mean(numpy.exp(
            1j * numpy.asarray(phase_errors)
        ))))
        differential_error = abs(self._wrapped_phase(
            phase_errors[0] - phase_errors[1]
        ))
        skipped_bad_windows = self._tracking_bad_windows
        boundary_errors = []
        for channel in range(2):
            boundary_gap = (
                self._last_tracked_tail_samples[channel]
                + 1
                + skipped_bad_windows * self.tracking_window_samples
                + first_raw_indices[channel]
            )
            expected_start = (
                self._last_tracked_phase[channel]
                + 2.0 * numpy.pi * estimates[channel]
                * boundary_gap / self.samp_rate
            )
            boundary_errors.append(self._wrapped_phase(
                start_phases[channel] - expected_start
            ))
        boundary_jump = max(abs(error) for error in boundary_errors)
        structural_jump = max(
            differential_error,
            residual_spans[0],
            residual_spans[1],
        )
        common_frequency_transition = abs(residual_hz) > max(
            4.0 * self.residual_tolerance_hz,
            1.0,
        )
        if structural_jump > self.phase_jump_threshold_rad:
            self._start_reacquire(
                "pilot structural discontinuity: metric "
                f"{structural_jump:.6f} rad exceeds "
                f"{self.phase_jump_threshold_rad:.6f} rad"
            )
            return
        if (boundary_jump > self.phase_jump_threshold_rad
                and not common_frequency_transition):
            self._start_reacquire(
                "unexplained pilot phase discontinuity at tracking boundary: "
                f"metric {boundary_jump:.6f} rad exceeds "
                f"{self.phase_jump_threshold_rad:.6f} rad without a "
                "corresponding frequency-slope change"
            )
            return

        self._tracking_bad_windows = 0
        if common_frequency_transition:
            print(
                "Cross-SDR CFO frequency-state transition accepted without "
                f"dropping lock: common residual {residual_hz:+.6f} Hz, "
                f"agreement {disagreement:.6f} Hz, skipped bad windows "
                f"{skipped_bad_windows}"
            )

        phase_feedback = self.tracking_phase_gain * common_phase_error
        feedback_factor = numpy.exp(-1j * phase_feedback)
        corrected_endpoint_phases = tuple(
            self._wrapped_phase(phase - phase_feedback)
            for phase in endpoint_phases
        )
        with self._lock:
            # Frequency feedback removes the measured phase slope. Phase
            # feedback separately returns the next output window to the
            # captured, non-zero pilot phase. Converting phase error into
            # another frequency term made the recurring LibreSDR frequency
            # states overshoot for several windows and contaminate MUSIC.
            self._accepted_cfo_hz += residual_hz
            accepted = self._accepted_cfo_hz
            self._set_correction_frequency(accepted, reset_phase=False)
            self._correction_phase = self._wrapped_phase(
                self._correction_phase - phase_feedback
            )
            self._estimates_hz = tuple(estimates)
            self._coherences = tuple(coherences)
            self._last_tracked_phase = corrected_endpoint_phases
            self._last_tracked_tail_samples = tuple(endpoint_tail_samples)

        # The estimator filters see the same corrected Bravo streams as the
        # outputs. Rotate their internal states by the identical common factor
        # so direct phase feedback does not create an artificial IIR transient
        # and false residual-CFO estimate in the following window.
        self._pilot_filter_states[1] *= feedback_factor
        self._pilot_filter_states[2] *= feedback_factor

    def _handle_bad_tracking_window(self, reason):
        """Hold lock briefly across one mixed hardware transition window."""
        self._tracking_bad_windows += 1
        if self._tracking_bad_windows <= self.tracking_bad_window_grace:
            print(
                "Cross-SDR CFO tracking transition window rejected; holding "
                "the current phase-continuous correction and lock "
                f"({self._tracking_bad_windows}/"
                f"{self.tracking_bad_window_grace}): {reason}"
            )
            return
        self._start_reacquire(
            f"{self._tracking_bad_windows} consecutive invalid tracking "
            f"windows: {reason}"
        )

    def _start_reacquire(self, reason):
        """Drop lock, retain the common rotator, and validate it again."""
        with self._lock:
            if not self._locked:
                return
            self._locked = False
            self._reacquiring = True
            self._phase_references = None
            self._last_tracked_tail_samples = None
            self._tracking_bad_windows = 0
            self._estimating_residual = True
            self._refinement_round = 1
            self._failed = False
            self._last_failure_reason = reason
            self._discontinuity_count += 1
            self._unlock_tag_pending = True
        self._samples_accumulated = 0
        self._relative_samples = [[], []]
        self.settling_remaining = self._next_validation_settling_samples()
        self._reset_pilot_filters()
        print(f"Cross-SDR CFO LOCK LOST: {reason}")
        print(
            "Cross-SDR CFO: common correction remains phase-continuous while "
            "the pilot is reacquired; downstream calibration is disarmed"
        )

    def _reject(self, reason):
        with self._lock:
            self._locked = False
            self._reacquiring = False
            self._phase_references = None
            self._last_tracked_tail_samples = None
            self._tracking_bad_windows = 0
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

    def _emit_unlock_tags(self, relative_offset):
        absolute_offset = self.nitems_written(0) + int(relative_offset)
        value = pmt.intern(self._last_failure_reason)
        key = pmt.intern(self._UNLOCK_TAG)
        for port in range(4):
            self.add_item_tag(port, absolute_offset, key, value)
        self._unlock_tag_pending = False

    def _apply_correction(self, input_items, output_items, start, stop):
        count = stop - start
        if count <= 0:
            return
        if (
                self._rotator_cache_step != self._correction_step
                or self._rotator_cache.size < count):
            capacity = max(65536, count)
            sample_index = numpy.arange(capacity, dtype=numpy.float64)
            self._rotator_cache = numpy.exp(
                1j * self._correction_step * sample_index
            ).astype(numpy.complex64)
            self._rotator_work = numpy.empty(capacity, dtype=numpy.complex64)
            self._rotator_cache_step = self._correction_step

        phase_factor = numpy.complex64(numpy.exp(1j * self._correction_phase))
        rotator = self._rotator_work[:count]
        numpy.multiply(
            self._rotator_cache[:count], phase_factor, out=rotator
        )
        numpy.multiply(
            input_items[2][start:stop], rotator,
            out=output_items[2][start:stop],
        )
        numpy.multiply(
            input_items[3][start:stop], rotator,
            out=output_items[3][start:stop],
        )
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

        cursor = 0
        while cursor < item_count:
            if self._unlock_tag_pending:
                self._emit_unlock_tags(cursor)
            if self._lock_tag_pending:
                self._emit_lock_tags(cursor)

            if self.settling_remaining:
                remaining_before = self.settling_remaining
                skipped = min(self.settling_remaining, item_count - cursor)
                if self._correction_active:
                    self._apply_correction(
                        input_items, output_items, cursor, cursor + skipped
                    )
                self._warm_pilot_filter_tail(
                    input_items,
                    output_items,
                    cursor,
                    skipped,
                    remaining_before,
                )
                self.settling_remaining -= skipped
                cursor += skipped
                continue

            if self.retry_remaining:
                remaining_before = self.retry_remaining
                skipped = min(self.retry_remaining, item_count - cursor)
                self._warm_pilot_filter_tail(
                    input_items,
                    output_items,
                    cursor,
                    skipped,
                    remaining_before,
                )
                self.retry_remaining -= skipped
                cursor += skipped
                if self.retry_remaining == 0:
                    with self._lock:
                        self._failed = False
                        attempt = self._rejection_count + 1
                    print(f"Cross-SDR CFO: starting estimation attempt {attempt}")
                continue

            # Reacquisition retains the already phase-continuous common
            # correction. Short tracking windows can therefore measure and
            # validate a post-slip residual without repeating the long initial
            # coarse-estimation window.
            window_samples = (
                self.tracking_window_samples
                if self._locked or self._reacquiring
                else self.estimation_samples
            )
            needed = window_samples - self._samples_accumulated
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
            if self._samples_accumulated == window_samples:
                if self._locked:
                    self._finish_tracking()
                else:
                    self._finish_estimation()

        # Tags produced exactly at a scheduler boundary are emitted on the first
        # sample of the next call, matching GNU Radio's stream-tag convention.

        return item_count
