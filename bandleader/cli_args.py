"""Shared argparse type validators for the Bandleader CLIs.

These run at parse time, so invalid values produce a standard argparse error
(exit code 2, no traceback) before any output file is created.
"""

from __future__ import annotations

import argparse


def positive_int(value: str) -> int:
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value}")
    return ivalue


def positive_float(value: str) -> float:
    try:
        fvalue = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from None
    if fvalue <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive number, got {value}")
    return fvalue


def int_in_range(lo: int, hi: int):
    """Return an argparse type that accepts integers within [lo, hi]."""

    def parse(value: str) -> int:
        try:
            ivalue = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
        if not lo <= ivalue <= hi:
            raise argparse.ArgumentTypeError(f"must be in range {lo}-{hi}, got {value}")
        return ivalue

    parse.__name__ = f"integer({lo}-{hi})"
    return parse


def float_in_range(lo: float, hi: float):
    """Return an argparse type that accepts numbers within [lo, hi]."""

    def parse(value: str) -> float:
        try:
            fvalue = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from None
        if not lo <= fvalue <= hi:
            raise argparse.ArgumentTypeError(f"must be in range {lo}-{hi}, got {value}")
        return fvalue

    parse.__name__ = f"number({lo}-{hi})"
    return parse
