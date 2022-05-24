# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Vladislav Govtva <vladislav.govtva@intel.com>

"""
This module provides the base class for generating HTML reports for raw test results.
"""

import dataclasses
import itertools
import json
import logging
from pathlib import Path
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound
from wultlibs import Deploy
from wultlibs.helperlibs import FSHelpers
from wultlibs.htmlreport import _IntroTable
from wultlibs.htmlreport.tabs import _MetricDTabBuilder, _Tabs
from wultlibs.htmlreport.tabs.stats import _ACPowerTabBuilder, _IPMITabBuilder
from wultlibs.htmlreport.tabs.stats.turbostat import _TurbostatTabBuilder

_LOG = logging.getLogger()

class ReportBase:
    """This is the base class for generating HTML reports for raw test results."""

    @staticmethod
    def _dump_json(obj, path, descr):
        """
        Helper function wrapping 'json.dump' operation with a standardised error message so that the
        error messages are consistent. Arguments are as follows:
         * obj - Python object to dump to JSON.
         * path - path to create JSON file at.
         * descr - description of object being dumped.
        """
        try:
            with open(path, "w", encoding="utf-8") as fobj:
                json.dump(obj, fobj, default=str)
        except Exception as err:
            raise Error(f"could not generate report: failed to JSON dump '{descr}' to '{path}':"
                        f"{err}") from None

    def _add_intro_tbl_links(self, label, paths):
        """
        Add links in 'paths' to the 'intro_tbl' dictionary. Arguments are as follows:
            * paths - dictionary in the format {Report ID: Path to Link to}.
            * label - the label that will be shown in the intro table for these links.
        """

        valid_paths = {}
        for res in self.rsts:
            reportid = res.reportid
            path = paths.get(reportid)

            # Do not add links for 'label' if 'paths' does not contain a link for every result or
            # if a path points to somewhere outside of the report directory.
            if path is None or self.outdir not in path.parents:
                return

            # If the path points to inside the report directory then make it relative to the output
            # directory so that the output directory is relocatable. That is, the whole directory
            # can be moved or copied without breaking the link.
            valid_paths[reportid] = path.relative_to(self.outdir)

        row = self._intro_tbl.create_row(label)

        for reportid, path in valid_paths.items():
            row.add_cell(reportid, label, link=path)

    def _prepare_intro_table(self, stats_paths, logs_paths):
        """
        Create the intro table, which is the very first table in the report and it shortly
        summarizes the entire report. The 'stats_paths' should be a dictionary indexed by report ID
        and containing the stats directory path. Similarly, the 'logs_paths' contains paths to the
        logs. Returns the path of the intro table file generated.
        """
        # Add tool information.
        tinfo_row = self._intro_tbl.create_row("Data Collection Tool")
        for res in self.rsts:
            tool_info = f"{res.info['toolname'].capitalize()} version {res.info['toolver']}"
            tinfo_row.add_cell(res.reportid, tool_info)

        # Add run date.
        date_row = self._intro_tbl.create_row("Collection Date")
        for res in self.rsts:
            date_row.add_cell(res.reportid, res.info.get("date"))

        # Add datapoint counts.
        dcount_row = self._intro_tbl.create_row("Datapoints Count")
        for res in self.rsts:
            dcount_row.add_cell(res.reportid, len(res.df.index))

        # Add measurement resolution.
        if all("resolution" in res.info for res in self.rsts):
            dres_row = self._intro_tbl.create_row("Device Resolution")
            for res in self.rsts:
                dres_row.add_cell(res.reportid, f"{res.info['resolution']}ns")

        # Add measured CPU.
        mcpu_row = self._intro_tbl.create_row("Measured CPU")
        for res in self.rsts:
            cpunum = res.info.get("cpunum")
            if cpunum is not None:
                cpunum = str(cpunum)

            mcpu_row.add_cell(res.reportid, cpunum)

        # Add links to the stats directories.
        self._add_intro_tbl_links("Statistics", stats_paths)
        # Add links to the logs directories.
        self._add_intro_tbl_links("Logs", logs_paths)

        intro_tbl_path = self.outdir / "intro_table.txt"
        self._intro_tbl.generate(intro_tbl_path)

        return intro_tbl_path.relative_to(self.outdir)

    def _copy_raw_data(self):
        """Copy raw test results to the output directory."""

        # Paths to the stats directory.
        stats_paths = {}
        # Paths to the logs directory.
        logs_paths = {}

        for res in self.rsts:
            resdir = res.dirpath

            if self.relocatable:
                dstpath = self.outdir / f"raw-{res.reportid}"
                try:
                    FSHelpers.copy_dir(resdir, dstpath, exist_ok=True, ignore=["html-report"])
                    FSHelpers.set_default_perm(dstpath)
                except Error as err:
                    raise Error(f"failed to copy raw data to report directory: {err}") from None

                # Use the path of the copied raw results rather than the original.
                resdir = dstpath

            if res.stats_path.is_dir():
                stats_paths[res.reportid] = resdir / res.stats_path.name
            else:
                stats_paths[res.reportid] = None

            if res.logs_path.is_dir():
                logs_paths[res.reportid] = resdir / res.logs_path.name
            else:
                logs_paths[res.reportid] = None

        return stats_paths, logs_paths

    def _copy_asset(self, src, descr, dst):
        """
        Copy asset file to the output directory. Arguments are as follows:
         * src - source path of the file to copy.
         * descr - description of the file which is being copied.
         * dst - where the file should be copied to.
        """

        asset_path = Deploy.find_app_data(self._projname, src, descr=descr)
        FSHelpers.move_copy_link(asset_path, dst, "copy", exist_ok=True)

    def _generate_results_tabs(self):
        """
        Generate and return a list of sub-tabs for the results tab. The results tab includes the
        main metrics, such as "WakeLatency". The elements of the returned list are tab dataclass
        objects, such as 'DTabDC'.
        """

        for res in self.rsts:
            _LOG.debug("calculate summary functions for '%s'", res.reportid)
            res.calc_smrys(regexs=self._smry_metrics, funcnames=self._smry_funcs)

        plot_axes = [(x, y) for x, y in itertools.product(self.xaxes, self.yaxes) if x != y]

        if self.exclude_xaxes and self.exclude_yaxes:
            x_axes = self._refres.find_colnames([self.exclude_xaxes])
            y_axes = self._refres.find_colnames([self.exclude_yaxes])
            exclude_axes = list(itertools.product(x_axes, y_axes))
            plot_axes = [axes for axes in plot_axes if axes not in exclude_axes]

        dtabs = []
        tab_metrics = [y for _, y in plot_axes]
        tab_metrics += self.chist + self.hist
        tab_metrics = Trivial.list_dedup(tab_metrics)

        for metric in tab_metrics:
            _LOG.info("Generating %s tab.", metric)

            tab_plots = []
            smry_metrics = []
            for axes in plot_axes:
                if metric in axes:
                    # Only add plots which have the tab metric on one of the axes.
                    tab_plots.append(axes)
                    # Only add metrics shown in the diagrams to the summary table.
                    smry_metrics += axes

            smry_metrics = Trivial.list_dedup(smry_metrics)

            metric_def = self._refres.defs.info[metric]
            dtab_bldr = _MetricDTabBuilder.MetricDTabBuilder(self.rsts, self.outdir, metric_def,
                                                             hover_metrics=self._hov_metrics)
            dtab_bldr.add_smrytbl(smry_metrics, self._smry_funcs)
            dtab_bldr.add_plots(tab_plots, self.hist, self.chist)
            dtabs.append(dtab_bldr.get_tab())

        return dtabs

    def _generate_stats_tabs(self, stats_paths):
        """
        Generate and return a list sub-tabs for the statistics tab. The statistics tab includes
        metrics from the statistics collectors, such as 'turbostat'.

        The 'stats_paths' argument is a dictionary mapping in the following format:
           {Report ID: Stats directory path}
        where "stats directory path" is the directory containing raw statistics files.

        The elements of the returned list are tab dataclass objects, such as 'CTabDC'.
        """

        _LOG.info("Generating statistics tabs.")

        mcpus = {res.reportid: str(res.info["cpunum"]) for res in self.rsts if "cpunum" in res.info}

        tab_builders = {
            _ACPowerTabBuilder.ACPowerTabBuilder: {},
            _TurbostatTabBuilder.TurbostatTabBuilder: {"measured_cpus": mcpus},
            _IPMITabBuilder.IPMITabBuilder: {}
        }

        tabs = []

        for tab_builder, args in tab_builders.items():
            try:
                tbldr = tab_builder(stats_paths, self.outdir, **args)
            except ErrorNotFound as err:
                _LOG.info("Skipping '%s' tab as '%s' statistics not found for all reports.",
                          tab_builder.name, tab_builder.name)
                _LOG.debug(err)
                continue

            _LOG.info("Generating '%s' tab.", tbldr.name)
            try:
                tabs.append(tbldr.get_tab())
            except Error as err:
                _LOG.info("Skipping '%s' statistics: error occurred during tab generation.",
                          tab_builder.name)
                _LOG.debug(err)
                continue

        return tabs

    def _generate_report(self):
        """Put together the final HTML report."""

        _LOG.info("Generating the HTML report.")

        # Make sure the output directory exists.
        try:
            self.outdir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise Error(f"failed to create directory '{self.outdir}': {err}") from None

        # Copy raw data and assets.
        stats_paths, logs_paths = self._copy_raw_data()
        for src, descr in self._assets:
            self._copy_asset(Path(src), descr, self.outdir / src)

        # 'report_info' stores data used by the Javascript to generate the main report page
        # including the intro table, the file path of the tabs JSON dump and the toolname.
        report_info = {}
        report_info["intro_tbl"] = self._prepare_intro_table(stats_paths, logs_paths)
        report_info["toolname"] = self._refinfo["toolname"].title()

        results_tabs = self._generate_results_tabs()

        try:
            stats_tabs = self._generate_stats_tabs(stats_paths)
        except Error as err:
            _LOG.info("Error occurred during statistics tabs generation: %s", err)
            stats_tabs = []

        tabs = []
        # Convert Dataclasses to dictionaries so that they are JSON serialisable.
        tabs.append(dataclasses.asdict(_Tabs.CTabDC("Results", results_tabs)))

        if stats_tabs:
            tabs.append(dataclasses.asdict(_Tabs.CTabDC("Stats", tabs=stats_tabs)))
        else:
            _LOG.info("All statistics have been skipped therefore the report will not contain a "
                      "'Stats' tab.")

        tabs_path = self.outdir / "tabs.json"
        self._dump_json(tabs, tabs_path, "tab container")

        report_info["tab_file"] = str(tabs_path.relative_to(self.outdir))
        rinfo_path = self.outdir / "report_info.json"
        self._dump_json(report_info, rinfo_path, "report information dictionary")

        self._copy_asset("js/index.html", "root HTML page of the report.",
                         self.outdir / "index.html")

    def _mangle_loaded_res(self, res):
        """
        This method is called for every 'pandas.DataFrame' corresponding to the just loaded CSV
        file. The subclass can override this method to mangle the 'pandas.DataFrame'.
        """

        for metric in res.df:
            defs = res.defs.info.get(metric)
            if not defs:
                continue

            # Some columns should be dropped from 'res.df' if they are "empty", i.e. contain only
            # zero values. For example, the C-state residency columns may be empty. This usually
            # means that the C-state was either disabled or just does not exist.
            if defs.get("drop_empty") and not res.df[metric].any():
                _LOG.debug("dropping empty column '%s'", metric)
                res.df.drop(metric, axis="columns", inplace=True)

        # Update metric lists in case some of the respective columns were removed from the loaded
        # 'pandas.Dataframe'.
        for name in ("_smry_metrics", "xaxes", "yaxes", "hist", "chist"):
            metrics = []
            for metric in getattr(self, name):
                if metric in res.df:
                    metrics.append(metric)
            setattr(self, name, metrics)

        for name in ("_hov_metrics", ):
            metrics = []
            val = getattr(self, name)
            for metric in val[res.reportid]:
                if metric in res.df:
                    metrics.append(metric)
            val[res.reportid] = metrics
        return res.df

    def _load_results(self):
        """Load the test results from the CSV file and/or apply the columns selector."""

        _LOG.debug("summaries will be calculated for these columns: %s",
                   ", ".join(self._smry_metrics))
        _LOG.debug("additional colnames: %s", ", ".join(self._more_colnames))

        for res in self.rsts:
            _LOG.debug("hover metrics: %s", ", ".join(self._hov_metrics[res.reportid]))

            metrics = []
            for metric in self._hov_metrics[res.reportid] + self._more_colnames:
                if metric in res.colnames_set:
                    metrics.append(metric)

            csel = Trivial.list_dedup(self._smry_metrics + metrics)
            res.set_csel(csel)
            res.load_df()

            # We'll be dropping columns and adding temporary columns, so we'll affect the original
            # 'pandas.DataFrame'. This is more efficient than creating copies.
            self._mangle_loaded_res(res)

        # Some columns from the axes lists could have been dropped, update the lists.
        self._drop_absent_colnames()

    def generate(self):
        """Generate the HTML report and store the result in 'self.outdir'.

        Important note: this method will modify the input test results in 'self.rsts'. This is done
        for effeciency purposes, to avoid copying the potentially large amounts of data
        (instances of 'pandas.DataFrame').
        """

        # Load the required datapoints into memory.
        self._load_results()

        # Put together the final HTML report.
        self._generate_report()

    def set_hover_metrics(self, regexs):
        """
        This methods allows for specifying metrics that have to be included to the hover text on the
        scatter plot. The 'regexs' argument should be a list of hover text metric regular
        expressions. In other words, each element of the list will be treated as a regular
        expression. Every metric will be matched against this regular expression, and matched
        metrics will be added to the hover text.
        """

        for res in self.rsts:
            self._hov_metrics[res.reportid] = res.find_colnames(regexs, must_find_any=False)

    def _drop_absent_colnames(self):
        """
        Verify that test results provide the columns in 'xaxes', 'yaxes', 'hist' and 'chist'. Drop
        the absent columns. Also drop uknown columns (those not present in the "definitions").
        """

        lists = ("xaxes", "yaxes", "hist", "chist")

        for name in lists:
            intersection = set(getattr(self, name))
            for res in self.rsts:
                intersection = intersection & res.colnames_set
            metrics = []
            for metric in getattr(self, name):
                if metric in intersection:
                    metrics.append(metric)
                else:
                    _LOG.warning("dropping column '%s' from '%s' because it is not present in one "
                                 "of the results", metric, name)
            setattr(self, name, metrics)

        for name in lists:
            for res in self.rsts:
                metrics = []
                for metric in getattr(self, name):
                    if metric in res.defs.info:
                        metrics.append(metric)
                    else:
                        _LOG.warning("dropping column '%s' from '%s' because it is not present in "
                                     "the definitions file at '%s'", metric, name, res.defs.path)
            setattr(self, name, metrics)

        for res in self.rsts:
            metrics = []
            for metric in self._hov_metrics[res.reportid]:
                if metric in res.defs.info:
                    metrics.append(metric)
                else:
                    _LOG.warning("dropping metric '%s' from hover text because it is not present "
                                 "in the definitions file at '%s'", metric, res.defs.path)
            self._hov_metrics[res.reportid] = metrics

    def _init_colnames(self):
        """
        Assign default values to the diagram/histogram metrics and remove possible duplication in
        user-provided input.
        """

        for name in ("xaxes", "yaxes", "hist", "chist"):
            if getattr(self, name):
                # Convert list of regular expressions into list of names.
                colnames = self._refres.find_colnames(getattr(self, name))
            else:
                colnames = []
            setattr(self, name, colnames)

        # Ensure '_hov_metrics' dictionary is initialized.
        self.set_hover_metrics(())

        self._drop_absent_colnames()

        # Both X- and Y-axes are required for scatter plots.
        if not self.xaxes or not self.yaxes:
            self.xaxes = self.yaxes = []

    def _init_assets(self):
        """
        'Assets' are the CSS and JS files which supplement the HTML which makes up the report.
        'self._assets' defines the assets which should be copied into the output directory. The list
        is in the format: (path_to_asset, asset_description).
        """

        self._assets = [
            ("js/dist/main.js", "bundled JavaScript"),
            ("js/dist/main.css", "bundled CSS"),
            ("js/dist/main.js.LICENSE.txt", "bundled dependency licenses"),
        ]

    def _validate_init_args(self):
        """Validate the class constructor input arguments."""

        if self.outdir.exists() and not self.outdir.is_dir():
            raise Error(f"path '{self.outdir}' already exists and it is not a directory")

        # Ensure that results are compatible.
        rname, rver = self._refinfo["toolname"], self._refinfo["toolver"]
        for res in self.rsts:
            name, ver = res.info["toolname"], res.info["toolver"]
            if name != rname:
                raise Error(f"the following test results are not compatible:\n"
                            f"1. {self._refres.dirpath}: created by '{rname}'\n"
                            f"2. {res.dirpath}: created by '{name}'\n"
                            f"Cannot put incompatible results to the same report")
            if ver != rver:
                _LOG.warning("the following test results may be not compatible:\n"
                             "1. %s: created by '%s' version '%s'\n"
                             "2. %s: created by '%s' version '%s'",
                             self._refres.dirpath, rname, rver, res.dirpath, name, ver)

        # Ensure the report IDs are unique.
        reportids = set()
        for res in self.rsts:
            reportid = res.reportid
            if reportid in reportids:
                # Try to construct a unique report ID.
                for idx in range(1, 20):
                    new_reportid = f"{reportid}-{idx:02}"
                    if new_reportid not in reportids:
                        _LOG.warning("duplicate reportid '%s', using '%s' instead",
                                     reportid, new_reportid)
                        res.reportid = new_reportid
                        break
                else:
                    raise Error(f"too many duplicate report IDs, e.g., '{reportid}' is problematic")

            reportids.add(res.reportid)

        if self.title_descr and Path(self.title_descr).is_file():
            try:
                with open(self.title_descr, "r", encoding="UTF-8") as fobj:
                    self.title_descr = fobj.read()
            except OSError as err:
                raise Error(f"failed to read the report description file {self.title_descr}:\n"
                            f"{err}") from err

        for res in self.rsts:
            if res.dirpath.resolve() == self.outdir.resolve():
                # Don't create report in results directory, use 'html-report' subdirectory instead.
                self.outdir = self.outdir.joinpath("html-report")

    def __init__(self, rsts, outdir, title_descr=None, xaxes=None, yaxes=None, hist=None,
                 chist=None, exclude_xaxes=None, exclude_yaxes=None):
        """
        The class constructor. The arguments are as follows.
          * rsts - list of 'RORawResult' objects representing the raw test results to generate the
                   HTML report for.
          * outdir - the output directory path to store the HTML report at.
          * title_descr - a string describing this report or a file path containing the description.
          *               The description will be put at the top part of the HTML report. It should
          *               describe the report in general (e.g., it compares platform A to platform
          *               B). By default no title description is added to the HTML report.
          * xaxes - list of regular expressions matching datapoints CSV file column names to use for
                    the X axis of scatter plot diagrams. A scatter plot will be generated for each
                    combination of 'xaxes' and 'yaxes' column name pair (except for the pairs in
                    'exclude_xaxes'/'exclude_yaxes'). Default is the first column in the datapoints
                    CSV file.
          * yaxes - list of regular expressions matching datapoints CSV file column names to use for
                    the Y axis of scatter plot diagrams. Default is the second column in the
                    datapoints CSV file.
          * hist - list of regular expressions matching datapoints CSV file column names to create a
                   histogram for. Default is the first column in the datapoints CSV file. An empty
                   string can be used to disable histograms.
          * chist - list of regular expressions matching datapoints CSV file column names to create
                    a cumulative histogram for. Default is he first column in the datapoints CSV
                    file. An empty string can be used to disable cumulative histograms.
          * exclude_xaxes - by default all diagrams of X- vs Y-axes combinations will be created.
                            The 'exclude_xaxes' is a list regular expressions matching datapoints
                            CSV file column names. There will be no scatter plot for each
                            combinations of 'exclude_xaxes' and 'exclude_yaxes'. In other words,
                            this argument along with 'exclude_yaxes' allows for excluding some
                            diagrams from the 'xaxes' and 'yaxes' combinations.
          * exclude_yaxes - same as 'exclude_xaxes', but for Y-axes.
        """

        self.rsts = rsts
        self.outdir = Path(outdir)
        self.title_descr = title_descr
        self.xaxes = xaxes
        self.yaxes = yaxes
        self.exclude_xaxes = exclude_xaxes
        self.exclude_yaxes = exclude_yaxes
        self.hist = hist
        self.chist = chist

        self._projname = "wult"

        # Users can change this to 'True' to make the reports relocatable. In which case the raw
        # results files will be copied from the test result directories to the output directory.
        self.relocatable = False

        # The first result is the 'reference' result.
        self._refres = rsts[0]
        # The raw reference result information.
        self._refinfo = self._refres.info

        # The intro table which appears at the top of all reports.
        self._intro_tbl = _IntroTable.IntroTable()

        # Names of metrics to provide the summary function values for (e.g., median, 99th
        # percentile). The summaries will show up in the summary tables (one table per metric).
        self._smry_metrics = None
        # List of functions to provide in the summary tables.
        self._smry_funcs = ("nzcnt", "max", "99.999%", "99.99%", "99.9%", "99%", "med", "avg",
                            "min", "std")
        # Per-test result list of metrics to include into the hover text of the scatter plot.
        # By default only the x and y axis values are included.
        self._hov_metrics = {}
        # Additional columns to load, if they exist in the CSV file.
        self._more_colnames = []

        self._validate_init_args()
        self._init_colnames()

        # We'll provide summaries for every metric participating in at least one diagram.
        smry_metrics = Trivial.list_dedup(self.yaxes + self.xaxes + self.hist + self.chist)
        # Summary table includes all test results, but the results may have data for different
        # metrics (e.g. they were collected with different wult versions, using different methods,
        # or on different systems). Therefore, only include metrics common to all test results.
        self._smry_metrics = []
        for metric in smry_metrics:
            for res in rsts:
                if metric not in res.colnames_set:
                    break
            else:
                self._smry_metrics.append(metric)

        self._init_assets()

        if (self.exclude_xaxes and not self.exclude_yaxes) or \
           (self.exclude_yaxes and not self.exclude_xaxes):
            raise Error("'exclude_xaxes' and 'exclude_yaxes' must both be 'None' or both not be "
                        "'None'")
