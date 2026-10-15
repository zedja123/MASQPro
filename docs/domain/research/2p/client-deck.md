# MASQPro client (gframe/): deck model, editor, validation, card data, deck transport

All paths are relative to `/home/user/MASQPro/gframe/`. Anything marked **[infer]** is a conclusion I drew; everything else I checked in the code.

## 1. Deck model, .ydk I/O, sharing codes

**Struct.** `deck.h:7-18`: `struct Deck { Vector main; Vector extra; Vector side; void clear(); }`, where `Vector = std::vector<const CardDataC*>`. There is no fourth pile. `DeckManager` holds `sent_deck` and `pre_deck` (`deck_manager.h:79-80`).

**Parser.** `LoadCardList` is in `deck_manager.cpp:359-404`:
```cpp
if(str[0] == '#') { if(!extralist || str != "#extra") continue; is_extra = true; }   // 374-378
if(str[0] == '!') { is_side = true; continue; }                                         // 379-382
```
- Any `#` line other than `#extra` is treated as a comment. That includes `#main`, `#created by` and a hypothetical `#master`.
- Any `!` line switches to side, and the flags never reset. So a `!master` header would be read as side.
- The `#extra` header is only honoured when the caller passes `separated=true`.
  - The deck editor passes it (`deck_con.cpp:412,425,524,907`).
  - The room READY path passes `false` (`menu_handler.cpp:316,812`). Then every card goes into `mainlist`, and `LoadDeck` re-sorts by type (`is_extra_deck_card`, `deck_manager.cpp:422-436,446`).
- With `separated=true`, every code under `#extra` is pushed into `deck.extra` whatever its type (`deck_manager.cpp:452-465`).

**What an older client or upstream EDOPro would do with a `#master` section.** I only checked MASQPro's parser; upstream EDOPro is assumed identical **[infer]**.
- Placed between `#main` and `#extra`: the Deck Master (DM) is read as a Main Deck card.
- Placed after `#extra`: in the editor the DM goes into Extra even if it is a Main Deck monster, and validation then fails with EXTRACOUNT (`deck_manager.cpp:282-288`).
- Placed after `!side`: the DM is read as a Side Deck card. This is harmless and still a legal deck elsewhere. **The safest position for a new section is the very end of the file.**

**Saving.** `SaveDeck` (`deck_manager.cpp:524-555`) writes `#created by …`, `#main`, the main cards, `#extra`, the extra cards, `!side`, the side cards. Each card goes through `MakeYdkEntryString` (`:556-560`), which can prepend a `# name` comment line.

**Deck hashing.** There is none. I grepped for it; "hash" only appears on LFLists (`deck_manager.cpp:169`, `game.cpp:2481`).

**Sharing codes.**
- `ExportDeckYdke` (`:561-571`) produces `ydke://<b64 main>!<b64 extra>!<b64 side>!`, each part being raw little-endian `uint32` codes.
- `ImportDeckYdke` (`:625-640`) stops scanning after 3 `!` delimiters (`for(...; delim < 3 && buffer[i]; ...)`). A fourth segment such as `…!<b64 master>!` is therefore silently ignored by older clients. Import calls `LoadDeck(deck, main, side, &extra)`, so the extra segment is taken verbatim.
- `ImportDeckBase64Omega` (`:666-684`) is the Omega format: gzip, a `mainc`/`sidec` byte each, at most 75+15 cards.
- `ExportDeckCardNames` (`:572-617`) exports plain text.

## 2. Deck editor UI

**Geometry** (virtual 1024×640, scaled with `Resize`):

| Area | Header bar | Pane |
|---|---|---|
| Main | `310,137,797,157` (`drawing.cpp:1281`) | `310,160,797,436` (`:1315`) |
| Extra | `310,440,797,460` | `310,463,797,533` (`:1350`) |
| Side | — | `310,560,797,630` (`:1383`) |
| Search results | — | `x 805-995` (`:1421`) |

- `wDeckEdit` (top-left control box) is `Scale(309,8,605,130)` (`game.cpp:551`).
- The Genesys checkbox sits inside it at `Scale(225,7,295,28)` (`game.cpp:557-558`).
- Card info `wInfos` is `Scale(1,275,301,639)` (`game.cpp:1455`).
- Main Deck rows: 10 per row while the deck has 40 cards or fewer, otherwise `(n-41)/4+11` per row (`drawing.cpp:1317`).

**Hit testing.** `DeckBuilder::GetHoveredCard` (`deck_con.cpp:927-1036`) hard-codes these bands:
- `hovered_pos = 1` (main): `y 164-435`
- `hovered_pos = 2` (extra): `y 466-530`
- `hovered_pos = 3` (side): `y 564-628`
- `hovered_pos = 4` (search): rect `{810,165,995,626}`
- Only `x 314..794` counts for the deck panes.

