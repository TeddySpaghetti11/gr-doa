# LibreSDR UCA MUSIC

This directory contains the four-channel LibreSDR uniform circular array (UCA)
flowgraph and same-session over-the-air phase calibration.

## Geometry and channel order

The physical array uses four elements with `162.63 mm` adjacent chord spacing,
which gives a radius of `114.997 mm`.

Stream order is fixed as:

1. `192.168.4.1 RX1` - top-right - `315 deg`
2. `192.168.4.1 RX2` - top-left - `45 deg`
3. `192.168.5.1 RX2` - bottom-left - `135 deg`
4. `192.168.5.1 RX1` - bottom-right - `225 deg`

The second LibreSDR is intentionally permuted in the flowgraph so the physical
stream order proceeds counter-clockwise with an element step of `+90 deg`.

Angles are **source bearings**, measured from the array centre towards the
transmitter. Calibration and MUSIC use the same manifold:

```text
a_m(theta) = exp(+j 2 pi rho cos(theta - beta_m))
```

where `rho = r/lambda`.

## Shared 10 MHz and 1 PPS synchronization

Feed the same distribution-amplifier 10 MHz and 1 PPS outputs to both
LibreSDRs. The 10 MHz reference aligns their clock frequencies; it does not by
itself command the two FPGA receive paths to begin on a common timing edge.

The Lesha firmware exposes ADI's external synchronizer as
`cf-ad9361-lpc.sync_start_enable`. The live receiver and both load diagnostics
automatically arm that control on `192.168.4.1` and `192.168.5.1` immediately
after their IIO streams start. Both calls are issued concurrently, and startup
stops with an explicit error if the receivers do not observe a PPS edge within
2.5 seconds. A working connection prints:

```text
LibreSDR PPS SYNC CONFIRMED: every receiver observed the external edge; startup settling may proceed
```

The existing five-second CFO settling interval follows this event, so samples
disturbed by the startup synchronization edge are not used for calibration.
Seeing `sync_start_enable=disarm` while the graph is stopped is normal: the
attribute automatically returns to `disarm` after a successfully armed PPS
edge. Merely connecting the PPS cable without arming this control does not
activate synchronization.

## Frequency-derived normalized radius

The normalized radius is no longer hard-coded. The flowgraph calculates a pilot
value for calibration and a target value for MUSIC from their actual RFs:

```text
array_radius = 0.16263 / sqrt(2)
pilot_rf = center_freq + pilot_offset
norm_radius = array_radius * pilot_rf / 299792458.0
target_rf = center_freq + target_offset
target_norm_radius = array_radius * target_rf / 299792458.0
```

With the current defaults, calibration uses `700.050 MHz` and MUSIC uses
`700.150 MHz`. The small difference is retained rather than silently treating
the target as if it were the pilot.

Note that `162.63 mm` equals exactly half a wavelength at about `921.70 MHz`.
The present test frequency is therefore extremely close to half-wavelength
adjacent spacing. A strong 180-degree ambiguity can still occur on array
symmetry axes even when the processing is correct. Validate at several off-axis
bearings rather than using only `0/90/180/270 deg`.

## Separate calibration and target signals

The live direction finder now uses two simultaneous B210 transmit channels. They
have deliberately different RF offsets and deliberately different jobs:

| B210 connector | Offset / RF | Antenna placement | Receiver use |
|---|---:|---|---|
| RF A `TX/RX` (UHD channel 0) | `+50 kHz` / `700.050 MHz` | Fixed at the bearing entered as `pilot_bearing` | Continuous cross-SDR tracking and OTA phase calibration only |
| RF B `TX/RX` (UHD channel 1) | `+150 kHz` / `700.150 MHz` | Movable target | MUSIC direction finding only |

