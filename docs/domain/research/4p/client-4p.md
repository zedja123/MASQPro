# MASQPro client (gframe/): what it would take to support more than two duelists

## Summary
- The client is built around exactly two sides: "self" (index 0) and "opponent" (index 1). Field containers, vertex tables, hit-testing, the LP and name HUD, field-zone selection bitmasks, replays and the spectator swap all use `[2]` arrays or `1 - x`.
- **Tag duels are not a multi-field layout.** They are still two sides, with a list of names per side and a "current duelist" index that rotates on `MSG_TAG_SWAP`.
- **Some parts already generalise.** Card rendering and hand hit-boxes both work from each card's world transform (`mTransform`), so rotated or scaled extra boards cost little. The lobby already has 6 duelist slots.

## 1. ClientField containers and player-perspective mapping

### Verified
- **Containers.** All field piles are `[2]` arrays (`client_field.h:30-36`):
  ```
  std::vector<ClientCard*> deck[2]; hand[2]; mzone[2]; szone[2]; grave[2]; remove[2]; extra[2];
  ```
  The same holds for `skills[2]` (`:47`), `extra_p_count[2]` (`:51`), `player_desc_hints[2]` (`:78`), `grave_act[2]`/`remove_act[2]`/`deck_act[2]`/`extra_act[2]`/`pzone_act[2]` (`:79-83`).
- **Duel state.** `DuelInfo` (`game.h:66-114`) holds `int current_player[2]; int lp[2]; std::wstring strLP[2]; uint16_t time_left[2];`. It keeps `bool isFirst; bool isTeam1;` and two name lists `selfnames`/`opponames`.
- **Perspective conversion.** It is one function (`game.cpp:3101-3103`):
  ```
  uint8_t Game::LocalPlayer(uint8_t player) { return dInfo.isFirst ? player : 1 - player; }
  ```
  - Call-site counts: 92 in `duelclient.cpp`, 4 in `event_handler.cpp`, 2 in `single_mode.cpp`, 2 in `client_card.cpp`.
  - Messages map the core's controller to the local view. Examples: `con = mainGame->LocalPlayer(BufferIO::Read<uint8_t>(pbuf))` at `duelclient.cpp:1721`, and `info.controler = mainGame->LocalPlayer(info.controler)` at `:1937`.
- **How `isFirst` is set:**
  - Lobby: `isFirst = (player_type < team1) || (player_type >= 7)` (`duelclient.cpp:906, 935`).
  - Duel start: `isFirst = (playertype & 0xf) ? false : true` (`:1659`).
  - Spectators: forced to `isFirst = true` (`:1003`).
- **Replay/spectator swap.** `ClientField::ReplaySwap()` (`client_field.cpp:628-670`):
  - It swaps every `[0]`/`[1]` pile, `lp`, `strLP`, `current_player` and `player_desc_hints`.
  - It sets `pcard->controler = 1 - pcard->controler` and flips `isFirst`/`isTeam1`.
  - It rotates the disabled-zone bitmask: `disabled_field = (disabled_field >> 16) | (disabled_field << 16)`.
- **Hardcoded loops.** `p < 2` / `i < 2` loops appear at `client_field.cpp:45, 58, 649, 686` and `drawing.cpp:330, 481, 624`. About 37 literal `controler == 0/1` or `player == 0/1` tests are spread across `duelclient`, `client_field`, `drawing`, `event_handler` and `client_card`.
- **Zone selection is a 32-bit, two-player wire format.**
  - In `MSG_SELECT_PLACE` (`duelclient.cpp:2234-2245`): `uint32_t flag = ...; if(selecting_player == 1) flag = flag << 16 | flag >> 16;`.
  - Masks used: player 0 = `0x7f` (monster zones) / `0x1f00` (S/T zones) / `0xc000` (Pendulum Zones); player 1 = the same values shifted by 16.
  - The same layout is used in `drawing.cpp:95-115` (`filter = 0x10000`, `0x1000000`) and in `event_handler.cpp:1363-1395`, which builds `respbuf[p] = LocalPlayer(0|1)`.

### Inference
Every "is this card mine?" decision reduces to `controler == 0`, so an N-seat client needs a single "view index" abstraction (0 = self, others = relative seats) in place of `LocalPlayer`'s binary flip.

## 2. Rendering

