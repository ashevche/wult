# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2019-2020 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module base class for wirte-only raw test result classes.
"""

import os
from wultlibs.helperlibs import YAML
from wultlibs.helperlibs.Exceptions import Error, ErrorNotSupported
from wultlibs.rawresultlibs import _CSV, _RawResultBase
from wultlibs.rawresultlibs._RawResultBase import FORMAT_VERSION

class WORawResultBase(_RawResultBase.RawResultBase):
    """This class represents a write-only raw test result."""

    def _check_can_continue(self):
        """
        Verify if it is OK to continue adding more datapoints to an existing test result."""

        if not self.dp_path.stat().st_size:
            # The datapoints file is empty. It is OK to continue.
            return

        if not self.info_path.is_file():
            raise Error(f"cannot continue a test result at '{self.dirpath}' because it does not "
                        f"have the info file ('{self.info_path}').")

        info = YAML.load(self.info_path)

        if info["format_version"] != FORMAT_VERSION:
            raise ErrorNotSupported(f"report at '{self.dirpath}' uses an unsupported format "
                                    f"version '{info['format_version']}', supported format version "
                                    f"is '{FORMAT_VERSION}'")

        if self.reportid != info["reportid"]:
            raise Error(f"cannot continue writing data belonging to report ID '{self.reportid}'\n"
                        f"to an existing test result directory '{self.dirpath}' with report ID "
                        f"'{info['reportid']}'.\nReport IDs must be the same.")

    def _init_outdir(self):
        """Initialize the output directory for writing or appending test results."""

        if self.dp_path.is_file() and self._cont:
            self._check_can_continue()

        try:
            self.dirpath.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise Error(f"failed to create directory '{self.dirpath}':\n{err}")

        self.csv = _CSV.WritableCSV(self.dp_path, cont=self._cont)

        if self.info_path.exists():
            if not self.info_path.is_file():
                raise Error(f"path '{self.info_path}' exists, but it is not a regular file")
            # Verify that we are going to be able writing to the info file.
            if not os.access(self.info_path, os.W_OK):
                raise Error(f"cannot access '{self.info_path}' for writing")
        else:
            # Create an empty info file in advance.
            try:
                self.info_path.open("tw+", encoding="utf-8").close()
            except OSError as err:
                raise Error(f"failed to create file '{self.info_path}':\n{err}")

    def write_info(self):
        """Write the 'self.info' dictionary to the 'info.yml' file."""

        YAML.dump(self.info, self.info_path)

    def __init__(self, reportid, outdir, cont=False):
        """
        The class constructor. The arguments are as follows.
          * reportid - reportid of the raw test result.
          * outdir - the output directory to store the raw results at.
          * cont - defines what to do if 'outdir' already contains test results. By default the
                   existing 'datapoints.csv' file gets overridden, but when 'cont' is 'True', the
                   existing 'datapoints.csv' file is "continued" instead (new datapoints are
                   appended).
        """

        super().__init__(outdir)

        # The writable CSV file object.
        self.csv = None
        self._cont = cont
        self.reportid = reportid

        self._init_outdir()

        self.info["format_version"] = FORMAT_VERSION
        self.info["reportid"] = reportid

        # Note, this format version assumes that the following elements should be added to
        # 'self.info' later by the owned of this object:
        #  * toolname - name of the tool creating the report.
        #  * toolver - version of the tool creating the report.

    def __del__(self):
        """The destructor."""
        self.close()

    def close(self):
        """Stop the experiment."""

        if getattr(self, "csv", None):
            self.csv.close()
            self.csv = None

    def __enter__(self):
        """Enter the run-time context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()