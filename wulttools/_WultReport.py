# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module includes the "report" 'wult' command implementation.
"""

from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error
from wultlibs.htmlreport import WultReport
from wultlibs import ToolsCommon
from wulttools import _WultCommon

def report_command(args):
    """Implements the 'report' command."""

    if args.report_size:
        if any({getattr(args, name) for name in ("xaxes", "yaxes", "hist", "chist")}):
            raise Error("'--size' and ('--xaxes', '--yaxes', '--hist', '--chist') options are "
                        "mutually exclusive, use either '--size' or the other options, not both")
        if args.report_size.lower() not in ("small", "medium", "large"):
            raise Error(f"bad '--size' value '{args.report_size}', use one of: small, medium, "
                        "large")

    # Split the comma-separated lists.
    for name in ("xaxes", "yaxes", "hist", "chist"):
        val = getattr(args, name)
        if val:
            if val == "none":
                setattr(args, name, "")
            else:
                setattr(args, name, Trivial.split_csv_line(val))
        elif args.report_size:
            size_default = _WultCommon.get_axes(name, args.report_size)
            if size_default:
                setattr(args, name, Trivial.split_csv_line(size_default))
            else:
                setattr(args, name, None)

    rsts = ToolsCommon.open_raw_results(args.respaths, args.toolname, reportids=args.reportids)

    if args.list_metrics:
        ToolsCommon.list_result_metrics(rsts)
        return

    for res in rsts:
        ToolsCommon.set_filters(args, res)

    if args.even_dpcnt:
        ToolsCommon.even_up_dpcnt(rsts)

    args.outdir = ToolsCommon.report_command_outdir(args, rsts)

    rep = WultReport.WultReport(rsts, args.outdir, title_descr=args.title_descr,
                                xaxes=args.xaxes, yaxes=args.yaxes, hist=args.hist,
                                chist=args.chist)
    rep.relocatable = args.relocatable
    rep.set_hover_metrics(_WultCommon.HOVER_METRIC_REGEXS)
    rep.generate()