### Verified
- **Board coordinates.** The board is a single plane: `SetS3DVertex(vField, -1.0f, -4.0f, 9.0f, 4.0f, ...)` (`materials.cpp:37`).
  - Self occupies y > 0. Monster zones: `vFieldMzone[0][i], 1.2f + i*1.1f, 0.8f, ..., 2.0f` (`:78`).
  - The opponent is the mirrored y < 0 half: `vFieldMzone[1][i], 6.7f - i*1.1f, -0.8f, ...` (`:153`).
  - The Extra Monster Zones sit at the centre line: `[0][5]`/`[0][6]` at y -0.6..0.6 (`:79-80`).
- **Vertex tables are typed for two players:**
  - `vFieldMzone[2][7]`, `vFieldContiAct[2][4]`, `vFieldSpell1/2[2]` (`materials.h:29-36`).
  - The private tables are `std::array<…,2>` indexed by [pzone mode][3-column mode][player] (`materials.h:53-64`).
  - `SetActiveVertices(three_columns, not_separate_pzones)` selects among them (`materials.cpp:233-240`).
- **Camera.**
  - Built once: `camera = smgr->addCameraSceneNode(0)`, `camera->setTarget({FIELD_X,0,0})` (`game.cpp:1966-1986`).
  - Constants: `FIELD_X=4.2, FIELD_Y=8.0, FIELD_Z=7.8`, an asymmetric frustum `CAMERA_LEFT=-0.90, CAMERA_RIGHT=0.45` (the left of the screen is reserved for the card-info panel), and `CAMERA_BOTTOM/TOP=±0.42` (`game.h:839-847`).
  - The top-down view only changes position and up-vector (`game.cpp:1949-1959`).
- **Card placement.** `ClientField::GetCardDrawCoordinates` (`client_field.cpp:786-950`):
  - Takes the zone quad centre from `matManager`.
  - Uses fixed rotations: `selfATK{0,0,0}`, `oppoATK{0,0,PI}`, `oppoDEF{0,0,HALF_PI}` (`:788-794`).
  - Overlay offsets are mirrored by `controler == 0` (`:859-862`).
  - Hand X/Y is hardcoded per side: `t->X = 1.55f + xoff1` vs `6.25f - xoff1`, `t->Y = 4.0f` vs `-3.4f` (`:891-919`).
  - It then sets `pcard->mTransform` (`:939-943`), and `DrawCard` uses `driver->setTransform(ETS_WORLD, pcard->mTransform)` (`drawing.cpp:373`).
- **Hand hit-boxes** are screen projections of each card's transform: `getCardScreenCoordinates` uses the projection, view and `mTransform` matrices (`client_field.cpp:753-771`), called from `RefreshHandHitboxes` (`:781-785`).
- **Board hit-testing** is a hand-written cascade of about 175 lines (`ClientField::GetHoverField`, `event_handler.cpp:2452-~2628`):
  - It projects the mouse onto the plane of `getExtra()[0]` (`MouseToField`, `:2439-2442`).
  - It then compares x/y against specific quads, e.g. `boardy >= matManager.getGrave()[1][2].Pos.Y` → `hovered_controler = 1`.
- **Background.**
  - The field texture is one quad for both halves: `DrawTextureRect(matManager.vField, … tField[three_columns][tfield])` (`drawing.cpp:83`).
  - Field Spells split the board with UV half-quads `vFieldSpell1/2` (`drawing.cpp:61-81`, `materials.cpp:38-41`).
- **Link-arrow highlighting** assumes the other side is `1 - hovered_controler`, e.g. `pcard2 = dField.mzone[1 - dField.hovered_controler][6]` (`drawing.cpp:274-323`).
- **LP, name and time HUD** (`drawing.cpp:529-617`):
  - Two fixed LP bars at `Resize(330,10,629,30)` and `Resize(691,10,990,30)`; two time bars (`:574-583`).
  - The turn-player frame is derived from **turn parity**: `((dInfo.turn % 2 && dInfo.isFirst) || …)` (`:531`). `MSG_NEW_TURN` discards the turn player: `/*const auto player = */mainGame->LocalPlayer(...)` (`duelclient.cpp:2937`).
  - LP-change text is placed by `lpplayer == 0` (`:566-570`).
  - There is no avatar system: the only "avatar" is Discord RPC (`discord_rpc.h:48`).

### How tag duels are shown (verified)
- Names stack under each LP bar, and the active duelist is drawn white versus grey: `if (i++ == dInfo.current_player[0]) … 0xffffffff else 0xff808080` (`drawing.cpp:594-615`).
- `MSG_TAG_SWAP` (`duelclient.cpp:4201-4283`) replaces one side's deck, hand and extra piles in place, then advances `current_player[player] %= team1|team2` (`:4276-4281`).
- Initial indices are set in `MSG_START` (`:1661-1674`).
- **Conclusion: there is no existing multi-field layout to build on.** Tag is "2 sides × N names".

