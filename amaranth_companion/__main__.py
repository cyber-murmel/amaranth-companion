#!/usr/bin/env python3

import sys
from argparse import ArgumentParser, Namespace
from logging import DEBUG, ERROR, INFO, WARNING, debug

from coloredlogs import install as color_log
from PyQt5.QtWidgets import QApplication

from .theme import ThemeMode, install as install_theme
from .windows.main_window import MainWindow


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

    parser.add_argument(
        "--theme",
        choices=[mode.value for mode in ThemeMode],
        default=None,
        help="colour theme for this run; defaults to the stored preference, "
        "or the desktop's light/dark setting",
    )

    return parser.parse_args(argv)


def get_log_level(verbose: int, quiet: bool) -> int:
    if quiet:
        return ERROR
    if not verbose:
        return WARNING
    return INFO if verbose == 1 else DEBUG


def main(theme: ThemeMode | None = None) -> int:
    app = QApplication(sys.argv)
    # before the window, so that it is built with the final palette
    install_theme(theme)
    window = MainWindow()
    window.show()
    return app.exec_()


def cli() -> int:
    """Console-script entry point."""
    args = parse_arguments()
    color_log(level=get_log_level(args.verbose, args.quiet))
    debug(args)
    return main(ThemeMode(args.theme) if args.theme else None)


if "__main__" == __name__:
    sys.exit(cli())
