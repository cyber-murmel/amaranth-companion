#!/usr/bin/env python3

import sys
from argparse import ArgumentParser, Namespace
from logging import DEBUG, ERROR, INFO, WARNING, debug

from coloredlogs import install as color_log
from PyQt5.QtWidgets import QApplication

from .windows.main_window import MainWindow
from . import qrc_resources  # noqa: F401 - registers the ":*.svg" icon paths


def parse_arguments(argv: list[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        prog="amaranth-companion",
        description="Visual editor for gateware based on amaranth-lang.",
    )

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q", "--quiet", action="store_true", help="turn off warnings"
    )
    verbosity.add_argument(
        "-v", "--verbose", action="count", default=0, help="set verbose loglevel"
    )

    return parser.parse_args(argv)


def get_log_level(verbose: int, quiet: bool) -> int:
    if quiet:
        return ERROR
    if not verbose:
        return WARNING
    return INFO if verbose == 1 else DEBUG


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


def cli() -> int:
    """Console-script entry point."""
    args = parse_arguments()
    color_log(level=get_log_level(args.verbose, args.quiet))
    debug(args)
    return main()


if "__main__" == __name__:
    sys.exit(cli())
