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
- The model's only job for dinner is to **tag** each day's lunch with
  1-3 values from a fixed base/protein vocabulary (`food_groups.py`) -
  classification, not creativity. The actual pairing is picked
  afterward by a deterministic weighted rotation (`dinner_rotation.py`),
  persisted in `data/dinner_rotation.json` (same pattern as the
  glossary), excluding whatever's already in that day's or the next
  day's lunch tags. This removes a judgment call from the model and
  guarantees variety: left to pure LLM choice, it kept converging on
  the same "safe" pairing. The weights themselves (e.g. oily fish twice
  as often as red meat) come from pediatric Mediterranean-diet guidance
  - see "Why these dinner-pairing frequencies" below.
- Every script validates the model's output against a schema and a
  known-good vocabulary and fails loudly (`MenuParseError`,
  `EnrichmentError`) on anything unexpected, rather than silently
  accepting a malformed or hallucinated response.
- Nothing requires the model to hold the whole PDF or month in context
  at once - each request is a flat list of per-day JSON records.
- Formatting is never left to the model: the 🧑‍🍳/🍽️ prefixes, the
  dinner pairing itself, and its Catalan translation are all added by
  `apply_enrichment.py` after the fact, not requested in its output.

## Why these dinner-pairing frequencies

Real pediatric Mediterranean-diet guidance doesn't recommend equal
frequency across protein types - fish and legumes should appear more
often than red meat, for instance - so `dinner_rotation.py` doesn't
rotate all groups at the same rate. Two sources were checked and agree
closely:

1. **[L'alimentació saludable en l'etapa escolar](https://salutpublica.gencat.cat/web/.content/minisite/aspcat/promocio_salut/alimentacio_saludable/02Publicacions/pub_alim_inf/guia_alimentacio_saludable_etapa_escolar/guia_alimentacio_etapa_escolar_plecs.pdf)** (Agència de Salut Pública de Catalunya, 2020) - the official Catalan guide for exactly this population (school-age children in Catalonia), with two relevant tables: overall weekly intake targets (§2.1) and, separately, what a 5-day school canteen menu should already provide (§3.3) - the same regulatory basis CATASA's menus are built to (see the PDF's own footer legal text).
2. **[Casas R, Ruiz-León AM, Argente J, et al. "A New Mediterranean Lifestyle Pyramid for Children and Youth."](https://pmc.ncbi.nlm.nih.gov/articles/PMC11875175/)** *Adv Nutr.* 2025;16(3):100381. The first Mediterranean-diet pyramid designed specifically for ages 3-18, published by the Mediterranean Diet Foundation's research network.

Overall weekly targets (both meals combined), where they agree:

| Group | Target | Source |
|---|---|---|
| Fish (+ shellfish) | ≥3/week, ≥2 of them oily | both (ASPCAT: 2-3; Casas et al.: ≥3, ≥2 oily) |
| Legumes | 3-4/week | both |
| Eggs | 3-4/week | both |
| Red meat | ≤2/week | both |
| Processed meat | ≤1/week (within the red-meat cap) | Casas et al. |
| Dairy | 1-3 (ASPCAT) / 3-4 (Casas et al.) **per day** - frequent regardless of dinner | both |
| Vegetables | at least at both lunch and dinner | ASPCAT |

**Deriving a dinner-specific target**: the school lunch already covers part of each weekly quota, per ASPCAT's own canteen table (§3.3, a 5-day-week count): fish ~1, eggs ~1, legumes ~1-2, white meat/poultry ~1-2, red/processed meat ~0-1. Subtracting that from the overall weekly target gives roughly what dinner should fill in - these are the actual weights in `food_groups.WEIGHTS`. One detail that matters: the guide's own §2.1 recommends school-lunch fish as plain white-fish fillets (some oily species are restricted under age 10, for mercury), so the ≥2/week oily-fish target falls almost entirely to dinner.

| Protein group | Weight | Reasoning |
|---|---|---|
| Oily Fish | 2 | carries almost the entire ≥2/week oily-fish target, since lunch's fish is typically white |
| Legumes | 2 | 3-4 overall − ~1-2 at lunch |
| Eggs | 2 | 3-4 overall − ~1 at lunch |
| Poultry | 2 | no weekly cap; absorbs most of the remaining protein slots |
| Fish (white) | 1 | lunch's ~1/week already covers most of the non-oily portion of the target |
| Seafood | 1 | shares fish's overall budget as a lower-priority variant |
| Meat (red, unprocessed) | 1 | ≤2 overall, already mostly used by lunch - keep rare |
| Dairy | 1 | already covered 1-4×/day elsewhere; occasional as a dinner headline |

`"Processed Meat"` (cured/smoked/sausage - botifarra, ham, hot dogs) is
a separate tag from plain `"Meat"`, since its cap (≤1/week) is tighter
than red meat's - but it's lunch-tagging-only, never suggested for
dinner (`food_groups.LUNCH_ONLY_GROUPS`): it's a limit to respect, not
something to recommend more of. Tagging it still excludes `"Meat"` from
that day's dinner pick (`LUNCH_ONLY_IMPLIES`), since they're the same
nutritional family.

Vegetables (`Vegetables`/`Salad`, weight 2) outweigh the other
`base_groups` (Rice, Pasta, Potato, Bread, Cereal, Soup, weight 1 each)
given the "every meal" guidance, rather than being rotated as just one
option among eight.

`dinner_rotation.py` picks whichever eligible group has the lowest
`count / weight` ratio - so a weight-2 group gets suggested roughly
twice as often as a weight-1 group, not at the same rate.

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
data/      glossary.json - translation cache; dinner_rotation.json - pairing state
tests/     fixtures (sample PDFs) + golden (expected JSON)
public/    the 4 live, published calendars (generated, not hand-edited)
```
