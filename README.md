# Gaia Menu

Turns Escola Gaia's monthly school lunch PDF into structured data and
public calendars, with dinner suggestions and an English translation.

## What it produces

**JSON.** One entry per school day, carrying the date, weekday, dishes,
dessert and allergen codes. Closure days and days with no menu never
reach the output.

**Four public .ics calendars**, accumulating month over month: lunch in
Catalan, lunch in English, the dinner suggestion in Catalan, and in
English. Anyone can subscribe from Google Calendar, Apple Calendar or
Outlook using the raw GitHub URL. Lunch events run 13:15 to 14:00 and
dinner events 19:00 to 20:00, Madrid time. Event titles are short
summaries carrying 🧑‍🍳 for lunch and 🍽️ for dinner, like
`🧑‍🍳 Amanida de patata + truita` and `🍽️ Soup + Fish`.

## Design: parsing needs no AI, enrichment needs very little

The PDF to JSON step in `parse_menu.py` is pure geometry over
`pdftotext -bbox` word coordinates. No model call, same output every run.
Its module docstring walks through how the table comes back together.

Enrichment does need judgment, so it goes through a model. The job is
narrow enough that a small one handles it:

**Translation is cached.** `data/glossary.json` grows as the school year
goes on, and only phrases it has never seen get sent out. By spring most
months need no new translation at all.

**The model tags, it does not choose.** Its only dinner-related job is
labelling each lunch with one to three values from a fixed vocabulary in
`food_groups.py`. That is classification, not invention.
`dinner_rotation.py` then picks the pairing, skipping whatever the day's
own lunch and the next day's lunch already cover. Letting the model pick
directly was the first design, and it kept converging on the same safe
answer. The weights behind the rotation come from pediatric
Mediterranean-diet guidance, covered below.

**Everything validates on the way in.** `parse_menu.py` and
`apply_enrichment.py` both exit 2 with the day or the layout rule that
failed, instead of quietly accepting a malformed or invented response.

**Formatting never reaches the model.** The emoji, the Catalan group
names and the pairing itself all come from `apply_enrichment.py` after
the fact, so nothing in `response.json` carries them.

The full contract for that round trip lives in
[`ENRICHMENT.md`](ENRICHMENT.md).

## Why these dinner-pairing frequencies

Pediatric Mediterranean-diet guidance does not ask for equal frequency
across protein types. Fish and legumes should turn up more often than red
meat. So `dinner_rotation.py` weights them. Two sources agree closely on
the numbers:

