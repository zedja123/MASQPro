# Domain research: the card data needed to work out a Deck Master's Domain

I ran a prototype extractor (`/tmp/claude-0/domain-proto/domain.py`, run with `python3 -I domain.py <code|name> | --sample N seed | --stats`). It finds the rulebook's expected Domain for all five examples. The databases give it what it needs: setcodes already follow the Japanese (OCG) archetype rules, and `alias` handles the "always treated as" cards. Two rules have to be added by hand: how to reduce an archetype to its base, and how to split combined sub-archetypes. The online server (Multirole) does not load card text, so the Domain probably has to be computed ahead of time.

Nothing in the repositories was changed. My only writes were under `/tmp/claude-0/domain-proto/`: the scripts (`domain.py`, `probe.py`, `fp.py`), `sample40.txt`, and a downloaded upstream `strings.conf` in `dl/`.

## 1. Database schema, setcodes and `alias`

**Checked in code and data.**
- **Schema** (`BabelCDB/cards.cdb`):
  - `datas(id, ot, alias, setcode, type, atk, def, level, race, attribute, category)`
  - `texts(id, name, desc, str1..str16)`
  - 14,759 rows. 9,224 are monsters that are not alternate artworks and not Tokens.
- **Setcode packing:** one 64-bit `setcode` holds up to four 16-bit archetype codes.
  - Multirole unpacks it in `multirole/src/Multirole/YGOPro/CardDatabase.cpp:159-162` with `setcodes[i] = (dbVal >> (i * 16U)) & 0xFFFF;`.
  - Example: `Numbers Last Hope` has `0x107b007f016c`. 55 monsters have three or more codes, and 7 have four.
- **How "belongs to archetype" is tested.** Each 16-bit code is a 12-bit base (`&0xfff`) plus up to four sub-archetype bits (`&0xf000`). Three places use the same test:
  - Engine: `ocgcore/card.h:185-187`, `return (set_code & 0xfffu) == (to_match & 0xfffu) && (set_code & to_match) == set_code;`
  - Lua: `cardscripts/utility.lua:1001`
  - Client: `gframe/data_manager.cpp:627-630`

  So a code with sub-bits only matches cards that carry all of those bits.
- **`alias` has two meanings in the same column:**
  - Alternate artwork: same name. The client checks this with `abs(alias-code) < 10` (`gframe/deck_manager.cpp:582`). That shortcut has 28 exceptions, for example Dark Magician `36996508` has alias `46986414`. All of them are Tokens except Black Luster Soldier `10000100`, Dark Magician `36996508`, Polymerization `27847700` and a dead `9995767` entry. A same-name comparison is the reliable test.
  - "Always treated as": different name. There are 18 non-Token rows like this, for example Harpie Lady 1/2/3 → Harpie Lady, Fallen of the White Dragon → Fallen of Albaz, Odd-Eyes Arcray → Supreme King Z-ARC, Neo-Spacian Twinkle Moss → Glow Moss ("also treated as").
  - The client counts copies by canonical code (`deck_manager.cpp:247`, `uint32_t code = cit->alias ? cit->alias : cit->code;`), and Multirole aliases its code map too (`Room/Context.cpp:302+`). So singleton-by-alias already matches the rulebook's Umi example.
- **Data quirk:** the Blue-Eyes White Dragon alternate artworks `89631140`–`89631144` have setcode `0x0` while the base card has `0xdd`. Archetype checks must use the canonical (alias) row.
- **Setcodes follow Japanese definitions:** Mobius, Erebus and Zaborg (the Monarchs) are `0x0`, Dark Magician of Chaos is `0x0`, and Chronicle Magician is `0x0`, not "Magician" `0x98`.

