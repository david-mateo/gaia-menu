---
name: gaia-menu
description: Escola Gaia school menu. Fetch the month's PDF, parse it to JSON, enrich it with titles and dinner pairings, and publish the four subscribed .ics calendars. Use for the scheduled monthly publish, or when asked for a month's menu as data or as a calendar.
disable-model-invocation: true
---

# Gaia school menu

Needs `pdftotext` on PATH (`brew install poppler`, `pacman -S poppler`).

Run every command from the repo root.

## The monthly run

Publish the new month into the four calendars in `public/`, then commit
and push to `main`. Work files live in one directory per month,
`W=~/.hermes/gaia-menu-work/<YYYYMM>`, which step 0 prints as `WORKDIR`.

`public/`, `archive/` and `data/glossary.json` are the only paths that
go to `main` this way. Put a code or doc change on its own branch.

Produce generated JSON by running the step that writes it, so a fix
means re-running a step rather than editing its output.

**Step 0, what now?** The job runs on the 28th through the 5th.

    python3 scripts/pipeline_status.py

The last line is `NEXT=`. `WAIT` and `DONE` both mean stop without
reporting. `FETCH` means step 1, `ENRICH` step 2, `APPLY` step 4,
`PUBLISH` step 5. Re-run step 0 after each step until it says `DONE` or
`WAIT`.

**Step 1, fetch and parse.**

    mkdir -p $W && python3 scripts/menu.py --download-dir $W -o $W/menu.json

**Step 2, prepare the request.**

    python3 scripts/prepare_enrichment.py $W/menu.json -o $W/request.json

**Step 3, write `$W/response.json`.** This step is yours, and
[`ENRICHMENT.md`](ENRICHMENT.md) is the contract: the schema, the title
rules, and how to tag a lunch. Done when every phrase in `new_phrases`
has a translation and every date in `request.json` has exactly one entry.

**Step 4, merge.**

    python3 scripts/apply_enrichment.py $W/menu.json $W/response.json -o $W/enriched.json

**Step 5, publish.** Upserts the four .ics files, copies the month into
`archive/<YYYYMM>/`, commits as "Hermes (gaia-menu)", pushes, and writes
`$W/published.done`.

    python3 scripts/publish_month.py $W <YYYYMM>

Report in at most two lines: the month, and what was pushed or the exact
error. Stay silent when step 0 opened with `WAIT` or `DONE`.

## Running it by hand

`scripts/menu.py` fetches and parses this month, printing JSON to stdout.

| Flag | Effect |
|---|---|
| `-o FILE` | write the JSON to FILE |
| `--ics FILE` | also write a .ics calendar |
| `--pdf FILE` | parse a PDF you already have, skipping the fetch |

Enriching by hand is the same three steps as 2 through 4 above, with
your own paths.

To update the published calendars from an enriched menu without the
scheduled job, run `scripts/publish_ics.py <enriched.json>`, then commit
and push `public/`.

## When a step fails

Every script exits 2 on bad input with a message on stderr naming the
day or the layout rule that did not hold, and exits 1 on a fetch or git
problem.

- **`menu.py` exit 1.** The listing page moved or the network failed.
  Report the stderr message as it stands.
- **`menu.py` exit 2.** The PDF no longer matches the expected layout,
  so the school changed the template. Report the exact message and stop;
  a maintainer adds a parsing rule, guided by `parse_menu.py`'s module
  docstring.
- **`apply_enrichment.py` exit 2.** Your `response.json` is missing a
  day, or names a food group outside the vocabulary. Correct
  `response.json` and re-run step 4.
- **`publish_month.py` exit 1.** Read the message, retry once, then
  report it.

## Hosting

Each calendar is served raw from GitHub:

    https://raw.githubusercontent.com/<owner>/<repo>/main/public/<file>.ics

This resolves only while the repo is public. When it is private, or has
no remote yet, stop and ask before creating a repo or changing its
visibility.

## Adding a month as a test fixture

    cp <pdf> tests/fixtures/<YYYYMM>-BASAL.pdf
    python3 scripts/run_tests.py          # writes <stem>.proposed.json

Read the proposed JSON against the PDF, then accept it with
`python3 scripts/run_tests.py --update-golden`.

## What lives where

`ls scripts/` lists the tooling; these are the parts its filenames do
not tell you.

- `models.py` holds the entities every stage passes around: `Menu`,
  `MenuDay`, `Enrichment`, `DinnerPairing`, and their JSON shapes.
- `food_groups.py` is the closed tag vocabulary, one `FoodGroup` per
  entry carrying its Catalan name, role and weekly dinner weight.
- `dinner_rotation.py` assigns the pairings, deriving its counts from
  `archive/` rather than from a state file.
- `data/glossary.json` is the Catalan to English phrase cache, grown by
  `apply_enrichment.py`.
- `archive/<YYYYMM>/` keeps each published month's `menu.json`,
  `response.json`, `enriched.json` and PDF (git-lfs). The dinner
  rotation replays the pairings recorded there, so every published month
  must also be archived.
- `public/*.ics` are the four live calendars. `publish_ics.py` writes
  them.
