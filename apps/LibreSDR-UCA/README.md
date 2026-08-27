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
2. **POST-FILTER relative phase** is the original diagnostic after the four
   independent translating/decimating FIR filters and before calibration. It
   runs at `proc_rate` (`350 kS/s`).
3. **Alpha internal** and **Bravo internal** plots compare RX1 with RX2 inside
   each LibreSDR before filtering. A flat same-radio trace with moving
   inter-radio traces isolates the problem to coherence between the devices.

All phase displays use the Ettus convention `arg(x0 * conj(xi))`; their labels
name both physical inputs to avoid an ambiguous channel number.

The raw four-channel FFT is also connected before all filters in physical UCA
order. It uses the QT sink's maximum valid size of 32,768 bins (about
`85.4 Hz/bin` at `2.8 MS/s`) and explicit channel labels so a small frequency
difference between the two radios can be seen directly. GNU Radio 3.11 rejects
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
ctest --test-dir build -R 'qa_(MUSIC_uca|uca_pilot_calibration)' --output-on-failure
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
5. Compare TRUE pre-filter, POST-FILTER, Alpha-internal, and Bravo-internal phase.
6. Inspect the 32,768-bin raw FFT for a channel- or radio-specific frequency shift.
7. Wait for `UCA calibration complete` and inspect all three coherence values. If
   `UCA CALIBRATION FAILED` appears, treat the output as uncalibrated bypass data.
8. Keep the source stationary and verify the MUSIC spectrum has clear structure.
9. Rotate through several known off-axis bearings and compare the peak movement.
10. Do not retune, restart, or power-cycle either LibreSDR without recalibrating.

The covariance estimator and MUSIC eigendecomposition remain based on the Ettus
architecture. The intentional changes are the UCA geometry, full-circle scan,
physical channel order, frequency-derived manifold, narrow pilot selection, and
same-session phase correction.
