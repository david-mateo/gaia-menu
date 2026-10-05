# Writing response.json

The enrichment round trip: `prepare_enrichment.py` writes a request, you
write the response, `apply_enrichment.py` merges and validates it. Step 3
of the monthly run in [`SKILL.md`](SKILL.md) is where this fires.

You supply the translation, the short titles, and the lunch tags.
The dinner pairing is not yours to choose: `apply_enrichment.py` computes
it from the tags you give it.

## What the request gives you

| Key | Use |
|---|---|
| `days` | each date with its Catalan `items` and `dessert` |
| `known_translations` | phrases the glossary already covers, reused as they stand |
| `new_phrases` | phrases needing a translation from you |
| `base_groups`, `protein_groups` | the tags a dinner can be built from |
| `lunch_only_groups` | tags valid on a lunch that are never suggested for dinner |

## What to write

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

`new_translations` covers every phrase in `new_phrases`. `days` has one
entry per date, matched exactly.

Fill each day in this order: `en_items` and `en_dessert` first, then
`en_title` summarising what you just translated, then `ca_title` from the
original Catalan items, then `lunch_groups`. `ca_title` is a fresh
summary of the Catalan, not a translation of `en_title`.

## Titles

Three or four words, two dishes joined by " + ". Drop articles, sauces
and garnish unless they carry the dish. A general word such as "Verdures"
works when it reads better than the literal name.

| Items | Title |
|---|---|
| Amanida de patata, Truita francesa, Enciam i tomàquet | Amanida de patata + truita |
| Macarrons integrals ecològics amb carbonara vegetal, Botifarra de porc amb samfaina | Macarrons + botifarra |
| Crema de carbassó, Escalopa d'au cordon bleu de gall dindi, Enciam i blat de moro | Crema de carbassó + escalopa de gall dindi |
| Amanida de cigrons (pastanaga, blat de moro i tomàquet), Mandonguilles mixtes a la jardinera (...) | Amanida de cigrons + mandonguilles |
| Arròs integral amb salsa de tomàquet, Salmó al forn amb anet, Enciam i olives | Arròs + Salmó |
| Bròquil, patata i pastanaga, Llenties estofades amb verdures | Verdures + llenties |
| Fideus a la cassola amb verdures, Truita de patata, Enciam i tomàquet | Fideus amb verdures + truita |

A dish split across two consecutive `items` entries is one dish the PDF
wrapped onto two lines, as in row 2 above. Read a short entry that does
not stand on its own as the tail of the one before it.

## Tagging a lunch

`lunch_groups` takes one to three tags from `base_groups`,
`protein_groups` or `lunch_only_groups` describing what the lunch holds.
A potato-and-egg dish with a side salad is
`["Potato", "Eggs", "Salad"]`. Tag what is on the plate; the pairing is
computed from it.

Tell the two fish groups apart by species, since they carry different
weekly targets:

- `Fish` is white or lean: lluç, bacallà, rap, llenguado, orada.
- `Oily Fish` is blue: salmó, tonyina, sardina, verat, seitó or anxova.

`Processed Meat` covers cured, smoked and sausage preparations such as
botifarra, pernil and frankfurts. It is a lunch tag only. Using it also
keeps plain `Meat` out of that day's dinner.

## How the pairing is computed

`apply_enrichment.py` takes one base group and one protein group per day,
skipping anything the day's own tags or the next school day's tags rule
out. Among the rest it takes whichever group sits furthest below its
weekly target, so `Oily Fish` at weight 2 comes up about twice as often
as `Meat` at weight 1. README.md "Why these dinner-pairing frequencies"
has the sourcing.

The counts come from replaying `archive/*/enriched.json`, so re-running a
month the archive already covers returns the pairings it already has.

## What the merge adds

Each day gains `lunch_food_groups`, `dinner_food_groups`, `title`,
`dinner`, and an `en` block holding the English items, dessert, title and
dinner. The emoji, the Catalan group names and the pairing all come from
the script, so `response.json` carries none of them.

`apply_enrichment.py` exits 2 naming the day when one is missing from
your response, when its `lunch_groups` is empty, or when it names a group
outside the vocabulary. Correct `response.json` and run the merge again.