### 4-field layout (inference)
Because the Domain rules make only the player in front share Extra Monster Zones, Link Arrows and columns, the current two-field board is exactly "self + front". Left and right opponents are independent boards. The options:

- **(a) Full table.**
  - Keep the existing y-mirrored pair, and add two side boards built by applying a world matrix (rotate ±90° about Z, scale about 0.5–0.6, translate to x < −1 and x > 9) to the "opponent" vertex tables.
  - Needs a wider frustum (`CAMERA_LEFT/RIGHT`), or the two side boards shown as compact strips. Cards become small at 720p.
  - Card rotations become `seatRot + ATK/DEF`.
- **(b) Focus view.** Render self + one selected opponent with the existing geometry, plus three small 2D summary panels (LP, hand/deck/GY counts) with a button to switch which opponent is in front. Spectators would get a seat switcher.
  - Least geometry work. However, attack arrows and targeting across non-displayed boards need a visual fallback, such as highlighting the panel.
- **Either way:**
  - `GetHoverField` should be rewritten as a generic loop over (seat, zone quad, seat transform), which is shorter than today's cascade.
  - Background texture: draw half-UV quads per board, the same way `vFieldSpell1/2` does.

## 3. Network and lobby

### Verified
- **`HostInfo`** (`network.h:40-61`) carries `int32_t team1; int32_t team2; int32_t best_of;`, flags in `duel_flag_low/high`, and `DeckSizes sizes`. Relay mode is a duel flag: `isRelay = params & DUEL_RELAY` (`duelclient.cpp:730`).
- **Seat packets:**
  - `STOC_HS_PlayerEnter{uint16_t name[20]; uint8_t pos;}`.
  - `STOC_HS_PlayerChange{uint8_t status; // pos<<4 | state}`.
  - `STOC_TypeChange{uint8_t type;}` (`network.h:172-206`): self position in the low nibble and the host bit in the high nibble (`duelclient.cpp:910-911`).
- **The lobby UI has 6 slots.** `stHostPrepDuelist[6]`, `chkHostPrepReady[6]`, `btnHostPrepKick[6]` (`game.h:262-264`, created at `game.cpp:1398-1403`).
  - Positions > 5 are dropped: `if(pkt.pos > 5) break;` (`duelclient.cpp:1123, 1141`).
  - Rows are laid out team1 then team2 (`:832-845`). The window grows if `team1+team2 >= 5` (`:818`).
  - The team-count edit boxes accept only `1..3` (`menu_handler.cpp:888`).
  - The room list prints `[{}vs{}]` (`server_lobby.cpp:111`).
- **Chat colouring** assumes two sides via an `isTeam1`/`isFirst` swap (`duelclient.cpp:1080-1112`).
- **Fixed two-player message formats:**
  - `MSG_START` reads exactly two LPs and two deck/extra counts (`duelclient.cpp:1675-1688`).
  - `MSG_RELOAD_FIELD` loops `for(int i = 0; i < 2; ++i)` (`:4306`).
  - `MSG_WIN` handles only `if(player < 2)` (`:1617`).
  - `STOC_TIME_LIMIT` maps through `LocalPlayer` (`:1071-1078`).
- **The engine is also two-player:** `std::array<player_info,2> player;` (`ocgcore/field.h:400`), and 85 occurrences of `1 - playerid`/`1 - p`/`1 - tp`-style expressions in `ocgcore/*.cpp`.
- **The embedded LAN host** (`gframe/generic_duel.cpp`) has `DuelPlayer* cur_player[2]`, `hand_result[2]`, `time_limit[2]` (`generic_duel.h:138-150`) and `1 - player` win logic (`generic_duel.cpp:784-789`).
- **Multirole** also models two teams (`hi.t0Count/t1Count`, `Waiting.cpp:149-171`).

### Inference
- A 4-player FFA fits the existing lobby as 2+2 slots (or 1+3) plus a duel flag marking FFA. No new seat packet is needed.
- The in-duel protocol does need changes: an N-entry `MSG_START`, N-player `MSG_RELOAD_FIELD`, a player-elimination message distinct from `MSG_WIN`, a turn-player field actually used by `MSG_NEW_TURN`, and per-seat place masks wider than 32 bits for `MSG_SELECT_PLACE`/`MSG_SELECT_DISFIELD`.

## 4. Replays and spectators