**Drag and drop** (`deck_con.cpp:644-699`).
- Mouse down pops the card from its pile (`pop_main/extra/side`).
- Mouse up calls `push_*` for the hovered pile. If that push is rejected, the card goes back to its source pile (`:689-697`).
- Right-click and middle-click have their own placement order: search → extra, else main, else side (`:786-787`); side → extra, else main (`:719`).

**Where a card is allowed to go:**
- `push_main` (`:1589-1621`) rejects Fusion, Synchro, Xyz and Link monsters, and caps the pile at **60** (`if(container.size() >= 60) return false;`, `:1612`).
- `push_extra` (`:1622-1648`) only accepts F/S/X/Link (and Rush Ritual), capped at **15** (`:1638`).
- `push_side` caps at 15 (`:1651`).
- `check_limit` (`:1683-1709`) counts copies by `limitcode = alias ? alias : code` across all three piles. Its default limit is 3, or 0 on a whitelist list.

**Genesys pattern to copy** (all verified):
- Checkbox: `chkGenesys` (`game.cpp:557`), config option `OPTION(bool, genesysPoints)` (`game_config.inl:74`), handler `CHECKBOX_GENESYS_POINTS` (`deck_con.cpp:610-623`), which switches to a Genesys list automatically.
- Badge: in `DrawThumb`, drawn at `genesysloc` (`drawing.cpp:1212,1222-1225`) by `DrawGenesysBadge` (`:1187`); texture from `ImageManager::CreateGenesysBadge` (`image_manager.cpp:84,290-292`).
- Header total: `IsGenesysActive()` and `epro::format(L"{} {}/{}", label,total,cap)` (`drawing.cpp:1291-1298`).
- Filter: enum value `LIMITATION_FILTER_GENESYS_POINTS` (`deck_con.h:41`), entry added to `cbLimit` (`game.cpp:3497-3499`), check in `CheckCardProperties` (`deck_con.cpp:1333-1335`).
- Strings: sysstrings 7100-7104 with hard-coded fallbacks.

**[infer] Where a DM slot could go.**
- (a) Replace the Side row (y 537-630) with a one-card "Deck Master" pane while Domain is active. The Domain rules digest doesn't mention a Side Deck.
- (b) Or put a single thumbnail at the right end of the main header or in `wDeckEdit`.

Either way needs a new `hovered_pos` value (for example 5), a new `push_master`/`pop_master` pair, a new `DeckType::MASTER` (`deck_con.h:79-83`), and an update to `RefreshLimitationStatus` (`deck_con.cpp:1468-1486`).

## 3. Validation

**`CheckDeckContent`** (`deck_manager.cpp:259-316`) runs in this order:
1. `forbiddentypes` across all piles (`:261`).
2. Legend and Skill counts.
3. `CheckCards` on main, then extra, then side, sharing one `ccount` map.
4. The Genesys block.

**Copy counting** in `CheckCards` (`:196-258`):
```cpp
uint32_t code = cit->alias ? cit->alias : cit->code;   // 247
ccount[code]++; if (dc > 3) return CARDCOUNT;          // 248-251
auto it = curlist->GetLimitationIterator(cit); ... LFLIST  // 252-255
```
- Copies are counted by alias, so "always treated as" cards that carry an `alias` (an Umi alias, for example) share one count.
- Whether Umi-alias cards actually have `datas.alias` set is a data question I did not check in the cdb.
- `GetLimitationIterator` (`deck_manager.h:28-35`) falls back to the alias only when not on a whitelist, or when the card is an alternate artwork (`IsInArtworkOffsetRange`: |code−alias| < 10, `data_manager.h:79-90`).
- The hard-coded `dc > 3` means singleton (1 copy) is not expressible today. The only way would be an LFList with every code limited to 1 **[infer]**.

**`CheckDeckSize`** (`:325-347`) compares the `DeckSizes{main,extra,side}{min,max}` struct (`network.h:24-29`, `uint16` each) using inclusive range `operator==` (`netserver.cpp:18-26`). Main excludes Skills. The host defaults are 40/60, 0/15, 0/15 (`duelclient.cpp:249-256`). "Main exactly 60, Extra up to 15" is therefore expressible as `main{60,60}`, `extra{0,15}`.

**DeckError codes** (`network.h:108-137`): NONE … TOOMANYSKILLS = 0xD. 0xE and 0xF are reserved by Multirole. `GENESYSPOINTS = 0x10`. The struct carries `count{current,minimum,maximum}` and `code`. The client renders it in `duelclient.cpp:~500-552`, with the Genesys case at `:543-547`.

