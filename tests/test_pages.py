import pytest

from pdfmanagement.core import InvalidInputError, parse_page_selection


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ("1", [0]),
        ("2,4", [1, 3]),
        ("1-3", [0, 1, 2]),
        ("1-3, 8, 10", [0, 1, 2, 7, 9]),
        ("8-", [7, 8, 9]),
        ("-2", [0, 1]),
        ("3,1-2", [2, 0, 1]),
        ("1,1,2", [0, 1]),
        ("2;4", [1, 3]),
        ("ALL", list(range(10))),
        ("todo", list(range(10))),
        ("impar", [0, 2, 4, 6, 8]),
        ("even", [1, 3, 5, 7, 9]),
    ],
)
def test_valid_selections(selection, expected):
    assert parse_page_selection(selection, 10) == expected


@pytest.mark.parametrize("selection", ["", "   ", "0", "abc", "5-2", "1-x", "11", "2-12", "1.5"])
def test_invalid_selections(selection):
    with pytest.raises(InvalidInputError):
        parse_page_selection(selection, 10)
