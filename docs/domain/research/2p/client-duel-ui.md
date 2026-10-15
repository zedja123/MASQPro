# Domain format: MASQPro client duel UI and core message handling (gframe/)

All paths are under `/home/user/MASQPro/gframe/`. Lines marked **[V]** were checked in the code. Lines marked **[I]** are my inferences.

## 1. ClientField containers, GetCard, MSG_MOVE with location 0, skill cards

**Containers [V]** (`client_field.h:31-48`):
- `deck/hand/mzone/szone/grave/remove/extra[2]` are vectors. `mzone` is resized to 7 and `szone` to 8 (`client_field.cpp:47-48`).
- `limbo_temp` is a vector. `ClientCard* skills[2]` holds the skill cards.
- `LOCATION_SKILL 0x400` exists only on the client (`client_field.h:193`).

**The wire format allows only 8 bits for a location [V].**
- `ReadLocInfo` reads `info.location = BufferIO::Read<uint8_t>(p)` (`core_utils.cpp:284`).
- The core also stores `uint8_t location` (`ocgcore/card.h:28,51`).
- All 8 bits 0x01-0x80 are already used (`ocgapi_constants.h:12-19`).
- So the core can never send 0x400. A DMZ marker has to be location 0 plus some way to tell it apart, or an otherwise impossible 8-bit combination.

**GetList / GetCard [V]** (`client_field.cpp:136-180`):
- `GetList` switches only over DECK/HAND/MZONE/SZONE/GRAVE/REMOVED/EXTRA and returns `nullptr` for anything else, including 0 and LOCATION_SKILL.
- `GetCard` returns 0 when the list is null: `auto lst = GetList(location & (~LOCATION_OVERLAY), controler); if(!lst) return 0;`.

**MSG_MOVE** (`duelclient.cpp:3051-3110`) [V]:
- If `previous.location == 0`, it builds a new card (`ClientCard* pcard = new ClientCard{}; ... AddCard(pcard, current.controler, current.location, current.sequence)`) and fades it in (3065-3079).
- If `current.location == 0`, it looks the card up with `GetCard(previous...)`, fades it out, calls `RemoveCard` and then `delete pcard;` (3080-3104).
- [I] If the DMZ is reported as location 0, a DM leaving the DMZ shows up as a fresh card fading in, and a DM returning to the DMZ is deleted. This is visually acceptable, but the DMZ card is never shown unless MSG_MOVE is intercepted.

**Skill cards [V]** (`duelclient.cpp:1530-1606`):

| Hint | What it does |
|---|---|
| `HINT_SKILL` (200) | Creates `skills[player]` with `location = LOCATION_SKILL`, `position = POS_FACEUP`, `SetCode(data & 0xffffffff)`, then `MoveCard(pcard,10)` |
| `HINT_SKILL_COVER` (201) | `cover = data & 0xffffffff`, code = `data >> 32`, face-down |
| `HINT_SKILL_FLIP` (202) | Bit `0x100000000` turns it face-up, bit `0x200000000` turns it face-down |
| `HINT_SKILL_REMOVE` (203) | Fades the card out and deletes it |

- The constants are in `core_utils.h:113-116`.
- These hints are still processed while catching up (reconnecting): `if(mainGame->dInfo.isCatchingUp && type < HINT_SKILL) return true;` (1402).
- **Position:** `GetCardDrawCoordinates` maps `case LOCATION_SKILL: return matManager.getSkill()[controler];` (`client_field.cpp:813`).
- **Drawing:** `drawing.cpp:347-348`. The cover texture comes from `GetTextureCard(pcard->cover, imgType::COVER)` (`drawing.cpp:381-385`).
- **Clicking:** a skill card can be hovered for card info (`event_handler.cpp:1550-1551`) but cannot be clicked for commands, because `clicked_card` is set only when `hovered_location & 0xe` (1141).
- Skills are actually used through the "conti" button. Their handler card is sent out of the duel with `SendtoDeck(c,tp,-2,REASON_RULE)` (`cardscripts/proc_skill.lua:164`). Its activatable entries then resolve to `limbo_temp` cards (`duelclient.cpp:1890-1896`) with `EFFECT_CLIENT_MODE_RESOLVE`, which places them in `conti_cards`, reached via `POSITION_HINT` (`event_handler.cpp:1331-1338`).
- **Other code that touches skills:** `Clear` (`client_field.cpp:71-78`), `ReplaySwap` (648, 657), `RefreshAllCards` (694).

