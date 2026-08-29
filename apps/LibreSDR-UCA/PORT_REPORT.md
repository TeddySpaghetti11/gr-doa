# LibreSDR UCA implementation report

## Final finding

The original bearings were not trustworthy. The two LibreSDRs remained
coherent internally, but their common inter-device phase moved nonlinearly.
The old correction interpreted short phase slopes as distinct CFO states,
continually adjusted its frequency rotator, dropped lock, and caused frozen UCA
calibration coefficients to be discarded. The visible `5--60 Hz` transitions
were measurements of real phase motion, but they were artifacts as a model of
piecewise-stable oscillator frequency.

PPS arming succeeded and each radio's two channels remained aligned. That did
not establish a permanent shared phase or host-stream item epoch between the
two independent receivers. A raw, low-load beacon capture confirmed this:
Alpha's internal relative frequency was approximately `-0.009 Hz`, while the
common Bravo-to-Alpha phase slope varied broadly (median `13.1 Hz`, 5th–95th
percentile about `-41` to `+20.8 Hz`) and sometimes jumped close to pi. There
were no IIO overruns in that capture.

## Implemented correction

The live graph now uses `cross_sdr_pilot_phase_corrector` after narrow beacon
and target filters. It:

1. correlates the fixed beacon's pseudo-random amplitude marker to estimate the
   item lag between Alpha and Bravo;
2. delays the corresponding four pilot and four target streams into alignment;
3. measures common Alpha-to-Bravo phase motion independently through both Bravo
   pilot channels on every sample;
4. smooths and applies one identical correction to both Bravo channels; and
5. emits compatible validity tags without returning to the legacy CFO recovery
   state machine.

The B210 transmitter now sends the fixed marked beacon at `+140 kHz`, gain
`25 dB`, and the movable target at `+150 kHz`, gain `40 dB`. The 10 kHz spacing
is sufficient for the 2 kHz selector filters while the lower beacon gain limits
leakage into the target selector.

The filters decimate the `525 kS/s` receiver streams by two before alignment,
allowing `+/-256` processed samples of marker search without full-rate Python
load. After correction, vector decimation by four restores the established
`65.625 kS/s` MUSIC processing rate.

Static calibration is intentionally performed with the target at its known
startup bearing (`target_calibration_bearing`, default `345 deg`) and at the
exact target RF. The fixed 180-degree beacon remains responsible for continuous
stream alignment and phase tracking. This avoids the non-repeatable cross-
frequency static phase transfer observed when a 140 kHz beacon calibration was
applied to a 150 kHz target on receivers without a deterministic shared phase
epoch.

Calibration minimum coherence is `0.97`. The coefficients are retained through
brief tracking-quality degradation and are invalidated only when the actual
calibration state is no longer usable. The legacy full-rate/windowed CFO block
is disabled in the live GRC flowgraph and retained only for diagnostics.

## Hardware verification

The complete transmitter and receiver chain was exercised twice, including a
receiver restart between runs, with the fixed beacon at `180 deg` and target at
`345 deg`.

| Run | Measured lag | Marker score | Target calibration coherence | Bearing result |
|---|---:|---:|---|---|
| 1 | `+206` samples | `0.997` | `0.9848 / 0.9887 / 0.9931` | mean `346.80 deg`; median error `+2 deg`; 90th-percentile absolute error `7 deg` |
| 2 | `-44` samples | `0.997` | `0.9850 / 0.9866 / 0.9928` | mean `344.92 deg`; median error `0 deg`; 90th-percentile absolute error `0 deg` |

On run 2, 846 of 923 captured estimates were exactly `345 deg`, with another
76 at `344 deg`. The calibrated measured target phases relative to element 0
were `[0, 36.33, 167.86, 132.34] deg`; the UCA model for `345 deg` predicts
`[0, 35.39, 167.46, 132.07] deg`.

Both runs were free of IIO `O` overruns, repeated lock loss, and CFO
drop/reacquisition. These tests demonstrate repeatable operation for the known
bearing on the connected hardware. Additional bearings should still be tested
after moving the target, especially in a reflective indoor environment.

## Operator requirement

The transmitter must be started first. Hold the fixed beacon at `180 deg` and
the target at the configured `target_calibration_bearing` until both `Cross-SDR
DIRECT PILOT LOCKED` and `UCA calibration complete` are printed. The target may
then move; the fixed beacon must remain stationary and transmitting. Restarting
either receiver requires repeating this same-session calibration.
