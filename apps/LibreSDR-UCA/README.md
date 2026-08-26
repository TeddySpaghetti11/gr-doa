# LibreSDR UCA MUSIC

This directory contains the four-channel LibreSDR flowgraph for the 903 MHz
uniform circular array. It is separate from the Ettus X440/linear-array examples
so the upstream demonstrations remain useful as references.

## Geometry and channel order

The supplied defaults assume:

- four UCA elements;
- 162.63 mm adjacent chord spacing;
- 903 MHz center frequency;
- 114.997 mm circle radius, or `0.346379923` wavelengths;
- `192.168.4.1` RX1/RX2 are elements 0/1;
- `192.168.5.1` RX1/RX2 are elements 2/3;
- element indices advance by +90 degrees around the circle.

Set `element0_bearing` to the physical bearing from the array center toward
element 0. If the numbered elements run in the opposite direction, change
`element_bearing_step` from `90.0` to `-90.0`. All pilot and MUSIC bearings use
this same coordinate system.

## Build and install

After changing the OOT module, rebuild and reinstall it before opening the new
flowgraph in GNU Radio Companion:

```sh
cmake -S . -B build
cmake --build build -j$(nproc)
ctest --test-dir build -R 'qa_(MUSIC_uca|uca_pilot_calibration)' --output-on-failure
sudo cmake --install build
sudo ldconfig
```

The original Ettus QA tests additionally need `oct2py` and Octave. The new
`qa_MUSIC_uca` and `qa_uca_pilot_calibration` tests do not.

The GNU Radio 3.10 FMComms2/3/4 source template installed on the development
machine accepts an RF-bandwidth field in GRC but does not emit a corresponding
runtime setter in the generated Python. The flowgraph therefore requests
`2.8 MHz`, but do not assume that value was applied: inspect the live AD9361
`rf_bandwidth` IIO attribute (or set it outside this source block) when exact
analogue bandwidth is important to a measurement.

## Measurement procedure

1. Set `pilot_bearing` in `run_MUSIC_uca_live_cal.grc` to the measured bearing
   of the B210 from the array center.
2. Confirm the element-to-channel order above and use the same manual gain on
   all four receiver channels.
3. Start the B210 calibration tone with
   `../Narrowband-Flowgraphs/phase_offset_measurement_correction/run_DoA_transmitter.grc`.
   Its active UHD path is configured for a 903 MHz center and +5 kHz tone;
   confirm that `TxAddr` contains your B210's serial number.
4. Start `run_MUSIC_uca_live_cal.grc` and watch its console. The output remains
   zero while the two sources settle and pilot samples are accumulated.
5. Wait for `UCA calibration complete`. The block prints the measured pairwise
   phase, predicted geometric phase, and frozen hardware-phase correction for
   every channel relative to channel 0.
6. Switch off the B210 transmitter without stopping the receiver flowgraph.
7. Activate the target transmitter. The GUI shows the calibrated channel traces,
   full 0–360 degree MUSIC spectrum, and estimated bearing.

Do not restart or retune either LibreSDR between steps 5 and 7. With the current
firmware, a new start or retune can change inter-device timing or RF phase and
therefore requires a new OTA calibration.

## Limitations

The pilot block performs a unit-magnitude phase correction at the pilot
frequency, matching Ettus's relative phase-correction stage; it deliberately
does not equalize channel amplitudes. This is appropriate for narrowband MUSIC
near that frequency, but it is not a wideband sample synchronizer. A wideband or
frequency-separated target requires
coarse/fractional delay estimation using a known broadband calibration waveform.
For the first validation runs, place the target signal at the same RF/baseband
frequency as the calibration pilot.

The receiver flowgraph intentionally does not depend on 1 PPS. Same-session OTA
calibration absorbs a fixed start offset at the pilot frequency, but it cannot
repair a sample discontinuity or relative drift that occurs after calibration.

Indoor multipath also affects OTA calibration. Keep the B210 in the far field
with a clear line of sight where practical, and repeat measurements at several
known bearings to validate the assumed UCA manifold and bearing convention.

## Equations

For element position angle `beta_m`, normalized radius `rho = r/lambda`, and
bearing `theta`, calibration and MUSIC both use

```text
a_m(theta) = exp(-j 2 pi rho cos(theta - beta_m)).
```

For channel `i` relative to channel 0, the calibration block forms the circular
mean phase ratio `q_i = unit(sum(x_0 conj(x_i)))`. Its predicted geometric ratio
is `g_i = a_0(theta_cal) conj(a_i(theta_cal))`. The unit-magnitude correction is

```text
c_i = unit(q_i / g_i) = exp(j (phi_hardware,0 - phi_hardware,i)).
```

Applying `c_i x_i` removes only the relative hardware/channel phase. The UCA
manifold phase `a_i(theta_cal)` remains in the corrected signal.
