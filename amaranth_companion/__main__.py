#!/usr/bin/env python3.10

from argparse import (
    ArgumentParser,
    Action,
    FileType,
    ArgumentError,
    ArgumentTypeError,
    Namespace,
)
from logging import debug, info, warning, error, exception
from logging import DEBUG, INFO, WARNING, ERROR
from coloredlogs import install as color_log

from .windows.main_window import MainWindow
from . import qrc_resources
from PyQt5.QtWidgets import QApplication
import sys


def parse_arguments():
    parser = ArgumentParser(
        description="",
        prog="amaranth_compnaion",
        epilog="""
        """,
    )

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q", "--quiet", action="store_true", help="turn off warnings"
    )
    verbosity.add_argument(
        "-v", "--verbose", action="count", help="set verbose loglevel"
    )

    args = parser.parse_args()

    return args


def get_log_level(verbose: int, quiet: bool):
    return (
        ERROR if quiet else WARNING if not verbose else INFO if 1 == verbose else DEBUG
    )  #  2 <= verbose


def main(args: Namespace):
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec_()


if "__main__" == __name__:
    args = parse_arguments()
    color_log(level=get_log_level(args.verbose, args.quiet))
    debug(args)
    exit(main(args))