1. [L'alimentació saludable en l'etapa escolar](https://salutpublica.gencat.cat/web/.content/minisite/aspcat/promocio_salut/alimentacio_saludable/02Publicacions/pub_alim_inf/guia_alimentacio_saludable_etapa_escolar/guia_alimentacio_etapa_escolar_plecs.pdf),
   Agència de Salut Pública de Catalunya, 2020. The official Catalan
   guide for this exact population, carrying two useful tables: weekly
   intake targets in §2.1, and what a five-day school canteen menu should
   already supply in §3.3. It is the same regulatory basis CATASA builds
   these menus to, as the PDF's own footer says.
2. Casas R, Ruiz-León AM, Argente J, et al. [A New Mediterranean Lifestyle Pyramid for Children and Youth](https://pmc.ncbi.nlm.nih.gov/articles/PMC11875175/).
   *Adv Nutr.* 2025;16(3):100381. The first Mediterranean-diet pyramid
   drawn specifically for ages 3 to 18.

Weekly targets across both meals, where the two agree:

| Group | Target | Source |
|---|---|---|
| Fish including shellfish | ≥3/week, ≥2 of them oily | both; ASPCAT says 2-3, Casas et al. ≥3 with ≥2 oily |
| Legumes | 3-4/week | both |
| Eggs | 3-4/week | both |
| Red meat | ≤2/week | both |
| Processed meat | ≤1/week, inside the red-meat cap | Casas et al. |
| Dairy | 1-3 or 3-4 **per day**, frequent either way | both |
| Vegetables | at both lunch and dinner | ASPCAT |

School lunch already covers part of each quota. ASPCAT's canteen table
counts roughly one fish, one egg, one or two legume, one or two white
meat and up to one red or processed meat serving across a five-day week.
Subtracting that from the weekly target leaves what dinner should carry,
which is the `weight` each `FoodGroup` in `food_groups.py` holds.

One detail drives the largest weight. ASPCAT recommends school-lunch fish
as plain white fillets, and restricts some oily species under age 10 over
mercury, so the oily-fish target falls almost entirely to dinner.

| Protein group | Weight | Why |
|---|---|---|
| Oily Fish | 2 | carries nearly the whole ≥2/week oily target, since lunch fish is white |
| Legumes | 2 | 3-4 overall, about 1-2 at lunch |
| Eggs | 2 | 3-4 overall, about 1 at lunch |
| Poultry | 2 | no weekly cap, so it absorbs the remaining slots |
| Fish (white) | 1 | lunch already covers most of the non-oily share |
| Seafood | 1 | draws on the same budget as fish, at lower priority |
| Meat (red, unprocessed) | 1 | ≤2 overall and mostly spent at lunch, so keep it rare |
| Dairy | 1 | already eaten 1 to 4 times a day elsewhere |

`Processed Meat` is a separate tag from plain `Meat`, because its cap is
the tighter of the two. It only ever tags a lunch, and never becomes a
suggestion, since it is a limit to respect rather than a target to hit.
Tagging it still keeps `Meat` out of that day's dinner, the two being the
same family.

Vegetables and Salad carry weight 2 against the other base groups at
weight 1, following the "at every meal" guidance.

`dinner_rotation.py` picks whichever eligible group has the lowest
count divided by weight, so a weight-2 group comes up about twice as
often as a weight-1 group.

## The archive

`publish_month.py` writes `archive/<YYYYMM>/` for every month it
publishes, holding `menu.json`, the `response.json` the model produced,
`enriched.json`, and the source PDF through git-lfs.

It is not only a record. The dinner rotation keeps no state file at all.
`dinner_rotation.derive_state()` replays the pairing recorded on every
archived day to rebuild its counts, so a month that gets published but
not archived stays invisible to every later month's balancing.

Two things follow. Rotation history cannot drift from what was actually
published, because it *is* what was published. And a group retired from
`food_groups.py` gets skipped on replay rather than crashing the next
run, so the vocabulary can change without a migration.

`response.json` earns its place for a second reason. It is the one
artefact the PDF cannot reproduce, being model judgment.

## Setup

Python 3.10 or newer, standard library only, plus `pdftotext`:

```
brew install poppler      # macOS
pacman -S poppler         # Arch
```

## Usage

### As a series of scripts

```
python3 scripts/menu.py -o menu.json --ics menu.ics       # fetch, parse, ics; no AI

python3 scripts/prepare_enrichment.py menu.json -o request.json
# write response.json yourself, or hand request.json to a model; ENRICHMENT.md has the contract
python3 scripts/apply_enrichment.py menu.json response.json -o enriched.json

python3 scripts/publish_ics.py enriched.json               # upserts public/*.ics
git add public/ && git commit -m "Publish menu" && git push
```

`scripts/run_tests.py` runs everything: golden-file checks for the parser
over `tests/fixtures/*.pdf`, then the unit tests covering the rotation
and the .ics upsert.

### As a skill, for Claude Code, Codex, Hermes or any agent with a shell

`SKILL.md` is the operating manual, holding the commands, the failure
modes, and a pointer to `ENRICHMENT.md` for the response contract. It is
plain Markdown with YAML frontmatter, so any agent that reads a file and
runs a shell command can follow it.

**Claude Code.** Symlink the repo into `~/.claude/skills/gaia-menu` and
invoke `/gaia-menu`. The frontmatter sets `disable-model-invocation`, so
it fires only when invoked by name.

**Any other harness.** Point the agent at the repo and tell it to read
`SKILL.md`, for instance "read SKILL.md and get this month's menu as an
ics". An unrelated harness ignores the frontmatter keys and reads the
body, which is where the instructions are.

## Layout

```
scripts/   the tooling; models.py holds the entities the stages share
data/      glossary.json, the Catalan to English phrase cache
archive/   one directory per published month
tests/     fixtures and goldens for the parser, unit tests for the rest
public/    the four live calendars, written by publish_ics.py
```