### Verified
- **Replays.**
  - Names are parsed as `home_count + opposing_count` (`replay.h:151-153`, `replay.cpp:200-218, 241`).
  - Side counts come from `GetPlayersCount(int side)`, which returns home or opposing only (`replay.cpp:324-328`).
  - `ReplayThread` splits names into `selfnames`/`opponames` and forces `isFirst = isTeam1 = true` (`replay_mode.cpp:76-97`).
  - Header flags include `REPLAY_TAG 0x2` (`replay.h:15`).
- **Spectators.** They are `player_type = 7` and see a "swap" button (`btnSpectatorSwap`, `duelclient.cpp:1000`). It calls `ReplaySwap()`, which only exchanges two sides (`duelclient.cpp:1350, 4412`; `replay_mode.cpp:64, 224`).

### Inference
- The replay format can keep its header and record 4 names. FFA needs a flag, or `home_count=4, opposing_count=0`, plus a seat count.
- Spectator and replay "swap" becomes "rotate viewpoint seat". This is best done by changing the seat→view mapping and calling `RefreshAllCards()`, not by swapping arrays.

## Implications for a 4-player Domain mode

**Design options:**
1. **2-player Domain first.** No client multi-seat work: Domain Master Zone rendering plus lobby/deck checks only. This should ship independently.
2. **N-seat client with a focus view (recommended for 4 players).**
   - Add `MAX_SEATS=4`. Turn every `[2]` in `ClientField`/`DuelInfo` into `std::array<…,4>`.
   - Replace `LocalPlayer` with `ViewSeat(p) = (p - self_seat + N) % N`, using a front-seat map where 2 = front in a 4-player game.
   - Keep the existing two-board geometry for self + the "focused" opponent (default: the player in front, which matches the shared-EMZ rule).
   - Draw the other two as compact rotated boards, or as 2D panels with a click-to-focus button.
   - Generalise the place masks to per-seat 16-bit masks.
3. **Full 4-board table.**
   - Generate side-board vertices by matrix transform of the existing opponent tables, widen the frustum, and generalise hit-testing.
   - Most immersive, but readability at 720p is a real risk.

**Effort for option 2 (rough):**

| File | Work | Approx. lines |
|---|---|---|
| `client_field.h/.cpp` | arrays, `Initial`/`Clear`/`ReplaySwap` → `SetViewSeat`, `GetCardDrawCoordinates` per-seat transform, hand placement | 300 |
| `materials.h/.cpp` | per-seat transform table, compact-board vertices | 150 |
| `drawing.cpp` | `DrawBackGround` per board, selection lines per seat, `DrawLinkedZones` front-only, LP/name/time HUD for 4 + elimination state, turn-player highlight from the real turn player, `DrawCards`/`DrawMisc` loops | 400 |
| `event_handler.cpp` | generic `GetHoverField` rewrite (~175 → ~150), place-select response building, hover name tooltip (`:1640-1660`) | 300 |
| `duelclient.cpp` | ~92 `LocalPlayer` sites (mostly mechanical); `MSG_START`, `MSG_RELOAD_FIELD`, `MSG_SELECT_PLACE`/`DISFIELD`, `MSG_WIN` + new elimination msg, `MSG_NEW_TURN`, chat, time limit, lobby `isFirst` | 500 |
| `game.h/.cpp` | `DuelInfo`, seat switcher UI, team-count limits | 100 |
| `replay.cpp`, `replay_mode.cpp` | names, seat count | 80 |
| `generic_duel.cpp` (LAN host) | N-seat, or disable FFA on LAN and require Multirole | 300 or 20 |

Total: about 2,000–2,500 changed lines across about 12 client files. That is before the much larger engine (ocgcore) and Multirole work, which the client depends on for message formats.

**Main risks:**
- The engine protocol is the critical path: every two-player message format above must change together with the core and Multirole, or the client cannot be tested.
- **Ordering:** the 32-bit place mask and the `1 - x` patterns are spread out, so a missed site can show cards on the wrong board without any error. Start by replacing `LocalPlayer` with a seat map that asserts its input is in range.
- **Readability:** a full 4-board layout makes cards small at 720p, which is why the recommendation is a focus view or compact side boards.
- **UI for multi-target effects:** choosing which opponent is targeted or affected needs player-select prompts.
- **Elimination mid-duel:** a removed player's board has to stay visible but inert while their empty turns are still processed.
- **Spectators and replays:** both need seat rotation, and old 2-side assumptions in `ReplaySwap` and `isTeam1` will break silently if left in place.