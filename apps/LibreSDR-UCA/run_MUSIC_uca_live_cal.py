#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: LibreSDR UCA MUSIC - Live OTA Calibration
# Author: gr-doa LibreSDR research port
# Copyright: None
# Description: Continuously tracked +140 kHz calibration pilot and independently filtered +150 kHz target for live direction finding.
# GNU Radio version: v3.11.0.0git-1103-g14d6a758

from gnuradio import qtgui
from PyQt5 import Qt
from gnuradio import blocks
from gnuradio import doa
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import iio
import sip
import threading
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation



def snipfcn_pps_sync_before_start(self):
    doa.arm_libresdr_pps_sync(('ip:192.168.4.1', 'ip:192.168.5.1'))


def snippets_main_after_init(tb):
    snipfcn_pps_sync_before_start(tb)

class run_MUSIC_uca_live_cal(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "LibreSDR UCA MUSIC - Live OTA Calibration", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("LibreSDR UCA MUSIC - Live OTA Calibration")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("gnuradio/flowgraphs", "run_MUSIC_uca_live_cal")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)
        self.flowgraph_started = threading.Event()

        ##################################################
        # Variables
        ##################################################
        self.target_offset = target_offset = 150e3
        self.pilot_offset = pilot_offset = 140e3
        self.center_freq = center_freq = int(700e6)
        self.target_rf = target_rf = center_freq + target_offset
        self.samp_rate = samp_rate = int(525e3)
        self.pilot_rf = pilot_rf = center_freq + pilot_offset
        self.pilot_decim = pilot_decim = 2
        self.array_radius = array_radius = 0.16263 / (2**0.5)
        self.target_norm_radius = target_norm_radius = array_radius * target_rf / 299792458.0
        self.target_calibration_bearing = target_calibration_bearing = 345.0
        self.snapshot_size = snapshot_size = 2**11
        self.rx_gain = rx_gain = 40
        self.rf_bandwidth = rf_bandwidth = int(2.8e6)
        self.pspectrum_len = pspectrum_len = 360
        self.proc_rate = proc_rate = samp_rate / pilot_decim
        self.pilot_transition = pilot_transition = 2e3
        self.pilot_passband = pilot_passband = 2e3
        self.pilot_bearing = pilot_bearing = 180
        self.overlap_size = overlap_size = 0
        self.num_targets = num_targets = 1
        self.num_elements = num_elements = 4
        self.norm_radius = norm_radius = array_radius * pilot_rf / 299792458.0
        self.element_bearing_step = element_bearing_step = 90.0
        self.element0_bearing = element0_bearing = 315.0
        self.cfo_validation_settling_samples = cfo_validation_settling_samples = 2**12
        self.cfo_settling_samples = cfo_settling_samples = int(5 * samp_rate)
        self.cfo_retry_delay_samples = cfo_retry_delay_samples = 2**16
        self.cfo_residual_tolerance_hz = cfo_residual_tolerance_hz = 1.0
        self.cfo_min_coherence = cfo_min_coherence = 0.90
        self.cfo_max_refinement_rounds = cfo_max_refinement_rounds = 3
        self.cfo_max_abs_hz = cfo_max_abs_hz = 20000.0
        self.cfo_estimation_samples = cfo_estimation_samples = 2**16
        self.cfo_agreement_tolerance_hz = cfo_agreement_tolerance_hz = 10.0
        self.calibration_skip = calibration_skip = 2**11
        self.calibration_samples = calibration_samples = 2**12
        self.calibration_file = calibration_file = "/tmp/gr-doa-uca-phase-offsets.cfg"

        ##################################################
        # Blocks
        ##################################################

        self.target_output_decimator = blocks.keep_one_in_n(gr.sizeof_gr_complex*4, 4)
        self.target_filter_3 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), target_offset, samp_rate)
        self.target_filter_2 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), target_offset, samp_rate)
        self.target_filter_1 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), target_offset, samp_rate)
        self.target_filter_0 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), target_offset, samp_rate)
        self.target_aligned_vectorizer = blocks.streams_to_vector(gr.sizeof_gr_complex*1, 4)
        self.target_aligned_streams = blocks.vector_to_streams(gr.sizeof_gr_complex*1, 4)
        self.qtgui_compass_0 = self._qtgui_compass_0_win = qtgui.GrCompass('', 250, 0.10, False, 1,False,1,"default")
        self._qtgui_compass_0_win.setColors("default","red", "black", "black")
        self._qtgui_compass_0 = self._qtgui_compass_0_win
        self.top_layout.addWidget(self._qtgui_compass_0_win)
        self.pilot_output_decimator = blocks.keep_one_in_n(gr.sizeof_gr_complex*4, 4)
        self.pilot_filter_3 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_2 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_1 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_0 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_aligned_vectorizer = blocks.streams_to_vector(gr.sizeof_gr_complex*1, 4)
        self.pilot_aligned_discard = blocks.null_sink(gr.sizeof_gr_complex*4)
        self.peak_magnitude_discard = blocks.null_sink(gr.sizeof_float*num_targets)
        self.peak_finder = doa.find_local_max(num_targets, pspectrum_len, 0.0, 360.0)
        self.ota_calibration = doa.uca_pilot_calibration(
            num_inputs=num_elements,
            norm_radius=target_norm_radius,
            pilot_angle=target_calibration_bearing,
            element0_angle=element0_bearing,
            element_angle_step=element_bearing_step,
            skip_samples=calibration_skip,
            calibration_samples=calibration_samples,
            config_filename=calibration_file,
            min_coherence=0.97,
            start_tag_key='cfo_locked',
            separate_data_inputs=True,
            retry_on_failure=True)
        self.ota_calibration.set_min_output_buffer(65536)
        self.music_uca = doa.MUSIC_uca(target_norm_radius, num_targets, num_elements, pspectrum_len, element0_bearing, element_bearing_step)
        self.libresdr_b = iio.fmcomms2_source_fc32('ip:192.168.5.1', [True, True, True, True], 1048576)
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
        self.libresdr_a = iio.fmcomms2_source_fc32('ip:192.168.4.1', [True, True, True, True], 1048576)
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
        self.direct_phase_correction = doa.cross_sdr_pilot_phase_corrector(
            settling_samples=(int(5 * proc_rate)),
            acquisition_samples=8192,
            min_coherence=0.95,
            max_differential_phase_rad=0.35,
            min_valid_fraction=0.90,
            max_alignment_lag=256,
            phase_smoothing_samples=64)
        self.covariance = doa.autocorrelate(num_elements, snapshot_size, overlap_size, 0, 'calibration_valid', 'calibration_invalid', 'doa_valid')
        self.bearing_validity = doa.bearing_validity_gate(num_targets, 'doa_valid')
        self.bearing_streams = blocks.vector_to_streams(gr.sizeof_float*1, num_targets)
        self.bearing_display = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.bearing_display.set_update_time(0.10)
        self.bearing_display.set_title("UCA MUSIC bearing")

        labels = ['Estimated bearing', '', '', '', '',
            '', '', '', '', '']
        units = ['degrees', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.bearing_display.set_min(i, 0)
            self.bearing_display.set_max(i, 360)
            self.bearing_display.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.bearing_display.set_label(i, "Data {0}".format(i))
            else:
                self.bearing_display.set_label(i, labels[i])
            self.bearing_display.set_unit(i, units[i])
            self.bearing_display.set_factor(i, factor[i])

        self.bearing_display.enable_autoscale(False)
        self._bearing_display_win = sip.wrapinstance(self.bearing_display.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._bearing_display_win, 0, 0, 1, 1)
        for r in range(0, 1):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.bearing_streams, 0), (self.bearing_display, 0))
        self.connect((self.bearing_streams, 0), (self.qtgui_compass_0, 0))
        self.connect((self.bearing_validity, 0), (self.bearing_streams, 0))
        self.connect((self.covariance, 0), (self.music_uca, 0))
        self.connect((self.direct_phase_correction, 2), (self.pilot_aligned_vectorizer, 2))
        self.connect((self.direct_phase_correction, 1), (self.pilot_aligned_vectorizer, 1))
        self.connect((self.direct_phase_correction, 0), (self.pilot_aligned_vectorizer, 0))
        self.connect((self.direct_phase_correction, 3), (self.pilot_aligned_vectorizer, 3))
        self.connect((self.direct_phase_correction, 7), (self.target_aligned_vectorizer, 3))
        self.connect((self.direct_phase_correction, 4), (self.target_aligned_vectorizer, 0))
        self.connect((self.direct_phase_correction, 5), (self.target_aligned_vectorizer, 1))
        self.connect((self.direct_phase_correction, 6), (self.target_aligned_vectorizer, 2))
        self.connect((self.libresdr_a, 0), (self.pilot_filter_0, 0))
        self.connect((self.libresdr_a, 1), (self.pilot_filter_1, 0))
        self.connect((self.libresdr_a, 0), (self.target_filter_0, 0))
        self.connect((self.libresdr_a, 1), (self.target_filter_1, 0))
        self.connect((self.libresdr_b, 1), (self.pilot_filter_2, 0))
        self.connect((self.libresdr_b, 0), (self.pilot_filter_3, 0))
        self.connect((self.libresdr_b, 1), (self.target_filter_2, 0))
        self.connect((self.libresdr_b, 0), (self.target_filter_3, 0))
        self.connect((self.music_uca, 0), (self.peak_finder, 0))
        self.connect((self.ota_calibration, 3), (self.covariance, 3))
        self.connect((self.ota_calibration, 2), (self.covariance, 2))
        self.connect((self.ota_calibration, 0), (self.covariance, 0))
        self.connect((self.ota_calibration, 1), (self.covariance, 1))
        self.connect((self.peak_finder, 1), (self.bearing_validity, 0))
        self.connect((self.peak_finder, 0), (self.peak_magnitude_discard, 0))
        self.connect((self.pilot_aligned_vectorizer, 0), (self.pilot_output_decimator, 0))
        self.connect((self.pilot_filter_0, 0), (self.direct_phase_correction, 0))
        self.connect((self.pilot_filter_1, 0), (self.direct_phase_correction, 1))
        self.connect((self.pilot_filter_2, 0), (self.direct_phase_correction, 2))
        self.connect((self.pilot_filter_3, 0), (self.direct_phase_correction, 3))
        self.connect((self.pilot_output_decimator, 0), (self.pilot_aligned_discard, 0))
        self.connect((self.target_aligned_streams, 1), (self.ota_calibration, 1))
        self.connect((self.target_aligned_streams, 0), (self.ota_calibration, 4))
        self.connect((self.target_aligned_streams, 0), (self.ota_calibration, 0))
        self.connect((self.target_aligned_streams, 2), (self.ota_calibration, 2))
        self.connect((self.target_aligned_streams, 1), (self.ota_calibration, 5))
        self.connect((self.target_aligned_streams, 2), (self.ota_calibration, 6))
        self.connect((self.target_aligned_streams, 3), (self.ota_calibration, 3))
        self.connect((self.target_aligned_streams, 3), (self.ota_calibration, 7))
        self.connect((self.target_aligned_vectorizer, 0), (self.target_output_decimator, 0))
        self.connect((self.target_filter_0, 0), (self.direct_phase_correction, 4))
        self.connect((self.target_filter_1, 0), (self.direct_phase_correction, 5))
        self.connect((self.target_filter_2, 0), (self.direct_phase_correction, 6))
        self.connect((self.target_filter_3, 0), (self.direct_phase_correction, 7))
        self.connect((self.target_output_decimator, 0), (self.target_aligned_streams, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "run_MUSIC_uca_live_cal")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_target_offset(self):
        return self.target_offset

    def set_target_offset(self, target_offset):
        self.target_offset = target_offset
        self.set_target_rf(self.center_freq + self.target_offset)
        self.target_filter_0.set_center_freq(self.target_offset)
        self.target_filter_1.set_center_freq(self.target_offset)
        self.target_filter_2.set_center_freq(self.target_offset)
        self.target_filter_3.set_center_freq(self.target_offset)

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
        self.set_target_rf(self.center_freq + self.target_offset)
        self.libresdr_a.set_frequency(self.center_freq)
        self.libresdr_b.set_frequency(self.center_freq)

    def get_target_rf(self):
        return self.target_rf

    def set_target_rf(self, target_rf):
        self.target_rf = target_rf
        self.set_target_norm_radius(self.array_radius * self.target_rf / 299792458.0)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_cfo_settling_samples(int(5 * self.samp_rate))
        self.set_proc_rate(self.samp_rate / self.pilot_decim)
        self.libresdr_a.set_samplerate(self.samp_rate)
        self.libresdr_b.set_samplerate(self.samp_rate)
        self.pilot_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))

    def get_pilot_rf(self):
        return self.pilot_rf

    def set_pilot_rf(self, pilot_rf):
        self.pilot_rf = pilot_rf
        self.set_norm_radius(self.array_radius * self.pilot_rf / 299792458.0)

    def get_pilot_decim(self):
        return self.pilot_decim

    def set_pilot_decim(self, pilot_decim):
        self.pilot_decim = pilot_decim
        self.set_proc_rate(self.samp_rate / self.pilot_decim)

    def get_array_radius(self):
        return self.array_radius

    def set_array_radius(self, array_radius):
        self.array_radius = array_radius
        self.set_norm_radius(self.array_radius * self.pilot_rf / 299792458.0)
        self.set_target_norm_radius(self.array_radius * self.target_rf / 299792458.0)

    def get_target_norm_radius(self):
        return self.target_norm_radius

    def set_target_norm_radius(self, target_norm_radius):
        self.target_norm_radius = target_norm_radius

    def get_target_calibration_bearing(self):
        return self.target_calibration_bearing

    def set_target_calibration_bearing(self, target_calibration_bearing):
        self.target_calibration_bearing = target_calibration_bearing

    def get_snapshot_size(self):
        return self.snapshot_size

    def set_snapshot_size(self, snapshot_size):
        self.snapshot_size = snapshot_size

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

    def get_pspectrum_len(self):
        return self.pspectrum_len

    def set_pspectrum_len(self, pspectrum_len):
        self.pspectrum_len = pspectrum_len

    def get_proc_rate(self):
        return self.proc_rate

    def set_proc_rate(self, proc_rate):
        self.proc_rate = proc_rate

    def get_pilot_transition(self):
        return self.pilot_transition

    def set_pilot_transition(self, pilot_transition):
        self.pilot_transition = pilot_transition
        self.pilot_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))

    def get_pilot_passband(self):
        return self.pilot_passband

    def set_pilot_passband(self, pilot_passband):
        self.pilot_passband = pilot_passband
        self.pilot_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.target_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))

    def get_pilot_bearing(self):
        return self.pilot_bearing

    def set_pilot_bearing(self, pilot_bearing):
        self.pilot_bearing = pilot_bearing

    def get_overlap_size(self):
        return self.overlap_size

    def set_overlap_size(self, overlap_size):
        self.overlap_size = overlap_size

    def get_num_targets(self):
        return self.num_targets

    def set_num_targets(self, num_targets):
        self.num_targets = num_targets

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




def main(top_block_cls=run_MUSIC_uca_live_cal, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()
    snippets_main_after_init(tb)
    tb.start()
    tb.flowgraph_started.set()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
