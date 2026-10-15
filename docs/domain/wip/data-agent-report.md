# Domain list data: report

The Domain list is generated and committed, with the generator and the reference tool. Its hash is **0xBC3B2D7E** ("Domain 1.4"). The current, unmodified client sees the same file as an empty list with hash 0x7DFCEE6A. The current Multirole drops it.

## What was built

All of this is in `/home/user/lflistszedja`, on branch `claude/clever-cori-fy407t`.

**`tools/domain_gen.py`** (standard library only, deterministic):
- **Inputs:** `--babel <dir>` reads `cards.cdb`, then `release-*.cdb`, then `prerelease-*.cdb`; for a code in several files, the first file wins. `--scripts <dir>` reads `archetype_setcode_constants.lua`. `-o` sets the output file.
- **Other modes:** `--check` exits 1 if the file is out of date, `--explain <code|name>` shows how one Domain was built, and `--report` lists unresolved quotes and differences with the scripts' `listed_names`/`listed_series`.
- **Which cards get a line (D1):** every Main or Extra Deck monster that is not a Token or Skill and either has `alias == 0` or has an alias pointing to a card with a different name.
- **Names:** cards with an alias to a different-name card can be named too (D9). Names that contain quotes (Therion "King" Regulus) are protected before quotes are split, and the card's own name is ignored.
- **Spell/Trap codes are dropped from `n` (D7).**
- **Attributes and Types:** taken from the text outside quotes, which covers Token definitions.
- **Text that is ignored:** "This card is not/always treated as" reminders, Normal monster flavor text (Pendulum Normals keep their Pendulum Effect), and the unofficial-translation note.
- **Base archetype reduction:** a sub-archetype becomes its base if the base is a known `SET_` constant. Otherwise a code with several sub-bits is split into the single-bit parts that are known constants; if no part is known, the code stays (Evoltile 0x304e).
- **Checks before writing:** the output is re-parsed with `domain_ref.py`. The run fails on duplicate codes, a hash of 0 or 0x7DFCEE6A, any running hash of 0, or a parsed line that differs from the generated one.

**`Domain.lflist.conf`:**
- It starts with `#[Domain]`, `!Domain 1.4`, `$domain`, then a short comment header (no header line starts with `#@`).
- It has 9,379 `#@dm` lines sorted by code, with no `#@forbid-dm` lines and no card lines.
- Empty fields are left out of a line. The file is 277 KB.

**`tools/domain_ref.py`:**
- **(a) Parsing**, on bytes, following the client:
  - Everything from the first CR on is dropped.
  - `$domain` and `$genesys` are prefix matches and only count after a `!` line. The first one wins; a later `$genesys` or `$domain` is ignored.
  - `#@` lines are data only after `$domain`; before it, or in any other list, they are comments.
  - Malformed lines and the duplicate rule are written into the docstring.
- **(b) Hash:**
  - Ordinary card lines are hashed exactly as `LoadLFListSingle` does it, including the `stoul`/`stol` quirks and the Genesys salts.
  - `$domain` adds DomainSalt 0x444F4D41.
  - Each `#@` line adds `rotl32(fnv1a32(text),1)`, where text is what follows `#@` minus trailing spaces and tabs.
- **(c) `check_deck`** (§3 with D2, D3 and D10). Order:
  1. 0x11 (always checked).
  2. 0x14.
  3. Sizes 60 / 0-15 / 0.
  4. FORBTYPE, with `TYPE_SKILL` always forbidden.
  5. Rush or Legend `ot` → 0x12.
  6. For each card (Deck Master, Main, Extra, Side): unknown code, allowed-cards scope, singleton by `alias ? alias : code` → 0x13, then banlist lines.
  7. Membership → 0x12.
  - The Deck Master's line is looked up by its own code, then by its alias. At check time its own Attribute, Type and setcodes are always added to the line.
- **Subcommands:** `hash`, `show`, `count`, `check <ydk>` (`#master` support), `selftest`, and `vectors <out>`, which writes a file of corner cases with expected hashes Plain 0x2D18ED69, Dom A 0xE63170A0, Gen 0x926D8EE8.

**`.github/local-files.txt`:** the list and both tools are added. I ran the mirror's save/reset/restore steps on a scratch repo: `cp -a --parents` keeps `tools/`, and the files are restored and staged.

**Client copy:** `/home/user/wt/client/lflists/Domain.lflist.conf`, identical, committed alone on `domain-client`.

## Tests run

All commands were run from `/home/user/lflistszedja`.