Both channels use `40 dB` TX gain. Do not connect either antenna to an `RX2`
connector. Leave the RF A calibration antenna stationary and transmitting for
the entire run. Move only the RF B target antenna after lock and calibration.
The value of `pilot_bearing` tells the calibration block where the fixed RF A
antenna is; it is not supplied to MUSIC as the target answer.

The four CFO-corrected receiver streams are split into two identical translated
filter banks. The `+50 kHz` bank estimates one phase-only coefficient per array
channel. Those coefficients are applied to the separate `+150 kHz` bank, and
only that corrected target bank enters covariance and MUSIC. Therefore moving
the RF B antenna changes the measured bearing while the RF A antenna continues
to provide the phase/frequency reference.

## Pilot and target filtering

The B210 pilot is now `+50 kHz` from the receiver centre instead of `+5 kHz`.
Each of the four receiver channels passes through matching Frequency Xlating FIR
filters. The pilot filter at `+50 kHz` feeds calibration; the target filter at
`+150 kHz` feeds covariance and MUSIC after pilot-derived phase correction:

```text
pilot_offset     = 50 kHz
pilot_decim      = 8
pilot_passband   = 10 kHz
pilot_transition = 10 kHz
proc_rate        = 65.625 kS/s
```

After translation the desired pilot is at DC, receiver DC is at `-50 kHz`, and
the pilot image is around `-100 kHz`, so the narrow low-pass rejects both.

The B210 transmitter flowgraph uses the same `700 MHz` centre, `+50 kHz` pilot,
`+150 kHz` target, and `40 dB` gain on both channels by default. Keep both
offsets matched to the receiver variables if you retune.

## Automatic cross-SDR CFO correction

The two raw IIO sources first enter `Cross-SDR CFO Corrector` in fixed physical
order: Alpha RX1, Alpha RX2, Bravo RX2, Bravo RX1. The block leaves Alpha
bit-for-bit unchanged. A streaming complex mixer and fourth-order low-pass
filter isolate `pilot_offset` with `pilot_passband` bandwidth before estimating
Bravo-minus-Alpha CFO independently from Bravo RX2/Alpha RX1 and Bravo
RX1/Alpha RX1. This prevents the other strong tones visible in the raw spectrum
from biasing the OTA-pilot estimate. Both estimates must pass the configured
magnitude and phase-coherence checks and agree within `10 Hz`.

Accepted estimates are averaged. One phase-continuous complex rotator with the
opposite frequency is then applied identically to both Bravo channels, so Bravo's
internal channel coherence is preserved. The rotator begins with zero phase and
the tracker captures the resulting non-zero Alpha-vs-Bravo pilot phase at lock.
It holds that arbitrary phase instead of driving it to zero, leaving propagation
and hardware phase for the existing OTA phase calibration.

Defaults at `525 kS/s` are five seconds of startup settling, a `2**16`-sample
estimation window, maximum `20 kHz` absolute CFO, and minimum `0.90` pilot-fit
coherence. The accepted coarse estimate is applied provisionally to both Bravo
channels. After another `2**12` settling samples, the block measures both
post-correction residual slopes over another `2**16` samples. It refines the
one common correction up to three times and declares lock only when the averaged
residual is at most `1 Hz`. The final measured residual is included even when
already inside that bound. Once locked, the pilot remains active and the block
continues fitting `16,384`-sample tracking windows. Each window updates the
common correction frequency; a low-gain phase servo removes accumulated drift
relative to the captured lock-time phase without removing that fixed phase.
Phase remains continuous whenever the correction frequency changes.

To avoid blocking the GNU Radio scheduler at multi-MS/s input rates, each CFO
fit retains the complete configured time window but uses a phase-unambiguous
stride of at most eight samples. Console diagnostics report the fit stride and
raw-window length. Once a correction is active, a cached complex rotator is
reused across scheduler calls; only its starting phase changes per call. This
preserves phase continuity and the one-common-rotator invariant while avoiding
a full complex exponential and a redundant Bravo copy for every output chunk.
Long RF/PLL settling and retry intervals bypass the internal estimator filters;
only their final 4,096 samples warm the fourth-order pilot filter before a CFO
window. Samples passed to the graph outputs are unaffected by this estimator-only
optimization.

