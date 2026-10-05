#!/usr/bin/env python3
"""Parse an Escola Gaia monthly menu PDF into JSON.

Usage: parse_menu.py <pdf> [-o output.json]

Rebuilds the 5-column (Dilluns..Divendres) weekly table from
`pdftotext -bbox` word coordinates, in four stages: Word, Line, Cell,
MenuDay.

  1. Column x-boundaries come from clustering the x-position of every
     "DIA" word in the document.
  2. Rows (weeks) are split on y-gaps larger than normal line spacing;
     everything at or after the footer paragraph is excluded.
  3. Calendar dates come from Python's `calendar` module (year and month
     read from the title line), anchored to whichever row carries a
     legible "DIA N" label. Other rows follow as consecutive weeks.
  4. Each cell is an optional "DIA N" label, an optional trailing
     allergen-code line "(1, 2, 7)", then either one ALL-CAPS closure
     line, or course lines where "-" means no item and the last line is
     dessert.

Closure days and cells with no menu are dropped from the output.

Raises MenuParseError (exit code 2) when a structural assumption fails,
with a message naming what did not match.
"""
import argparse
import calendar
import datetime
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from models import Menu, MenuDay  # noqa: E402

CATALAN_MONTHS = {
    "GENER": 1, "FEBRER": 2, "MARÇ": 3, "ABRIL": 4, "MAIG": 5, "JUNY": 6,
    "JULIOL": 7, "AGOST": 8, "SETEMBRE": 9, "OCTUBRE": 10, "NOVEMBRE": 11,
    "DESEMBRE": 12,
}
CATALAN_WEEKDAYS = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"]
NUM_COLS = 5

FOOTER_ANCHOR_WORDS = {"Tots", "CATASA"}
ALLERGEN_LINE_RE = re.compile(r"^\(\s*\d+(?:\s*,\s*\d+)*\s*\)$")
DIA_LABEL_RE = re.compile(r"^DIA(?:\s+(\d+))?$")
WORD_RE = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>'
)

ROW_GAP_THRESHOLD = 18.0  # pt; normal intra-cell line spacing is 8-15pt
Y_CLUSTER_TOL = 1.0
X_ANCHOR_TOL = 2.0
COLUMN_EPS = 0.05  # float tolerance for the boundary comparison
TITLE_BAND_Y = 100.0  # the month/year line sits above this
BODY_TOP_Y = 70.0
FOOTER_SEARCH_Y = 400.0  # the legal footer never starts above this


class MenuParseError(RuntimeError):
    """A structural assumption about the PDF layout did not hold."""


@dataclass(frozen=True, slots=True)
class Word:
    """One word with its bounding box, straight from pdftotext."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True, slots=True)
class Line:
    """Words sharing a baseline within one column, joined left to right."""

    y: float
    column: int
    text: str


@dataclass(frozen=True, slots=True)
class Cell:
    """One printed day box, before it is matched to a calendar date."""

    items: tuple[str, ...]
    dessert: str | None
    allergens: tuple[int, ...] | None
    closure_label: str | None = None
    day_label: int | None = None

    @property
    def has_menu(self) -> bool:
        return bool(self.items) or self.dessert is not None


# One printed week: five weekday columns, None where a column held no words.
WeekRow = tuple[Cell | None, ...]


def run_pdftotext_bbox(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-bbox", str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def unescape(text: str) -> str:
    return (text.replace("&apos;", "'").replace("&quot;", '"')
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


def extract_words(bbox_xml: str) -> list[Word]:
    return [
        Word(x0=float(m[0]), y0=float(m[1]), x1=float(m[2]), y1=float(m[3]),
             text=unescape(m[4]))
        for m in WORD_RE.findall(bbox_xml)
    ]


def cluster_1d(values: list[float], tol: float) -> list[list[int]]:
    """Groups indices of `values` where consecutive sorted values differ by
    less than tol. Returns a list of index clusters."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    clusters: list[list[int]] = []
    cur = [order[0]]
    for i in order[1:]:
        if values[i] - values[cur[-1]] < tol:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return clusters


def detect_month_year(words: list[Word]) -> tuple[int, int]:
    title_words = [w for w in words if w.y0 < TITLE_BAND_Y]
    month: int | None = None
    year: int | None = None
    for w in title_words:
        up = w.text.upper()
        if up in CATALAN_MONTHS:
            month = CATALAN_MONTHS[up]
        elif re.fullmatch(r"\d{4}", w.text):
            year = int(w.text)
    if not month or not year:
        raise MenuParseError(
            "Could not find a Catalan month name and 4-digit year in the "
            f"title band (y<{TITLE_BAND_Y:g}). Title words seen: "
            f"{[w.text for w in title_words]}"
        )
    return month, year


