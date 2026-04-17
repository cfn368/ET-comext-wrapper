# py_files/preamble.py
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt


def enable_autoreload(mode: int = 2) -> None:
    """
    Enable autoreload in IPython/Jupyter if available.
    mode=2 -> reload all modules (except those excluded by autoreload itself).
    Safe no-op outside notebooks.
    """
    try:
        from IPython import get_ipython  # type: ignore
    except Exception:
        return

    ip = get_ipython()
    if ip is None:
        return

    # load extension if needed, then set mode
    ip.run_line_magic("load_ext", "autoreload")
    ip.run_line_magic("autoreload", str(int(mode)))


def set_aej():
    mpl.rcParams.update({
        "font.family": "serif",
        "font.size": 15,

        "axes.linewidth": 1.0,
        "lines.linewidth": 1.2,
        "legend.frameon": False,

        "xtick.direction": "out",
        "ytick.direction": "out",

        "axes.spines.top": True,
        "axes.spines.right": True,

        # legend
        "legend.frameon": True,
        "legend.fancybox": True,
        "legend.borderaxespad": 0.4,
        "legend.handlelength": 2.0,
        "legend.handletextpad": 0.6,
        "legend.labelspacing": 0.35,

        "savefig.bbox": "tight",
        "savefig.dpi": 300,
    })


def setup_notebook(*, autoreload: int = 2, aej: bool = True, **aej_kwargs) -> None:
    """
    One call in a notebook to get the usual environment:
      - autoreload
      - matplotlib style
    """
    enable_autoreload(autoreload)
    if aej:
        set_aej(**aej_kwargs)


# What you get with: from py_files.preamble import *
__all__ = [
    "enable_autoreload", "set_aej", "setup_notebook",
    "np", "pd", "plt",
]