A rejected coarse or residual window prints finite/non-zero sample counts,
waits `2**16` samples, and retries automatically. No `cfo_locked` tag is emitted
until the post-correction residual passes every check. During tracking, one
low-coherence transition window is tolerated while the existing common rotator
and lock remain active. If the following coherent window shows the same new
phase slope on both Bravo comparisons, that common frequency-state change is
accepted without moving the captured phase reference and without emitting
`cfo_unlocked`. This prevents a recurring coherent SDR frequency transition
from repeatedly zeroing and recalibrating the downstream direction finder.

Discontinuity detection is based on phase continuity between adjacent windows,
not merely on the temporary distance from the fixed lock-time phase while its
servo is recovering. A common phase jump without a matching slope change, a
differential phase jump, or more than one consecutive invalid tracking window
still emits `cfo_unlocked` and starts reacquisition without resetting the common
rotator phase. A successful reacquisition emits another `cfo_locked`. The
downstream phase calibration discards its old coefficients on `cfo_unlocked`
and restarts its skip/calibration interval on the new lock tag.

Reacquisition uses the `16,384`-sample tracking window and only the final 4,096
samples of filter warm-up, rather than repeating the long startup acquisition.
This lets the graph recover from a stream slip or receiver frequency step while
the retained common rotator remains phase-continuous. The live graph uses 4,096
post-lock settling samples and 16,384 calibration samples so phase calibration
finishes inside a stable interval.

## AD9361 settings

Both LibreSDRs use:

```text
Gain mode:              Manual
Quadrature tracking:    False
RF DC correction:       True
Baseband DC correction: True
```

The same manual gain is used on all channels. Quadrature tracking stays disabled
after calibration so an adaptive update cannot change relative RF phase.

## Coherence diagnostics

The flowgraph deliberately exposes the phase at three boundaries so a failure
can be localized without changing the receiver architecture:

1. **TRUE pre-filter relative phase** is connected directly to the IIO source
   outputs in physical order `A RX1, A RX2, B RX2, B RX1` and runs at
   `samp_rate` (`525 kS/s`).
2. **POST-CFO relative phase** is after the common CFO rotator and four identical
   translating/decimating FIR filters, but before constant phase calibration. It
   runs at `proc_rate` (`65.625 kS/s`) and should be flat after CFO lock.
3. **Alpha internal** and **Bravo internal** plots compare RX1 with RX2 inside
   each LibreSDR before filtering. A flat same-radio trace with moving
   inter-radio traces isolates the problem to coherence between the devices.

All phase displays use the Ettus convention `arg(x0 * conj(xi))`; their labels
name both physical inputs to avoid an ambiguous channel number.

The full-rate and multi-trace diagnostic sinks remain in the GRC source but are
disabled by default to protect continuous four-channel IIO delivery on the test
laptop. The bearing display and compass remain enabled. After an overrun-free
calibration, enable only the specific phase or spectrum diagnostic needed for a
short inspection; the POST-CFO relative-phase display is the preferred check
that the corrected cross-SDR phase is flat.

The raw four-channel FFT remains connected before the CFO block and all filters in physical UCA
order. It uses 8,192 bins (about `64.1 Hz/bin` at `525 kS/s`) and explicit
channel labels so a small frequency difference between the two radios can be
seen directly. This raw display is expected to retain the original Alpha/Bravo
separation. A second 8,192-bin
**POST-CFO filtered pilot spectrum** runs at `proc_rate`; all four peaks should
coincide there after lock. GNU Radio 3.11 rejects
65,536 for this sink even though that would otherwise be preferred.

## Calibration coherence

The calibration block averages the complex cross product

```text
C_i = sum(x_0 * conj(x_i))
```

