"""Work out which month a hand-named menu PDF is for.

The school names files by hand, so the month can be a number, a name or a
short name (Catalan, Spanish or English), with or without a year, in any
position: 202611-..., ESCOLA-GAIA_BASAL-NOVEMBRE, BASAL_nov_26, 11-2026-menu,
Menu Novembre 2026, ...

detect_month(name, upload_year, upload_month) -> "YYYYMM" or None.
None means no month or more than one conflicting month was found; callers
must treat that as "not this month", never guess.

Evidence, strongest first: a 6-digit YYYYMM/MMYYYY token, a month word, a
lone 1-2 digit number 1..12. Tokens are whole words split on punctuation and
letter/digit boundaries, so "marinada" never reads as "mar". A missing year
is taken from the upload date: the year that puts the month closest to it.
"""
import re
import unicodedata

_MONTHS = {
    1: "gener enero january gen ene jan",
    2: "febrer febrero february feb",
    3: "marc marzo march mar",
    4: "abril april abr apr",
    5: "maig mayo may mai",
    6: "juny junio june jun",
    7: "juliol julio july jul",
    8: "agost agosto august ago aug",
    9: "setembre septiembre september set sep sept",
    10: "octubre october oct",
    11: "novembre noviembre november nov",
    12: "desembre diciembre december des dic dec",
}
_WORDS = {w: m for m, ws in _MONTHS.items() for w in ws.split()}


def _tokens(name: str) -> list[str]:
    name = name.rsplit("/", 1)[-1]
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z]+|\d+", name)


def _year_near(month: int, upload_year: int, upload_month: int) -> int:
    """Year that puts `month` closest to the upload month."""
    return min((upload_year - 1, upload_year, upload_year + 1),
               key=lambda y: abs((y * 12 + month) - (upload_year * 12 + upload_month)))


def detect_month(name: str, upload_year: int, upload_month: int) -> str | None:
    toks = _tokens(name)
    nums = [t for t in toks if t.isdigit()]
    years = [int(t) for t in nums if len(t) == 4 and 2000 <= int(t) <= 2099]
    month = year = None

    for t in nums:  # strongest: YYYYMM or MMYYYY in one token
        if len(t) == 6:
            for y, m in ((int(t[:4]), int(t[4:])), (int(t[2:]), int(t[:2]))):
                if 2000 <= y <= 2099 and 1 <= m <= 12:
                    month, year = m, y
                    break

    if month is None:
        found = {_WORDS[t] for t in toks if t in _WORDS}
        if len(found) > 1:
            return None
        if found:
            month = found.pop()

    if month is None:  # weakest: bare numbers 1..12 (2 digits may also be a year)
        small = [t for t in nums if len(t) <= 2 and 1 <= int(t) <= 12]
        big = [t for t in nums if len(t) == 2 and int(t) > 12]
        if len(small) == 1 and len(big) <= 1:
            month = int(small[0])
            if big:
                year = 2000 + int(big[0])
        elif len(small) == 2 and not big:
            return None  # "11-12": which is the month?
        else:
            return None

    if year is None:
        yrs = set(years)
        if len(yrs) > 1:
            return None
        if yrs:
            year = yrs.pop()
        else:
            # two-digit year next to a word month ("nov_26")
            two = [int(t) for t in nums if len(t) == 2 and int(t) > 12]
            year = 2000 + two[0] if len(two) == 1 else _year_near(month, upload_year, upload_month)
    return f"{year:04d}{month:02d}"
