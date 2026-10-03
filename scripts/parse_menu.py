#!/usr/bin/env python3
"""Parse an Escola Gaia monthly menu PDF into JSON.

Usage: parse_menu.py <pdf> [-o output.json]

Reconstructs the 5-column (Dilluns..Divendres) weekly table from
`pdftotext -bbox` word coordinates:

  1. Column x-boundaries come from clustering the x-position of every
     "DIA" word in the document.
  2. Rows (weeks) are split on y-gaps larger than normal line spacing;
     everything at/after the footer paragraph is excluded.
  3. Calendar dates come from Python's `calendar` module (year/month read
     from the title line), anchored to whichever row(s) carry a legible
     "DIA N" label; other rows are consecutive weeks from there.
  4. Each cell is: optional "DIA N" label, optional trailing allergen-code
     line "(1, 2, 7)", then either one ALL-CAPS closure line, or course
     lines where "-" means no item and the last line is dessert.
  5. Closure days and cells with no menu content are dropped from the
     output.

Raises MenuParseError (exit code 2) when a structural assumption fails,
with a message identifying what didn't match.
"""
import argparse
import calendar
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

Word = dict[str, Any]       # {"x0", "y0", "x1", "y1", "text"}
Line = dict[str, Any]       # {"y", "col", "text"}
Cell = dict[str, Any]       # {"holiday", "holiday_label", "items", "dessert", "allergens"}
MenuDoc = dict[str, Any]    # parse_menu()'s return shape (see module docstring)

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

ROW_GAP_THRESHOLD = 18.0  # pt; normal intra-cell line spacing is ~8-15pt
Y_CLUSTER_TOL = 1.0
X_ANCHOR_TOL = 2.0


class MenuParseError(RuntimeError):
    """Raised when a structural assumption about the PDF layout doesn't hold."""


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
    words = []
    for m in WORD_RE.finditer(bbox_xml):
        xmin, ymin, xmax, ymax, text = m.groups()
        words.append({
            "x0": float(xmin), "y0": float(ymin),
            "x1": float(xmax), "y1": float(ymax),
            "text": unescape(text),
        })
    return words


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
    title_words = [w for w in words if w["y0"] < 100]
    month: int | None = None
    year: int | None = None
    for w in title_words:
        up = w["text"].upper()
        if up in CATALAN_MONTHS:
            month = CATALAN_MONTHS[up]
        elif re.fullmatch(r"\d{4}", w["text"]):
            year = int(w["text"])
    if not month or not year:
        raise MenuParseError(
            "Could not find a Catalan month name + 4-digit year in the title "
            "band (y<100). Title words seen: "
            f"{[w['text'] for w in title_words]}"
        )
    return month, year


def detect_column_anchors(words: list[Word]) -> list[float]:
    dia_xmins = [w["x0"] for w in words if w["text"] == "DIA"]
    if len(dia_xmins) < NUM_COLS:
        raise MenuParseError(
            f"Only found {len(dia_xmins)} 'DIA' label word(s) in the whole "
            f"document; need at least {NUM_COLS} (one column anchor each) "
            "to self-calibrate column boundaries."
        )
    clusters = cluster_1d(dia_xmins, X_ANCHOR_TOL)
    anchors = sorted(sum(c) / len(c) for c in [[dia_xmins[i] for i in cl] for cl in clusters])
    if len(anchors) != NUM_COLS:
        raise MenuParseError(
            f"Expected {NUM_COLS} distinct column x-anchors from 'DIA' labels, "
            f"found {len(anchors)}: {anchors}"
        )
    return anchors  # ascending, left edge of each column


def column_bounds_from_anchors(anchors: list[float]) -> list[float]:
    spacing = anchors[1] - anchors[0]
    bounds = anchors + [anchors[-1] + spacing * 1.3]
    return bounds


COLUMN_EPS = 0.05  # float tolerance for the boundary comparison below


def column_of(x0: float, bounds: list[float]) -> int:
    for i in range(NUM_COLS):
        if bounds[i] - COLUMN_EPS <= x0 < bounds[i + 1] - COLUMN_EPS:
            return i
    return 0 if x0 < bounds[0] else NUM_COLS - 1


def find_footer_cutoff_y(words: list[Word]) -> float:
    candidates = [w["y0"] for w in words
                  if w["text"] in FOOTER_ANCHOR_WORDS and w["y0"] > 400]
    return min(candidates) if candidates else float("inf")


WEEKDAY_HEADER_WORDS = {w.upper() for w in CATALAN_WEEKDAYS}


