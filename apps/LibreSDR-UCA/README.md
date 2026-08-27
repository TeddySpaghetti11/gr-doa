# LibreSDR UCA MUSIC

This directory contains the four-channel LibreSDR uniform circular array (UCA)
flowgraph and same-session over-the-air phase calibration.

## Geometry and channel order

The physical array uses four elements with `162.63 mm` adjacent chord spacing,
which gives a radius of `114.997 mm`.

Stream order is fixed as:

1. `192.168.4.1 RX1` - bottom-right - `225 deg`
2. `192.168.4.1 RX2` - bottom-left - `135 deg`
3. `192.168.5.1 RX2` - top-left - `45 deg`
4. `192.168.5.1 RX1` - top-right - `315 deg`

The second LibreSDR is intentionally permuted in the flowgraph so the element
step is `-90 deg`.

Angles are **source bearings**, measured from the array centre towards the
transmitter. Calibration and MUSIC use the same manifold:

```text
a_m(theta) = exp(+j 2 pi rho cos(theta - beta_m))
```

where `rho = r/lambda`.

## Frequency-derived normalized radius

`norm_radius` is no longer hard-coded. The flowgraph calculates it from the
actual pilot RF frequency:

```text
array_radius = 0.16263 / sqrt(2)
pilot_rf = center_freq + pilot_offset
norm_radius = array_radius * pilot_rf / 299792458.0
```

With the current defaults (`center_freq = 920.9 MHz`, `pilot_offset = +50 kHz`),
the processed RF is `920.95 MHz` and `norm_radius` is about `0.3532653`.

Note that `162.63 mm` equals exactly half a wavelength at about `921.70 MHz`.
The present test frequency is therefore extremely close to half-wavelength
adjacent spacing. A strong 180-degree ambiguity can still occur on array
symmetry axes even when the processing is correct. Validate at several off-axis
bearings rather than using only `0/90/180/270 deg`.

## Pilot filtering

The B210 pilot is now `+50 kHz` from the receiver centre instead of `+5 kHz`.
Each of the four receiver channels passes through an identical Frequency Xlating
FIR Filter before calibration and covariance formation:

```text
pilot_offset     = 50 kHz
pilot_decim      = 8
pilot_passband   = 10 kHz
pilot_transition = 10 kHz
proc_rate        = 350 kS/s
```

After translation the desired pilot is at DC, receiver DC is at `-50 kHz`, and
the pilot image is around `-100 kHz`, so the narrow low-pass rejects both.

The B210 transmitter flowgraph uses the same `920.9 MHz` centre and `+50 kHz`
tone by default. Keep those values matched to the receiver variables if you
retune.

## Automatic cross-SDR CFO correction

The two raw IIO sources first enter `Cross-SDR CFO Corrector` in fixed physical
order: Alpha RX1, Alpha RX2, Bravo RX2, Bravo RX1. The block leaves Alpha
bit-for-bit unchanged. A streaming complex mixer and fourth-order low-pass
filter isolate `pilot_offset` with `pilot_passband` bandwidth before estimating
Bravo-minus-Alpha CFO independently from Bravo RX2/Alpha RX1 and Bravo
RX1/Alpha RX1. This prevents the other strong tones visible in the raw spectrum
from biasing the OTA-pilot estimate. Both estimates must pass the configured
magnitude and phase-coherence checks and agree within `10 Hz`.

Accepted estimates are averaged once. One phase-continuous complex rotator with
the opposite frequency is then applied identically to both Bravo channels, so
Bravo's internal channel coherence is preserved. The rotator begins with zero
phase and therefore leaves all constant phase offsets for the existing OTA phase
calibration.

Defaults at `2.8 MS/s` are `2**16` startup-settling samples, a `2**18`-sample
estimation window, maximum `20 kHz` absolute CFO, and minimum `0.90` pilot-fit
coherence. The accepted coarse estimate is applied provisionally to both Bravo
channels. After another `2**16` settling samples, the block measures both
post-correction residual slopes over another `2**18` samples. It refines the
one common correction up to three times and freezes only when the averaged
residual is at most `1 Hz`. The final measured residual is included in the
frozen correction even when already inside that bound. Phase remains continuous
when the correction frequency is refined.

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
waits `2**20` samples, and retries automatically. No `cfo_locked` tag is emitted
until the post-correction residual passes every check. The downstream phase
calibration waits for that tag before counting its own skip or calibration
samples.

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
   `samp_rate` (`2.8 MS/s`).