- **Generator:** `python3 -I tools/domain_gen.py --babel /tmp/claude-0/genesys/BabelCDB --scripts /home/user/zedja123/cardscripts` writes 9,379 lines with hash 0xBC3B2D7E. Adding `--check` gives exit 0, and a second run with `PYTHONHASHSEED=123` produces a byte-identical file.
- **`python3 -I tools/domain_ref.py hash *.lflist.conf`:** all nine existing lists match a C++ build of the client's actual `LoadLFListSingle` body, extracted with sed. Domain.lflist.conf gives 0xBC3B2D7E, and the unmodified client gives 0x7DFCEE6A for it.
- **Fuzzing:** 900 random malformed files gave the same hashes in Python and in the C++ client code (0 mismatches).
- **Separate C++ version of the Domain extension:** I wrote one from the spec. It gives 0xBC3B2D7E and the same three vector hashes.
- **`domain_ref.py selftest`:** passes, including the FNV-1a test values.
- **Deck scenarios** (scratch script, Chronicle Magician as Deck Master): every case gave the expected verdict.
  - Legal deck: OK.
  - Bad Deck Master: no Deck Master, a Spell, a Token or an unknown code all give 0x11.
  - Wrong sizes: 59 Main, 1 Side or 16 Extra give the size errors.
  - Singleton: a duplicate card gives 0x13; so do a Deck Master copy in the Main Deck and Dark Magician with one of its alternate artworks.
  - Domain: an out-of-domain monster gives 0x12, while a Blue-Eyes White Dragon alternate artwork passes through its alias.
  - Other settings: the TCG-only setting gives OCGONLY. With content checks off, 0x11 and the size check still apply.

## Rulebook examples

Counts are out of 9,364 deckable monsters (`alias == 0`, not Tokens, all loaded databases).

| Deck Master | Line | Monsters in Domain |
|---|---|---|
| Chronicle Magician | `#@dm 60948488 a=20 r=2 s=dd,10a2 n=46986414,89631139` | 3,186 |
| Lo, the Prayers of the Voiceless Voice | `#@dm 25801745 a=10 r=2005 s=19e` | 3,677 |
| Dark Magician Girl | `#@dm 38033121 a=20 r=2 s=cf,10a2,20a2 n=30208479,46986414` | 3,209 |
| Destiny HERO - Malicious | `#@dm 9411399 a=20 r=1 s=8` | 3,626 |
| Incredible Ecclesia, the Virtuous | `#@dm 55273560 a=10 r=2 s=16d,1cf n=68468459` | 2,544 |
| Cyber-Stein | `#@dm 69015963 a=20 r=20` | 3,469 |

All six match the rulebook. Dark Magician Girl also gets "Chaos" (0xcf) from Magician of Black Chaos; the policy note accepts that.

## Where I departed from the spec

1. **D8 trigger words:** I extended them to allow a card kind before the word, e.g. `"Firewall" Link Monster`. Without this, Protectcode Talker lost "Firewall".
2. **Name resolution:** plurals and "(s)" are resolved ("Hyenas", "Servant(s) of Endymion"). There is one old name, "Frog the Jam" → Slime Toad, and three regional archetype names ("True Draco"/"True King" → `SET_TRUE_DRACO_KING`, "Goblin Biker" → `SET_GOBLIN_RIDER`). These tables are in the generator, not a separate override file.
3. **Rush database:** `prerelease-cards-rush.cdb` matches the `prerelease-*` pattern, so it is excluded by name. Rows with the Rush or Legend scope bit are also skipped.
4. **strings.conf is not used:** the upstream copy is stale and contradicts the constants (it lists 0x1066 as "Symphonic Warrior", while the constants make it "Magnet"). Archetype names come only from `SET_` constants. The names this loses mostly belong to codes no monster carries.
5. **Script data:** `listed_names`/`listed_series` are only used by `--report`, because the text is what the rulebook goes by.
6. **Hashing rule I had to choose:** every `#@` line in a Domain list is hashed, even unknown or malformed ones, and a code with several lines keeps the first. **The client and Multirole must do the same.**
7. **Order of 0x14:** I treat the forbidden-Deck-Master check as a content check, so it is skipped when content checks are off; 0x11 is still checked.
8. **A card's archetypes:** both the Deck Master's own archetypes and a named monster's archetypes use own row ∪ alias row, as D2 defines a card's archetypes.
9. **Runtime top-up:** at check time, only the Deck Master's own-row setcodes are added, following D2 to the letter.

## Known gaps

- 158 quoted strings are still unresolved. Most are Token names; the rest are broken nested quotes, number fragments, and prerelease names not in the databases (e.g. "Trirealm Rift").
- Some results are wide by policy: mentioning LV5 brings in all "LV", and base reduction turns Mecha Phantom Beast into all of "Phantom Beast" (0x1b).
- The Pendulum Normal flavor text is cut at the `----` separator.
- Prerelease codes have to be regenerated when the cards become official.

## Commits

- LFListsZedja:
  - `6c068a4b457c923dae4fcecedd042155a2187f81` reference implementation
  - `9b9b6482f18ce9353ebc7788a712b5718d1706b0` generator
  - `c5c6fb196a5dc9fdd1366dc96495a8b56e65e3cd` list + local-files
- Client (`domain-client`): `bd3053883eb9af3a97c02fdfae2b47883c735f54`

Nothing was pushed.

Files:
- `/home/user/lflistszedja/Domain.lflist.conf`
- `/home/user/lflistszedja/tools/domain_gen.py`
- `/home/user/lflistszedja/tools/domain_ref.py`
- `/home/user/lflistszedja/.github/local-files.txt`
- `/home/user/wt/client/lflists/Domain.lflist.conf`