def build_lines(words: list[Word], bounds: list[float], y_max: float) -> list[Line]:
    """Groups words into (y, column, text) lines. Excludes the title band,
    the weekday-name header row (matched by text, not position), and
    anything at/after the footer."""
    body_words = [w for w in words
                  if w["y0"] >= 70 and w["y0"] < y_max
                  and w["text"].upper() not in WEEKDAY_HEADER_WORDS]
    if not body_words:
        raise MenuParseError("No body words found between the title and footer bands.")
    y_clusters = cluster_1d([w["y0"] for w in body_words], Y_CLUSTER_TOL)
    lines: list[Line] = []
    for cl in y_clusters:
        cluster_words = [body_words[i] for i in cl]
        y = sum(w["y0"] for w in cluster_words) / len(cluster_words)
        by_col: dict[int, list[Word]] = {}
        for w in cluster_words:
            by_col.setdefault(column_of(w["x0"], bounds), []).append(w)
        for col, ws in by_col.items():
            ws.sort(key=lambda w: w["x0"])
            text = " ".join(w["text"] for w in ws)
            lines.append({"y": y, "col": col, "text": text})
    lines.sort(key=lambda l: (l["y"], l["col"]))
    return lines


def group_rows(lines: list[Line]) -> list[list[Line]]:
    """Splits lines into week-row blocks using a y-gap threshold."""
    ys = sorted(set(l["y"] for l in lines))
    row_breaks = [ys[0]]
    for prev, cur in zip(ys, ys[1:]):
        if cur - prev > ROW_GAP_THRESHOLD:
            row_breaks.append(cur)
    rows = []
    for i, start_y in enumerate(row_breaks):
        end_y = row_breaks[i + 1] if i + 1 < len(row_breaks) else float("inf")
        row_lines = [l for l in lines if start_y - 0.5 <= l["y"] < end_y - 0.5]
        rows.append(row_lines)
    return rows


def parse_cell(content_lines: list[str]) -> Cell:
    """Takes one day's content lines (DIA-label already removed). Returns
    a dict with holiday/items/dessert/allergens."""
    allergens: list[int] | None = None
    if content_lines and ALLERGEN_LINE_RE.match(content_lines[-1]):
        allergens = [int(n) for n in re.findall(r"\d+", content_lines[-1])]
        content_lines = content_lines[:-1]

    is_holiday = (
        len(content_lines) == 1
        and content_lines[0].isupper()
        and any(c.isalpha() for c in content_lines[0])
    )
    if is_holiday:
        return {
            "holiday": True, "holiday_label": content_lines[0],
            "items": [], "dessert": None, "allergens": allergens,
        }

    if not content_lines:
        return {"holiday": False, "holiday_label": None,
                "items": [], "dessert": None, "allergens": allergens}

    dessert = None if content_lines[-1] == "-" else content_lines[-1]
    items = [l for l in content_lines[:-1] if l != "-"]
    return {"holiday": False, "holiday_label": None,
            "items": items, "dessert": dessert, "allergens": allergens}


def parse_rows_into_cells(rows: list[list[Line]]) -> list[list[Cell | None]]:
    """Splits each row-block's 5 columns into day_label + cell dict.
    Returns a list of rows, each a list of 5 entries (None where a column
    had no words)."""
    parsed_rows: list[list[Cell | None]] = []
    for row_lines in rows:
        by_col: dict[int, list[Line]] = {c: [] for c in range(NUM_COLS)}
        for l in row_lines:
            by_col[l["col"]].append(l)
        for c in by_col:
            by_col[c].sort(key=lambda l: l["y"])

        row_out: list[Cell | None] = []
        for c in range(NUM_COLS):
            col_lines = [l["text"] for l in by_col[c]]
            if not col_lines:
                row_out.append(None)
                continue
            day_label = None
            m = DIA_LABEL_RE.match(col_lines[0])
            if m:
                day_label = int(m.group(1)) if m.group(1) else None
                col_lines = col_lines[1:]
            cell = parse_cell(col_lines)
            cell["day_label"] = day_label
            row_out.append(cell)
        parsed_rows.append(row_out)
    return parsed_rows


