#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: B210 Dual-Channel Calibration and Target TX
# Author: Ettus Research; LibreSDR UCA configuration
# Copyright: None
# Description: TX/RX0 sends the fixed +50 kHz calibration pilot; TX/RX1 sends the movable +150 kHz direction-finding target. Both use 40 dB gain.
# GNU Radio version: v3.11.0.0git-1103-g14d6a758

def struct(data): return type('Struct', (object,), data)()
from gnuradio import analog
from gnuradio import uhd
import time
import threading
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation




class run_DoA_transmitter(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "B210 Dual-Channel Calibration and Target TX", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.input_variables = input_variables = struct({

            'PilotToneFreq': 50e3,

            'SampleRate': 1e6,

            'CenterFreq': 700e6,

            'TxAddr': "serial=310C4AE",

            'Gain': 40,

            'TargetToneFreq': 150e3,














        })

        ##################################################
        # Blocks
        ##################################################

        self.uhd_usrp_sink_0 = uhd.usrp_sink(
            ",".join((input_variables.TxAddr, "")),
            uhd.stream_args(
                cpu_format="fc32",
                args='',
                channels=[0, 1],
            ),
            '',
        )
        self.uhd_usrp_sink_0.set_clock_source('internal', 0)
        self.uhd_usrp_sink_0.set_samp_rate(input_variables.SampleRate)
        self.uhd_usrp_sink_0.set_time_unknown_pps(uhd.time_spec(0))

        self.uhd_usrp_sink_0.set_center_freq(input_variables.CenterFreq, 0)
        self.uhd_usrp_sink_0.set_antenna("TX/RX", 0)
        self.uhd_usrp_sink_0.set_gain(input_variables.Gain, 0)

        self.uhd_usrp_sink_0.set_center_freq(input_variables.CenterFreq, 1)
        self.uhd_usrp_sink_0.set_antenna("TX/RX", 1)
        self.uhd_usrp_sink_0.set_gain(input_variables.Gain, 1)
        self.analog_sig_source_x_1 = analog.sig_source_c(input_variables.SampleRate, analog.GR_SIN_WAVE, input_variables.TargetToneFreq, 1, 0, 0)
        self.analog_sig_source_x_0 = analog.sig_source_c(input_variables.SampleRate, analog.GR_SIN_WAVE, input_variables.PilotToneFreq, 1, 0, 0)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_sig_source_x_0, 0), (self.uhd_usrp_sink_0, 0))
        self.connect((self.analog_sig_source_x_1, 0), (self.uhd_usrp_sink_0, 1))


    def get_input_variables(self):
        return self.input_variables

    def set_input_variables(self, input_variables):
        self.input_variables = input_variables




def main(top_block_cls=run_DoA_transmitter, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
