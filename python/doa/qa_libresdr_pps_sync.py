#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib.util
import os
import subprocess
import unittest
from unittest import mock


_MODULE_PATH = os.path.join(os.path.dirname(__file__), "libresdr_pps_sync.py")
_SPEC = importlib.util.spec_from_file_location("libresdr_pps_sync", _MODULE_PATH)
pps_sync = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pps_sync)


def _result(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["iio_attr"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class qa_libresdr_pps_sync(unittest.TestCase):
    def test_both_radios_arm_and_observe_external_edge(self):
        def invoke(uri, value=None, timeout=5.0):
            del uri, timeout
            if value == "arm":
                return _result("arm\n")
            return _result("dev 'cf-ad9361-lpc', attr 'sync_start_enable', value :'disarm'\n")

        with mock.patch.object(pps_sync, "_invoke_iio_attr", side_effect=invoke):
            self.assertTrue(pps_sync.arm_libresdr_pps_sync(
                ("ip:192.168.4.1", "ip:192.168.5.1"),
                trigger_timeout=0.2,
            ))

    def test_missing_pps_edge_is_rejected(self):
        def invoke(uri, value=None, timeout=5.0):
            del uri, value, timeout
            return _result("arm\n")

        with mock.patch.object(pps_sync, "_invoke_iio_attr", side_effect=invoke):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                pps_sync.arm_libresdr_pps_sync(
                    ("ip:192.168.4.1", "ip:192.168.5.1"),
                    trigger_timeout=0.02,
                )

    def test_iio_write_failure_is_rejected(self):
        def invoke(uri, value=None, timeout=5.0):
            del value, timeout
            if uri.endswith("5.1"):
                return _result(stderr="connection failed", returncode=1)
            return _result("arm\n")

        with mock.patch.object(pps_sync, "_invoke_iio_attr", side_effect=invoke):
            with self.assertRaisesRegex(RuntimeError, "could not be armed"):
                pps_sync.arm_libresdr_pps_sync(
                    ("ip:192.168.4.1", "ip:192.168.5.1")
                )


if __name__ == "__main__":
    unittest.main()
