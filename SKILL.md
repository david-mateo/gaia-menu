---
name: gaia-menu
description: Fetch Escola Gaia's monthly BASAL school lunch menu PDF, parse it into structured JSON, and optionally export it as an .ics calendar file. Can also enrich each day with a short title, a recommended dinner pairing, and an English translation. Use when the user wants this month's (or a given) school menu turned into calendar entries, structured data, or a bilingual menu with dinner suggestions.
---

# MONTHLY PIPELINE (start here when run as the scheduled job)

Goal: each month, upsert the new month into the 4 public calendars in
`public/`, then commit + push to `main`. Run from the repo root. One work
dir per month: `W=~/.hermes/gaia-menu-work/<YYYYMM>` (step 0 prints it
as WORKDIR). Follow steps in order. Never hand-edit generated JSON.

Only generated output (`public/`, `archive/`, `data/glossary.json`) goes
to `main`.
Any code/doc change belongs on a separate branch, never `main`.

**Step 0 - what now?** (job runs on the 28th..5th)

    python3 scripts/pipeline_status.py

Read the last line `NEXT=...`: WAIT -> stop silently. FETCH -> 1.
ENRICH -> 2. APPLY -> 4. PUBLISH -> 5. DONE -> stop silently.
After each step run step 0 again until DONE or WAIT.

**Step 1 - fetch + parse**

    mkdir -p $W && python3 scripts/menu.py --download-dir $W -o $W/menu.json

Exit 1 = fetch problem, exit 2 = layout changed: report stderr verbatim, STOP.

**Step 2 - prepare request**

    python3 scripts/prepare_enrichment.py $W/menu.json -o $W/request.json

**Step 3 - write $W/response.json** (you; schema and rules in the
"Enrich" section below). Translate every phrase in `new_phrases`.

**Step 4 - merge**

    python3 scripts/apply_enrichment.py $W/menu.json $W/response.json -o $W/enriched.json

Exit 2 = fix response.json per the message, re-run.

**Step 5 - publish** (upserts the 4 .ics, commits as "Hermes (gaia-menu)",
pushes to main, writes `$W/published.done`)

    python3 scripts/publish_month.py $W <YYYYMM>

Exit 1 = read the message, retry once, else report it.

Final report (2 lines max): month, what was pushed (or the exact error).
Stay silent if step 0 said WAIT or DONE at the start.

---

# Gaia school menu

Requires `pdftotext` on PATH (`brew install poppler` / `pacman -S poppler`).

## Run it

```
python3 scripts/menu.py
```

Prints this month's menu as JSON to stdout. That's the whole normal case.

Flags, combine as needed:

| Flag | Effect |
|---|---|
| `-o FILE` | write JSON to FILE instead of stdout |
| `--ics FILE` | also write a .ics calendar file |
| `--pdf FILE` | parse a PDF you already have instead of fetching |

Example, full pipeline to a calendar file:

```
python3 scripts/menu.py -o menu.json --ics menu.ics
```

## If it fails

- **Exit code 1**: couldn't fetch the PDF (network/page changed). Report
  the stderr message as-is.
- **Exit code 2**: the PDF didn't match the expected menu layout
  (`MenuParseError`, with a specific reason on stderr). This means the
  school changed the template. **Do not guess a fix or hand-edit the
  JSON.** Report the exact error message. A maintainer will read
  `scripts/parse_menu.py`'s module docstring (lists every parsing rule)
  and add one new rule to cover the new case.

## Enrich with titles, dinner pairings, and English (optional)

Adds to each day a short title, a dinner-pairing suggestion, and an
English translation. It's a round trip: scripts prepare the input and
merge/validate the output; you (the model running this skill) fill in
the summarizing, translating, and lunch-tagging in between. The dinner
pairing itself is **not** your call - `apply_enrichment.py` computes it
deterministically from the tags you provide (see "Dinner pairing"
below).

```
python3 scripts/prepare_enrichment.py menu.json -o request.json
# you write response.json (schema below)
python3 scripts/apply_enrichment.py menu.json response.json -o enriched.json
```

