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
stationary pilot should be close to 1; the block prints a warning below `0.90`.
For validation, values around `0.98-1.00` are preferable.

If the same-radio channel is highly coherent but channels from the other
LibreSDR are not, investigate inter-device timing/coherence before interpreting
the MUSIC result.

The existing Phase Offset Est plots remain Ettus's instantaneous
`arg(x0*conj(xi))` diagnostics. The averaged calibration phase and coherence
printed in the console are more reliable indicators for a stationary CW pilot.

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

## Test procedure

1. Confirm the physical channel order above.
2. Set `pilot_bearing` to the actual B210 bearing for the current setup.
3. Start the B210 calibration transmitter.
4. Start `run_MUSIC_uca_live_cal.grc`.
5. Wait for `UCA calibration complete` and inspect all three coherence values.
6. Keep the source stationary and verify the MUSIC spectrum has clear structure.
7. Rotate through several known off-axis bearings and compare the peak movement.
8. Do not retune, restart, or power-cycle either LibreSDR without recalibrating.

The covariance estimator and MUSIC eigendecomposition remain based on the Ettus
architecture. The intentional changes are the UCA geometry, full-circle scan,
physical channel order, frequency-derived manifold, narrow pilot selection, and
same-session phase correction.