def detect_column_anchors(words: list[Word]) -> list[float]:
    """The left edge of each weekday column, self-calibrated from the
    x-position of every "DIA" label in the document."""
    dia_xmins = [w.x0 for w in words if w.text == "DIA"]
    if len(dia_xmins) < NUM_COLS:
        raise MenuParseError(
            f"Only found {len(dia_xmins)} 'DIA' label word(s) in the whole "
            f"document; need at least {NUM_COLS}, one column anchor each, "
            "to self-calibrate column boundaries."
        )
    clusters = cluster_1d(dia_xmins, X_ANCHOR_TOL)
    anchors = sorted(sum(vals) / len(vals)
                     for vals in ([dia_xmins[i] for i in cl] for cl in clusters))
    if len(anchors) != NUM_COLS:
        raise MenuParseError(
            f"Expected {NUM_COLS} distinct column x-anchors from 'DIA' labels, "
            f"found {len(anchors)}: {anchors}"
        )
    return anchors


def column_bounds_from_anchors(anchors: list[float]) -> list[float]:
    spacing = anchors[1] - anchors[0]
    return anchors + [anchors[-1] + spacing * 1.3]


def column_of(x0: float, bounds: list[float]) -> int:
    for i in range(NUM_COLS):
        if bounds[i] - COLUMN_EPS <= x0 < bounds[i + 1] - COLUMN_EPS:
            return i
    return 0 if x0 < bounds[0] else NUM_COLS - 1


def find_footer_cutoff_y(words: list[Word]) -> float:
    candidates = [w.y0 for w in words
                  if w.text in FOOTER_ANCHOR_WORDS and w.y0 > FOOTER_SEARCH_Y]
    return min(candidates) if candidates else float("inf")


WEEKDAY_HEADER_WORDS = {w.upper() for w in CATALAN_WEEKDAYS}


def build_lines(words: list[Word], bounds: list[float], y_max: float) -> list[Line]:
    """Groups words into lines. Skips the title band, the weekday-name
    header row (matched by text, not position), and the footer."""
    body = [w for w in words
            if BODY_TOP_Y <= w.y0 < y_max
            and w.text.upper() not in WEEKDAY_HEADER_WORDS]
    if not body:
        raise MenuParseError("No body words found between the title and footer bands.")

    lines: list[Line] = []
    for cluster in cluster_1d([w.y0 for w in body], Y_CLUSTER_TOL):
        words_here = [body[i] for i in cluster]
        y = sum(w.y0 for w in words_here) / len(words_here)
        by_column: dict[int, list[Word]] = {}
        for w in words_here:
            by_column.setdefault(column_of(w.x0, bounds), []).append(w)
        for column, column_words in by_column.items():
            column_words.sort(key=lambda w: w.x0)
            lines.append(Line(y=y, column=column,
                               text=" ".join(w.text for w in column_words)))
    lines.sort(key=lambda line: (line.y, line.column))
    return lines


def group_rows(lines: list[Line]) -> list[list[Line]]:
    """Splits lines into week-row blocks on the y-gap threshold."""
    ys = sorted({line.y for line in lines})
    breaks = [ys[0]]
    for prev, cur in zip(ys, ys[1:]):
        if cur - prev > ROW_GAP_THRESHOLD:
            breaks.append(cur)

    rows = []
    for i, start_y in enumerate(breaks):
        end_y = breaks[i + 1] if i + 1 < len(breaks) else float("inf")
        rows.append([line for line in lines if start_y - 0.5 <= line.y < end_y - 0.5])
    return rows


def parse_cell(lines: list[str]) -> Cell:
    """Turns one column's text lines into a Cell: an optional leading
    "DIA N" label, an optional trailing allergen-code line, then either a
    single ALL-CAPS closure line or course lines where "-" means no item
    and the last line is dessert."""
    day_label: int | None = None
    label_match = DIA_LABEL_RE.match(lines[0]) if lines else None
    if label_match:
        day_label = int(label_match.group(1)) if label_match.group(1) else None
        lines = lines[1:]

    allergens: tuple[int, ...] | None = None
    if lines and ALLERGEN_LINE_RE.match(lines[-1]):
        allergens = tuple(int(n) for n in re.findall(r"\d+", lines[-1]))
        lines = lines[:-1]

    is_closure = (len(lines) == 1 and lines[0].isupper()
                  and any(c.isalpha() for c in lines[0]))
    if is_closure:
        return Cell(items=(), dessert=None, allergens=allergens,
                     closure_label=lines[0], day_label=day_label)
    if not lines:
        return Cell(items=(), dessert=None, allergens=allergens, day_label=day_label)

    dessert = None if lines[-1] == "-" else lines[-1]
    items = tuple(line for line in lines[:-1] if line != "-")
    return Cell(items=items, dessert=dessert, allergens=allergens, day_label=day_label)