**request.json** gives you, per day, `items`/`dessert`; `known_translations`
(Catalan phrases already in the glossary - reuse verbatim); `new_phrases`
(Catalan phrases you must translate); and `base_groups`/`protein_groups`
plus `lunch_only_groups`, the closed lists you must tag each day's lunch
from (`lunch_only_groups` tags are valid on `lunch_groups` but will never
be suggested back to you as a dinner pairing - currently just
`"Processed Meat"`, for cured/smoked/sausage preparations like botifarra,
ham, or hot dogs: a cap to respect, not something to recommend more of).

**response.json** you write:

```json
{
  "new_translations": {"<phrase from new_phrases>": "<english>"},
  "days": [
    {
      "date": "2026-10-01",
      "en_items": ["Potato salad", "French omelette", "Lettuce and tomato"],
      "en_dessert": "Seasonal fruit",
      "ca_title": "Amanida de patata + truita",
      "en_title": "Potato salad + omelette",
      "lunch_groups": ["Potato", "Eggs", "Salad"]
    }
  ]
}
```

`new_translations` must cover every phrase in `new_phrases`. One `days`
entry per date, matched exactly.

Fill each day's fields in this order: `en_items`/`en_dessert` first
(translate), then `en_title` (summarize what you just translated), then
`ca_title` directly from the original Catalan items (pick and shorten
the 1-2 main dishes - not a translation of `en_title`), then
`lunch_groups`.

**Title** (`ca_title`/`en_title`): 3-4 words, "dish + dish" joined by
" + ". Drop articles, sauces, and garnish unless they're the point - a
generic category word (e.g. "Verdures") is fine when it reads better than
the literal dish name. Real examples:

| Items | Title |
|---|---|
| Amanida de patata, Truita francesa, Enciam i tomàquet | Amanida de patata + truita |
| Macarrons integrals ecològics amb carbonara vegetal, Botifarra de porc amb samfaina | Macarrons + botifarra |
| Crema de carbassó, Escalopa d'au cordon bleu de gall dindi, Enciam i blat de moro | Crema de carbassó + escalopa de gall dindi |
| Amanida de cigrons (pastanaga, blat de moro i tomàquet), Mandonguilles mixtes a la jardinera (...) | Amanida de cigrons + mandonguilles |
| Arròs integral amb salsa de tomàquet, Salmó al forn amb anet, Enciam i olives | Arròs + Salmó |
| Bròquil, patata i pastanaga, Llenties estofades amb verdures | Verdures + llenties |
| Fideus a la cassola amb verdures, Truita de patata, Enciam i tomàquet | Fideus amb verdures + truita |

A dish split across two consecutive `items` entries means the PDF
wrapped its name onto two lines (e.g. "Macarrons integrals ecològics
amb" / "carbonara vegetal" is one dish, row 2 above). Read a short item
that doesn't stand alone as a continuation of the previous one.

**`lunch_groups`**: 1-3 tags from `base_groups`/`protein_groups`/
`lunch_only_groups` describing what today's lunch actually contains
(e.g. a potato-and-egg dish with a side salad →
`["Potato", "Eggs", "Salad"]`). This is classification, not creativity -
tag what's there, don't try to guess a good dinner pairing yourself.

Use `"Fish"` for white/lean fish (lluç/hake, bacallà/cod, rap/monkfish,
llenguado/sole, orada/sea bream) and `"Oily Fish"` for oily/blue fish
(salmó/salmon, tonyina/tuna, sardina/sardine, verat/mackerel,
seitó-anxova/anchovy) - get the species right rather than defaulting to
one (see README.md for why the split matters).

**Dinner pairing**: computed by script, not you. `apply_enrichment.py`
picks one `base_groups` entry and one `protein_groups` entry per day,
excluding anything in that day's own `lunch_groups` or the next school
day's (a `lunch_only_groups` tag like `"Processed Meat"` also excludes
its `LUNCH_ONLY_IMPLIES` counterpart, e.g. plain `"Meat"`). Among what's
left it prefers whichever group is furthest below its weekly
weight-adjusted target (`food_groups.WEIGHTS` - `"Oily Fish"` is
weighted twice `"Meat"`, so it is suggested roughly twice as often).
There is no rotation state file: the counts are derived by replaying
`archive/*/enriched.json`, and re-running an already-archived date
returns the same pairing rather than reassigning.