| Card | id | alias | setcode | attr | race | type |
|---|---|---|---|---|---|---|
| Umi | 22702055 | 0 | 0 | – | – | 0x80002 (Field Spell) |
| A Legendary Ocean | 295517 | 22702055 | 0 | – | – | Field Spell |
| Pacifis, the Phantasm City | 2819435 | 22702055 | 0 | – | – | Field Spell |
| Sea Stealth II | 58203736 | **0** | 0x17a Sea Stealth | – | – | 0x20002 (Continuous Spell) |
| Harpie Lady | 76812113 | 0 | 0x64 | WIND(8) | Winged Beast 0x200 | 0x11 (Normal) |
| Harpie Lady 1 / 2 / 3 | 91932350 / 27927359 / 54415063 | 76812113 | 0x64 | WIND | Winged Beast | 0x21 (Effect) |
| Harpie Lady Sisters | 12206212 | **0** | 0x64 | WIND | Winged Beast | 0x2000021 |
| Dark Magician Girl | 38033121 (10 alternate artworks, including 38033120) | 0 | 0x30a2 | DARK(0x20) | Spellcaster | 0x21 |
| Destiny HERO - Malicious | 9411399 | 0 | 0xc008 | DARK | Warrior | 0x21 |
| Cyber-Stein | 69015963 | 0 | **0** | DARK | Machine | 0x21 |
| Chronicle Magician | 60948488 | 0 | 0 | DARK | Spellcaster | 0x21 |
| Lo, the Prayers of the Voiceless Voice | 25801745 | 0 | 0x19e | LIGHT | Fairy | 0x21 |
| Incredible Ecclesia, the Virtuous | 55273560 (+…61, …62) | 0 | 0x1cf | LIGHT | Spellcaster | 0x1021 (Tuner) |
| Fallen of Albaz | 68468459 (+…60, …61) | 0 | **0** | DARK | Dragon | 0x21 |

The `ot` values in cards.cdb are 1, 2 or 3 (plus one row with 0).

**The base-archetype rule cannot be a plain `& 0xfff`** (checked against the data). Dark Magician Girl is `0x30a2`. Its base `0xa2` is named "Magician" in `strings.conf`, but there is no `SET_` constant for it, and it only appears on Magician of Chaos and Magician of Black Chaos MAX (`0xa200cf`). The rulebook wants "Dark Magician" (`0x10a2`) plus "Magician Girl" (`0x20a2`) instead. The prototype's rule:
- Reduce to the base only when the base exists as a `SET_` constant: `0xc008` → `0x8` HERO.
- Split a code with several sub-bits into its named single-bit codes: `0x30a2` → `0x10a2` and `0x20a2`.

221 monster sub-codes have a base with no constant, and 260 codes have several sub-bits.

## 2. Where archetype names come from

**Checked.**
- **No `strings.conf` exists anywhere locally** (MASQPro, cardscripts, BabelCDB, multirole or `MASQPro.zip`).
  - The client loads it at runtime from `./config/strings.conf` and `./expansions/strings.conf` (`gframe/data_handler.cpp:130-131`).
  - It parses `!setname` lines in `gframe/data_manager.cpp:256-257,294-295`; `GetSetCode` (data_manager.cpp:401) matches by substring, with `|` separating alternative names.
- **Upstream copy:** I fetched ProjectIgnis/Distribution `config/strings.conf` to `/tmp/claude-0/domain-proto/dl/strings.conf`. It has 756 `!setname` lines.
  - It lacks recent archetypes: `0x1cf` Ecclesia is missing, and 30 setcodes used by monsters have no name.
  - 23 names are duplicated, including "Magician" for both `0x98` and `0xa2`, plus "Number" and "Shark".
- **`cardscripts/archetype_setcode_constants.lua`** has 615 `SET_*` constants (for example `SET_HERO = 0x8` at line 25, `SET_DESTINY_HERO = 0xc008` at 30, `SET_DARK_MAGICIAN = 0x10a2` at 245, `SET_MAGICIAN_GIRL = 0x20a2` at 246, `SET_DARK_MAGICIAN_GIRL = 0x30a2` at 247, `SET_ECCLESIA = 0x1cf` at 603, `SET_RB = 0x1ca` at 593). Names are normalised identifiers only. "R.B." becomes `RB`, which my normaliser turns into `R_B`, so it doesn't match.
- `card_counter_constants.lua` has 615 `CARD_*` constants, for example `CARD_ALBAZ` at line 7 and `CARD_DARK_MAGICIAN` at 30.
- Multirole loads only `id,alias,setcode,type,atk,def,level,race,attribute` and `ot,category` (`CardDatabase.cpp:76,82`). **It never reads `texts`.**