## 2. Idle and battle command parsing and the command menu

**MSG_SELECT_IDLECMD** (`duelclient.cpp:1784-1931`) [V]:
- Each entry is read as `code(u32), con(u8), loc(u8), seq(u32)`. Then `pcard = GetCard(con, loc, seq); list.push_back(pcard); pcard->cmdFlag |= COMMAND_X`.
- This covers summonable (1800), spsummonable (1812), repos (1845), mset (1857) and sset (1869).
- **There is no null check in these loops**, so a summonable/spsummonable/mset entry with location 0 dereferences null and crashes.
- Only the activatable lists fall back to a `limbo_temp` card (`if(!pcard) { pcard = new ClientCard{}; ... limbo_temp.push_back(pcard); }` at 1890-1896, and the same in BATTLECMD at 1733-1739). Those cards get `COMMAND_ACTIVATE` but cannot be clicked anywhere.
- For spsummon, `switch(pcard->location)` sets `deck_act`, `grave_act` and similar flags (1813-1834). These drive the spinning "activate" marker in `DrawMisc` (`drawing.cpp:481-492`).
- `limbo_temp` is cleared in `SendResponse` (4424-4426).

**Responses depend only on the list index, not the location [V]:**
- Summon: `SetResponseI(i << 16)` (`event_handler.cpp:433-445`)
- Special Summon: `(i<<16)+1` (447-458)
- Activate during idle: `(index << 16) + 5` (373)
- Codes 2, 3 and 4 are repos, mset and sset.
- So a DMZ card works as long as its `ClientCard*` is in the right list.

**Click flow [V]:**
- `EMIE_LMOUSE_LEFT_UP` runs `GetHoverField(mousepos); if(hovered_location & 0xe) clicked_card = GetCard(...)` (`event_handler.cpp:1140-1143`).
- For `MSG_SELECT_IDLECMD/BATTLECMD/CHAIN`, `case LOCATION_HAND: case LOCATION_MZONE: case LOCATION_SZONE: { int command_flag = clicked_card->cmdFlag; ... list_command = 0; ShowMenu(command_flag, x, y);` (1286-1297).
- `ShowMenu` lays out the Activate, Summon, SPSummon, MSet, SSet, Repos and Attack buttons from the flag bits (2629-2680). The flags are defined in `game.h:824-835`.
- Field-card selection (MSG_SELECT_CARD) also requires `hovered_location & 0xe` (1409, 1449).

**What a DMZ card needs in order to get commands [I]:**
1. A client-only container (for example `std::vector<ClientCard*> dmz[2]` sized 1, or a pointer like `skills`) and a client-only location constant (for example `LOCATION_DMZ 0x800`).
2. A way to map the core's (con, loc, seq) to it.
   - Mapping plain `loc==0` in `GetList` would also capture skill-handler and other location-0 cards that currently fall back to `limbo_temp`.
   - So the core needs a distinguishable encoding, for example a reserved sequence value or a dedicated 8-bit value.
3. Change `if(hovered_location & 0xe)` at 1141 and 1534 to also accept `LOCATION_DMZ`.
4. Add `case LOCATION_DMZ:` next to HAND/MZONE/SZONE at 1286.
5. Add a `GetHoverField` branch (see §3).
6. Add the card to `DrawCards`, `Clear`, `ReplaySwap`, `RefreshAllCards` and `GetCardDrawCoordinates`.
7. Add a hover highlight vertex in `DrawBackGround` (`drawing.cpp:178-193`).

A cheaper option is to keep the DM as a `limbo_temp`-style card and only add it to the IDLECMD null fallbacks. But then it cannot be clicked, so a DMZ slot on screen is still needed.

## 3. Field geometry