def parse_rows_into_cells(rows: list[list[Line]]) -> list[WeekRow]:
    """One WeekRow per printed week, five columns each."""
    week_rows: list[WeekRow] = []
    for row_lines in rows:
        by_column: dict[int, list[Line]] = {c: [] for c in range(NUM_COLS)}
        for line in row_lines:
            by_column[line.column].append(line)

        cells: list[Cell | None] = []
        for column in range(NUM_COLS):
            texts = [line.text for line in sorted(by_column[column], key=lambda l: l.y)]
            cells.append(parse_cell(texts) if texts else None)
        week_rows.append(tuple(cells))
    return week_rows


def assign_calendar_weeks(
    week_rows: list[WeekRow], year: int, month: int
) -> tuple[list[list[int]], list[int]]:
    """Maps each printed row to a 0-based week-of-month index into
    calendar.monthdayscalendar(year, month). Rows with a legible day label
    anchor the sequence; the rest follow as consecutive weeks. Returns
    (weeks, week_index_per_row)."""
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    anchored_week: list[int | None] = [None] * len(week_rows)

    for r, row in enumerate(week_rows):
        for c, cell in enumerate(row):
            if cell is None or cell.day_label is None:
                continue
            candidates = [wi for wi, week in enumerate(weeks) if week[c] == cell.day_label]
            if not candidates:
                raise MenuParseError(
                    f"Row {r} col {c}: label DIA {cell.day_label} matches no "
                    f"{CATALAN_WEEKDAYS[c]} in {month}/{year} "
                    f"(calendar weeks: {weeks})"
                )
            if anchored_week[r] is not None and anchored_week[r] not in candidates:
                raise MenuParseError(
                    f"Row {r}: conflicting week anchors (col {c} DIA "
                    f"{cell.day_label} implies week(s) {candidates}, but the row "
                    f"was already anchored to week {anchored_week[r]})"
                )
            anchored_week[r] = candidates[0]

    anchors = [i for i, week in enumerate(anchored_week) if week is not None]
    if not anchors:
        raise MenuParseError(
            "No row in the document carries a legible 'DIA N' label, so the "
            "rows cannot be anchored to calendar weeks. Needs manual review."
        )

    base_row = anchors[0]
    base_week = anchored_week[base_row]
    assert base_week is not None
    resolved: list[int] = []
    for r in range(len(week_rows)):
        expected = base_week + (r - base_row)
        if anchored_week[r] is not None and anchored_week[r] != expected:
            raise MenuParseError(
                f"Row {r}: anchored week {anchored_week[r]} does not match the "
                f"expected consecutive offset {expected} from row {base_row} "
                f"(week {base_week})."
            )
        if not 0 <= expected < len(weeks):
            raise MenuParseError(
                f"Row {r} maps to week-of-month index {expected}, outside the "
                f"{len(weeks)} calendar weeks of {month}/{year}."
            )
        resolved.append(expected)
    return weeks, resolved


def build_days(
    week_rows: list[WeekRow],
    weeks: list[list[int]],
    week_index_per_row: list[int],
    year: int,
    month: int,
) -> list[MenuDay]:
    """One MenuDay per school day that has a menu."""
    days: list[MenuDay] = []
    for r, row in enumerate(week_rows):
        week = weeks[week_index_per_row[r]]
        for c, cell in enumerate(row):
            day_number = week[c]
            if day_number == 0:
                continue  # not a day of this month, so the box is blank
            date = datetime.date(year, month, day_number)
            if cell is None:
                raise MenuParseError(
                    f"{date.isoformat()} ({CATALAN_WEEKDAYS[c]}) is a real "
                    "calendar day in this grid but its cell held no words."
                )
            if cell.closure_label is not None or not cell.has_menu:
                continue
            days.append(MenuDay(
                date=date,
                weekday=CATALAN_WEEKDAYS[c],
                items=list(cell.items),
                dessert=cell.dessert,
                allergens=list(cell.allergens) if cell.allergens is not None else None,
                day_label_from_pdf=cell.day_label,
                date_label_mismatch=(cell.day_label is not None
                                      and cell.day_label != day_number),
            ))
    return days


def parse_menu(pdf_path: Path) -> Menu:
    words = extract_words(run_pdftotext_bbox(pdf_path))
    month, year = detect_month_year(words)
    bounds = column_bounds_from_anchors(detect_column_anchors(words))
    lines = build_lines(words, bounds, find_footer_cutoff_y(words))
    week_rows = parse_rows_into_cells(group_rows(lines))
    weeks, week_index_per_row = assign_calendar_weeks(week_rows, year, month)
    return Menu(year=year, month=month,
                 days=build_days(week_rows, weeks, week_index_per_row, year, month))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path, help="Path to a downloaded menu PDF")
    ap.add_argument("-o", "--output", type=Path, help="Write JSON here instead of stdout")
    args = ap.parse_args()

    try:
        menu = parse_menu(args.pdf)
    except MenuParseError as e:
        print(f"MenuParseError: {e}", file=sys.stderr)
        return 2

    out = json.dumps(menu.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
