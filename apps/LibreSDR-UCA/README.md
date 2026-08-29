# LibreSDR four-channel UCA MUSIC

This flowgraph performs live direction finding with two two-channel LibreSDRs
and a dual-channel B210 transmitter. It was validated on the connected hardware
with the target at `345 deg`.

## Physical arrangement

Receiver stream order is fixed and must match the antenna wiring:

1. `192.168.4.1 RX1` — `315 deg`
2. `192.168.4.1 RX2` — `45 deg`
3. `192.168.5.1 RX2` — `135 deg`
4. `192.168.5.1 RX1` — `225 deg`

The four elements have `162.63 mm` adjacent chord spacing, giving a radius of
`162.63 / sqrt(2) mm`. Bearings are source directions measured from the array
centre toward the transmitter.

Connect the B210 as follows:

| B210 output | Signal | Placement | Default TX gain |
|---|---|---|---:|
| RF A `TX/RX` (channel 0) | Fixed tracking beacon at `700.140 MHz` | `180 deg`, never moved during a run | `25 dB` |
| RF B `TX/RX` (channel 1) | Direction-finding target at `700.150 MHz` | `345 deg` during startup, then movable | `40 dB` |

The beacon is deliberately 15 dB below the target. Its pseudo-random amplitude
marker lets the receiver measure the item offset between the two independent
LibreSDR streams without interrupting either stream.

Both LibreSDRs require the distributed external 10 MHz and 1 PPS connections.
The graph arms `sync_start_enable` on both receivers and stops if the shared PPS
edge is not observed. This aligns the receiver startup event, but it does not
make the two independent device streams share a permanent phase epoch. The
fixed beacon supplies that missing continuous phase reference.

## Required startup procedure

The order matters:

1. Put the fixed beacon antenna at `180 deg`.
2. Put the target antenna at the known startup bearing, `345 deg` by default.
   If it is physically somewhere else, change `target_calibration_bearing` in
   `run_MUSIC_uca_live_cal.grc` to that measured bearing before generating.
3. Start `run_DoA_transmitter.grc` **first** and leave it running.
4. Start `run_MUSIC_uca_live_cal.grc`.
5. Do not move either antenna until the receiver prints both:

   ```text
   Cross-SDR DIRECT PILOT LOCKED
   UCA calibration complete
   ```

6. After calibration completes, move only the target antenna. Keep the fixed
   beacon and both transmitter channels running for the entire receiver run.
7. Stop the receiver before stopping the transmitter.

The compass is not valid before `UCA calibration complete`. A rejected
calibration window retries automatically; leave both antennas stationary while
it retries.

If the console instead mentions `Cross-SDR CFO coarse`, `frequency-state
transition`, or repeated CFO lock loss, a stale generated or installed graph is
being run. Those messages belong to the disabled legacy tracker, not the live
path described here.

## What the live correction does

The old windowed CFO state estimator remains in the GRC file only as a disabled
diagnostic block. It is not connected to the live bearing path.

The live path first isolates the `+140 kHz` beacon and `+150 kHz` target using
matched translating filters with decimation by two. At `262.5 kS/s`, the
`Cross-SDR Direct Pilot Phase Corrector`:

- searches up to `+/-256` processed samples for the beacon marker alignment;
- captures the initial Alpha-to-Bravo reference over 8,192 samples;
- estimates the common Bravo phase motion directly on every sample from both
  beacon observations;
- applies one identical smoothed correction to both Bravo receiver channels,
  preserving their internal channel phase; and
- reports degradation without destroying the calibration coefficients or
  entering a frequency-state reacquisition loop.

The aligned target streams are then decimated by four to `65.625 kS/s`.
Startup OTA calibration uses the target itself at its known bearing. This is
intentional: transferring a static phase calibration from `700.140 MHz` to
`700.150 MHz` was not repeatable across independently clocked receivers. The
fixed beacon handles continuous alignment and phase tracking; the target
provides the exact-frequency array calibration only at startup.

The calibration threshold is `0.97`, appropriate for the measured target
coherence. Once accepted, its phase-only coefficients are frozen and applied to
the target stream. They are no longer discarded merely because a short tracking
window is noisy. The bearing gate suppresses output before calibration and
during an explicitly degraded pilot interval.

The `5--60 Hz` values seen in earlier logs were legitimate short-term slopes of
the measured Alpha-to-Bravo phase, not stable oscillator states. Converting each
slope into a new CFO state caused the lock/drop/reacquire loop and invalidated
otherwise usable calibration. The direct phase tracker follows the underlying
phase itself and does not classify those slopes as frequency transitions.

## Expected successful log

A normal startup contains one PPS confirmation, one direct-pilot lock, one
successful UCA calibration, and then bearing output. The alignment lag can
change after a receiver restart; that is expected and is measured from the
marker. It must be within `+/-256` processed samples, with a high marker score.

Example values from two hardware restarts:

| Run | Alignment lag | Marker score | Calibration coherence (channels 1–3) | 345° target result |
|---|---:|---:|---|---:|
| 1 | `+206` | `0.997` | `0.9848 / 0.9887 / 0.9931` | mean `346.8 deg`, median error `+2 deg` |
| 2 | `-44` | `0.997` | `0.9850 / 0.9866 / 0.9928` | mean `344.9 deg`, median error `0 deg` |

Neither run produced IIO `O` overruns or lock recovery cycles. An isolated
buffer-allocation alignment warning from GNU Radio is harmless. Repeated `O`
characters are not harmless: they mean input samples were lost, so stop and
restart with the optional spectrum/phase displays disabled.

## Build, install, and run

From the repository root:

```sh
cmake -S . -B build
cmake --build build -j2
ctest --test-dir build --output-on-failure
sudo cmake --install build
sudo ldconfig
```

Generate the two checked-in Python files after editing either GRC file. Then run
the transmitter first:

```sh
python3 apps/Narrowband-Flowgraphs/phase_offset_measurement_correction/run_DoA_transmitter.py
```

Leave it running and start the receiver in a second terminal:

```sh
python3 apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.py
```

The generated Python and GRC versions have the same defaults. After a receiver
restart, always repeat startup calibration with the target at the configured
known bearing. Do not reuse a coefficient file across a restart as a substitute
for this same-session calibration.

## Diagnostics

The optional full-rate FFT and phase displays are disabled by default because
they previously pushed the laptop into IIO overruns. Enable only one temporarily
after a clean calibration if it is needed.

For acquisition/load isolation, the directory also contains:

- `diagnose_libresdr_iio_overflow.grc`, which tests the two IIO sources without
  correction, calibration, MUSIC, or GUI load; and
- `diagnose_libresdr_cfo_calibration_load.grc`, retained for comparison with the
  legacy windowed CFO implementation.

The second graph is not the implementation used by the live receiver. Its CFO
state messages should not be used to diagnose a current live run.
