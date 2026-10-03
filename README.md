# Gaia Menu

Turns Escola Gaia's monthly school lunch PDF into structured data and
public calendars, with optional dinner-pairing suggestions and English
translation.

## What it produces

- **JSON**: one entry per school day (date, weekday, dishes, dessert,
  allergen codes). Closure days and menu-less days are omitted.
- **4 public `.ics` calendars**, each accumulating across months:
  lunch in Catalan, lunch in English, a recommended dinner pairing in
  Catalan, and in English. Subscribable from Google Calendar / Apple
  Calendar / Outlook via raw GitHub URLs. Event titles are a short
  summary, prefixed with 🧑‍🍳 for lunch and 🍽️ for dinner, e.g.
  `🧑‍🍳 Amanida de patata + truita` / `🍽️ Soup + Fish`.

## Design: parsing needs no AI, enrichment needs very little

The PDF → JSON step (`parse_menu.py`) is pure geometry and deterministic
rules over `pdftotext -bbox` word coordinates - no model call, same
output every run. See its module docstring for exactly how the table is
reconstructed.

The optional enrichment step (short title, dinner-pairing suggestion,
English translation) genuinely needs judgment, so it does go through an
LLM - but the task is narrowed enough that a small/cheap model is
sufficient:

- Translation is cached (`data/glossary.json`); only phrases not seen
  before are sent for translation, which trends toward zero as the
  glossary fills in over a school year.
- Dinner pairings must be exactly two words from a **fixed 16-word
  vocabulary** (`food_groups.py`), not free text - this keeps Catalan
  translation of the pick a plain dict lookup, and gives the model a
  closed, low-ambiguity choice instead of an open-ended one.
- Every script validates the model's output against a schema and a
  known-good vocabulary and fails loudly (`MenuParseError`,
  `EnrichmentError`) on anything unexpected, rather than silently
  accepting a malformed or hallucinated response.
- Nothing requires the model to hold the whole PDF or month in context
  at once - each request is a flat list of per-day JSON records.
- Formatting is never left to the model: the 🧑‍🍳/🍽️ prefixes and the
  Catalan translation of a dinner pick are added by
  `apply_enrichment.py` after the fact, not requested in its output.

## Setup

Requires Python 3.10+ (standard library only - no `pip install`) and
`pdftotext`:

```
brew install poppler      # macOS
pacman -S poppler          # Arch
```

## Usage

### As a series of scripts

```
python3 scripts/menu.py -o menu.json --ics menu.ics       # fetch, parse, ics (no AI)

python3 scripts/prepare_enrichment.py menu.json -o request.json
# fill in response.json yourself, or hand request.json to any LLM (see SKILL.md for the schema)
python3 scripts/apply_enrichment.py menu.json response.json -o enriched.json

python3 scripts/publish_ics.py enriched.json               # upserts public/*.ics
git add public/ && git commit -m "Publish menu" && git push
```

`scripts/run_tests.py` is the regression suite for the parsing step
(`tests/fixtures/*.pdf` → `tests/golden/*.json`).

### As a skill (Claude Code, Codex, Hermes, or any agent that can run shell commands)

`SKILL.md` is the full operating manual: exact commands, the
request/response JSON schemas for enrichment, title/dinner examples, and
what to do when something fails. It's plain Markdown with YAML
frontmatter - any agent that can read a file and run shell commands can
follow it, not just Claude.

- **Claude Code**: symlink this repo into `~/.claude/skills/gaia-menu`
  and invoke with `/gaia-menu`. `disable-model-invocation: true` in the
  frontmatter means it only runs when explicitly invoked, never
  auto-triggered from conversation.
- **Codex, Hermes, or another agent harness**: point the agent at this
  repo and tell it to read `SKILL.md` and follow it (e.g. "read
  SKILL.md and get this month's menu as an ics"). The frontmatter keys
  are Claude Code-specific metadata an unrelated harness will just
  ignore; the body is the actual instructions.

## Layout

```
scripts/   all tooling (see SKILL.md for what each does)
data/      glossary.json - persistent translation cache
tests/     fixtures (sample PDFs) + golden (expected JSON)
public/    the 4 live, published calendars (generated, not hand-edited)
```