and now also reports normalized coherence

```text
gamma_i = |sum(x_0 conj(x_i))|
          / sqrt(sum(|x_0|^2) sum(|x_i|^2))
```

for each channel relative to channel 0. `gamma` is between 0 and 1. A clean
stationary pilot should be close to 1. Calibration now **fails** if any
non-reference channel is below `0.90`; values around `0.98-1.00` are preferable.

On failure the console prints `UCA CALIBRATION FAILED` and no coefficient file
is written. The live and load-diagnostic graphs enable automatic retry: the bad
window is discarded, output remains muted, and the block repeats its skip and
calibration interval until a coherent window succeeds. Other callers retain the
default explicit unity/bypass failure mode. Do not trust the MUSIC bearing until
the live console prints `UCA calibration complete`.

If the same-radio channel is highly coherent but channels from the other
LibreSDR are not, investigate inter-device timing/coherence before interpreting
the MUSIC result.

The averaged calibration phase and coherence printed in the console are more
reliable calibration indicators for a stationary CW pilot; the instantaneous
plots are intended to reveal ramps, discontinuities, and where they first occur.

## Build and test

```sh
cmake -S . -B build
cmake --build build -j$(nproc)
ctest --test-dir build -R 'qa_(MUSIC_uca|cross_sdr_cfo_corrector|continuous_cross_sdr_cfo_corrector|libresdr_pps_sync|uca_pilot_calibration)' --output-on-failure
sudo cmake --install build
sudo ldconfig
```

The UCA tests exercise the source-bearing steering convention, and the live
flowgraph uses the real `315, 45, 135, 225 deg` stream order shown above.

After installation, first run the headless dual-channel B210 flowgraph. It sends
the fixed calibration pilot on RF A and the movable target on RF B, both at
`40 dB` TX gain:

```sh
python3 apps/Narrowband-Flowgraphs/phase_offset_measurement_correction/run_DoA_transmitter.py
```

Leave it running, then start the checked-in receiver Python equivalent:

```sh
python3 apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.py
```

Alternatively, run exactly these two GRC files in this order:

1. `apps/Narrowband-Flowgraphs/phase_offset_measurement_correction/run_DoA_transmitter.grc`
2. `apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.grc`

The transmitter is intentionally headless, so success is a running console
without `U` underflows; it does not open a plot window. In the receiver raw FFT,
success first appears as distinct peaks near `+50 kHz` and `+150 kHz`. The Python
and GRC versions use the same channel order, diagnostics, and calibration
threshold.

## Test procedure

1. Confirm the physical four-element receive-channel order above.
2. Connect the stationary calibration antenna to B210 RF A `TX/RX`, place it at
   a known bearing, and set `pilot_bearing` to that physical bearing.
3. Connect the movable target antenna to B210 RF B `TX/RX` and place it at a
   different starting bearing. Do not enter this target bearing in the graph.
4. Start `run_DoA_transmitter.grc`; leave it running and verify there are no
   repeated `U` underflow characters.
5. Start `run_MUSIC_uca_live_cal.grc` (or the generated Python equivalent).
6. Verify the raw FFT contains both the `+50 kHz` pilot and `+150 kHz` target.
7. The receiver must first print `LibreSDR PPS SYNC CONFIRMED`. A PPS timeout
   means the direction result must not be used; check both distribution outputs,
   cables, and input signal levels.
8. The console must print `Cross-SDR CFO lock established`. During a radio
   frequency-state change, `tracking transition window rejected` followed by
   `frequency-state transition accepted without dropping lock` is expected.
   It must not be followed by recurring `Cross-SDR CFO LOCK LOST` messages while
   both transmit signals remain on. Repeated rejection or `O` overruns means the
   stream or pilot must be fixed before calibration can begin.
