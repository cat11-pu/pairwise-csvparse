"""csvparse: a small CSV reading and writing kernel."""

from .core import (
    BOM,
    DELIMITER,
    QUOTE,
    TERMINATOR,
    CSVError,
    Record,
    encode_rows,
    needs_quotes,
    parse_csv,
    parse_records,
)

__all__ = [
    "BOM",
    "CSVError",
    "DELIMITER",
    "QUOTE",
    "Record",
    "TERMINATOR",
    "encode_rows",
    "needs_quotes",
    "parse_csv",
    "parse_records",
]
