CLIENT A:
I finished the client part of Domain (deck building, host settings, network, validation and replays) on `domain-client` in `/home/user/wt/client`. It builds cleanly and its checks match the reference script exactly. Nothing is pushed. The deck editor and host UI were never run under a display; only the extracted logic is tested.

The interrupted agent left most of the non-editor work done but uncommitted. I reviewed it, kept it, fixed some details and added the deck editor, which did not exist yet.

**Commits**
- `ad8ef1d9` Domain: deck model, list data, validation, host rule, transport and replays
- `960c17d3` Domain: client check against the reference implementation
- `4f0f1930` Domain: lock the extra rules, keep no-shuffle, siding layout from the room

## What was implemented
- **Deck model** (`deck.h`, `deck_manager.cpp/.h`):
  - `Deck::master` is cleared by `clear()` and refreshed by `RefreshDeck`.
  - `.ydk`: `#master` is written after the side deck. The reader matches `#master` before the generic `#` skip, also when there is no extra list (room READY path). The first code wins.
  - ydke: a 4th segment, written only when there is a Deck Master.
  - The plain-text export gets a "Deck Master" section.
  - `LoadDeck`, `LoadDeckFromBuffer`, `LoadSide` and `SaveDeck(cardlist)` carry the Deck Master.
  - `ReadDeckMasterTrailer()` reads the network trailer.
- **List parsing** (`LoadLFListSingle`, new `gframe/domain_list.h`):
  - An explicit "inside a list" flag replaces the old `hash != 0` test.
  - `$domain` counts only after a `!` line; with both `$domain` and `$genesys`, the second is ignored.
  - `#@` lines are hashed (`rotl32(fnv1a32(text), 1)`) and parsed only inside a Domain list. Malformed lines are skipped but still hashed; for a duplicate code the first line wins.
  - Lookups use the card's own code, then its plain alias (amendments D1, D10).
  - The membership test follows D2 and always adds the Deck Master's own attribute, race and archetypes.
  - `GetLFList` no longer copies each list.
- **Validation**:
  - `CheckDeckMaster` returns 0x11 (missing, unknown, non-monster, Token or Skill) and 0x14 (forbidden Deck Master).
  - `CheckDomainDeckContent` checks, in the reference script's order: forbidden types with Skills always forbidden, Rush/Legend cards → 0x12, the allowed-cards setting, card placement, singleton by plain alias across Deck Master + Main + Extra → 0x13, ordinary banlist lines, then membership → 0x12.
  - The LAN host (`GenericDuel::PlayerReady`) runs the Deck Master check before the size check, even when content checks are off.
  - Error codes 0x11–0x14 are in `network.h`; their texts (strings 7115–7118, with English fallbacks) are in `duelclient.cpp`.
- **Deck editor** (`game.cpp`, `deck_con.cpp/.h`, `drawing.cpp`, `game_config.inl`, `menu_handler.h`):
  - A "Domain" checkbox (7111), saved as the `domainMode` option. Checking it switches to a Domain list.
  - When Domain is on, the Side row becomes the Deck Master pane: a "Deck Master" (7110) header with the card's name and a single card slot.
  - Drag and drop works both ways. A Main or Extra card dropped on the slot swaps with the old Deck Master. The Deck Master must be a monster (not Token or Skill) and cannot be changed while siding.
  - Right-click on the slot removes the Deck Master.
  - "In Domain" filter (7114), refreshed when the Deck Master changes.
  - The Main header shows "x/60". `check_limit` allows one copy, Deck Master included. The Side Deck is refused while Domain is on.
- **Network**:
  - The `CTOS_UPDATE_DECK` trailer is sent on both the ready and siding paths.
  - The LAN host parses it in `UpdateDeck`. `LoadSide` refuses siding unless the Deck Master is the original one; the client also refuses with message 1408.
- **Host**:
  - Rule "Domain" at index 9 and Custom at 10, in every place listed in P2. `UpdateDuelParam` keeps the Domain bit.
  - Bots: no bot is listed for Domain.
  - One function, `ApplyFormatHostRules` (replacing `ApplyGenesysHostRules`), locks the rule for both Genesys and Domain lists. With a Domain list it also locks the custom rules, card types and deck sizes. The Domain rule cannot be chosen without a Domain list.
  - `netserver.cpp` follows D6: a Domain list forces `DUEL_MODE_DOMAIN`, sizes 60/0-15/0, 1v1, no relay, no extra rules. Any other list clears the Domain bit.
  - Room info, room listing and the LAN list show "Domain".
  - The hand test has rule 9.
  - `generic_duel` and `single_mode` add each Deck Master right after that duelist's Extra Deck. They forward hints 204/205, and the LAN host also caches them for spectators.
