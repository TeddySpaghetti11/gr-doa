# Minimal Ettus gr-doa port report

Reference baseline: EttusResearch/gr-doa `upstream/main`, commit
`c416e4df566305cd6c472176971a8646f39bb0fa` (2026-03-17). The upstream project
and X440 workflow were also checked against the Ettus repository and DoA-X440
wiki.

## Result

The active port is the Ettus narrowband chain with only these functional
differences:

1. two FMComms2/3/4 IIO sources supply four LibreSDR channels;
2. a same-session, known-bearing OTA phase calibration removes fixed relative
   channel phase without removing the UCA manifold phase; and
3. MUSIC uses physical four-element UCA positions and scans 0-360 degrees.

The repair retains Ettus's covariance and MUSIC algorithms, removes the two
independent GUI smoothers, and reuses Ettus's `Phase Offset Est` block before
and after same-session OTA correction. The live graph uses a shorter 2,048-sample
non-overlapping covariance window so a bearing spans about 31.2 ms at the
65.625-kS/s target-processing rate. Validity tags now prevent a covariance
matrix from crossing a tracking or calibration state boundary. The three AD9361
tracking loops are disabled because they can move relative phase after
calibration. The MUSIC subspace implementation remains unchanged.

## Files changed by the correction

- `lib/MUSIC_uca_impl.cc`: removed non-geometry MUSIC deviations and restored
  the Ettus eigendecomposition, subspace, reciprocal spectrum, and normalization
  behavior.
- `python/doa/uca_pilot_calibration.py`: made calibration phase-only, retained
  expected geometry, added measured/geometry/hardware pairwise phase output,
  and writes an Ettus `phase_correct_hier`-compatible phase file.
- `python/doa/qa_MUSIC_uca.py`: added an end-to-end test through the unchanged
  Ettus covariance block.
- `python/doa/qa_uca_pilot_calibration.py`: verifies phase removal, geometry
  retention, no amplitude equalization, and calibration preservation across a
  soft tracking degradation.
- `python/doa/cross_sdr_cfo_corrector.py` and
  `continuous_cross_sdr_cfo_corrector.py`: separate phase and frequency gains,
  confirm large common frequency transitions, relax estimator-noise tolerance,
  and distinguish calibration-preserving soft recovery from hard phase-epoch
  loss.
- `lib/autocorrelate_impl.cc` and `python/doa/bearing_validity_gate.py`: require
  a completely valid calibrated snapshot and replace invalid directions with
  an explicit `NaN` marker.
- `grc/doa_uca_pilot_calibration.block.yml`, `README.md`, and
  `apps/LibreSDR-UCA/README.md`: corrected the calibration contract and recorded
  equations, ordering, and limitations.
- `apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.grc`: restored Ettus covariance and
  display parameters, disabled phase-moving AD9361 tracking loops, and added
  continuous raw/corrected phase panels using the upstream estimator.
- `apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.py`: regenerated from its
  authoritative GRC file.
- `apps/LibreSDR-UCA/UPSTREAM_AUDIT.md`: pre-change classification and failure
  chain.

The following altered Ettus example GRC files were restored byte-for-byte to
upstream, and their locally generated Python artifacts were removed:

- `apps/Narrowband-Flowgraphs/calibrate_lin_array.grc`
- `apps/Narrowband-Flowgraphs/run_MUSIC_lin_array.grc`
- `apps/Narrowband-Flowgraphs/phase_offset_measurement_correction/estimate_constant_phase_offsets_and_save.grc`
- `apps/Narrowband-Flowgraphs/phase_offset_measurement_correction/view_op_with_corrected_phase_offsets.grc`

The B210 transmitter uses two simultaneous 40 dB channels: RF A `TX/RX` sends
the fixed `+50 kHz` calibration beacon, while RF B `TX/RX` sends the movable
`+150 kHz` direction-finding target. MUSIC receives only the separately filtered
target; the known `pilot_bearing` is used only to derive phase calibration.

## Reverted deviations

- Duplicate enabled/disabled X440 and FMComms branches embedded in upstream
  examples.
- Two-element/single-LibreSDR paths mislabeled as the active array path.
- Generated Python copies of those modified upstream GRC examples.
- MUSIC eigensolver fallback output, denominator floor, alternate matrix-view
  handling, and separate maximum accumulator, none of which is required by UCA
  geometry.
- OTA amplitude equalization. Ettus's relative phase stage applies
  unit-magnitude correction, so this port now does the same.

## Remaining changes and why they are required

### LibreSDR source and channel order

The authoritative GRC maps channels as follows:

| Global index | SDR channel | Required physical antenna |
|---:|---|---|
| 0 | `192.168.4.1` RX1 | top-right, element 0, 315 degrees |
| 1 | `192.168.4.1` RX2 | top-left, element 1, 45 degrees |
| 2 | `192.168.5.1` RX2 | bottom-left, element 2, 135 degrees |
| 3 | `192.168.5.1` RX1 | bottom-right, element 3, 225 degrees |

The GRC connections deliberately permute the two `192.168.5.1` outputs to match
the existing physical wiring. With the B210 direction defined as 0 degrees, the
default element-0 angle is 315 degrees and the step is +90 degrees. This
identical logical index order is used by OTA calibration, covariance, and MUSIC.

### UCA steering vector

For adjacent chord `d = 162.63 mm`, the four-element circle radius is
`r = d/sqrt(2) = 114.997 mm`. At 903 MHz, the configured normalized radius is
`rho = r/lambda = 0.346379923`.

For element `m`:

```text
beta_m = element0_bearing + m * element_bearing_step
r_m/lambda = rho [cos(beta_m), sin(beta_m)]^T
u(theta) = [cos(theta), sin(theta)]^T
a_m(theta) = exp(-j 2 pi (r_m/lambda)^T u(theta))
           = exp(-j 2 pi rho cos(theta - beta_m)).
```

The same negative-exponent convention is used in MUSIC and calibration.

### OTA phase correction

For channel `i` relative to channel 0, let

```text
q_i = unit(sum_n x_0[n] conj(x_i[n]))
g_i = a_0(theta_cal) conj(a_i(theta_cal)).
```

Then the applied coefficient is

```text
c_0 = 1
c_i = unit(q_i / g_i)
    = exp(j (phi_hardware,0 - phi_hardware,i)).
```

Thus

```text
c_i x_i = |h_i| exp(j phi_hardware,0) a_i(theta_cal) s,
```

so relative hardware phase is removed and the expected UCA phase remains.
Channel magnitude is deliberately unchanged.

Same-session operation is necessary here: a saved correction followed by
reopening two independent radios can measure one startup phase and apply it to a
different startup phase.

## Ettus algorithm preservation

- Covariance calculation: matrix layout and `X^T conj(X) / N` calculation remain
  Ettus code. The active graph uses 2,048-sample, non-overlapping snapshots and
  adds state-tag gating around that calculation; invalid snapshots produce a
  zero matrix plus `doa_valid=false` rather than mixing phase epochs.
- Averaging selection: forward-only for the UCA. Ettus forward-backward mode
  uses a reversal matrix for ULA ordering. With UCA order 0, 90, 180, 270
  degrees, that reversal introduces the manifold for `90 degrees - theta`; it
  is not the correct UCA centro-symmetry permutation.
- MUSIC implementation: unchanged in behavior apart from the steering matrix
  and 0-360 degree grid. Armadillo `eig_sym` ascending ordering is retained;
  columns `0..M-K-1` form the noise subspace; the projector, reciprocal
  denominator, and `10 log10(P/Pmax)` normalization match Ettus.

## Synchronization assumptions

The Ettus X440 wrapper configures one multi-channel UHD device, calls
`set_time_unknown_pps`, and uses a timed command to tune all channels. The X440
channels also share device sample timing and clock/LO infrastructure.

Two independent FMComms IIO source blocks do not expose an equivalent joint
timed stream start or joint tune in this graph. A shared external 10 MHz
reference can stabilize frequency/sample-rate drift, but without reliable PPS
there is no demonstrated common sample epoch. A fixed offset is absorbed by
same-session narrowband calibration at the pilot frequency. Calibration cannot
repair a later sample slip, loss of samples, relative drift, or the different
phase produced by the same time offset at a substantially different baseband
frequency.

## Failure localization and unresolved hardware evidence

The corrected software passes:

- synthetic UCA covariance -> MUSIC bearings over the full circle;
- synthetic OTA hardware-phase injection -> phase-only correction while
  preserving the expected UCA manifold; and
- synthetic four streams -> unchanged Ettus autocorrelation -> UCA MUSIC,
  resolving the injected 73 degree bearing within 0.5 degree.

The live, transmitter, and compatibility diagnostic GRC files compile
successfully with GNU Radio Companion Compiler 3.11.0.

Live source-only acquisition from both LibreSDRs completed without an IIO `O`
overrun at 1 MS/s and again at 625 kS/s. A separate pre-correction pilot probe at
525 kS/s isolated a periodic frequency discontinuity to Alpha: Bravo remained
near `+690 Hz` relative to the transmitted pilot, while Alpha alternated between
approximately `-880 Hz` and `+2195 Hz` every 524,288 samples. Transition windows
lost coherence, producing an observed Bravo-minus-Alpha CFO alternation near
`+1570 Hz` and `-1503 Hz`. This is real input-stream behavior rather than a
correction-loop oscillation; a deterministic replay at the hardware settings
remains locked.