def assign_calendar_weeks(
    parsed_rows: list[list[Cell | None]], year: int, month: int
) -> tuple[list[list[int]], list[int]]:
    """Maps each row-block to a 0-based week-of-month index (into
    calendar.monthdayscalendar(year, month)), using rows with a legible
    day_label as anchors and filling in the rest as consecutive weeks.
    Returns (weeks, week_index_for_row)."""
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    week_index_for_row: list[int | None] = [None] * len(parsed_rows)

    for r, row in enumerate(parsed_rows):
        for c, cell in enumerate(row):
            if cell is None or cell.get("day_label") is None:
                continue
            day = cell["day_label"]
            candidates = [wi for wi, wk in enumerate(weeks) if wk[c] == day]
            if not candidates:
                raise MenuParseError(
                    f"Row {r} col {c}: label DIA {day} doesn't match any "
                    f"{CATALAN_WEEKDAYS[c]} in {month}/{year} "
                    f"(calendar weeks: {weeks})"
                )
            if week_index_for_row[r] is not None and week_index_for_row[r] not in candidates:
                raise MenuParseError(
                    f"Row {r}: conflicting week anchors (col {c} DIA {day} "
                    f"implies week(s) {candidates}, but row was already "
                    f"anchored to week {week_index_for_row[r]})"
                )
            week_index_for_row[r] = candidates[0]

    anchored = [i for i, wi in enumerate(week_index_for_row) if wi is not None]
    if not anchored:
        raise MenuParseError(
            "No row in the document has a single legible 'DIA N' label - "
            "cannot anchor rows to calendar weeks. Manual/LLM review needed."
        )
    # fill remaining rows as consecutive weeks from the first anchor
    base_row, base_week = anchored[0], week_index_for_row[anchored[0]]
    assert base_week is not None
    resolved: list[int] = []
    for r in range(len(parsed_rows)):
        expected = base_week + (r - base_row)
        if week_index_for_row[r] is not None and week_index_for_row[r] != expected:
            raise MenuParseError(
                f"Row {r}: anchored week {week_index_for_row[r]} doesn't "
                f"match the expected consecutive offset {expected} from "
                f"row {base_row} (week {base_week})."
            )
        if expected < 0 or expected >= len(weeks):
            raise MenuParseError(
                f"Row {r} maps to week-of-month index {expected}, outside "
                f"the {len(weeks)} calendar weeks of {month}/{year}."
            )
        resolved.append(expected)
    return weeks, resolved


def build_days(
    parsed_rows: list[list[Cell | None]],
    weeks: list[list[int]],
    week_index_for_row: list[int],
    year: int,
    month: int,
    diet: str,
    source: str,
) -> MenuDoc:
    """Returns one entry per school day with menu content. Closure days
    and empty cells are omitted."""
    days: list[dict[str, Any]] = []
    for r, row in enumerate(parsed_rows):
        week = weeks[week_index_for_row[r]]
        for c, cell in enumerate(row):
            day_num = week[c]
            if day_num == 0:
                continue  # not a day in this month (leading/trailing blank)
            date_str = f"{year:04d}-{month:02d}-{day_num:02d}"
            if cell is None:
                raise MenuParseError(
                    f"{date_str} ({CATALAN_WEEKDAYS[c]}) is a real calendar "
                    "day in this grid but no cell content was found at all."
                )
            if cell["holiday"] or (not cell["items"] and cell["dessert"] is None):
                continue
            mismatch = cell.get("day_label") is not None and cell["day_label"] != day_num
            days.append({
                "date": date_str,
                "weekday": CATALAN_WEEKDAYS[c],
                "items": cell["items"],
                "dessert": cell["dessert"],
                "allergens": cell["allergens"],
                "day_label_from_pdf": cell.get("day_label"),
                "date_label_mismatch": mismatch,
            })
    return {
        "source": source, "diet": diet,
        "year": year, "month": month,
        "month_name": [k for k, v in CATALAN_MONTHS.items() if v == month][0].title(),
        "days": days,
    }


def guess_diet(pdf_path: Path) -> str:
    m = re.search(r"_([A-Z\-]+?)(?:-MP)?\.pdf$", pdf_path.name, re.IGNORECASE)
    return m.group(1).upper() if m else "UNKNOWN"


def parse_menu(pdf_path: Path) -> MenuDoc:
    bbox_xml = run_pdftotext_bbox(pdf_path)
    words = extract_words(bbox_xml)
    month, year = detect_month_year(words)
    anchors = detect_column_anchors(words)
    bounds = column_bounds_from_anchors(anchors)
    footer_y = find_footer_cutoff_y(words)
    lines = build_lines(words, bounds, footer_y)
    rows = group_rows(lines)
    parsed_rows = parse_rows_into_cells(rows)
    weeks, week_index_for_row = assign_calendar_weeks(parsed_rows, year, month)
    diet = guess_diet(pdf_path)
    return build_days(parsed_rows, weeks, week_index_for_row, year, month, diet, pdf_path.name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path, help="Path to a downloaded menu PDF")
    ap.add_argument("-o", "--output", type=Path, help="Write JSON here instead of stdout")
    args = ap.parse_args()

    try:
        data = parse_menu(args.pdf)
    except MenuParseError as e:
        print(f"MenuParseError: {e}", file=sys.stderr)
        return 2

    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
