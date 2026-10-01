"""CSV export hygiene shared by every download (audit log, insights, timetable)."""

# A cell that starts with one of these is evaluated as a formula by Excel, LibreOffice and
# Google Sheets (CSV/formula injection, SEC-06). Text from users and custodians reaches every
# export, so text cells are prefixed with an apostrophe, which spreadsheets show as plain text.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value):
    """Neutralise a formula-looking text cell; None becomes an empty cell; numbers pass through."""
    if isinstance(value, str) and value[:1] in FORMULA_PREFIXES:
        return "'" + value
    return "" if value is None else value


def unguard(value: str) -> str:
    """Undo `spreadsheet_safe` when one of our own exports is imported again."""
    if value[:1] == "'" and value[1:2] in FORMULA_PREFIXES:
        return value[1:]
    return value
