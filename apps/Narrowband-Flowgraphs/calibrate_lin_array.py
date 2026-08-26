#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: calibrate linear array
# Author: jreitmei
# GNU Radio version: 3.10.12.0

def struct(data): return type('Struct', (object,), data)()
from gnuradio import blocks
from gnuradio import doa
from gnuradio import iio
import gnuradio.doa as doa
import os
import threading
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation




class calibrate_lin_array(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "calibrate linear array", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.input_variables = input_variables = struct({


            'SampleRate': 1e6,

            'CenterFreq': 2.495e9,

            'RxAddr': "addr=10.94.17.65",


            'NumArrayElements': 2,

            'NormSpacing': 0.1208,

            'SnapshotSize': 2**11,

            'OverlapSize': 2**10,

            'PilotAngle': 90,

            'DirectoryConfigFiles': "/tmp",

            'RelativePhaseOffsets': "measure_relative_phase_offsets_2495MHz.cfg",

            'AntennaCalibration': "calibration_lin_array_2495MHz.cfg",

            'Samples2Avg': 2**11,






        })
        self.samp_rate = samp_rate = int(2.8e6)
        self.rel_phase_offsets_file_name = rel_phase_offsets_file_name = os.path.join(input_variables.DirectoryConfigFiles, input_variables.RelativePhaseOffsets)
        self.freq = freq = int(1.24086e9)
        self.bandwidth = bandwidth = 2800000
        self.antenna_calibration_file_name = antenna_calibration_file_name = os.path.join(input_variables.DirectoryConfigFiles, input_variables.AntennaCalibration)

        ##################################################
        # Blocks
        ##################################################

        self.iio_fmcomms2_source_0 = iio.fmcomms2_source_fc32('ip:192.168.1.10', [True, True, True, True], 32768)
        self.iio_fmcomms2_source_0.set_len_tag_key('packet_len')
        self.iio_fmcomms2_source_0.set_frequency(freq)
        self.iio_fmcomms2_source_0.set_samplerate(samp_rate)
        if True:
            self.iio_fmcomms2_source_0.set_gain_mode(0, 'slow_attack')
            self.iio_fmcomms2_source_0.set_gain(0, 64)
        if True:
            self.iio_fmcomms2_source_0.set_gain_mode(1, 'slow_attack')
            self.iio_fmcomms2_source_0.set_gain(1, 64)
        self.iio_fmcomms2_source_0.set_quadrature(True)
        self.iio_fmcomms2_source_0.set_rfdc(True)
        self.iio_fmcomms2_source_0.set_bbdc(True)
        self.iio_fmcomms2_source_0.set_filter_params('Auto', '', 0, 0)
        self.doa_save_antenna_calib_0_0 = doa.save_antenna_calib(input_variables.NumArrayElements, antenna_calibration_file_name, input_variables.Samples2Avg)
        self.doa_phase_correct_hier_0_0 = doa.phase_correct_hier(num_ports=input_variables.NumArrayElements, config_filename=rel_phase_offsets_file_name)
        self.doa_calibrate_lin_array_0_0 = doa.calibrate_lin_array(input_variables.NormSpacing, input_variables.NumArrayElements, input_variables.PilotAngle)
        self.doa_autocorrelate_0_0 = doa.autocorrelate(input_variables.NumArrayElements, input_variables.SnapshotSize, input_variables.OverlapSize, 1)
        self.blocks_complex_to_magphase_0_0 = blocks.complex_to_magphase(input_variables.NumArrayElements)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.blocks_complex_to_magphase_0_0, 0), (self.doa_save_antenna_calib_0_0, 0))
        self.connect((self.blocks_complex_to_magphase_0_0, 1), (self.doa_save_antenna_calib_0_0, 1))
        self.connect((self.doa_autocorrelate_0_0, 0), (self.doa_calibrate_lin_array_0_0, 0))
        self.connect((self.doa_calibrate_lin_array_0_0, 0), (self.blocks_complex_to_magphase_0_0, 0))
        self.connect((self.doa_phase_correct_hier_0_0, 0), (self.doa_autocorrelate_0_0, 0))
        self.connect((self.doa_phase_correct_hier_0_0, 1), (self.doa_autocorrelate_0_0, 1))
        self.connect((self.iio_fmcomms2_source_0, 1), (self.doa_phase_correct_hier_0_0, 1))
        self.connect((self.iio_fmcomms2_source_0, 0), (self.doa_phase_correct_hier_0_0, 0))


    def get_input_variables(self):
        return self.input_variables

    def set_input_variables(self, input_variables):
        self.input_variables = input_variables

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.iio_fmcomms2_source_0.set_samplerate(self.samp_rate)

    def get_rel_phase_offsets_file_name(self):
        return self.rel_phase_offsets_file_name

    def set_rel_phase_offsets_file_name(self, rel_phase_offsets_file_name):
        self.rel_phase_offsets_file_name = rel_phase_offsets_file_name

    def get_freq(self):
        return self.freq

    def set_freq(self, freq):
        self.freq = freq
        self.iio_fmcomms2_source_0.set_frequency(self.freq)

    def get_bandwidth(self):
        return self.bandwidth

    def set_bandwidth(self, bandwidth):
        self.bandwidth = bandwidth

    def get_antenna_calibration_file_name(self):
        return self.antenna_calibration_file_name

    def set_antenna_calibration_file_name(self, antenna_calibration_file_name):
        self.antenna_calibration_file_name = antenna_calibration_file_name




def main(top_block_cls=calibrate_lin_array, options=None):
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
