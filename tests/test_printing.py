"""Impresion: calculos de ajuste al papel y estructura de Windows (sin imprimir de verdad)."""

import ctypes
import sys

import pytest

from pdfmanagement.core import printing


def test_portrait_page_on_portrait_paper_is_centered():
    placement = printing.fit_page(595, 842, 4800, 6600)
    assert not placement.rotate
    x0, y0, x1, y1 = placement.box
    assert x1 - x0 == 4667 or abs((x1 - x0) / (y1 - y0) - 595 / 842) < 0.01
    assert x0 >= 0 and y0 >= 0 and x1 <= 4800 and y1 <= 6600
    assert abs((x0 + x1) / 2 - 2400) <= 1


def test_landscape_page_is_rotated_to_use_the_paper():
    placement = printing.fit_page(842, 595, 4800, 6600)
    assert placement.rotate
    x0, y0, x1, y1 = placement.box
    assert (y1 - y0) > (x1 - x0), "girada queda vertical, como el papel"


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="solo Windows")
def test_print_dialog_structure_matches_windows():
    expected = 120 if ctypes.sizeof(ctypes.c_void_p) == 8 else 66
    assert ctypes.sizeof(printing._PrintDlg) == expected