**Then**, merge and validate:

```
python3 scripts/apply_enrichment.py menu.json response.json -o enriched.json
```

This adds `lunch_food_groups` (= your `lunch_groups`, kept for
transparency), `title` ("🧑‍🍳 " + `ca_title`), and `dinner` ("🍽️ " + the
Catalan base/protein words joined by " + ") to each day, plus an `en`
block with the English items/dessert/title/dinner (same two emoji). The
emoji, the dinner pairing, and the Catalan food-group words all come
from the script - don't put them in response.json yourself. It also
merges `new_translations` into `data/glossary.json`.

Fails with exit code 2 if a day is missing from your response, its
`lunch_groups` is empty, or contains a value outside
`base_groups`/`protein_groups`/`lunch_only_groups`. Fix response.json
and rerun - don't hand-edit enriched.json.

## Publish the 4 public calendars

The repo is public and `public/*.ics` are served as raw GitHub URLs that
people subscribe to from Google Calendar (see "Hosting" below).
`publish_ics.py` upserts events by UID: repeated or out-of-order runs
don't duplicate or drop previously-published months.

```
python3 scripts/publish_ics.py enriched.json
git add public/ && git commit -m "Publish <Month Year> menu" && git push
```

This updates, in place:

| File | Content |
|---|---|
| `public/lunch_ca.ics` | Lunch, Catalan |
| `public/lunch_en.ics` | Lunch, English |
| `public/dinner_ca.ics` | Dinner pairing, Catalan |
| `public/dinner_en.ics` | Dinner pairing, English |

Running it against un-enriched JSON still works: `lunch_ca` fills in with
fallback titles; the other three skip every day (no error).

### Hosting

Subscription URL for each file:
`https://raw.githubusercontent.com/<owner>/<repo>/main/public/<file>.ics`

The repo must be public for this to resolve. If it hasn't been made
public yet, or has no GitHub remote, stop and ask before creating a
repo or changing its visibility.

## Adding a new month as a test fixture

```
cp <new-pdf> tests/fixtures/<YYYYMM>-BASAL.pdf
python3 scripts/run_tests.py            # writes a .proposed.json for review
# read the .proposed.json against the actual PDF, then:
python3 scripts/run_tests.py --update-golden
```

## Files

- `scripts/menu.py` - fetch/parse/ics entry point.
- `scripts/fetch_menu.py`, `parse_menu.py`, `to_ics.py` - the pieces
  `menu.py` wraps; only touch these directly for development/debugging.
- `scripts/prepare_enrichment.py`, `apply_enrichment.py`, `food_groups.py`,
  `dinner_rotation.py` - the title/dinner/translation round trip above.
- `scripts/pipeline_status.py`, `publish_month.py` - scheduled-job helpers (what to do next; publish + commit + push to main).
- `scripts/publish_ics.py` - upserts a month's JSON into `public/*.ics`.
- `scripts/run_tests.py` - regression runner against `tests/fixtures/*.pdf`
  (parsing only, not enrichment).
- `data/glossary.json` - persistent Catalan→English phrase cache, grown
  by `apply_enrichment.py`.
- `archive/<YYYYMM>/` - each published month's `menu.json`,
  `response.json`, `enriched.json` and source PDF (git-lfs), written by
  `publish_month.py`. The dinner rotation is derived from the
  `dinner_food_groups` in these `enriched.json` files, so every
  published month must also be archived.
- `public/*.ics` - the 4 live, publicly-hosted calendars (see "Publish
  the 4 public calendars" above). Don't hand-edit; only `publish_ics.py`
  writes these.