Quads come from `SetS3DVertex(v, x1, y1, x2, y2, ...)` (`materials.cpp:20-25`). Player 0 is the side with high Y, at the bottom of the screen: the hand is at `Y=4.0` (`client_field.cpp:899-900`) and the deck at X 6.9-7.7, which is the player's right [V].

**Five-column field [V]:**

| Zone | Coordinates (X, Y) | Source |
|---|---|---|
| Main Monster Zones (MMZ) p0 | X `1.2+1.1i .. 2.3+1.1i`, Y 0.8-2.0 | 68-69 |
| Spell/Trap (S/T) p0 | Y 2.0-3.2 | 72-77 |
| **EMZ** seq 5 | X 2.3-3.4, Y -0.6..0.6 | 70 |
| **EMZ** seq 6 | X 4.5-5.6, Y -0.6..0.6 | 71 |
| Opponent mirror EMZ | `vFieldMzone[1][5]` 5.6..4.5, `[1][6]` 3.4..2.3 | 116-117 |
| Field zone p0, separate PZones | 0.2-1.0, 0.1-1.3 | 79 |
| L Scale (PZone) | 0.2-1.0, 1.4-2.6 | 85 |
| R Scale (PZone) | 6.9-7.7, 1.4-2.6 | 91 |
| Skill zone p0, separate PZones | X -0.8..0.0, Y 1.4-2.6 | 155 |
| Skill zone p1 | 7.9-8.7, -0.1..-1.3 | 157 |
| Conti button | -0.8..0.0, 0.1-1.3 | 144-147 |

- The arrays are indexed `[not_separate_pzones][three_columns][player]` and selected by `SetActiveVertices` (233-240).
- The field outline is a baked texture, `tField[three_columns][tfield]` (`drawing.cpp:91`). New slots must be drawn on top, for example with `DrawSelectionLine` or a quad texture.

**Free slots in the EMZ row [V]:**
- At Y -0.6..0.6, the column positions X 1.2-2.3 (column 0) and X 5.6-6.7 (column 4) are empty.
- `GetHoverField` already computes `sequence` for this row and only handles `sequence == 1` and `3` (`event_handler.cpp:2595-2616`). Sequences 0 and 4 leave `hovered_location = 0`.
- [I] Suggested placement: p0's DMZ at X 1.2-2.3 and p1's DMZ at X 6.7-5.6, both in the EMZ row. That puts each DMZ to the left of the EMZs from its owner's point of view, matches the rulebook's "left/right of EMZ", and keeps the field rotationally symmetric. The hover hook is just adding `sequence==0`/`4` cases there.
- [I] The official spot under the S/T row (Y > 3.2) collides with the hand at Y 4.0.
- Three-column and other layouts are not needed for Domain because it uses the Master Rule 5 field. In those layouts, `three_columns` disables sequences 0 and 4 (2585), so the skill-zone vertices would be the fallback.

**Card position [V]:**
- `ClientCard::UpdateDrawCoordinates` calls `dField.GetCardDrawCoordinates` (`client_card.cpp:9-11`).
- `GetCardDrawCoordinates` returns early with `if(!pcard->location) return;` (800). Its `GetPos()` switch (805-823) needs a `LOCATION_DMZ` case that returns the new quad. Rotation and the face-down flip follow (832-847).
- Chain marker positions come from `GetChainDrawCoordinates`, which defaults to (0,0,0) for unknown locations (701-750).

## 4. Duel rule combobox and host flow (the Genesys pattern)

**Rule list:**
- `ReloadCBDuelRule` adds indices 0-4 (MR1-5, strings 1260-1264), 5 Speed (1258), 6 Rush (1259), 7 Goat (1248) and 8 Genesys (`HasSysString(7103) ? ... : L"Genesys"`) (`game.cpp:3553-3565`).
- Custom (1630) is appended at index 9 by `UpdateDuelParam` (3174-3178).
- Index 9 is hard-coded in `removeItem(9)` (3132, 3140, 3148, 3159, 3171; `menu_handler.cpp:1027`) and `setSelected(9)` (`game.cpp:3178`).

