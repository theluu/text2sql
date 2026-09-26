import re
import unicodedata

_WORD = re.compile(r"[0-9a-z]+")


def strip_accents(text: str) -> str:
    """'Doanh thu Hà Nội' -> 'Doanh thu Ha Noi' (handles đ/Đ, which NFKD leaves alone)."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Lowercase, accent-free, single-spaced: the form used for matching VI and EN alike."""
    return " ".join(_WORD.findall(strip_accents(text).lower()))


def tokens(text: str) -> list[str]:
    return normalize(text).split()
