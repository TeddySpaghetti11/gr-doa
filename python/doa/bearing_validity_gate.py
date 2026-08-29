#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Replace invalid direction estimates with an explicit NaN marker."""

# Copyright 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import threading

import numpy
import pmt
from gnuradio import gr


class bearing_validity_gate(gr.sync_block):
    """Pass bearing vectors only when the covariance carries a valid tag.

    The validity-aware covariance block emits one boolean tag per covariance
    matrix. Invalid estimates are represented as NaN rather than a plausible
    compass bearing, so GUI sinks cannot silently display stale-looking data.
    """

    def __init__(self, vector_length=1, validity_tag_key="doa_valid"):
        if vector_length < 1:
            raise ValueError("Bearing vector length must be positive")
        if not validity_tag_key:
            raise ValueError("Validity tag key must not be empty")

        self.vector_length = int(vector_length)
        self.validity_tag_key = str(validity_tag_key)
        self._valid = False
        self._lock = threading.Lock()

        gr.sync_block.__init__(
            self,
            name="Bearing Validity Gate",
            in_sig=[(numpy.float32, self.vector_length)],
            out_sig=[(numpy.float32, self.vector_length)],
        )

    def valid(self):
        with self._lock:
            return self._valid

    def work(self, input_items, output_items):
        item_count = min(len(input_items[0]), len(output_items[0]))
        source = input_items[0][:item_count]
        destination = output_items[0][:item_count]
        destination[:] = source

        absolute_start = self.nitems_read(0)
        tags = self.get_tags_in_range(
            0,
            absolute_start,
            absolute_start + item_count,
            pmt.intern(self.validity_tag_key),
        )
        tags.sort(key=lambda tag: tag.offset)

        cursor = 0
        with self._lock:
            valid = self._valid
            for tag in tags:
                event_cursor = max(cursor, int(tag.offset) - absolute_start)
                if not valid:
                    destination[cursor:event_cursor] = numpy.nan
                cursor = event_cursor
                valid = bool(pmt.to_bool(tag.value))
            if not valid:
                destination[cursor:item_count] = numpy.nan
            self._valid = valid

        return item_count

