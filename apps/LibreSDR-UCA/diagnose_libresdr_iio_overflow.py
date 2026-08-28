#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: LibreSDR Four-Channel IIO Overflow Diagnostic
# Author: gr-doa LibreSDR research port
# Copyright: None
# Description: Streams both RX channels from both LibreSDRs directly into a null sink for a fixed interval. Any printed O is an IIO receive overflow independent of CFO correction, calibration, MUSIC, and GUI processing.
# GNU Radio version: v3.11.0.0git-1103-g14d6a758

from gnuradio import blocks
from gnuradio import blocks, gr
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


def snipfcn_pps_sync_after_start(self):
    doa.arm_libresdr_pps_sync(('ip:192.168.4.1', 'ip:192.168.5.1'))


def snippets_main_after_start(tb):
    snipfcn_pps_sync_after_start(tb)


class diagnose_libresdr_iio_overflow(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "LibreSDR Four-Channel IIO Overflow Diagnostic", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.test_seconds = test_seconds = 20
        self.samp_rate = samp_rate = int(525e3)
        self.rx_gain = rx_gain = 40
        self.rf_bandwidth = rf_bandwidth = int(2.8e6)
        self.center_freq = center_freq = int(700e6)

        ##################################################
        # Blocks
        ##################################################

        self.rate_messages = blocks.message_debug(False, gr.log_levels.info)
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
        self.bravo_rx2_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))
        self.bravo_rx1_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))
        self.alpha_rx2_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))
        self.alpha_rx1_rate = blocks.probe_rate(gr.sizeof_gr_complex*1, 2000.0, 0.25, "Alpha RX1 source-only rate")
        self.alpha_rx1_head = blocks.head(gr.sizeof_gr_complex*1, (int(test_seconds * samp_rate)))
        self.all_channels_sink = blocks.null_sink(gr.sizeof_gr_complex*1)


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.alpha_rx1_rate, 'rate'), (self.rate_messages, 'print'))
        self.connect((self.alpha_rx1_head, 0), (self.alpha_rx1_rate, 0))
        self.connect((self.alpha_rx2_head, 0), (self.all_channels_sink, 0))
        self.connect((self.bravo_rx1_head, 0), (self.all_channels_sink, 1))
        self.connect((self.bravo_rx2_head, 0), (self.all_channels_sink, 2))
        self.connect((self.libresdr_a, 0), (self.alpha_rx1_head, 0))
        self.connect((self.libresdr_a, 1), (self.alpha_rx2_head, 0))
        self.connect((self.libresdr_b, 0), (self.bravo_rx1_head, 0))
        self.connect((self.libresdr_b, 1), (self.bravo_rx2_head, 0))


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

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.libresdr_a.set_frequency(self.center_freq)
        self.libresdr_b.set_frequency(self.center_freq)




def main(top_block_cls=diagnose_libresdr_iio_overflow, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    snippets_main_after_start(tb)
    tb.wait()


if __name__ == '__main__':
    main()