**Call sites.** The local host runs these in `GenericDuel::PlayerReady` (`generic_duel.cpp:373-381`): size first, then content unless `no_check_deck_content`. The deck editor does no blocking validation; only the push caps apply.

## 4. Card data available to the client

**`CardDataC`** (`data_manager.h:62-104`) has `code, alias, setcodes_p, type, level, attribute, race (uint64), attack, defense, lscale, rscale, link_marker, ot, category, std::vector<uint16_t> setcodes`.
- `setcodes` is filled from the 64-bit `datas.setcode`, up to 4 codes of 16 bits each (`data_manager.cpp:127-136`).
- **[infer]** The base archetype would be `setcode & 0x0fff`, the usual EDOPro sub-archetype convention.
- The editor's archetype search uses an exact `std::find` (`deck_con.cpp:1352-1356`), so it does no base matching.

**`CardString`** (`data_manager.h:105-111`) has `name, text, uppercase_*, desc[16]`. Accessors are `GetName` and `GetText`.

**Strings.** `LoadStrings` (`data_manager.cpp:229-265`) parses `!system`, `!victory`, `!counter` and `!setname <hex> <name>` into `_setnameStrings`. They are read through `GetSetName(code)` (`data_manager.h:174`) and reverse-looked-up with `GetSetCode(names)` (`data_manager.cpp:401-420`). Sources are `./config/strings.conf` and `./expansions/strings.conf` (`data_handler.cpp:130-131`), plus each repo's `strings.conf` (`game.cpp:2694`).

**Scripts on disk.** The client has them. `script_dirs` holds `./expansions/script/` and subfolders, `archives`, `./script/` and subfolders (`game.cpp:4045-4051`), and repo `script_path`s are prepended (`game.cpp:2778-2783`). `Game::FindScript` (`game.cpp:3926-3945`) resolves a file.

The client has no Lua API of its own: it links `lua` only for a static core (`premake5.lua:254-256`), and nothing in gframe uses `lua_State`. Reading `s.listed_names` (3198 official scripts declare it) would therefore mean text-parsing Lua, including constant names such as `CARD_DARK_FUSION` (`official/c58332301.lua:40`), or precomputed data. `s.listed_series` appears 5603 times. There is no `listed_attributes` or `listed_races`, so attribute and race mentions are not available as script metadata **[infer from grep]**.

## 5. Network submission, hand test, replays

**`CTOS_UPDATE_DECK` (0x2)** (`network.h:277`) is built in `menu_handler.cpp:34-53` and, for siding, `deck_con.cpp:359-385`:
```
u32 mainc = main.size()+extra.size(); u32 sidec = side.size();
u32 codes[main..., extra..., side...]    // pcard->code (dummy cards send 0)
```
There is no section boundary between main and extra. The receiver re-sorts by type: `GenericDuel::UpdateDeck` calls `LoadDeckFromBuffer` → `LoadDeck(..., nullptr extralist)` (`generic_duel.cpp:406-424`, `deck_manager.cpp:348-358`).

Consequences:
- A DM appended to the buffer would land in main or extra by its type.
- A new pile needs a format change: a third count, or a sentinel or marker code.
- Siding uses `LoadSide` (`deck_manager.cpp:474-522`), which requires identical multisets and identical main and extra sizes.

**Local duel build** (`generic_duel.cpp:597-688`).
- Rule cards from `extra_rules` are added with `OCG_DuelNewCard` at location 0.
- Note that `DECK_MASTER = 0x800` (`network.h:352`) is already taken: it adds card 153999999, the anime "Virtual World" Deck Master rule (`cardscripts/unofficial/c153999999.lua`, which uses `DeckMaster` from `c153000000.lua`). **This is a name collision risk.**
- Each player's deck goes in as `LOCATION_DECK` and their Extra as `LOCATION_EXTRA`.
- `MSG_START` is 18 bytes carrying only deck and extra counts (`:700-708`).

**Test hand** (`single_mode.cpp:89-155`).
- The script name `"hand-test-mode"` sets `DUEL_ATTACK_FIRST_TURN`.
- The deck builder's current deck is shuffled and loaded for player 0, and for player 1 too unless `handTestNoOpponent`, via `OCG_DuelNewCard` (DECK, EXTRA).
- It then runs `Debug.ReloadFieldEnd()`. The duel rule comes from `cbHandTestDuelRule` (`deck_con.cpp:184-206`; index 8 = `DUEL_MODE_GENESYS`).
- No deck validation runs here.