- **Replays**:
  - `REPLAY_DOMAIN = 0x400` (the next free bit in both the client and Multirole) is set on the YRP1 header only.
  - Writers: the LAN host and the hand test (the no-opponent branch writes a count of 0).
  - Readers: `ParseDecks` and `old_replay_mode`, which re-adds the Deck Master in the same order.
  - `ReplayDeck::master` exists, and "save decks from replay" keeps it.

## Testing
- **Build**:
  - Command: copy `gframe/` and `ocgcore/` into `/tmp/claude-0/mbuild`, then `./premake5 gmake2 --architecture=x64 --vcpkg-root=$PWD/vcpkg --sound=sfml --no-joystick=true --no-direct3d && make -Cbuild -j2 config=release_x64 ygopro`.
  - `rsync` is not installed, so the copy is done with `cp -a` in `/tmp/claude-0/-home-user/748cb8ed-8740-5baf-a166-480b1bf66532/scratchpad/client/sync_build.sh`. It does not delete files that were removed from the worktree.
  - Result: exit 0 on the final tree. No new gframe warnings: the only gframe warning is the existing `image_manager.cpp` "unused variable 'is_base'".
  - One linker warning, `-Wstringop-overflow` in `ocgcore/lua/src/lstrlib.c`, appears at the static-core link of the `ygopro` target. It comes from the unmodified Lua sources, not this work. I did not build the unmodified tree for that target to compare.
- **Checks against the reference**:
  - Command (exit 0):
    ```
    python3 -I tests/domain/client/check_client.py --ref /home/user/lflistszedja/tools/domain_ref.py --babel /tmp/claude-0/genesys/BabelCDB --list lflists/Domain.lflist.conf --decks 300 lflists/Genesys.lflist.conf /home/user/lflistszedja/*.lflist.conf
    ```
  - The script cuts the real functions out of the gframe sources, compiles them with small stubs, and compares them with `domain_ref.py`. Result: **73 ok, 0 failures**.
  - **Hashes**: Domain.lflist.conf gives 0xBC3B2D7E with 9,379 Deck Master lines. The reference's three corner-case lists also match, as do all ten existing lists (Genesys, TCG, OCG, GOAT, Rush, Speed and others).
  - **Rulebook examples** (Chronicle Magician, Lo, Destiny HERO - Malicious, Incredible Ecclesia, Cyber-Stein, Dark Magician Girl): for each, the set of monsters in the domain is identical to the reference's (3,186 / 3,677 / 3,626 / 2,544 / 3,469 / 3,209), and the named cards fall on the expected side. 60 random Deck Masters also match exactly.
  - **Decks**: 600 random legal and illegal decks (with and without content checks) give the same result as the reference. Named cases pass:
    - Umi + A Legendary Ocean → 0x13.
    - Cyber Dragon + Cyber Harpie Lady → legal, through the card's own archetype.
    - Chronicle Magician + Cyber Dragon → 0x12.
    - A Deck Master plus its alternate artwork → 0x13.
  - **File and trailer**: four `.ydk` `#master` cases and four trailer cases pass.

## Deviations from the spec
- The Genesys checkbox moved from (225,7,295,28) to (225,0,295,17) so the Domain checkbox fits under it at (225,17,295,34). There was no other free spot in the deck box.
- Choosing a Domain list in the editor ticks the Domain checkbox automatically; Genesys does not do this.
- Side Deck cards in a deck still show while Domain is on, to the right of the Deck Master slot, tinted red and with a red count, so they can be moved out.
- Cards outside the domain get a red tint in the Main and Extra panes.
- Without a Deck Master, the "In Domain" filter shows the cards that could be one.
- Right-click on a search result sets the Deck Master when Shift is held, or when there is no Deck Master yet and the card is a monster.
- With a Domain list, the host screen also clears and locks the extra-rule checkboxes, matching the host side.
- The LAN host keeps the TCG chain option and the no-shuffle option when it forces the Domain flags. It does not force LP, starting hand or draw count; D6 does not ask for that.
- There is no Omega export to warn about; Omega import simply clears the Deck Master.

