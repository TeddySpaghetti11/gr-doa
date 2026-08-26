#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# SPDX-License-Identifier: GPL-3.0
# GNU Radio Python Flow Graph
# Title: LibreSDR UCA MUSIC - Live OTA Calibration

from PyQt5 import Qt
from gnuradio import blocks
from gnuradio import doa
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio import iio
from gnuradio import qtgui
from gnuradio.fft import window
import signal
import sip
import sys
import threading


class run_MUSIC_uca_live_cal(gr.top_block, Qt.QWidget):
    def __init__(self):
        gr.top_block.__init__(
            self, "LibreSDR UCA MUSIC - Live OTA Calibration", catch_exceptions=True
        )
        Qt.QWidget.__init__(self)
        self.setWindowTitle("LibreSDR UCA MUSIC - Live OTA Calibration")
        qtgui.util.check_set_qss()

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
        self.settings = Qt.QSettings(
            "gnuradio/flowgraphs", "run_MUSIC_uca_live_cal"
        )
        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {exc}", file=sys.stderr)
        self.flowgraph_started = threading.Event()

        # ---------------------------------------------------------------
        # Physical and DSP parameters
        # ---------------------------------------------------------------
        self.center_freq = center_freq = int(920.9e6)
        self.samp_rate = samp_rate = int(2.8e6)
        self.rf_bandwidth = rf_bandwidth = int(2.8e6)
        self.rx_gain = rx_gain = 40

        self.pilot_offset = pilot_offset = 50e3
        self.pilot_decim = pilot_decim = 8
        self.pilot_passband = pilot_passband = 10e3
        self.pilot_transition = pilot_transition = 10e3
        self.proc_rate = proc_rate = samp_rate / pilot_decim

        self.array_radius = array_radius = 0.16263 / (2 ** 0.5)
        self.pilot_rf = pilot_rf = center_freq + pilot_offset
        self.norm_radius = norm_radius = (
            array_radius * pilot_rf / 299792458.0
        )

        self.num_elements = num_elements = 4
        self.pilot_bearing = pilot_bearing = 90.0
        self.element0_bearing = element0_bearing = 225.0
        self.element_bearing_step = element_bearing_step = -90.0

        self.calibration_skip = calibration_skip = 2 ** 14
        self.calibration_samples = calibration_samples = 2 ** 16
        self.snapshot_size = snapshot_size = 2 ** 15
        self.overlap_size = overlap_size = 2 ** 14
        self.num_targets = num_targets = 1
        self.pspectrum_len = pspectrum_len = 720
        self.calibration_file = calibration_file = (
            "/tmp/gr-doa-uca-phase-offsets.cfg"
        )

        print(
            "LibreSDR UCA setup: "
            f"centre={center_freq/1e6:.6f} MHz, "
            f"pilot={pilot_rf/1e6:.6f} MHz, "
            f"norm_radius={norm_radius:.9f}, "
            f"processed_rate={proc_rate/1e3:.1f} kS/s"
        )

        # ---------------------------------------------------------------
        # GUI
        # ---------------------------------------------------------------
        self.bearing_display = qtgui.number_sink(
            gr.sizeof_float, 0, qtgui.NUM_GRAPH_HORIZ, 1, None
        )
        self.bearing_display.set_update_time(0.10)
        self.bearing_display.set_title("UCA MUSIC bearing")
        self.bearing_display.set_min(0, 0)
        self.bearing_display.set_max(0, 360)
        self.bearing_display.set_label(0, "Estimated bearing")
        self.bearing_display.set_unit(0, "degrees")
        self.bearing_display.set_factor(0, 1)
        self.bearing_display.enable_autoscale(False)
        self._bearing_display_win = sip.wrapinstance(
            self.bearing_display.qwidget(), Qt.QWidget
        )
        self.top_grid_layout.addWidget(self._bearing_display_win, 0, 0, 1, 1)

        self.corrected_channels = qtgui.time_sink_c(
            1024, proc_rate, "Calibrated UCA channels", 4, None
        )
        self.corrected_channels.set_update_time(0.10)
        self.corrected_channels.set_y_axis(-1, 1)
        self.corrected_channels.set_y_label("Amplitude", "")
        self.corrected_channels.enable_tags(True)
        self.corrected_channels.enable_autoscale(True)
        self.corrected_channels.enable_grid(True)
        self.corrected_channels.enable_axis_labels(True)
        for index, label in enumerate(
            ["Element 0", "Element 1", "Element 2", "Element 3"]
        ):
            self.corrected_channels.set_line_label(index * 2, f"Re {label}")
            self.corrected_channels.set_line_label(index * 2 + 1, f"Im {label}")
        self._corrected_channels_win = sip.wrapinstance(
            self.corrected_channels.qwidget(), Qt.QWidget
        )
        self.top_grid_layout.addWidget(self._corrected_channels_win, 0, 1, 1, 1)

        self.spectrum_display = qtgui.vector_sink_f(
            pspectrum_len,
            0,
            360.0 / pspectrum_len,
            "Bearing (degrees)",
            "Normalized pseudo-spectrum (dB)",
            "Full-circle UCA MUSIC",
            1,
            None,
        )
        self.spectrum_display.set_update_time(0.10)
        self.spectrum_display.set_y_axis(-40, 0)
        self.spectrum_display.enable_autoscale(False)
        self.spectrum_display.enable_grid(True)
        self.spectrum_display.set_x_axis_units("degrees")
        self.spectrum_display.set_y_axis_units("dB")
        self.spectrum_display.set_ref_level(0)
        self.spectrum_display.set_line_label(0, "MUSIC pseudo-spectrum")
        self.spectrum_display.set_line_width(0, 2)
        self._spectrum_display_win = sip.wrapinstance(
            self.spectrum_display.qwidget(), Qt.QWidget
        )
        self.top_grid_layout.addWidget(self._spectrum_display_win, 1, 0, 1, 2)

        self.raw_phase_display = qtgui.time_sink_f(
            1024, proc_rate, "Raw relative phase (instantaneous)", 3, None
        )
        self.raw_phase_display.set_update_time(0.10)
        self.raw_phase_display.set_y_axis(-3.2, 3.2)
        self.raw_phase_display.set_y_label("Phase", "radians")
        self.raw_phase_display.enable_tags(False)
        self.raw_phase_display.enable_autoscale(False)
        self.raw_phase_display.enable_grid(True)
        self.raw_phase_display.enable_axis_labels(True)
        for index, label in enumerate(
            ["Raw ch1/ch0", "Raw ch2/ch0", "Raw ch3/ch0"]
        ):
            self.raw_phase_display.set_line_label(index, label)
        self._raw_phase_display_win = sip.wrapinstance(
            self.raw_phase_display.qwidget(), Qt.QWidget
        )
        self.top_grid_layout.addWidget(self._raw_phase_display_win, 2, 0, 1, 1)

        self.corrected_phase_display = qtgui.time_sink_f(
            1024, proc_rate, "Corrected relative phase (instantaneous)", 3, None
        )
        self.corrected_phase_display.set_update_time(0.10)
        self.corrected_phase_display.set_y_axis(-3.2, 3.2)
        self.corrected_phase_display.set_y_label("Phase", "radians")
        self.corrected_phase_display.enable_tags(False)
        self.corrected_phase_display.enable_autoscale(False)
        self.corrected_phase_display.enable_grid(True)
        self.corrected_phase_display.enable_axis_labels(True)
        for index, label in enumerate(
            ["Corrected ch1/ch0", "Corrected ch2/ch0", "Corrected ch3/ch0"]
        ):
            self.corrected_phase_display.set_line_label(index, label)
        self._corrected_phase_display_win = sip.wrapinstance(
            self.corrected_phase_display.qwidget(), Qt.QWidget
        )
        self.top_grid_layout.addWidget(
            self._corrected_phase_display_win, 2, 1, 1, 1
        )

        self.raw_spectrum = qtgui.freq_sink_c(
            1024,
            window.WIN_BLACKMAN_hARRIS,
            0,
            samp_rate,
            "Raw RX1 spectrum - verify +50 kHz pilot",
            1,
            None,
        )
        self.raw_spectrum.set_update_time(0.10)
        self.raw_spectrum.set_y_axis(-140, 10)
        self.raw_spectrum.set_y_label("Relative Gain", "dB")
        self.raw_spectrum.enable_autoscale(False)
        self.raw_spectrum.enable_grid(False)
        self.raw_spectrum.set_fft_average(1.0)
        self._raw_spectrum_win = sip.wrapinstance(
            self.raw_spectrum.qwidget(), Qt.QWidget
        )
        self.top_layout.addWidget(self._raw_spectrum_win)

        self.compass = self._compass_win = qtgui.GrCompass(
            "", 250, 0.10, False, 1, False, 1, "default"
        )
        self._compass_win.setColors("default", "red", "black", "black")
        self.top_layout.addWidget(self._compass_win)

        # ---------------------------------------------------------------
        # Signal processing blocks
        # ---------------------------------------------------------------
        self.libresdr_a = iio.fmcomms2_source_fc32(
            "ip:192.168.4.1", [True, True, True, True], 32768
        )
        self.libresdr_a.set_len_tag_key("packet_len")
        self.libresdr_a.set_frequency(center_freq)
        self.libresdr_a.set_samplerate(samp_rate)
        self.libresdr_a.set_gain_mode(0, "manual")
        self.libresdr_a.set_gain(0, rx_gain)
        self.libresdr_a.set_gain_mode(1, "manual")
        self.libresdr_a.set_gain(1, rx_gain)
        self.libresdr_a.set_quadrature(False)
        self.libresdr_a.set_rfdc(True)
        self.libresdr_a.set_bbdc(True)
        self.libresdr_a.set_filter_params("Auto", "", 0, 0)

        self.libresdr_b = iio.fmcomms2_source_fc32(
            "ip:192.168.5.1", [True, True, True, True], 32768
        )
        self.libresdr_b.set_len_tag_key("packet_len")
        self.libresdr_b.set_frequency(center_freq)
        self.libresdr_b.set_samplerate(samp_rate)
        self.libresdr_b.set_gain_mode(0, "manual")
        self.libresdr_b.set_gain(0, rx_gain)
        self.libresdr_b.set_gain_mode(1, "manual")
        self.libresdr_b.set_gain(1, rx_gain)
        self.libresdr_b.set_quadrature(False)
        self.libresdr_b.set_rfdc(True)
        self.libresdr_b.set_bbdc(True)
        self.libresdr_b.set_filter_params("Auto", "", 0, 0)

        pilot_taps = firdes.low_pass(
            1.0, samp_rate, pilot_passband, pilot_transition
        )
        self.pilot_filters = [
            filter.freq_xlating_fir_filter_ccc(
                pilot_decim, pilot_taps, pilot_offset, samp_rate
            )
            for _ in range(num_elements)
        ]

        self.ota_calibration = doa.uca_pilot_calibration(
            num_inputs=num_elements,
            norm_radius=norm_radius,
            pilot_angle=pilot_bearing,
            element0_angle=element0_bearing,
            element_angle_step=element_bearing_step,
            skip_samples=calibration_skip,
            calibration_samples=calibration_samples,
            config_filename=calibration_file,
        )
        self.raw_phase_estimator = doa.phase_offset_est(
            num_elements, calibration_skip
        )
        self.corrected_phase_estimator = doa.phase_offset_est(
            num_elements, calibration_skip + calibration_samples
        )
        self.covariance = doa.autocorrelate(
            num_elements, snapshot_size, overlap_size, 0
        )
        self.music_uca = doa.MUSIC_uca(
            norm_radius,
            num_targets,
            num_elements,
            pspectrum_len,
            element0_bearing,
            element_bearing_step,
        )
        self.peak_finder = doa.find_local_max(
            num_targets, pspectrum_len, 0.0, 360.0
        )
        self.peak_magnitude_discard = blocks.null_sink(
            gr.sizeof_float * num_targets
        )
        self.bearing_streams = blocks.vector_to_streams(
            gr.sizeof_float, num_targets
        )

        # ---------------------------------------------------------------
        # Connections.  Preserve physical stream order:
        # A RX1, A RX2, B RX2, B RX1 -> elements 0,1,2,3.
        # ---------------------------------------------------------------
        self.connect((self.libresdr_a, 0), (self.pilot_filters[0], 0))
        self.connect((self.libresdr_a, 1), (self.pilot_filters[1], 0))
        self.connect((self.libresdr_b, 1), (self.pilot_filters[2], 0))
        self.connect((self.libresdr_b, 0), (self.pilot_filters[3], 0))
        self.connect((self.libresdr_a, 0), (self.raw_spectrum, 0))

        for channel in range(num_elements):
            self.connect(
                (self.pilot_filters[channel], 0),
                (self.ota_calibration, channel),
            )
            self.connect(
                (self.pilot_filters[channel], 0),
                (self.raw_phase_estimator, channel),
            )
            self.connect(
                (self.ota_calibration, channel),
                (self.covariance, channel),
            )
            self.connect(
                (self.ota_calibration, channel),
                (self.corrected_channels, channel),
            )
            self.connect(
                (self.ota_calibration, channel),
                (self.corrected_phase_estimator, channel),
            )

        for index in range(num_elements - 1):
            self.connect(
                (self.raw_phase_estimator, index),
                (self.raw_phase_display, index),
            )
            self.connect(
                (self.corrected_phase_estimator, index),
                (self.corrected_phase_display, index),
            )

        self.connect((self.covariance, 0), (self.music_uca, 0))
        self.connect((self.music_uca, 0), (self.spectrum_display, 0))
        self.connect((self.music_uca, 0), (self.peak_finder, 0))
        self.connect((self.peak_finder, 0), (self.peak_magnitude_discard, 0))
        self.connect((self.peak_finder, 1), (self.bearing_streams, 0))
        self.connect((self.bearing_streams, 0), (self.bearing_display, 0))
        self.connect((self.bearing_streams, 0), (self.compass, 0))

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()
        event.accept()


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


if __name__ == "__main__":
    main()
