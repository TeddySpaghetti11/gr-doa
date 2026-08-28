# LibreSDR UCA port audit

Baseline: EttusResearch/gr-doa `upstream/main` at commit
`c416e4df566305cd6c472176971a8646f39bb0fa` (2026-03-17).

This audit records the repository state before the minimal-port corrections.

## Core implementation comparison

| File or stage | State before correction | Classification | Finding |
|---|---|---|---|
| `lib/autocorrelate_impl.cc` | Identical to upstream | Preserve | Ettus snapshot, overlap, matrix layout, and covariance calculation were not rewritten. The UCA flowgraph selects forward-only averaging; Ettus ULA examples select forward-backward averaging. |
| `lib/MUSIC_lin_array_impl.cc` | Identical to upstream | Preserve | This remains the reference for eigendecomposition, ascending Armadillo eigenvalue order, noise-subspace selection, pseudo-spectrum, and normalization. |
| `lib/MUSIC_uca_impl.cc` | New independent implementation | Required UCA geometry plus unnecessary deviation | The UCA manifold is required, but added argument checks, eigensolver failure output, denominator flooring, and a different matrix-view construction are unrelated to UCA geometry. |
| `python/doa/uca_pilot_calibration.py` | New raw-sample complex gain/phase estimator | Required OTA adaptation plus unnecessary deviation | It correctly removes the predicted pilot manifold before correction, but it replaces Ettus's phase-only relative-channel correction with complex amplitude equalization and introduces a new calibration architecture. |
| `apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.grc` | New combined receive/calibrate/MUSIC graph | Required LibreSDR source, OTA calibration, and UCA geometry | Same-session calibration is justified because reopening either independent LibreSDR can change the cross-device phase. The graph maps the existing wiring into counter-clockwise element order A RX1, A RX2, B RX2, B RX1. The downstream path should remain Ettus-like. |
| UCA covariance averaging parameter | `Forward` | Required UCA geometry | Ettus's `Forward-Backward` option uses a reversal matrix appropriate to its ULA ordering. With UCA order 0, 90, 180, 270 degrees, that reversal maps a source at theta to a second source at 90-theta; it is not a valid unchanged UCA operation. The covariance implementation itself remains unchanged. |
| UCA channel mapping | A/.4 RX1 -> 0, A/.4 RX2 -> 1, B/.5 RX2 -> 2, B/.5 RX1 -> 3 | Required LibreSDR mapping, physically specified by the setup diagram | The graph permutes the two B/.5 outputs so the top-right, top-left, bottom-left, bottom-right wiring becomes logical elements 0, 1, 2, 3 without moving cables. |
| `apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.py` | Generated from GRC | Generated artifact | It must not be the only location of a permanent fix and must be regenerated after the GRC/source correction. |

## Changes to upstream example flowgraphs

| Files | Classification | Finding |
|---|---|---|
| `apps/Narrowband-Flowgraphs/calibrate_lin_array.grc` | Unnecessary deviation / potentially incorrect | Added a second, enabled FMComms path while retaining disabled X440 blocks; reduced the active path to one two-channel LibreSDR; changed element count, spacing, angle, AGC, and frequency independently of the dedicated four-channel UCA path. |
| `apps/Narrowband-Flowgraphs/run_MUSIC_lin_array.grc` | Unnecessary deviation / potentially incorrect | Added duplicated enabled/disabled processing branches and only one two-channel LibreSDR, while still running the ULA MUSIC block. It is not the requested four-element UCA. |
| `estimate_constant_phase_offsets_and_save.grc` | Required source experiment mixed with unnecessary deviation | The two FMComms sources are relevant, but the edits duplicate and disable the upstream X440 graph rather than providing a clean LibreSDR-specific graph. |
| `view_op_with_corrected_phase_offsets.grc` | Diagnostic-only mixed with unnecessary deviation | The four-channel viewing path is useful diagnostics, but it was embedded as a duplicate branch in an upstream example. |
| Generated `.py` files beside those GRC files | Generated artifacts / unnecessary repository divergence | These files were generated from the modified examples and are not authoritative source. |
| `run_DoA_transmitter.grc` | Required OTA transmitter configuration | B210 serial selection, 700 MHz center frequency, separate 50 kHz pilot and 150 kHz target outputs, and 40 dB gain on both TX channels are hardware/calibration changes. |

## Failure-chain assessment before correction

1. Synthetic UCA covariance tests produce the expected MUSIC bearing, so the
   UCA manifold is internally self-consistent in simulation.
2. Synthetic OTA calibration tests preserve the expected UCA phase while
   removing injected channel phase/gain offsets.
3. The first unverified boundary is therefore the four live streams entering
   calibration: their physical antenna order, sample correspondence, and
   phase stability across the two independent network devices.
4. A nearly flat live pseudo-spectrum is consistent with loss of mutual
   coherence, an incorrect physical channel order, or a calibration/model angle
   mismatch. It is not evidence that Ettus's covariance or MUSIC subspace
   processing needs replacement.
5. No live capture or timestamp evidence is present in the repository, so
   cross-LibreSDR phase instability cannot be established from source code
   alone.

## Minimal correction decision

- Keep the working pair of FMComms2/3/4 source blocks.
- Keep same-session OTA calibration, because a separate calibration flowgraph
  would reopen the two radios and can invalidate the measured startup phase.
- Restrict OTA correction to the fixed relative phase component after removing
  the known UCA geometric phase; do not equalize amplitude in this phase stage.
- Make UCA MUSIC follow the Ettus implementation line-for-line apart from
  construction of the physical-position steering matrix and the 0-360 degree
  scan.
- Keep `autocorrelate_impl.cc` unchanged and use forward covariance for this UCA
  ordering.
- Restore unrelated upstream narrowband examples rather than maintaining
  parallel disabled block trees in them.