**Flags:**
- `DUEL_MODE_GENESYS` is only a combination of existing flags (`ocgapi_constants.h:444-445`).
- The highest flag in use is `DUEL_NORMAL_SUMMON_FACEUP_DEF 0x1000000000` (433).
- **`UpdateDuelParam` rebuilds `duel_param` only from the 32 `chkCustomRules`** (`game.h:226`; mapping at `game.cpp:3107-3120`, where `i>21 → 0x100ULL << (i-3)`, so i=31 maps to bit 36).
- [I] A new `DUEL_DOMAIN` bit (for example 0x2000000000) will be silently dropped when the host tab switches back, unless:
  - `chkCustomRules` grows to 33 entries, with system string 1631+32 = 1663 (this also touches the `menu_handler.cpp:944-958/1029-1043` loops and `duelclient.cpp:765-781`), or
  - `UpdateDuelParam` OR-preserves the bit, or
  - Domain is detected through a `case DUEL_MODE_DOMAIN:` before `default` (3168-3176).

**COMBOBOX_DUEL_RULE** (`menu_handler.cpp:996-1051`):
- Case 8 sets `duel_param = DUEL_MODE_GENESYS`, `setDeckSizes(ocg_deck_sizes)`, `forbiddentypes`, `ebStartHand "5"` and `goto remove`.
- It then syncs the checkboxes and calls `LockGenesysZones(... getSelected() == 8)`.
- The same index switch appears in the host-tab handler (917-943) and in hand test (`deck_con.cpp:185-206`, `case 8: options.duelFlags = DUEL_MODE_GENESYS;`).
- For Domain, deck sizes would be a new `DeckSizes{{60,60},{0,15},{...}}` [I].

**Other host pieces:**
- `ApplyGenesysHostRules` (`game.cpp:3190-3205`) forces index 8 when a Genesys list is chosen. It is called from BUTTON_CREATE_HOST/HOST2 and COMBOBOX_HOST_LFLIST (`menu_handler.cpp:224, 238, 1054`).
- Bot filter: `BotRuleFilter(){ return sel == 8 ? 5 : sel + 1; }` (`game.cpp:3206-3209`). `WindBotPanel::Refresh` keeps bots whose `masterRules` contains the filter value (`windbot_panel.cpp:32`).
  - [I] Domain should return a value that no bot lists, since bots have no Deck Master.
- `ReloadElementsStrings` keeps the selection with `if (prev >= 7) UpdateDuelParam()` (`game.cpp:3657-3662`).
- **LAN host (netserver.cpp):** at 376-381, a Genesys list strips `DUEL_PZONE|DUEL_SEPARATE_PZONE|DUEL_EMZONE` from `duel_flag_low` and ORs in the forbidden types. Bits above 31 arrive in `pkt.info.duel_flag_high` (`network.h:51,57`), which the client sets at `duelclient.cpp:236-237`.
- `generic_duel.cpp:598` combines the low and high words into the core options.
- Deck check: `CheckDeckSize` and `CheckDeckContent(..., lflist, ..., forbiddentypes, rituals_in_extra)` (`generic_duel.cpp:373-380`).
- **Room info display:** `GetMasterRule` has no Genesys case, so Genesys falls into the `rule >= 6` branch and is listed as custom rules plus "Custom" (`duelclient.cpp:754-782`). A Domain label would go there.
- **Risk [V]:** `MSG_RELOAD_FIELD` reads only `uint32_t opts` (`duelclient.cpp:4299-4300`), so a high-bit Domain flag is lost on reconnect. `HasFieldFlag` checks still work because the EMZ and PZone flags are in the low word.

## 5. Yes/No prompts and hint strings

**MSG_SELECT_YESNO** (`duelclient.cpp:1962-1970`) [V]:
- It shows `stQMessage->setText(gDataManager->GetDesc(desc, compat).data())` and pops up `wQuery`. No card is involved.
- `BUTTON_YES` → `SetResponseI(1)` (`event_handler.cpp:215-221`); `BUTTON_NO` → `SetResponseI(0)` (253-259).

**MSG_SELECT_EFFECTYN** (1933-1960) [V]:
- It does `GetCard(info...)` and then `pcard->code` with **no null check**. Using it for a location-0 card would crash, so YESNO is the safe choice.