## Known gaps
- No interactive test: dragging, the Deck Master pane, the host locks, siding and replay save/load were checked by reading the code only.
- Hand test: the Domain rule is not picked automatically when the editor's Domain option is on.
- Language change: the checkbox labels are not reloaded, same as Genesys.
- In a Domain room, an older client that sends no trailer is rejected with 0x11. When siding, it gets the existing side error.

CLIENT B:
I implemented the client duel UI for the Deck Master Zone (spec §4, P1 client side, P4, P7, P8) on `domain-client` in `/home/user/wt/client`, in three commits. It builds with no new warnings, and a new message-level test passes with 0 failures. Nothing was checked visually, because there is no display here. The other agent's deck-building/host work was left as it was.

## What I implemented
- **`client_field.h` / `client_field.cpp`**
  - New state: `dmz[2]`, `dmz_returns[2]`, `dmz_act[2]`, and the client-only location `LOCATION_DMZ 0x800` (next to `LOCATION_SKILL`).
  - New helpers:
    - `PutInDeckMasterZone`: places the card face-up and clears its counters and hints.
    - `TakeFromDeckMasterZone`.
    - `HasDeckMasterZone()`: true when the duel has `DUEL_DOMAIN` or a slot holds a card.
    - `ForgetCard`: drops every pointer to a card about to be deleted and deletes its materials.
  - `GetCard`: `(con, 0, DMZ_SEQUENCE)` returns `dmz[con]`, and `(con, 0x80, DMZ_SEQUENCE, sub)` returns its materials.
  - `GetCardDrawCoordinates` places the slot card and materials attached to it. `GetChainDrawCoordinates` handles `(0, DMZ_SEQUENCE)`.
  - `Clear`, `ReplaySwap` (swaps cards and return counts) and `RefreshAllCards` know the slot. The constructor and the two clear-flag functions reset `dmz_act`.
  - `UpdateCard` keeps the slot card face-up if the core reports its face-down position.
- **`materials.h` / `.cpp`**: `vFieldDmz` is X 1.2–2.3, Y −0.6..0.6 for the local player, mirrored at 6.7–5.6 for the opponent. `getDmz()` falls back to the skill-zone vertices on the 3-column field.
- **`duelclient.cpp`**
  - `HINT_DMZ` creates or updates the slot card (code, return count), with a fade-in. `HINT_DMZ_REMOVE` removes it only if it is still there. Both run while catching up and in replays.
  - `MSG_MOVE`: when previous or current is `(con, 0, DMZ_SEQUENCE)`, `MoveDeckMaster` moves the existing card in or out of the slot.
    - It keeps the card's Xyz materials, and handles moves to overlay, from overlay and to hand.
    - If the client never saw the card, it falls back to creating a new one.
    - Attaching materials onto the slot card now animates.
  - New `GetCommandCard`: every idle/battle list (summon, special summon, reposition, monster set, spell/trap set, attack) gets a temporary card when the card is unknown. Indexes stay aligned and nothing dereferences null.
  - Command lists, including the chain list, set `dmz_act` for the slot card.
  - `MSG_SELECT_EFFECTYN`: English fallback text for 7112, a null guard, and no `SetCode` or highlight for cards in the Deck.
  - `MSG_RELOAD_FIELD` keeps the high word of `duel_params` and keeps the slot cards and return counts across its `Clear()`.
- **`event_handler.cpp`**
  - Click sets `clicked_card = dmz[c]`. `case LOCATION_DMZ` added to the idle/battle/chain menu (Summon / Set / Special Summon / Activate), the waiting-state menu and the material list.
  - Hover shows a tooltip: name, "Deck Master" (7110), stats from the card data, and the cost line (7113, 500 × returns).
  - `GetHoverField`: Extra Monster Zone row sequence 0 is the local slot and 4 the opponent's. On the 3-column field the skill zone maps to the slot.
- **`drawing.cpp` / `game.h`**: slot outline (gold) only when there is a slot to show; hover highlight; the card in `DrawCards`; activation marker; the label 7119 inside an empty slot, split onto two lines if it does not fit (`DrawDeckMasterZoneLabel`).

