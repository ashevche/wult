# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Adam Hawley <adam.james.hawley@intel.com>

"""
This module provides the capability of populating a statistic tab.
"""

import logging

from pepclibs.helperlibs.Exceptions import Error
from wultlibs.htmlreport import _SummaryTable, _ScatterPlot, _Histogram
from wultlibs import DFSummary
from wultlibs.htmlreport.tabs import _BaseTab

_LOG = logging.getLogger()


class StatsTab(_BaseTab.BaseTabDC):
    """
    This class defines what is expected by the JavaScript side when adding a statistics tab to HTML
    reports.
    """

class StatsTabBuilder:
    """
    This base class provides the capability of populating a statistics tab.

    Public methods overview:
    1. Generate an 'StatsTab' instance containing plots and a summary table which represent all
       of the statistics found during initialisation.
       * 'get_tab()'
    """

    def _prepare_smrys_tbl(self):
        """Construct a 'SummaryTable' to summarise the statistics added with '_add_stats()'."""

        smrytbl = _SummaryTable.SummaryTable()

        smrytbl.add_metric(self.title, self._metric_defs["short_unit"], self.descr,
                           fmt="{:.2f}")

        for rep, df in self._reports.items():
            smry_dict = DFSummary.calc_col_smry(df, self._metric_colname, self.smry_funcs)
            for fname in self.smry_funcs:
                smrytbl.add_smry_func(rep, self.title, fname, smry_dict[fname])

        smrytbl.generate(self.smry_path)

    def get_tab(self):
        """
        Returns a 'StatsTab' instance which contains an aggregate of all of the statistics found
        in 'stats_paths', provided to the class constructor. This 'StatsTab' can then be used to
        populate an HTML tab.
        """

        plotpaths = []
        for plot in self._plots:
            plot.generate()
            plotpaths.append(plot.outpath.relative_to(self._basedir))

        try:
            self._prepare_smrys_tbl()
        except Exception as err:
            raise Error(f"failed to generate summary table: {err}") from None

        return StatsTab(self.title, plotpaths, self.smry_path.relative_to(self._basedir))

    def _init_plots(self):
        """
        Initialise the plots and populate them using the pandas Dataframe objects in
        'self._reports'.
        """

        self._plots = []

        # Initialise scatter plot.
        s_path = self._outdir / f"{self.name}-scatter.html"
        s = _ScatterPlot.ScatterPlot(self._time_colname, self._metric_colname, s_path,
                                     self._time_defs["title"], self._metric_defs["title"],
                                     self._time_defs["short_unit"], self._metric_defs["short_unit"])

        for reportid, df in self._reports.items():
            s.add_df(s.reduce_df_density(df, reportid), reportid)

        self._plots.append(s)

        # Initialise histogram.
        h_path = self._outdir / f"{self.name}-histogram.html"
        h = _Histogram.Histogram(self._metric_colname, h_path, self._metric_defs["title"],
                                 self._metric_defs["short_unit"])

        for reportid, df in self._reports.items():
            h.add_df(df, reportid)

        self._plots.append(h)

    def __init__(self, reports, outdir, basedir, metric_name, metric_colname, time_colname, defs):
        """
        The class constructor. Adding a stats tab will create a 'metricname' sub-directory and
        store plots and the summary table in it. Arguments are as follows:
         * reports - dictionary containing the statistics data for each report:
                     '{reportid: stats_df}'
         * outdir - the output directory in which to create the 'metricname' sub-directory.
         * basedir - base directory of the report. All paths should be made relative to this.
         * metric_name - name of the metric to create the tab for.
         * metric_colname - name of the column in the 'stats_df's which contains data for
                           'metricname'.
         * time_colname - name of the column in the 'stats_df's which represents the elpased time.
         * defs - dictionary containing the definitions for this metric.
        """

        # File system-friendly tab name.
        self.name = metric_name
        self._basedir = basedir
        self._outdir = outdir / self.name
        self.smry_path = self._outdir / "summary-table.txt"

        try:
            self._outdir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise Error(f"failed to create directory '{self._outdir}': {err}") from None

        self._metric_defs = defs[self.name]
        self._metric_colname = metric_colname
        self._time_defs = defs["Time"]
        self._time_colname = time_colname
        self.title = self._metric_defs["title"]
        self.descr = self._metric_defs["descr"]
        self.smry_funcs = self._metric_defs["default_funcs"]

        # Reduce 'reports' to only the metric and time columns which are needed for this tab.
        self._reports = {}
        for reportid, df in reports.items():
            if self._metric_colname in df:
                self._reports[reportid] = df[[self._metric_colname, self._time_colname]].copy()

        if not self._reports:
            raise Error(f"failed to generate '{self.name}' tab: no data under column"
                        f"'{self._metric_colname}' provided.")


        self._plots = []
        try:
            self._init_plots()
        except Exception as err:
            raise Error(f"failed to initialise plots: {err}") from None