**Replays.**
- `ReplayHeader` and `ExtendedReplayHeader` are in `replay.h:28-60`; the flags are at `:14-23`.
- Old-format (YRP1) deck block per player is `u32 n, n×u32 main, u32 m, m×u32 extra`, followed by `u32 r, r×u32 rule cards` (writers at `generic_duel.cpp:652-692`; reader `Replay::ParseDecks` at `replay.cpp:237-255`). `ReplayDeck` only has `main_deck` and `extra_deck` (`replay.h:64-66`).
- The new-format replay (YRPX) embeds the YRP1 buffer as an `OLD_REPLAY_MODE` packet (`generic_duel.cpp:1437-1446`, `replay.cpp:285-291`).
- Old-mode playback rebuilds the duel with `DuelNewCard` DECK and EXTRA only (`old_replay_mode.cpp:131-173`).
- "Save decks from replay" writes main and extra (`menu_handler.cpp:468-473`).

## Implications for Domain

**Hook points:**
1. **`Deck`** (`deck.h`): add `Vector master` (or a single pointer), and update `clear()`, `RefreshDeck` (`deck_manager.cpp:156`), `LoadDeck`, `SaveDeck` (both overloads), `ExportDeckYdke`/`ImportDeckYdke` (4th segment), and `ExportDeckCardNames`.
2. **.ydk**: write a `#master` section after `!side`. Older parsers then treat the DM as a side card, which is harmless. Recognise `#master` in `LoadCardList` even when `separated=false`, otherwise the DM merges into main/extra on the READY path.
3. **Validation**: add a Domain branch in `CheckDeckContent` (after `:291`, like Genesys at `:293-315`):
   - exactly one monster DM;
   - main exactly 60, extra at most 15, excluding the DM;
   - singleton by `alias?alias:code` across DM + Main + Extra;
   - domain membership: Spell/Trap, DIVINE and Divine-Beast always allowed; otherwise match attribute, race, base setcode or the mention data.
   - Add new `DeckError` codes ≥ 0x11 (for example DM missing/invalid, out-of-domain with `code`), with text in `duelclient.cpp` (~`:543`) and sysstrings beside 7100-7104. Multirole must mirror these in its checker.
4. **Domain data**: the cdb gives attribute, race and setcodes. Mentioned names, archetypes, attributes and races are not reliably derivable at runtime: `listed_names` is Lua with constants, and there is no attribute or race metadata. Generate a data file (for example `domain.conf`, keyed by DM code) offline, loaded by both client and Multirole, possibly hashed into the list like the Genesys salt (`deck_manager.cpp:37-42`).
5. **Editor**:
   - new `hovered_pos` and pane (Side row reuse or a dedicated slot) in `GetHoveredCard`, `DrawDeckBd`, the drag handlers and `DeckType`;
   - a Domain checkbox, mirroring `chkGenesys`;
   - in-domain filtering through a new `LIMITATION_FILTER_*` plus a check in `CheckCardProperties`;
   - `check_limit` capped at 1;
   - the `push_main` 60 cap is already fine.
6. **Transport**: `CTOS_UPDATE_DECK` cannot express the DM. Options:
   - (a) send `mainc` = main+extra+DM and append the DM last, with a Domain-specific "last code is DM" convention (the server must know the room is Domain);
   - (b) a negative-free sentinel such as a third `u32` count after `sidec`. Old servers would read it as card data, so the format must be gated by room mode.
   - Both `menu_handler.cpp:34` and `deck_con.cpp:372` (siding) must change, as must `GenericDuel::UpdateDeck`/`LoadSide` and Multirole.
7. **Duel setup**: add the DM with a new location (an engine `LOCATION_DMZ`, or a flagged card) in `generic_duel.cpp` (~`:652-688`), `single_mode.cpp:128-151`, `old_replay_mode.cpp:138-166` and Multirole. `MSG_START` and `dField.Initial` currently carry only deck and extra counts.
8. **Replay**: YRP1 has no DM slot. Either append a per-player DM block guarded by a new `REPLAY_*` flag (an old reader would misparse it without the flag check), or add the DM as a rule-card-like entry. The rule-card list is global, not per-player, so it would need an encoding.

**Risks:**
- The anime `DECK_MASTER` extra-rule name and card 153999999 collide conceptually; pick distinct identifiers (for example `DUEL_MODE_DOMAIN`).
- The re-sort-by-type in `LoadDeck` silently moves a misplaced DM.
- The `dc > 3` hard cap and `GetLimitationIterator` alias rules differ: alias-based singleton counting is right for Umi-type cards, but the LFList lookup ignores non-artwork aliases.
- Siding (`LoadSide`) compares multisets and main/extra sizes, so a DM pile must be included or excluded consistently.
- Older clients joining a Domain room would send decks without a DM; the server must reject them clearly.
- Duel-rule index 8 is Genesys and 9 is Custom (`game.cpp:3168-3182`, `deck_con.cpp:184-206`), so adding Domain shifts Custom again, in many places.