## How I tested it
- **Build:**
  `/tmp/claude-0/-home-user/748cb8ed-8740-5baf-a166-480b1bf66532/scratchpad/client/build_ui.sh`
  This copies `gframe/` and `ocgcore/` into the build tree, then runs `./premake5 gmake2 --architecture=x64 --vcpkg-root=$PWD/vcpkg --sound=sfml --no-joystick=true --no-direct3d && make -Cbuild -j2 config=release_x64 ygopro`. Result: rc=0. The only warnings already appear in earlier build logs: `image_manager.cpp` unused `is_base`, lto-wrapper, and the Lua `memcpy` warning.
- **Message-level test:**
  `tests/domain/client/run_dmz_ui_test.sh /tmp/claude-0/mbuild` prints `OK (0 failures)`.
  It links `tests/domain/client/dmz_ui_test.cpp` against the real build objects (everything except `edopro_main.o`). It feeds `DuelClient::ClientAnalyze` in catching-up replay mode on a NULL/console Irrlicht device. It checks:
  - `HINT_DMZ`, `HINT_DMZ_REMOVE` (both when the slot is empty and when the card is still there) and the `GetCard` mapping;
  - slot positions and opponent rotation, and the chain position;
  - an idle command message with the slot card in every list, plus temporary cards for unknown entries and `dmz_act`;
  - materials attached to the slot card, then the card leaving to the Main Monster Zone with them (same `ClientCard` pointer);
  - a move to the GY and back into the slot with the code hidden, then the return count;
  - `ReplaySwap` both ways, and the fallbacks for an unknown slot;
  - `MSG_RELOAD_FIELD` keeping `DUEL_MODE_DOMAIN` and the slot, the 3-column fallback, and `Clear`.

## Deviations from the spec
- `rsync` is not installed, so the build script uses `cp -a` instead of `rsync -a --delete`. The only extra file in the build tree is the generated, excluded `CGUITTFont/bundled_font.cpp`.
- P8 applies to every Deck card in `MSG_SELECT_EFFECTYN`, as the v2 wording says, not only to prompt 7112.
- `GetCard` keys on `DMZ_SEQUENCE` alone, not on the card code (critique #4); E0/P4 make the sequence unambiguous.
- The cost line also shows when the cost is 0. The label is drawn only when the slot is empty.
- Additions beyond the spec: the activation marker, keeping the slot through `MSG_RELOAD_FIELD`, and the face-up guard on card updates.
- I fixed an existing use-after-free in `SendResponse`. Temporary cards were deleted before `ClearCommandFlag` / `ClearChainSelect` / `ClearSelect` ran over the lists that still pointed to them; the order is now reversed.

## Known gaps
- No visual check: geometry, label fit and animations are verified only by reading the code. The animated (non-catching-up) branches are not run by the test. The `MSG_UPDATE_CARD` guard and the `MSG_SELECT_EFFECTYN` change are also not covered by the test.
- `MSG_CHAINING` and `MSG_FLIPSUMMONING` still have no null guard. The engine never reports the card in the slot there.
- A reload in the middle of a duel drops materials attached to the slot card; materials only sit there briefly during an Xyz Summon.
- Cards from the slot shown in selection or confirm panels appear as plain location-0 cards (per P4), without a "Deck Master Zone" location text.
- When the Deck Master leaves the slot face-down, the opponent's client keeps its code. The server hides it, but the card is public anyway.
- Strings 7110, 7112, 7113 and 7119 use the built-in English text unless `strings.conf` ships them.

## Commits
- `16b06b2b` Domain: Deck Master Zone in the duel field
- `e84724e5` Domain: client checks for the Deck Master Zone, safe temporary cards
- `134acf69` Domain: keep the Deck Master Zone card face-up on card updates

Files changed: `gframe/client_field.{h,cpp}`, `gframe/materials.{h,cpp}`, `gframe/duelclient.cpp`, `gframe/event_handler.cpp`, `gframe/drawing.cpp`, `gframe/game.h`. New files: `/home/user/wt/client/tests/domain/client/dmz_ui_test.cpp` and `/home/user/wt/client/tests/domain/client/run_dmz_ui_test.sh`.