## 3. How the prototype works (`domain.py`)

- **Which text counts** (`effect_text`, line 71):
  - Removes the `* The above text is unofficial…` suffix that unofficial OCG translations carry.
  - Normal monsters: all text is ignored.
  - Pendulum Normal monsters: only the part before the `----` separator is kept. This also covers Prima Materiactor, whose flavor text is labelled `[ Monster Effect ]`.
  - Removes the reminders "(This card is not / always / also always treated as …)" (line 24). In the whole database this pattern matched 93 + 31 + 16 + 8 + 4 + 3 + 2 occurrences. The non-matches are "treated as an Xyz Summon" and similar, plus the unparenthesised "This card's name is also treated as" (Twinkle Moss).
- **Quoted names** (line 22): card names that themselves contain quotes are protected first (Therion "King" Regulus, K9-X "Ripper/M"). A trailing `(s)` is dropped and self-mentions are ignored. Each name is then checked two ways:
  1. Exact card name (excluding Tokens). If it is a monster, its archetypes are added after the base reduction.
  2. Normalised `SET_` or setname name, reduced to its base.
- **Attributes and Types:** scanned only after removing quoted text. Attributes match uppercase words exactly; Types match longest first with an optional `-Type` or plural suffix (lines 20-21). This picks up Token definitions such as `(Wyrm-Type/WATER/Level 8/…)`.
- **Script data:** the `s.listed_names` and `s.listed_series` tables from `official/c<code>.lua`. `id`, numbers, `CARD_*` and `SET_*` are resolved.
- **Membership test** (`in_domain`, line 170), in order: Spell/Trap; DIVINE or Divine-Beast; canonical code mentioned; archetype match using the engine's test; Attribute; Type.

## 4. Results

**Rulebook examples** (computed; "monsters in Domain" is out of 9,224):

| Deck Master | Computed Domain | Rulebook | Monsters in Domain |
|---|---|---|---|
| Chronicle Magician | DARK, Spellcaster, names Dark Magician + Blue-Eyes White Dragon → archetypes 0x10a2 Dark Magician, 0xdd Blue-Eyes | identical | 3,127 |
| Lo | LIGHT, Fairy, Warrior, Dragon (from text), 0x19e Voiceless Voice | identical | 3,617 |
| Dark Magician Girl | DARK, Spellcaster, own 0x10a2 + 0x20a2; names Dark Magician and Magician of Black Chaos → also **0xcf "Chaos"** | rulebook names Dark Magician and Magician Girl. Chaos follows from the "mentioned monster's archetype" rule; whether that is intended needs a decision | 3,151 |
| Destiny HERO - Malicious | DARK, Warrior, 0x8 HERO; `listed_names={id}` (self) ignored | identical | 3,572 |
| Incredible Ecclesia | LIGHT, Spellcaster, own 0x1cf, name Fallen of Albaz (setcode 0, so no archetype), 0x16d Swordsoul; script `listed_names={CARD_ALBAZ}`, `listed_series={SET_SWORDSOUL}` (c55273560.lua:49-50) agree | identical | 2,501 |
| Cyber-Stein | DARK, Machine, no archetypes (reminder removed, setcode 0) | identical | — |

