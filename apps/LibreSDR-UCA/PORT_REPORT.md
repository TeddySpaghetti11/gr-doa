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

The repair restores Ettus's `32768/16384` covariance window, removes the two
independent GUI smoothers, and reuses Ettus's `Phase Offset Est` block before
and after same-session OTA correction. The three AD9361 tracking loops are
disabled because they can move relative phase after calibration. No covariance
or MUSIC subspace rewrite was added.

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
  retention, and no amplitude equalization.
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

The user's uncommitted B210 transmitter setting, including 89 dB TX gain, was
preserved. The task did not lower or otherwise tune gains.

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
| 0 | `192.168.4.1` RX1 | bottom-right, element 0, 225 degrees |
| 1 | `192.168.4.1` RX2 | bottom-left, element 1, 135 degrees |
| 2 | `192.168.5.1` RX2 | top-left, element 2, 45 degrees |
| 3 | `192.168.5.1` RX1 | top-right, element 3, 315 degrees |

The GRC connections deliberately permute the two `192.168.5.1` outputs to match
the existing physical wiring. With the B210 direction defined as 0 degrees, the
default element-0 angle is 225 degrees and the step is -90 degrees. This
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

- Covariance implementation: unchanged from upstream. Snapshot length, overlap,
  matrix layout, and `X^T conj(X) / N` calculation remain Ettus code. The active
  graph again uses Ettus's `32768` snapshot and `16384` overlap values.
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

The GRC file compiles successfully with GNU Radio Companion Compiler 3.10.12.

Live checks of `ip:192.168.4.1` and `ip:192.168.5.1` both timed out from the test
environment. There are no live captures or timestamp logs in the repository.
Consequently, there is no direct evidence here that cross-LibreSDR phase is
unstable. The first unverified point is the four live streams entering
calibration: physical cable order, sample correspondence, and phase stability.

On the next hardware run, compare the block's printed ch1/ch0, ch2/ch0, and
ch3/ch0 measured phases with their predicted geometric phases. The new raw and
corrected phase panels continue plotting those relationships after calibration;
drift or jumps concentrated in ch2/ch0 and ch3/ch0 isolate the fault to the
cross-LibreSDR boundary.

## Test summary

```text
cmake --build build-fix -j2
  PASS

ctest --test-dir build-fix -R 'qa_(MUSIC_uca|uca_pilot_calibration)'
  2/2 test programs passed (4 test cases total)

grcc -o /tmp apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.grc
  PASS
```

The complete upstream suite runs 7 test programs: the two UCA programs pass;
the other five stop at import because the environment lacks the upstream QA
dependency `oct2py`. That is an environment dependency failure, not a DSP test
failure.

## Concise diff summary

Relative to the local commit at task start, the correction removes roughly two
thousand lines of duplicated modified flowgraph/generated code and adds focused
audit, documentation, and covariance-to-MUSIC QA. Relative to Ettus upstream,
the remaining additions are the dedicated LibreSDR UCA graph, B210 OTA pilot
configuration, UCA steering block/bindings, same-session known-bearing phase
calibration, and their tests/documentation.
