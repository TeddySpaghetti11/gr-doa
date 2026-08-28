#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Arm and verify the LibreSDR external-PPS ADC synchronizer."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from concurrent.futures import ThreadPoolExecutor
import re
import subprocess
import time


_DEVICE = "cf-ad9361-lpc"
_ATTRIBUTE = "sync_start_enable"
_VALUE_PATTERN = re.compile(r"value\s*:\s*'([^']+)'")


def _invoke_iio_attr(uri, value=None, timeout=5.0):
    command = [
        "iio_attr",
        "-T",
        str(max(1, int(float(timeout) * 1000.0))),
        "-u",
        str(uri),
        "-d",
        _DEVICE,
        _ATTRIBUTE,
    ]
    if value is not None:
        command.append(str(value))
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=float(timeout) + 1.0,
    )


def _read_state(uri, timeout):
    result = _invoke_iio_attr(uri, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{uri}: unable to read PPS sync state: {detail}")

    output = result.stdout.strip()
    match = _VALUE_PATTERN.search(output)
    state = match.group(1) if match else output
    if state not in ("arm", "disarm"):
        raise RuntimeError(
            f"{uri}: unrecognized PPS sync state returned by iio_attr: {output!r}"
        )
    return state


def arm_libresdr_pps_sync(uris, trigger_timeout=2.5, command_timeout=5.0):
    """Arm multiple LibreSDRs and require a common external sync pulse.

    The calls are issued concurrently so every radio is waiting before the
    next one-PPS edge. ADI's ``sync_start_enable`` attribute automatically
    returns to ``disarm`` after the FPGA observes that edge.
    """
    uris = tuple(str(uri) for uri in uris)
    if len(uris) < 2:
        raise ValueError("PPS synchronization requires at least two LibreSDRs")
    if trigger_timeout <= 0.0 or command_timeout <= 0.0:
        raise ValueError("PPS synchronization timeouts must be positive")

    print(
        "LibreSDR PPS sync: arming "
        + ", ".join(uris)
        + "; waiting for the shared 1 PPS edge"
    )
    with ThreadPoolExecutor(max_workers=len(uris)) as executor:
        results = list(executor.map(
            lambda uri: _invoke_iio_attr(
                uri, value="arm", timeout=command_timeout
            ),
            uris,
        ))

    failures = []
    for uri, result in zip(uris, results):
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            failures.append(f"{uri}: {detail}")
    if failures:
        raise RuntimeError(
            "LibreSDR PPS sync could not be armed: " + "; ".join(failures)
        )

    deadline = time.monotonic() + float(trigger_timeout)
    states = ["unknown"] * len(uris)
    while time.monotonic() < deadline:
        with ThreadPoolExecutor(max_workers=len(uris)) as executor:
            states = list(executor.map(
                lambda uri: _read_state(uri, command_timeout), uris
            ))
        if all(state == "disarm" for state in states):
            print(
                "LibreSDR PPS SYNC CONFIRMED: every receiver observed the "
                "external edge; startup settling may proceed"
            )
            return True
        time.sleep(0.05)

    raise RuntimeError(
        "LibreSDR PPS sync timed out waiting for the external edge; states: "
        + ", ".join(f"{uri}={state}" for uri, state in zip(uris, states))
        + ". Check the 1 PPS source, distribution outputs, cabling, and input "
        "voltage levels. Bearings must not be trusted without synchronization."
    )
