#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: LibreSDR UCA MUSIC - Live OTA Calibration
# Author: gr-doa LibreSDR research port
# Description: Keep this flowgraph running after calibration; switching off the B210 does not invalidate frozen corrections.
# GNU Radio version: 3.10.12.0

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio import blocks
from gnuradio import doa
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
        self.snapshot_size = snapshot_size = 2**12
        self.samp_rate = samp_rate = int(2.8e6)
        self.rx_gain = rx_gain = 40
        self.rf_bandwidth = rf_bandwidth = int(2.8e6)
        self.pspectrum_len = pspectrum_len = 720
        self.pilot_bearing = pilot_bearing = 0.0
        self.overlap_size = overlap_size = 2**11
        self.num_targets = num_targets = 1
        self.num_elements = num_elements = 4
        self.norm_radius = norm_radius = 0.346379923
        self.element_bearing_step = element_bearing_step = -90.0
        self.element0_bearing = element0_bearing = 225.0
        self.center_freq = center_freq = int(903e6)
        self.calibration_skip = calibration_skip = 2**14
        self.calibration_samples = calibration_samples = 2**16
        self.calibration_file = calibration_file = "/tmp/gr-doa-uca-903MHz.cfg"

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
            config_filename=calibration_file)
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
        self.libresdr_b.set_quadrature(True)
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
        self.libresdr_a.set_quadrature(True)
        self.libresdr_a.set_rfdc(True)
        self.libresdr_a.set_bbdc(True)
        self.libresdr_a.set_filter_params('Auto', '', 0, 0)
        self.covariance = doa.autocorrelate(num_elements, snapshot_size, overlap_size, 0)
        self.corrected_channels = qtgui.time_sink_c(
            1024, #size
            samp_rate, #samp_rate
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


        labels = ['Element 0', 'Element 1', 'Element 2', 'Element 3', '',
            '', '', '', '', '']
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
        self.bearing_streams = blocks.vector_to_streams(gr.sizeof_float*1, num_targets)
        self.bearing_display = qtgui.number_sink(
            gr.sizeof_float,
            0.15,
            qtgui.NUM_GRAPH_HORIZ,
            1,
            None # parent
        )
        self.bearing_display.set_update_time(0.10)
        self.bearing_display.set_title("UCA MUSIC bearing")

        labels = ['Estimated bearing', 'Target 2', 'Target 3', '', '',
            '', '', '', '', '']
        units = ['degrees', 'degrees', 'degrees', '', '',
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
        self.connect((self.covariance, 0), (self.music_uca, 0))
        self.connect((self.libresdr_a, 1), (self.ota_calibration, 1))
        self.connect((self.libresdr_a, 0), (self.ota_calibration, 0))
        self.connect((self.libresdr_b, 1), (self.ota_calibration, 2))
        self.connect((self.libresdr_b, 0), (self.ota_calibration, 3))
        self.connect((self.music_uca, 0), (self.peak_finder, 0))
        self.connect((self.music_uca, 0), (self.spectrum_display, 0))
        self.connect((self.ota_calibration, 2), (self.corrected_channels, 2))
        self.connect((self.ota_calibration, 3), (self.corrected_channels, 3))
        self.connect((self.ota_calibration, 0), (self.corrected_channels, 0))
        self.connect((self.ota_calibration, 1), (self.corrected_channels, 1))
        self.connect((self.ota_calibration, 0), (self.covariance, 0))
        self.connect((self.ota_calibration, 1), (self.covariance, 1))
        self.connect((self.ota_calibration, 2), (self.covariance, 2))
        self.connect((self.ota_calibration, 3), (self.covariance, 3))
        self.connect((self.peak_finder, 1), (self.bearing_streams, 0))
        self.connect((self.peak_finder, 0), (self.peak_magnitude_discard, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "run_MUSIC_uca_live_cal")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_snapshot_size(self):
        return self.snapshot_size

    def set_snapshot_size(self, snapshot_size):
        self.snapshot_size = snapshot_size

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.libresdr_a.set_samplerate(self.samp_rate)
        self.libresdr_b.set_samplerate(self.samp_rate)
        self.corrected_channels.set_samp_rate(self.samp_rate)

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

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.libresdr_a.set_frequency(self.center_freq)
        self.libresdr_b.set_frequency(self.center_freq)

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
