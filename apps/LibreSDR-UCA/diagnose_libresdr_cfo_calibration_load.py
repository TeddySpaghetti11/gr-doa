#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: LibreSDR CFO and Calibration Load Diagnostic
# Author: gr-doa LibreSDR research port
# Copyright: None
# Description: Runs the two LibreSDR sources through only cross-SDR CFO correction, pilot filtering, and UCA phase calibration. MUSIC and every GUI diagnostic are excluded, and all four calibrated outputs terminate in a Null Sink.
# GNU Radio version: v3.11.0.0git-1103-g14d6a758

from gnuradio import blocks
from gnuradio import doa
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import iio
import threading
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation




class diagnose_libresdr_cfo_calibration_load(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "LibreSDR CFO and Calibration Load Diagnostic", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.pilot_offset = pilot_offset = 50e3
        self.center_freq = center_freq = int(920.9e6)
        self.pilot_rf = pilot_rf = center_freq + pilot_offset
        self.array_radius = array_radius = 0.16263 / (2**0.5)
        self.test_seconds = test_seconds = 20
        self.samp_rate = samp_rate = int(2.1e6)
        self.rx_gain = rx_gain = 40
        self.rf_bandwidth = rf_bandwidth = int(2.8e6)
        self.pilot_transition = pilot_transition = 10e3
        self.pilot_passband = pilot_passband = 10e3
        self.pilot_decim = pilot_decim = 8
        self.pilot_bearing = pilot_bearing = 0
        self.num_elements = num_elements = 4
        self.norm_radius = norm_radius = array_radius * pilot_rf / 299792458.0
        self.element_bearing_step = element_bearing_step = -90.0
        self.element0_bearing = element0_bearing = 225.0
        self.cfo_validation_settling_samples = cfo_validation_settling_samples = 2**16
        self.cfo_settling_samples = cfo_settling_samples = 2**16
        self.cfo_retry_delay_samples = cfo_retry_delay_samples = 2**20
        self.cfo_residual_tolerance_hz = cfo_residual_tolerance_hz = 1.0
        self.cfo_min_coherence = cfo_min_coherence = 0.90
        self.cfo_max_refinement_rounds = cfo_max_refinement_rounds = 3
        self.cfo_max_abs_hz = cfo_max_abs_hz = 20000.0
        self.cfo_estimation_samples = cfo_estimation_samples = 2**18
        self.cfo_agreement_tolerance_hz = cfo_agreement_tolerance_hz = 10.0
        self.calibration_skip = calibration_skip = 2**14
        self.calibration_samples = calibration_samples = 2**16
        self.calibration_file = calibration_file = "/tmp/gr-doa-uca-phase-offsets-load-diagnostic.cfg"

        ##################################################
        # Blocks
        ##################################################

        self.pilot_filter_3 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_2 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_1 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_0 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.ota_calibration = doa.uca_pilot_calibration(
            num_inputs=num_elements,
            norm_radius=norm_radius,
            pilot_angle=pilot_bearing,
            element0_angle=element0_bearing,
            element_angle_step=element_bearing_step,
            skip_samples=calibration_skip,
            calibration_samples=calibration_samples,
            config_filename=calibration_file,
            min_coherence=0.90,
            start_tag_key='cfo_locked')
        self.libresdr_b = iio.fmcomms2_source_fc32('ip:192.168.5.1', [True, True, True, True], 262144)
        self.libresdr_b.set_len_tag_key('packet_len')
        self.libresdr_b.set_frequency(center_freq)
        self.libresdr_b.set_samplerate(samp_rate)
        if True:
            self.libresdr_b.set_gain_mode(0, 'manual')
            self.libresdr_b.set_gain(0, rx_gain)
        if True:
            self.libresdr_b.set_gain_mode(1, 'manual')
            self.libresdr_b.set_gain(1, rx_gain)
        self.libresdr_b.set_quadrature(False)
        self.libresdr_b.set_rfdc(True)
        self.libresdr_b.set_bbdc(True)
        self.libresdr_b.set_filter_params('Auto', '', 0, 0)
        self.libresdr_a = iio.fmcomms2_source_fc32('ip:192.168.4.1', [True, True, True, True], 262144)
        self.libresdr_a.set_len_tag_key('packet_len')
        self.libresdr_a.set_frequency(center_freq)
        self.libresdr_a.set_samplerate(samp_rate)
        if True:
            self.libresdr_a.set_gain_mode(0, 'manual')
            self.libresdr_a.set_gain(0, rx_gain)
        if True:
            self.libresdr_a.set_gain_mode(1, 'manual')
            self.libresdr_a.set_gain(1, rx_gain)
        self.libresdr_a.set_quadrature(False)
        self.libresdr_a.set_rfdc(True)
        self.libresdr_a.set_bbdc(True)
        self.libresdr_a.set_filter_params('Auto', '', 0, 0)
        self.cfo_correction = doa.cross_sdr_cfo_corrector(
            samp_rate=samp_rate,
            pilot_offset_hz=pilot_offset,
            pilot_bandwidth_hz=pilot_passband,
            settling_samples=cfo_settling_samples,
            estimation_samples=cfo_estimation_samples,
            validation_settling_samples=cfo_validation_settling_samples,
            residual_tolerance_hz=cfo_residual_tolerance_hz,
            max_refinement_rounds=cfo_max_refinement_rounds,
            retry_delay_samples=cfo_retry_delay_samples,
            agreement_tolerance_hz=cfo_agreement_tolerance_hz,
            max_abs_cfo_hz=cfo_max_abs_hz,
            min_coherence=cfo_min_coherence)
        self.calibrated_sink = blocks.null_sink(gr.sizeof_gr_complex*1)
        self.bravo_rx2_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))
        self.bravo_rx1_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))
        self.alpha_rx2_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))
        self.alpha_rx1_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))


        ##################################################
        # Connections
        ##################################################
        self.connect((self.alpha_rx1_head, 0), (self.cfo_correction, 0))
        self.connect((self.alpha_rx2_head, 0), (self.cfo_correction, 1))
        self.connect((self.bravo_rx1_head, 0), (self.cfo_correction, 3))
        self.connect((self.bravo_rx2_head, 0), (self.cfo_correction, 2))
        self.connect((self.cfo_correction, 0), (self.pilot_filter_0, 0))
        self.connect((self.cfo_correction, 1), (self.pilot_filter_1, 0))
        self.connect((self.cfo_correction, 2), (self.pilot_filter_2, 0))
        self.connect((self.cfo_correction, 3), (self.pilot_filter_3, 0))
        self.connect((self.libresdr_a, 0), (self.alpha_rx1_head, 0))
        self.connect((self.libresdr_a, 1), (self.alpha_rx2_head, 0))
        self.connect((self.libresdr_b, 0), (self.bravo_rx1_head, 0))
        self.connect((self.libresdr_b, 1), (self.bravo_rx2_head, 0))
        self.connect((self.ota_calibration, 1), (self.calibrated_sink, 1))
        self.connect((self.ota_calibration, 2), (self.calibrated_sink, 2))
        self.connect((self.ota_calibration, 0), (self.calibrated_sink, 0))
        self.connect((self.ota_calibration, 3), (self.calibrated_sink, 3))
        self.connect((self.pilot_filter_0, 0), (self.ota_calibration, 0))
        self.connect((self.pilot_filter_1, 0), (self.ota_calibration, 1))
        self.connect((self.pilot_filter_2, 0), (self.ota_calibration, 2))
        self.connect((self.pilot_filter_3, 0), (self.ota_calibration, 3))


    def get_pilot_offset(self):
        return self.pilot_offset

    def set_pilot_offset(self, pilot_offset):
        self.pilot_offset = pilot_offset
        self.set_pilot_rf(self.center_freq + self.pilot_offset)
        self.pilot_filter_0.set_center_freq(self.pilot_offset)
        self.pilot_filter_1.set_center_freq(self.pilot_offset)
        self.pilot_filter_2.set_center_freq(self.pilot_offset)
        self.pilot_filter_3.set_center_freq(self.pilot_offset)

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.set_pilot_rf(self.center_freq + self.pilot_offset)
        self.libresdr_a.set_frequency(self.center_freq)
        self.libresdr_b.set_frequency(self.center_freq)

    def get_pilot_rf(self):
        return self.pilot_rf

    def set_pilot_rf(self, pilot_rf):
        self.pilot_rf = pilot_rf
        self.set_norm_radius(self.array_radius * self.pilot_rf / 299792458.0)

    def get_array_radius(self):
        return self.array_radius

    def set_array_radius(self, array_radius):
        self.array_radius = array_radius
        self.set_norm_radius(self.array_radius * self.pilot_rf / 299792458.0)

    def get_test_seconds(self):
        return self.test_seconds

    def set_test_seconds(self, test_seconds):
        self.test_seconds = test_seconds
        self.alpha_rx1_head.set_length((int(self.test_seconds * self.samp_rate)))
        self.alpha_rx2_head.set_length((int(self.test_seconds * self.samp_rate)))
        self.bravo_rx1_head.set_length((int(self.test_seconds * self.samp_rate)))
        self.bravo_rx2_head.set_length((int(self.test_seconds * self.samp_rate)))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.libresdr_a.set_samplerate(self.samp_rate)
        self.libresdr_b.set_samplerate(self.samp_rate)
        self.alpha_rx1_head.set_length((int(self.test_seconds * self.samp_rate)))
        self.alpha_rx2_head.set_length((int(self.test_seconds * self.samp_rate)))
        self.bravo_rx1_head.set_length((int(self.test_seconds * self.samp_rate)))
        self.bravo_rx2_head.set_length((int(self.test_seconds * self.samp_rate)))
        self.pilot_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))

    def get_rx_gain(self):
        return self.rx_gain

    def set_rx_gain(self, rx_gain):
        self.rx_gain = rx_gain
        self.libresdr_a.set_gain(0, self.rx_gain)
        self.libresdr_a.set_gain(1, self.rx_gain)
        self.libresdr_b.set_gain(0, self.rx_gain)
        self.libresdr_b.set_gain(1, self.rx_gain)

    def get_rf_bandwidth(self):
        return self.rf_bandwidth

    def set_rf_bandwidth(self, rf_bandwidth):
        self.rf_bandwidth = rf_bandwidth

    def get_pilot_transition(self):
        return self.pilot_transition

    def set_pilot_transition(self, pilot_transition):
        self.pilot_transition = pilot_transition
        self.pilot_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))

    def get_pilot_passband(self):
        return self.pilot_passband

    def set_pilot_passband(self, pilot_passband):
        self.pilot_passband = pilot_passband
        self.pilot_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))

    def get_pilot_decim(self):
        return self.pilot_decim

    def set_pilot_decim(self, pilot_decim):
        self.pilot_decim = pilot_decim

    def get_pilot_bearing(self):
        return self.pilot_bearing

    def set_pilot_bearing(self, pilot_bearing):
        self.pilot_bearing = pilot_bearing

    def get_num_elements(self):
        return self.num_elements

    def set_num_elements(self, num_elements):
        self.num_elements = num_elements

    def get_norm_radius(self):
        return self.norm_radius

    def set_norm_radius(self, norm_radius):
        self.norm_radius = norm_radius

    def get_element_bearing_step(self):
        return self.element_bearing_step

    def set_element_bearing_step(self, element_bearing_step):
        self.element_bearing_step = element_bearing_step

    def get_element0_bearing(self):
        return self.element0_bearing

    def set_element0_bearing(self, element0_bearing):
        self.element0_bearing = element0_bearing

    def get_cfo_validation_settling_samples(self):
        return self.cfo_validation_settling_samples

    def set_cfo_validation_settling_samples(self, cfo_validation_settling_samples):
        self.cfo_validation_settling_samples = cfo_validation_settling_samples

    def get_cfo_settling_samples(self):
        return self.cfo_settling_samples

    def set_cfo_settling_samples(self, cfo_settling_samples):
        self.cfo_settling_samples = cfo_settling_samples

    def get_cfo_retry_delay_samples(self):
        return self.cfo_retry_delay_samples

    def set_cfo_retry_delay_samples(self, cfo_retry_delay_samples):
        self.cfo_retry_delay_samples = cfo_retry_delay_samples

    def get_cfo_residual_tolerance_hz(self):
        return self.cfo_residual_tolerance_hz

    def set_cfo_residual_tolerance_hz(self, cfo_residual_tolerance_hz):
        self.cfo_residual_tolerance_hz = cfo_residual_tolerance_hz

    def get_cfo_min_coherence(self):
        return self.cfo_min_coherence

    def set_cfo_min_coherence(self, cfo_min_coherence):
        self.cfo_min_coherence = cfo_min_coherence

    def get_cfo_max_refinement_rounds(self):
        return self.cfo_max_refinement_rounds

    def set_cfo_max_refinement_rounds(self, cfo_max_refinement_rounds):
        self.cfo_max_refinement_rounds = cfo_max_refinement_rounds

    def get_cfo_max_abs_hz(self):
        return self.cfo_max_abs_hz

    def set_cfo_max_abs_hz(self, cfo_max_abs_hz):
        self.cfo_max_abs_hz = cfo_max_abs_hz

    def get_cfo_estimation_samples(self):
        return self.cfo_estimation_samples

    def set_cfo_estimation_samples(self, cfo_estimation_samples):
        self.cfo_estimation_samples = cfo_estimation_samples

    def get_cfo_agreement_tolerance_hz(self):
        return self.cfo_agreement_tolerance_hz

    def set_cfo_agreement_tolerance_hz(self, cfo_agreement_tolerance_hz):
        self.cfo_agreement_tolerance_hz = cfo_agreement_tolerance_hz

    def get_calibration_skip(self):
        return self.calibration_skip

    def set_calibration_skip(self, calibration_skip):
        self.calibration_skip = calibration_skip

    def get_calibration_samples(self):
        return self.calibration_samples

    def set_calibration_samples(self, calibration_samples):
        self.calibration_samples = calibration_samples

    def get_calibration_file(self):
        return self.calibration_file

    def set_calibration_file(self, calibration_file):
        self.calibration_file = calibration_file




def main(top_block_cls=diagnose_libresdr_cfo_calibration_load, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    tb.wait()


if __name__ == '__main__':
    main()
