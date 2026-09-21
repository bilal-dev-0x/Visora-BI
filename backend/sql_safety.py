"""
Small, dependency-free helpers for building SQL identifiers safely.

Table names in the new dynamic-dataset architecture are derived from
dataset_id (a UUID4), never from a user-supplied filename directly, so
they always match _IDENTIFIER_RE by construction. safe_table_name() is
still enforced everywhere a table name reaches a query string, as a
defense-in-depth check rather than a trust assumption.

Column names come straight from uploaded CSV headers and can contain
almost anything (spaces, punctuation, quote characters). Those are
never validated against _IDENTIFIER_RE -- instead they are always
wrapped with quote_identifier(), which double-escapes embedded double
quotes the same way SQLite expects for quoted identifiers.
"""

import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_safe_identifier(name):
    """True if name is safe to use unquoted as a SQLite identifier."""
    return isinstance(name, str) and bool(_IDENTIFIER_RE.match(name))


def safe_table_name(table_name):
    """Validate a table name before it is interpolated into a query.

    Raises ValueError instead of silently allowing an unsafe identifier
    through -- callers should treat this as a programming error, since
    every table name in this project is derived from a UUID and should
    always pass.
    """
    if not is_safe_identifier(table_name):
        raise ValueError(f"Unsafe or invalid table name: {table_name!r}")
    return table_name


def quote_identifier(name):
    """Quote an arbitrary identifier (typically a column name) for use
    in a SQL statement, escaping embedded double quotes."""
    if not isinstance(name, str):
        name = str(name)
    return '"' + name.replace('"', '""') + '"'
