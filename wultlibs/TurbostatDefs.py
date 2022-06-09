# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to turbostat metrics definitions (AKA 'defs').
"""

from wultlibs import _DefsBase

def is_reqcs_metric(metric):
    """
    Returns 'True' or 'False' based on whether 'metric' is a metric which represents a requestable
    C-state.
    """

    return metric.startswith("C") and metric[1].isdigit() and metric.endswith("%")

def is_hwcs_metric(metric):
    """
    Returns 'True' or 'False' based on whether 'metric' is a metric which represents a hardware
    C-state.
    """

    return metric.startswith("CPU%")

def is_pkgcs_metric(metric):
    """
    Returns 'True' or 'False' based on whether 'metric' is a metric which represents a hardware
    package C-state.
    """

    return metric.startswith("Pkg%")

class TurbostatDefs(_DefsBase.DefsBase):
    """This module provides API to turbostat metrics definitions (AKA 'defs')."""

    def __init__(self, cstates):
        """
        The class constructor. Arguments are as follows:
         * cstates - a list of C-states parsed from raw turbostat statistic files.
        """

        super().__init__("turbostat")

        placeholders_info = [{"values": cstates, "placeholder": "Cx"},
                             {"values": [cs.lower() for cs in cstates], "placeholder": "cx"}]
        self._mangle_placeholders(placeholders_info)
