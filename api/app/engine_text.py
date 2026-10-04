"""Persian text helpers shared by the engine and the FAQ matcher (no other imports, so no cycles)."""
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_FA = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "‌": " "})


def fa_digits(text: str) -> str:
    """Display form for customers: ASCII digits -> Persian digits. Applied by the channels (never to callback data)."""
    return (text or "").translate(_TO_FA)


def norm(text: str) -> str:
    return (text or "").translate(_DIGITS).strip()


def fa_norm(text: str) -> str:
    """Search-friendly form: ASCII digits, Persian ی/ک, no ZWNJ, lowercase, single spaces."""
    return " ".join(norm(text).translate(_FA).lower().split())
