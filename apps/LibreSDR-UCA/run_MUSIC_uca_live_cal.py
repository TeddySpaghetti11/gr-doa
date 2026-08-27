#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: LibreSDR UCA MUSIC - Live OTA Calibration
# Author: gr-doa LibreSDR research port
# Copyright: None
# Description: Narrow translated pilot, source-bearing UCA steering, and calibration coherence diagnostics.
# GNU Radio version: v3.11.0.0git-1103-g14d6a758

from gnuradio import qtgui
from PyQt5 import Qt
from gnuradio import blocks
from gnuradio import doa
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import iio
import gnuradio.doa as doa
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
        self.pilot_offset = pilot_offset = 50e3
        self.center_freq = center_freq = int(920.9e6)
        self.samp_rate = samp_rate = int(2.8e6)
        self.pilot_rf = pilot_rf = center_freq + pilot_offset
        self.pilot_decim = pilot_decim = 8
        self.array_radius = array_radius = 0.16263 / (2**0.5)
        self.snapshot_size = snapshot_size = 2**15
        self.rx_gain = rx_gain = 40
        self.rf_bandwidth = rf_bandwidth = int(2.8e6)
        self.pspectrum_len = pspectrum_len = 720
        self.proc_rate = proc_rate = samp_rate / pilot_decim
        self.pilot_transition = pilot_transition = 10e3
        self.pilot_passband = pilot_passband = 10e3
        self.pilot_bearing = pilot_bearing = 0
        self.overlap_size = overlap_size = 2**14
        self.num_targets = num_targets = 1
        self.num_elements = num_elements = 4
        self.norm_radius = norm_radius = array_radius * pilot_rf / 299792458.0
        self.element_bearing_step = element_bearing_step = -90.0
        self.element0_bearing = element0_bearing = 225.0
        self.calibration_skip = calibration_skip = 2**14
        self.calibration_samples = calibration_samples = 2**16
        self.calibration_file = calibration_file = "/tmp/gr-doa-uca-phase-offsets.cfg"

        ##################################################
        # Blocks
        ##################################################

        self.spectrum_display = qtgui.vector_sink_f(
            pspectrum_len,
            0,
            (360.0/pspectrum_len),
            "Bearing (degrees)",
            "Normalized pseudo-spectrum (dB)",
            "Full-circle UCA MUSIC",
            1, # Number of inputs
            None # parent
        )
        self.spectrum_display.set_update_time(0.10)
        self.spectrum_display.set_y_axis((-40), 0)
        self.spectrum_display.enable_autoscale(False)
        self.spectrum_display.enable_grid(True)
        self.spectrum_display.set_x_axis_units("degrees")
        self.spectrum_display.set_y_axis_units("dB")
        self.spectrum_display.set_ref_level(0)


        labels = ['MUSIC pseudo-spectrum', '', '', '', '',
            '', '', '', '', '']
        widths = [2, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.spectrum_display.set_line_label(i, "Data {0}".format(i))
            else:
                self.spectrum_display.set_line_label(i, labels[i])
            self.spectrum_display.set_line_width(i, widths[i])
            self.spectrum_display.set_line_color(i, colors[i])
            self.spectrum_display.set_line_alpha(i, alphas[i])

        self._spectrum_display_win = sip.wrapinstance(self.spectrum_display.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._spectrum_display_win, 1, 0, 1, 2)
        for r in range(1, 2):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.raw_fft_display = qtgui.freq_sink_c(
            32768, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "TRUE pre-filter raw spectra (32768-bin FFT)", #name
            4,
            None # parent
        )
        self.raw_fft_display.set_update_time(0.10)
        self.raw_fft_display.set_y_axis((-140), 10)
        self.raw_fft_display.set_y_label('Relative Gain', 'dB')
        self.raw_fft_display.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.raw_fft_display.enable_autoscale(False)
        self.raw_fft_display.enable_grid(False)
        self.raw_fft_display.set_fft_average(1.0)
        self.raw_fft_display.enable_axis_labels(True)
        self.raw_fft_display.enable_control_panel(False)
        self.raw_fft_display.set_fft_window_normalized(False)



        labels = ['A RX1 / element 0', 'A RX2 / element 1', 'B RX2 / element 2', 'B RX1 / element 3', '',
            '', '', '', '', '']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(4):
            if len(labels[i]) == 0:
                self.raw_fft_display.set_line_label(i, "Data {0}".format(i))
            else:
                self.raw_fft_display.set_line_label(i, labels[i])
            self.raw_fft_display.set_line_width(i, widths[i])
            self.raw_fft_display.set_line_color(i, colors[i])
            self.raw_fft_display.set_line_alpha(i, alphas[i])

        self._raw_fft_display_win = sip.wrapinstance(self.raw_fft_display.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._raw_fft_display_win)
        self.qtgui_compass_0 = self._qtgui_compass_0_win = qtgui.GrCompass('', 250, 0.10, False, 1,False,1,"default")
        self._qtgui_compass_0_win.setColors("default","red", "black", "black")
        self._qtgui_compass_0 = self._qtgui_compass_0_win
        self.top_layout.addWidget(self._qtgui_compass_0_win)
        self.prefilter_phase_estimator = doa.phase_offset_est(num_elements, (calibration_skip * pilot_decim))
        self.prefilter_phase_display = qtgui.time_sink_f(
            1024, #size
            samp_rate, #samp_rate
            "TRUE PRE-FILTER relative phase (direct IIO)", #name
            3, #number of inputs
            None # parent
        )
        self.prefilter_phase_display.set_update_time(0.10)
        self.prefilter_phase_display.set_y_axis(-3.2, 3.2)

        self.prefilter_phase_display.set_y_label('Phase', 'radians')

        self.prefilter_phase_display.enable_tags(False)
        self.prefilter_phase_display.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.prefilter_phase_display.enable_autoscale(False)
        self.prefilter_phase_display.enable_grid(True)
        self.prefilter_phase_display.enable_axis_labels(True)
        self.prefilter_phase_display.enable_control_panel(False)
        self.prefilter_phase_display.enable_stem_plot(False)


        labels = ['TRUE PRE-FILTER A RX2 vs A RX1', 'TRUE PRE-FILTER B RX2 vs A RX1', 'TRUE PRE-FILTER B RX1 vs A RX1', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(3):
            if len(labels[i]) == 0:
                self.prefilter_phase_display.set_line_label(i, "Data {0}".format(i))
            else:
                self.prefilter_phase_display.set_line_label(i, labels[i])
            self.prefilter_phase_display.set_line_width(i, widths[i])
            self.prefilter_phase_display.set_line_color(i, colors[i])
            self.prefilter_phase_display.set_line_style(i, styles[i])
            self.prefilter_phase_display.set_line_marker(i, markers[i])
            self.prefilter_phase_display.set_line_alpha(i, alphas[i])

        self._prefilter_phase_display_win = sip.wrapinstance(self.prefilter_phase_display.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._prefilter_phase_display_win, 3, 0, 1, 2)
        for r in range(3, 4):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.postfilter_phase_estimator = doa.phase_offset_est(num_elements, calibration_skip)
        self.postfilter_phase_display = qtgui.time_sink_f(
            1024, #size
            proc_rate, #samp_rate
            "POST-FILTER relative phase (before calibration)", #name
            3, #number of inputs
            None # parent
        )
        self.postfilter_phase_display.set_update_time(0.10)
        self.postfilter_phase_display.set_y_axis(-3.2, 3.2)

        self.postfilter_phase_display.set_y_label('Phase', 'radians')

        self.postfilter_phase_display.enable_tags(False)
        self.postfilter_phase_display.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.postfilter_phase_display.enable_autoscale(False)
        self.postfilter_phase_display.enable_grid(True)
        self.postfilter_phase_display.enable_axis_labels(True)
        self.postfilter_phase_display.enable_control_panel(False)
        self.postfilter_phase_display.enable_stem_plot(False)


        labels = ['POST-FILTER A RX2 vs A RX1', 'POST-FILTER B RX2 vs A RX1', 'POST-FILTER B RX1 vs A RX1', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(3):
            if len(labels[i]) == 0:
                self.postfilter_phase_display.set_line_label(i, "Data {0}".format(i))
            else:
                self.postfilter_phase_display.set_line_label(i, labels[i])
            self.postfilter_phase_display.set_line_width(i, widths[i])
            self.postfilter_phase_display.set_line_color(i, colors[i])
            self.postfilter_phase_display.set_line_style(i, styles[i])
            self.postfilter_phase_display.set_line_marker(i, markers[i])
            self.postfilter_phase_display.set_line_alpha(i, alphas[i])

        self._postfilter_phase_display_win = sip.wrapinstance(self.postfilter_phase_display.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._postfilter_phase_display_win, 2, 0, 1, 1)
        for r in range(2, 3):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.pilot_filter_3 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_2 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_1 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.pilot_filter_0 = filter.freq_xlating_fir_filter_ccc(pilot_decim, firdes.low_pass(1.0, samp_rate, pilot_passband, pilot_transition), pilot_offset, samp_rate)
        self.peak_magnitude_discard = blocks.null_sink(gr.sizeof_float*num_targets)
        self.peak_finder = doa.find_local_max(num_targets, pspectrum_len, 0.0, 360.0)
        self.ota_calibration = doa.uca_pilot_calibration(
            num_inputs=num_elements,
            norm_radius=norm_radius,
            pilot_angle=pilot_bearing,
            element0_angle=element0_bearing,
            element_angle_step=element_bearing_step,
            skip_samples=calibration_skip,
            calibration_samples=calibration_samples,
            config_filename=calibration_file,
            min_coherence=0.90)
        self.music_uca = doa.MUSIC_uca(norm_radius, num_targets, num_elements, pspectrum_len, element0_bearing, element_bearing_step)
        self.libresdr_b = iio.fmcomms2_source_fc32('ip:192.168.5.1', [True, True, True, True], 32768)
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
        self.libresdr_a = iio.fmcomms2_source_fc32('ip:192.168.4.1', [True, True, True, True], 32768)
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
        self.covariance = doa.autocorrelate(num_elements, snapshot_size, overlap_size, 0)
        self.corrected_phase_estimator = doa.phase_offset_est(num_elements, (calibration_skip + calibration_samples))
        self.corrected_phase_display = qtgui.time_sink_f(
            1024, #size
            proc_rate, #samp_rate
            "Corrected relative phase (instantaneous)", #name
            3, #number of inputs
            None # parent
        )
        self.corrected_phase_display.set_update_time(0.10)
        self.corrected_phase_display.set_y_axis(-3.2, 3.2)

        self.corrected_phase_display.set_y_label('Phase', 'radians')

        self.corrected_phase_display.enable_tags(False)
        self.corrected_phase_display.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.corrected_phase_display.enable_autoscale(False)
        self.corrected_phase_display.enable_grid(True)
        self.corrected_phase_display.enable_axis_labels(True)
        self.corrected_phase_display.enable_control_panel(False)
        self.corrected_phase_display.enable_stem_plot(False)


        labels = ['Corrected ch1/ch0', 'Corrected ch2/ch0', 'Corrected ch3/ch0', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(3):
            if len(labels[i]) == 0:
                self.corrected_phase_display.set_line_label(i, "Data {0}".format(i))
            else:
                self.corrected_phase_display.set_line_label(i, labels[i])
            self.corrected_phase_display.set_line_width(i, widths[i])
            self.corrected_phase_display.set_line_color(i, colors[i])
            self.corrected_phase_display.set_line_style(i, styles[i])
            self.corrected_phase_display.set_line_marker(i, markers[i])
            self.corrected_phase_display.set_line_alpha(i, alphas[i])

        self._corrected_phase_display_win = sip.wrapinstance(self.corrected_phase_display.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._corrected_phase_display_win, 2, 1, 1, 1)
        for r in range(2, 3):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.corrected_channels = qtgui.time_sink_c(
            1024, #size
            proc_rate, #samp_rate
            "Calibrated UCA channels", #name
            4, #number of inputs
            None # parent
        )
        self.corrected_channels.set_update_time(0.10)
        self.corrected_channels.set_y_axis(-1, 1)

        self.corrected_channels.set_y_label('Amplitude', "")

        self.corrected_channels.enable_tags(True)
        self.corrected_channels.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.corrected_channels.enable_autoscale(True)
        self.corrected_channels.enable_grid(True)
        self.corrected_channels.enable_axis_labels(True)
        self.corrected_channels.enable_control_panel(False)
        self.corrected_channels.enable_stem_plot(False)


        labels = ['Element 0', 'Element 1', 'Element 2', 'Element 3', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(8):
            if len(labels[i]) == 0:
                if (i % 2 == 0):
                    self.corrected_channels.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.corrected_channels.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.corrected_channels.set_line_label(i, labels[i])
            self.corrected_channels.set_line_width(i, widths[i])
            self.corrected_channels.set_line_color(i, colors[i])
            self.corrected_channels.set_line_style(i, styles[i])
            self.corrected_channels.set_line_marker(i, markers[i])
            self.corrected_channels.set_line_alpha(i, alphas[i])

        self._corrected_channels_win = sip.wrapinstance(self.corrected_channels.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._corrected_channels_win, 0, 1, 1, 1)
        for r in range(0, 1):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.bravo_internal_phase_estimator = doa.phase_offset_est(2, (calibration_skip * pilot_decim))
        self.bravo_internal_phase_display = qtgui.time_sink_f(
            1024, #size
            samp_rate, #samp_rate
            "Bravo internal pre-filter phase: RX1 vs RX2", #name
            1, #number of inputs
            None # parent
        )
        self.bravo_internal_phase_display.set_update_time(0.10)
        self.bravo_internal_phase_display.set_y_axis(-3.2, 3.2)

        self.bravo_internal_phase_display.set_y_label('Phase', 'radians')

        self.bravo_internal_phase_display.enable_tags(False)
        self.bravo_internal_phase_display.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.bravo_internal_phase_display.enable_autoscale(False)
        self.bravo_internal_phase_display.enable_grid(True)
        self.bravo_internal_phase_display.enable_axis_labels(True)
        self.bravo_internal_phase_display.enable_control_panel(False)
        self.bravo_internal_phase_display.enable_stem_plot(False)


        labels = ['arg(B RX1 * conj(B RX2))', 'Signal 2', 'Signal 3', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(1):
            if len(labels[i]) == 0:
                self.bravo_internal_phase_display.set_line_label(i, "Data {0}".format(i))
            else:
                self.bravo_internal_phase_display.set_line_label(i, labels[i])
            self.bravo_internal_phase_display.set_line_width(i, widths[i])
            self.bravo_internal_phase_display.set_line_color(i, colors[i])
            self.bravo_internal_phase_display.set_line_style(i, styles[i])
            self.bravo_internal_phase_display.set_line_marker(i, markers[i])
            self.bravo_internal_phase_display.set_line_alpha(i, alphas[i])

        self._bravo_internal_phase_display_win = sip.wrapinstance(self.bravo_internal_phase_display.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._bravo_internal_phase_display_win, 4, 1, 1, 1)
        for r in range(4, 5):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
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
        self.alpha_internal_phase_estimator = doa.phase_offset_est(2, (calibration_skip * pilot_decim))
        self.alpha_internal_phase_display = qtgui.time_sink_f(
            1024, #size
            samp_rate, #samp_rate
            "Alpha internal pre-filter phase: RX1 vs RX2", #name
            1, #number of inputs
            None # parent
        )
        self.alpha_internal_phase_display.set_update_time(0.10)
        self.alpha_internal_phase_display.set_y_axis(-3.2, 3.2)

        self.alpha_internal_phase_display.set_y_label('Phase', 'radians')

        self.alpha_internal_phase_display.enable_tags(False)
        self.alpha_internal_phase_display.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.alpha_internal_phase_display.enable_autoscale(False)
        self.alpha_internal_phase_display.enable_grid(True)
        self.alpha_internal_phase_display.enable_axis_labels(True)
        self.alpha_internal_phase_display.enable_control_panel(False)
        self.alpha_internal_phase_display.enable_stem_plot(False)


        labels = ['arg(A RX1 * conj(A RX2))', 'Signal 2', 'Signal 3', 'Signal 4', 'Signal 5',
            'Signal 6', 'Signal 7', 'Signal 8', 'Signal 9', 'Signal 10']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'black', 'cyan',
            'magenta', 'yellow', 'dark red', 'dark green', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(1):
            if len(labels[i]) == 0:
                self.alpha_internal_phase_display.set_line_label(i, "Data {0}".format(i))
            else:
                self.alpha_internal_phase_display.set_line_label(i, labels[i])
            self.alpha_internal_phase_display.set_line_width(i, widths[i])
            self.alpha_internal_phase_display.set_line_color(i, colors[i])
            self.alpha_internal_phase_display.set_line_style(i, styles[i])
            self.alpha_internal_phase_display.set_line_marker(i, markers[i])
            self.alpha_internal_phase_display.set_line_alpha(i, alphas[i])

        self._alpha_internal_phase_display_win = sip.wrapinstance(self.alpha_internal_phase_display.qwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._alpha_internal_phase_display_win, 4, 0, 1, 1)
        for r in range(4, 5):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.alpha_internal_phase_estimator, 0), (self.alpha_internal_phase_display, 0))
        self.connect((self.bearing_streams, 0), (self.bearing_display, 0))
        self.connect((self.bearing_streams, 0), (self.qtgui_compass_0, 0))
        self.connect((self.bravo_internal_phase_estimator, 0), (self.bravo_internal_phase_display, 0))
        self.connect((self.corrected_phase_estimator, 2), (self.corrected_phase_display, 2))
        self.connect((self.corrected_phase_estimator, 0), (self.corrected_phase_display, 0))
        self.connect((self.corrected_phase_estimator, 1), (self.corrected_phase_display, 1))
        self.connect((self.covariance, 0), (self.music_uca, 0))
        self.connect((self.libresdr_a, 0), (self.alpha_internal_phase_estimator, 0))
        self.connect((self.libresdr_a, 1), (self.alpha_internal_phase_estimator, 1))
        self.connect((self.libresdr_a, 0), (self.pilot_filter_0, 0))
        self.connect((self.libresdr_a, 1), (self.pilot_filter_1, 0))
        self.connect((self.libresdr_a, 1), (self.prefilter_phase_estimator, 1))
        self.connect((self.libresdr_a, 0), (self.prefilter_phase_estimator, 0))
        self.connect((self.libresdr_a, 0), (self.raw_fft_display, 0))
        self.connect((self.libresdr_a, 1), (self.raw_fft_display, 1))
        self.connect((self.libresdr_b, 1), (self.bravo_internal_phase_estimator, 1))
        self.connect((self.libresdr_b, 0), (self.bravo_internal_phase_estimator, 0))
        self.connect((self.libresdr_b, 1), (self.pilot_filter_2, 0))
        self.connect((self.libresdr_b, 0), (self.pilot_filter_3, 0))
        self.connect((self.libresdr_b, 0), (self.prefilter_phase_estimator, 3))
        self.connect((self.libresdr_b, 1), (self.prefilter_phase_estimator, 2))
        self.connect((self.libresdr_b, 0), (self.raw_fft_display, 3))
        self.connect((self.libresdr_b, 1), (self.raw_fft_display, 2))
        self.connect((self.music_uca, 0), (self.peak_finder, 0))
        self.connect((self.music_uca, 0), (self.spectrum_display, 0))
        self.connect((self.ota_calibration, 0), (self.corrected_channels, 0))
        self.connect((self.ota_calibration, 3), (self.corrected_channels, 3))
        self.connect((self.ota_calibration, 2), (self.corrected_channels, 2))
        self.connect((self.ota_calibration, 1), (self.corrected_channels, 1))
        self.connect((self.ota_calibration, 1), (self.corrected_phase_estimator, 1))
        self.connect((self.ota_calibration, 2), (self.corrected_phase_estimator, 2))
        self.connect((self.ota_calibration, 3), (self.corrected_phase_estimator, 3))
        self.connect((self.ota_calibration, 0), (self.corrected_phase_estimator, 0))
        self.connect((self.ota_calibration, 1), (self.covariance, 1))
        self.connect((self.ota_calibration, 2), (self.covariance, 2))
        self.connect((self.ota_calibration, 0), (self.covariance, 0))
        self.connect((self.ota_calibration, 3), (self.covariance, 3))
        self.connect((self.peak_finder, 1), (self.bearing_streams, 0))
        self.connect((self.peak_finder, 0), (self.peak_magnitude_discard, 0))
        self.connect((self.pilot_filter_0, 0), (self.ota_calibration, 0))
        self.connect((self.pilot_filter_0, 0), (self.postfilter_phase_estimator, 0))
        self.connect((self.pilot_filter_1, 0), (self.ota_calibration, 1))
        self.connect((self.pilot_filter_1, 0), (self.postfilter_phase_estimator, 1))
        self.connect((self.pilot_filter_2, 0), (self.ota_calibration, 2))
        self.connect((self.pilot_filter_2, 0), (self.postfilter_phase_estimator, 2))
        self.connect((self.pilot_filter_3, 0), (self.ota_calibration, 3))
        self.connect((self.pilot_filter_3, 0), (self.postfilter_phase_estimator, 3))
        self.connect((self.postfilter_phase_estimator, 1), (self.postfilter_phase_display, 1))
        self.connect((self.postfilter_phase_estimator, 2), (self.postfilter_phase_display, 2))
        self.connect((self.postfilter_phase_estimator, 0), (self.postfilter_phase_display, 0))
        self.connect((self.prefilter_phase_estimator, 2), (self.prefilter_phase_display, 2))
        self.connect((self.prefilter_phase_estimator, 1), (self.prefilter_phase_display, 1))
        self.connect((self.prefilter_phase_estimator, 0), (self.prefilter_phase_display, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "run_MUSIC_uca_live_cal")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

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

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_proc_rate(self.samp_rate / self.pilot_decim)
        self.libresdr_a.set_samplerate(self.samp_rate)
        self.libresdr_b.set_samplerate(self.samp_rate)
        self.pilot_filter_0.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_1.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_2.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.pilot_filter_3.set_taps(firdes.low_pass(1.0, self.samp_rate, self.pilot_passband, self.pilot_transition))
        self.raw_fft_display.set_frequency_range(0, self.samp_rate)
        self.prefilter_phase_display.set_samp_rate(self.samp_rate)
        self.alpha_internal_phase_display.set_samp_rate(self.samp_rate)
        self.bravo_internal_phase_display.set_samp_rate(self.samp_rate)

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
        self.spectrum_display.set_x_axis(0, (360.0/self.pspectrum_len))

    def get_proc_rate(self):
        return self.proc_rate

    def set_proc_rate(self, proc_rate):
        self.proc_rate = proc_rate
        self.corrected_channels.set_samp_rate(self.proc_rate)
        self.corrected_phase_display.set_samp_rate(self.proc_rate)
        self.postfilter_phase_display.set_samp_rate(self.proc_rate)

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