2. **POST-CFO relative phase** is after the common CFO rotator and four identical
   translating/decimating FIR filters, but before constant phase calibration. It
   runs at `proc_rate` (`350 kS/s`) and should be flat after CFO lock.
3. **Alpha internal** and **Bravo internal** plots compare RX1 with RX2 inside
   each LibreSDR before filtering. A flat same-radio trace with moving
   inter-radio traces isolates the problem to coherence between the devices.

All phase displays use the Ettus convention `arg(x0 * conj(xi))`; their labels
name both physical inputs to avoid an ambiguous channel number.

The raw four-channel FFT remains connected before the CFO block and all filters in physical UCA
order. It uses the QT sink's maximum valid size of 32,768 bins (about
`85.4 Hz/bin` at `2.8 MS/s`) and explicit channel labels so a small frequency
difference between the two radios can be seen directly. This raw display is
expected to retain the original Alpha/Bravo separation. A second 8,192-bin
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

On failure the console prints `UCA CALIBRATION FAILED`, no coefficient file is
written, and the block switches to unity/bypass output. This keeps downstream
plots alive with explicitly uncalibrated samples and prevents an invalid phase
estimate from being frozen or described as successful. Do not trust the MUSIC
bearing until the flowgraph is restarted and all channels pass calibration.

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
ctest --test-dir build -R 'qa_(MUSIC_uca|cross_sdr_cfo_corrector|uca_pilot_calibration)' --output-on-failure
sudo cmake --install build
sudo ldconfig
```

The UCA tests now exercise the real `225, 135, 45, 315 deg` stream order and the
source-bearing steering convention.

After installation, start the B210 `+50 kHz` pilot using its existing gain
setting, then run the checked-in Python equivalent:

```sh
python3 apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.py
```

Alternatively, open `apps/LibreSDR-UCA/run_MUSIC_uca_live_cal.grc` in GNU Radio
Companion and run it there. The Python and GRC versions use the same channel
order, diagnostics, and calibration threshold.

## Test procedure

1. Confirm the physical channel order above.
2. Set `pilot_bearing` to the actual B210 bearing for the current setup.
3. Start the B210 calibration transmitter.
4. Start `run_MUSIC_uca_live_cal.grc` (or the generated Python equivalent).
5. The console must print `Cross-SDR CFO lock established`. A rejection now
   retries automatically; repeated rejection or `O` overruns means the stream or
   pilot must be fixed before calibration can begin.
6. Compare TRUE pre-filter, POST-CFO, Alpha-internal, and Bravo-internal phase.
7. The raw FFT may show the original radio-specific shift; verify all four peaks
   coincide in `POST-CFO filtered pilot spectra`.
8. Wait for `UCA calibration complete` and inspect all three coherence values. If
   `UCA CALIBRATION FAILED` appears, treat the output as uncalibrated bypass data.
9. Keep the source stationary and verify the MUSIC spectrum has clear structure.
10. Rotate through several known off-axis bearings and compare the peak movement.
11. Do not retune, restart, or power-cycle either LibreSDR without recalibrating.

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
two channels per radio, `2.1 MS/s` sample rate, and `262144`-sample IIO buffers,
but contains no CFO, calibration, MUSIC, or GUI blocks. Four Head blocks feed a
rate probe and Null Sink, so the test prints the measured Alpha RX1 stream rate
every two seconds and stops automatically after 20 seconds.

1. Stop every other receiver flowgraph using either LibreSDR.
2. Open `diagnose_libresdr_iio_overflow.grc` in GNU Radio Companion.
3. Generate and run it without changing the wiring.
4. Confirm that the periodic `Alpha RX1 source-only rate` messages are close to
   `2.1e6` samples/second, then check the complete 20-second console output:
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
- any `O`, or calibration failure after a valid CFO lock: the load or blocking
  operation is already present in the CFO/filter/calibration path and must be
  optimized before restoring MUSIC;
- repeated CFO rejection without `O`: investigate pilot stability/content
  rather than host throughput.

This diagnostic writes any accepted coefficients only to
`/tmp/gr-doa-uca-phase-offsets-load-diagnostic.cfg`, never the live calibration
file.

The covariance estimator and MUSIC eigendecomposition remain based on the Ettus
architecture. The intentional changes are the UCA geometry, full-circle scan,
physical channel order, frequency-derived manifold, narrow pilot selection, and
same-session CFO/phase correction.