9. Compare TRUE pre-filter, POST-CFO, Alpha-internal, and Bravo-internal phase.
10. The raw FFT may show the original radio-specific shift; verify all four peaks
   coincide in `POST-CFO filtered pilot spectra`.
11. Wait for `UCA calibration complete` and inspect all three coherence values. If
   `UCA CALIBRATION FAILED` appears, treat the output as uncalibrated bypass data.
12. Keep RF A fixed. Move only the RF B antenna around the receive array. The
    compass and peak bearing should follow RF B after the covariance-window
    update delay; they should not remain pinned to `pilot_bearing`.
13. Test several off-axis positions and avoid judging the system from only the
    symmetric `0/90/180/270` axes or a strong indoor reflection.
14. Do not retune, restart, or power-cycle either LibreSDR without recalibrating.

A stream of `O` characters is an IIO receive overrun, not a 10 MHz lock report.
It means samples were lost because the host/network/GUI did not drain one or
both radios fast enough. Since the two IIO sources can lose different buffers,
an overrun can preserve each radio's internal RX1/RX2 phase while destroying
Alpha-vs-Bravo coherence. CFO and phase calibration results from a run containing
overruns must not be trusted; reduce display/host load or the configured sample
rate and restart until the run is overrun-free.

### Source-only overflow test

Use `diagnose_libresdr_iio_overflow.grc` before changing CFO or calibration
thresholds when the live graph prints `O`. It uses the same two IIO addresses,
two channels per radio, `525 kS/s` sample rate, and `262144`-sample IIO buffers,
but contains no CFO, calibration, MUSIC, or GUI blocks. Four Head blocks feed a
rate probe and Null Sink, so the test prints the measured Alpha RX1 stream rate
every two seconds and stops automatically after 20 seconds.

1. Stop every other receiver flowgraph using either LibreSDR.
2. Open `diagnose_libresdr_iio_overflow.grc` in GNU Radio Companion.
3. Generate and run it without changing the wiring.
4. Confirm that the periodic `Alpha RX1 source-only rate` messages are close to
   `525e3` samples/second, then check the complete 20-second console output:
   - no `O`: raw four-channel acquisition is sustainable; the added processing
     in the live graph is causing the overruns;
   - any `O`: the failure already exists in the IIO/device/transport path and
     must be fixed before CFO or phase calibration can be trusted.

The buffer-allocation alignment warning is unrelated and can be ignored for
this test.

If the source-only test completes without any `O`, run the next-stage
`diagnose_libresdr_cfo_calibration_load.py` directly from a terminal. This
20-second graph retains the live CFO corrector, four pilot filters, and gated
phase calibration, but replaces MUSIC and every GUI branch with a four-input
Null Sink. It waits five seconds after the IIO sources start before taking its
first CFO window so RF/PLL startup drift is not mistaken for a stable offset:

```sh
python3 -u apps/LibreSDR-UCA/diagnose_libresdr_cfo_calibration_load.py \
  2>&1 | tee /tmp/libresdr_cfo_calibration_load.txt
```

- no `O` and `UCA calibration complete`: CFO/calibration processing is
  sustainable, so the downstream MUSIC/diagnostic workload causes the live
  graph overruns;
- any `O`: the load or blocking operation is already present in the
  CFO/filter/calibration path and must be optimized before restoring MUSIC;
- a calibration failure followed by a successful automatic retry is acceptable;
  repeated failures without `UCA calibration complete` mean the pilot is not
  coherent enough for direction finding;
- repeated CFO rejection without `O`: investigate pilot stability/content
  rather than host throughput.

This diagnostic writes any accepted coefficients only to
`/tmp/gr-doa-uca-phase-offsets-load-diagnostic.cfg`, never the live calibration
file.

The covariance estimator and MUSIC eigendecomposition remain based on the Ettus
architecture. The intentional changes are the UCA geometry, full-circle scan,
physical channel order, frequency-derived manifold, narrow pilot selection, and
same-session CFO/phase correction.