The corrector continuously estimates Alpha-versus-Bravo pilot phase slope and
applies one common complex rotator to both Bravo channels. Alpha is copied
unchanged, Bravo's internal phase difference is therefore preserved, and the
loop does not servo the absolute cross-SDR phase to zero. A fixed geometric or
hardware phase remains available to the downstream OTA calibration.

Acquisition and post-lock quality limits are separate. Residual slope,
two-channel agreement, and coherence are checked before a post-lock estimate
can update the Bravo rotator. The live settings allow 1 Hz disagreement and
three bad windows, damp ordinary residual updates with a 0.25 frequency gain,
and require two coherent, same-direction observations before treating an
uninterrupted residual above 5 Hz as a real frequency-state transition. This
prevents a single phase-step-contaminated fit from being misclassified as a
lasting 5--60 Hz frequency state.

A rejected tracking interval now emits `cfo_tracking_degraded`, which gates
covariance and bearings while preserving the common rotator, original phase
reference, and frozen UCA coefficients. Successful validation restores that
same phase datum and emits `cfo_tracking_recovered`. Only a structural or
differential phase discontinuity emits `cfo_unlocked`; that hard phase-epoch
loss discards calibration and requires a later qualified `cfo_locked` plus a
fresh OTA measurement. Consequently the historical log's frequent coherent
0.25--0.4 Hz estimator disagreements no longer cause calibration churn, while
uncertain samples are not presented as usable bearings.

On 2026-08-28 the dual-channel B210 graph was run on the attached B210 over USB
2: UHD accepted both TX channels at `40 dB`, and a 15-second run produced no
`U` underflows. Both LibreSDRs were reachable and the full rebuilt receiver
established CFO lock and repeatedly completed OTA calibration with coherence
between roughly `0.97` and `0.99`. The same previously isolated Alpha frequency
state transitions then caused repeated unlock/reacquire cycles without printed
IIO `O` overruns; those cycles are the failure reproduced and corrected by the
new recurring-transition regression. The dual-signal wiring is operational.

On 2026-08-29 a full headless hardware run used both LibreSDRs, PPS arming, and
the dual-channel B210 at `700 MHz` and `40 dB` TX gain. An initial run exposed
that post-lock estimates were applied before their stricter qualification was
checked: 41 of 54 accepted updates exceeded the configured 20 Hz limit, with a
maximum of 236.457 Hz. Moving the qualification into the base tracker fixed
that ordering bug. A strict 20 Hz run then correctly rejected the recurrent
Lesha frequency states, but was too restrictive to acquire a stable operating
period. The deployed limit is therefore 80 Hz: it accepts the observed normal
40--60 Hz states while rejecting the separate 100--236 Hz events.

The final 80 Hz run produced no IIO `O` overruns. It qualified one continuous
lock, completed OTA calibration once with channel coherences `0.9995`, `0.9995`,
and `0.9994`, and had no lock loss after calibration for the remainder of the
run. There were four reacquisitions before final calibration, including one
strict-limit rejection; the largest accepted residual was 77.772 Hz and the
largest two-Bravo-estimate disagreement was 0.126 Hz against a 0.25 Hz limit.
This validates the correction and reacquisition path on the attached hardware.
A real live-GUI bearing walk-around is still required to quantify room
multipath, antenna-pattern error, and short bearing transients. Any actual `O`
overrun remains a hard invalidation of that run and must still force
reacquisition.

A follow-up check at the locally edited 902 MHz setting found no usable pilot:
all acquisition attempts had noise-like coherence around 0.00--0.03. The
software correctly refused to lock. The committed TX, receiver, and diagnostic
therefore remain consistently set to the hardware-validated 700 MHz centre
frequency; changing frequency requires changing all three together and first
confirming that the RF path and antennas deliver both tones there.

## Test summary

```text
cmake --build build -j4
  PASS

ctest --test-dir build -R 'qa_(MUSIC_uca|cross_sdr_cfo_corrector|continuous_cross_sdr_cfo_corrector|libresdr_pps_sync|uca_pilot_calibration)'
  5/5 test programs passed

grcc -o /tmp apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.grc
  PASS
```

The complete configured suite has ten test programs. The five relevant programs
above pass. The other five legacy linear-array/Octave programs stop at import
because the environment lacks the upstream QA dependency `oct2py`. That is an
environment dependency failure, not a failure of the cross-SDR or UCA DSP.

## Concise diff summary

Relative to the local commit at task start, the correction removes roughly two
thousand lines of duplicated modified flowgraph/generated code and adds focused
audit, documentation, and covariance-to-MUSIC QA. Relative to Ettus upstream,
the remaining additions are the dedicated LibreSDR UCA graph, B210 OTA pilot
configuration, UCA steering block/bindings, same-session known-bearing phase
calibration, and their tests/documentation.