**GetDesc** (`data_manager.cpp:379-400`) [V]:
- In non-compat mode, `code = strCode >> 20`, `stringid = strCode & 0xfffff`.
- `code == 0` → `GetSysString(stringid)`.
- Otherwise it uses the card's str1-16. A missing entry returns `unknown_string`.
- `GetSysString` falls back to `unknown_string` when missing (`data_manager.h:162-163, 214-219`).

**Prompt text options [I]:**
- The core can send `desc = <sysstring id>` for "Return your Deck Master to the Deck Master Zone?".
- No `strings.conf` exists in the repo or in the BabelCDB checkout. It is loaded from `data_path/strings.conf` (`game.cpp:2694`), so the string has to be shipped.
- The Genesys strings 7101-7103 use a `HasSysString(...) ? ... : L"fallback"` pattern. That fallback is not available inside `MSG_SELECT_YESNO`, so a guard for the Domain id would have to be added there.
- `MSG_HINT HINT_MESSAGE/HINT_EVENT/HINT_SELECTMSG` also resolve through `GetDesc` (1407-1420).

## Implications for Domain

**Hook points:**

- **Client DMZ container and location:** add `dmz[2]` and `LOCATION_DMZ` (for example 0x800), modelled on `skills[2]` and `LOCATION_SKILL` (`client_field.h:47, 193`). Wire it into:
  - `Clear`, `ReplaySwap`, `RefreshAllCards`
  - `GetCardDrawCoordinates` `GetPos` (`client_field.cpp:805-823`)
  - `DrawCards` (`drawing.cpp:327`), the hover vertex (`drawing.cpp:178-193`) and an outline slot in `DrawBackGround`
- **Creating the DM at duel start:** either a new client hint (for example `HINT_DMZ 204`) handled like `HINT_SKILL` (`duelclient.cpp:1530`), which is already processed while catching up, or a dedicated encoding in MSG_MOVE.
- **MSG_MOVE (`duelclient.cpp:3065-3104`):** when `previous` is the DMZ, take the card from `dmz[con]` instead of `new`. When `current` is the DMZ, move it into `dmz[con]` instead of `delete`.
- **IDLECMD and BATTLECMD (`duelclient.cpp:1708-1931`):** make `GetCard` resolve the DMZ encoding. Add null guards on summon, spsummon and mset (1799-1857), and set a `dmz_act` flag for the activate marker.
- **Click and hover:** change `hovered_location & 0xe` at `event_handler.cpp:1141/1534`, add `case LOCATION_DMZ` at 1286, and add EMZ-row `sequence==0` (p0) and `sequence==4` (p1) cases at 2595-2616. Command responses need no change because they are index based.
- **Rule UI:**
  - Add a Domain item, either at index 9 (moving Custom to 10 and updating every `removeItem(9)`/`setSelected(9)`/`== 8`) or with Custom left last.
  - Add matching cases in `menu_handler.cpp:917-943, 996-1051`, `deck_con.cpp:185`, `UpdateDuelParam` and `BotRuleFilter`.
  - Add a new `DUEL_DOMAIN` flag with a constant in `ocgapi_constants.h` that is kept in sync with the core and multirole.
- **Prompt:** `MSG_SELECT_YESNO` with a new system string id, shipped in `strings.conf`, ideally with a `HasSysString` fallback.

**Risks:**

- The core location is `uint8_t`: 0x400-style values are impossible and every bit is taken. If DMZ is location 0 without a discriminator, it clashes with skill-handler and `limbo_temp` cards.
- Null dereferences on location-0 cards in summon, spsummon, mset, EFFECTYN (1951), CHAINING (3508) and FLIPSUMMONING (3476) are crash paths if the core ever reports a DMZ card in those messages.
- `UpdateDuelParam` drops non-checkbox flag bits, and `MSG_RELOAD_FIELD` truncates options to 32 bits, so the choice of flag bit matters.
- Reconnect and spectators: `MSG_RELOAD_FIELD` serializes only the MZONE/SZONE/... piles (4300-4345), so DMZ state must be re-sent, for example by replaying the hint.
- WindBot has no Domain support, so bots should be filtered out.
- Topdown view and the 3-column layout need fallback DMZ vertices.