**Statistics** (`--stats`, all 9,224 monsters):
- 8,539 have an `official/c*.lua` script. 684 of the 685 without one are Normal monsters; the other is Red-Eyes Darkness Metal Dragon.
- 1,273 have non-self `listed_names`, 3,515 have `listed_series`, and 4,348 have either.
- Average mentions extracted from text, per monster: names 0.224, archetypes 0.524, Attributes 0.159, Types 0.257. That is 1.16 items per monster on average, at most 9. 6,155 monsters have at least one.
- Text versus script:
  - 404 monsters mention a card in text that is missing from `listed_names`. Most are Fusion materials (Cyber End Dragon → "Cyber Dragon", ABC-Dragon Buster) or Spells such as Polymerization. So `listed_names` is incomplete.
  - 82 have `listed_names` entries that are not in the text, mostly Tokens.
  - `listed_series` keeps sub-codes (Predaplant `0x10f3`), while base reduction gives `0xf3` "Predap".
- 256 quoted strings were unresolved, across 197 monsters:
  - Token names (harmless)
  - Renamed cards ("Frog the Jam", now Slime Toad)
  - Quoted effect text with nested quotes (Prototype Sky Striker Ace - Amatsu: `"Destroy 1 "Sky Striker Ace" Link Monster…"`)
  - Numbers ("101", "107")
  - A database typo (Psychic Omnibuster has a missing closing quote)

**Random sample of 40 Effect monsters** (seed 7, `sample40.txt`):
- I found no Attribute or Type false positives. A database-wide scan of every Type-word match that isn't followed by "monster" (`fp.py`) found only real uses: lists, Token definitions, "for each Wyrm".
- Questionable results, all policy rather than parsing:
  - Ultimate Insect LV3 mentions LV5, which pulls in **0x41 "LV"**: every LV monster.
  - Base reduction widens mentioned archetypes: Mecha Phantom Beast → Phantom Beast `0x1b`, Sky Striker Ace → `0x115`, The Phantom Knights → `0xdb`.
  - Non-matches are only the nested-quote case above and unresolved Token names.

## Inferred, not verified
- That the rulebook applies base reduction to mentioned archetypes, not only to the Deck Master's own.
- That Fusion/Synchro material lines count as part of the "effect box".
- That negated mentions ("non-WATER") count. The prototype counts them.

## Implications for Domain

1. **Server has no text.** Multirole cannot extract a Domain at runtime (`CardDatabase.cpp:76`). Ship a precomputed Domain table generated offline by this extractor, loaded by both client and server. It would be keyed by canonical code, holding an Attribute mask, a 64-bit Type mask, archetype codes and named card codes. It could be its own file, or an extension of the lflist-style file the Genesys work added. Hand-fixes go in that file, and card scripts stay untouched.
2. **Membership needs only data both sides already load:** `setcode` and the engine's `match_setcode` test (`card.h:185`), `attribute`, `race`, `type`, `alias`. Always resolve to the canonical (alias) row first, because of the Blue-Eyes alternate artworks with setcode 0.
3. **Singleton:** reuse the existing alias counting (`deck_manager.cpp:247`, `Context.cpp` alias map) with a limit of 1, and include the Deck Master in the count. That covers Umi/Ocean/Pacifis and Harpie Lady 1/2/3. Sea Stealth II and Harpie Lady Sisters stay separate.
4. **Alias semantics:** treat "same name" as an alternate artwork, not `abs(diff) < 10` (28 exceptions). An alias with a different name is a "treated as" card, and it counts as the canonical card for both singleton and name mentions.
5. **Base-archetype rule:** implement it as written above (base only if it is a known `SET_` constant; split codes with several sub-bits) and commit the result into the table. Don't compute it in C++ from `strings.conf`: the upstream file is incomplete (no `0x1cf`) and has duplicate names.
6. **Risks that need a curated override list:**
   - Unexpectedly broad results (LV, Chaos, Phantom Beast)
   - Renamed or old card names
   - Nested-quote effect text
   - Material lines
   - Normal monsters, whose Domain is only Attribute, Type and own archetype
   - New archetypes not in the `SET_` or setname lists
7. **Deck format:** Deck Master codes must be Main or Extra Deck monsters (`type & TYPE_MONSTER`, not Token). OCG-only cards carry unofficial text; it is stripped, but those texts are fan translations.