1. **Blocker: the LAN host and hand test drop HINT_DMZ (204) and HINT_DMZ_REMOVE (205), and LAN spectators never catch up on them.**
   - Evidence, LAN host: `gframe/generic_duel.cpp:846-878`. The `MSG_HINT` switch only lists 1-11 and 200-203 and has no `default`, so it sends 204/205 to nobody. They are still recorded, because `record` stays true.
   - Evidence, spectators: `Catchup()` (`generic_duel.cpp:137-149`) replays only `packets_cache`. No `MSG_HINT` is ever pushed there; only `MOVE`, `SET`, `CONFIRM`, etc. and the `default` branch (`:1259-1262`) are.
   - Evidence, hand test: `single_mode.cpp:356-391` calls `Analyze()` only for the listed hint types.
   - The spec's "Hints ≥200 are already processed while catching up" is true only for the client handler (`duelclient.cpp:1402`). Multirole is fine: `CoreUtils.cpp:233` routes unknown subtypes to everyone, and `SaveToSpectatorCache` keeps them.
   - **Spec change:** add to §3/§4: "generic_duel.cpp and single_mode.cpp: add `case 204: case 205:` to the 10/201-203 group. generic_duel also does `packets_cache.push_back(packet)` for 204/205."

2. **Blocker/major: the host UI loses bit 37, and the index shift deletes the Domain entry.**
   - Evidence, lost flag: `UpdateDuelParam` (`game.cpp:3104-3184`) rebuilds `duel_param` only from `chkCustomRules`. The highest bit it can produce is 36 (`0x100ULL<<(i-3)`, i≤31).
   - Two callers turn Domain into MR5 this way:
     - switching the host tabs: `menu_handler.cpp:912-913` (`curTab==0`)
     - changing language: `game.cpp:3657-3659` (`prev >= 7`)
   - Evidence, deleted entry: `CHECK(5)` calls `cbDuelRule->removeItem(9)` (`game.cpp:3159`), and `COMBOBOX_DUEL_RULE`'s `remove:` label calls `combobox->removeItem(9)` (`menu_handler.cpp:1027`).
     - With Domain at 9, picking Domain removes Domain itself.
     - So does selecting MR5.
   - Evidence, lock reset: `ApplyGenesysHostRules` runs `cbDuelRule->setEnabled(!genesys)` (`game.cpp:3203`), which re-enables the selector while a Domain list is chosen.
   - **Spec change:** list every site.
     - In `UpdateDuelParam`, set `flag |= duel_param & DUEL_DOMAIN` before the switch. Add `case DUEL_MODE_DOMAIN: setSelected(9); if(flag2==DUEL_MODE_DOMAIN_FORB){removeItem(10);break;}`.
     - All `removeItem(9)` become `removeItem(10)` (`game.cpp:3132,3140,3148,3159,3171`; `menu_handler.cpp:1027`). `setSelected(9)` becomes `setSelected(10)` (`game.cpp:3178`).
     - Add `case 9` in the tab handler (`menu_handler.cpp:917-943`), in `COMBOBOX_DUEL_RULE` (sizes {60,60},{0,15},{0,0}, hand 5), and in hand test (`deck_con.cpp:185-206`).
     - Make `BotRuleFilter` return a value that no bot lists.
     - Merge the Genesys and Domain lock into one function so that one list type does not unlock the other.

3. **Major: the replay plumbing is underspecified, and one gap is a heap overflow in Multirole.**
   - Evidence, overflow: Multirole sizes the YRP buffer exactly with `YRPPastHeaderSize()` (`YGOPro/Replay.cpp:198-222`), then writes through a raw pointer. Only an `assert` checks the size (`:288`). If the DM blocks are not counted, release builds overflow `vec`.
   - Evidence, flags: `HEADER_FLAGS` is `constexpr` (`:56`). `ParseDecks` (`replay.cpp:237-255`) reads decks only from the **YRP1** header. That covers the standalone `_LastReplay.yrp` and the YRP embedded in YRPX.
   - Evidence, a missing writer: `single_mode.cpp:108-151` writes YRP1 deck blocks too. `old_replay_mode.cpp:131-170` re-simulates hand tests from them, so leaving it out desyncs hand-test replays. Its `handTestNoOpponent` branch writes `0,0` and would also need a DM count of 0.
   - Evidence, save decks: "Save decks from replay" (`menu_handler.cpp:468-473`) and `ReplayDeck` (`replay.h:64-66`) drop the DM.
   - **Spec change:**
     - Set `REPLAY_DOMAIN` on the YRP1 header (Multirole: `HEADER_FLAGS | (domain?REPLAY_DOMAIN:0)` for the YRP header only).
     - Add `4+4n` per duelist to `YRPPastHeaderSize`.
     - Add single_mode as a writer.
     - Add `ReplayDeck::master`, and save it in "save decks".
     - Pin the call order: "the DM `OCG_DuelNewCard` immediately follows that duelist's Extra cards, identically in generic_duel, single_mode, Multirole and old_replay_mode", because card IDs depend on order.
     - State that older readers will misparse YRP1 decks (YRPX playback still works).

4. **Major: `GetCard(con,0,seq)` → `dmz[con]` captures other cards at location 0.**
   - Evidence, which cards sit at location 0:
     - Rule cards are added at (0,0,0) (`generic_duel.cpp:643-647`; Multirole `Dueling.cpp:119-127`, including `EXTRA_RULE_DECK_MASTER` 153999999).
     - Skill handlers and `EnableExtraRules` cards are moved to location 0 with their old sequence (`proc_skill.lua:164`, `utility.lua:2568`). `add_card` does not reset the sequence for location 0 (`field.cpp:137-199`).
   - Evidence, why it matters: the IDLECMD activatable list creates a limbo card only when `GetCard` returns null (`duelclient.cpp:1890`, same in BATTLECMD at 1733 and in CHAIN at 2155). A skill's "conti" entry would therefore attach `COMMAND_ACTIVATE` or `chain_code` to the DM.
   - Also, `MSG_SELECT_CARD`, `MSG_SELECT_UNSELECT_CARD` and `MSG_CONFIRM_CARDS` handle `location==0` before calling `GetCard` (`duelclient.cpp:2001, 2059, 2082, 2606`). So "GetCard … so MSG_SELECT_CARD finds it" is false. Those messages show the DM as a panel limbo card, which works.
   - **Spec change:** "Return `dmz[con]` for loc 0 only when the entry's code equals `dmz[con]->code` (all idle, battle and chain lists). Leave the SELECT_CARD, UNSELECT and CONFIRM location-0 panel paths as they are."

5. **Major: Domain can run without validation, and the bit/list pairing is not enforced.**
   - Evidence:
     - `no_check_deck_content` / `dontCheckDeckContent` skips content checks (`generic_duel.cpp:374`; `Context.cpp:269`). Spec rule 1 (DM present and a monster) would be skipped too, and duel start would still add any code (Spell, Token, Skill, unknown) as `LOCATION_DECK_MASTER`.
     - A client can also send bit 37 with a non-Domain list or no list: Multirole keeps `banlistHash=0` (`RoomHosting.cpp:201-202`), and the flag reaches the core unchanged.
     - Relay or tag: the core accepts `duelist≠0` only for DECK/EXTRA (`ocgapi.cpp:84-85`), and Multirole rotates which player is duelist 0 (`Dueling.cpp:151`).
     - `extraRules` can add 153999999 or other location-0 rule cards.
     - Multirole loads whatever `libocgcore.so` the bin repo serves and never checks its version. On an unmodified core, `(uint8_t)0x40000000` is 0, so the DM becomes an inert location-0 card and bit 37 is ignored.
   - **Spec change:**
     - Servers clear `DUEL_DOMAIN` unless the list is a Domain list (`netserver.cpp:376`, `RoomHosting.cpp:217`).
     - Domain forces `t0Count=t1Count=1`, clears `DUEL_RELAY` and clears `extraRules`.
     - Check 1 runs even when content checks are off.
     - The core ignores a DM that is not a monster.
     - Bump `OCG_VERSION`, and Multirole and the LAN host refuse Domain rooms on an older core.

6. **Major: siding drops or swaps the DM.**
   - Evidence, client and LAN host:
     - LAN: `LoadSide` builds `ndeck` from the buffer and ends with `deck = ndeck` (`deck_manager.cpp:474-522`), so the DM is lost unless the trailer is parsed into it.
     - Client: `BUTTON_SIDE_OK` (`deck_con.cpp:359-385`) builds its own buffer and also needs the trailer.
   - Evidence, Multirole: `Sidedecking.cpp:103-112` compares only the sizes and the Main/Extra/Side code map, then calls `SetCurrentDeck(sideDeck)` without `CheckDeck`. Game 2 runs with no DM, or with a different one.
   - **Spec change:** "In siding, a Domain room requires the trailer and DM == original DM (LAN host `LoadSide`, Multirole `Sidedecking`), else SIDEERROR. `Deck`/`Event::UpdateDeck`/`LoadDeck` carry the DM."

7. **Minor/major: `MSG_RELOAD_FIELD` strips bit 37 on the client, and the field reset paths do not know the DMZ.**
   - Evidence, reload: `duelclient.cpp:4299-4301` sets `dInfo.duel_params = opts` (u32). Hand test always emits a reload through `Debug.ReloadFieldEnd()` (`single_mode.cpp:153`). Any UI gated on `duel_params & DUEL_DOMAIN` (zone outline, info text) is off in hand test.
   - Evidence, reset paths: in best-of-3, `MSG_START` starts a new game, so `Clear()` must delete `dmz[]`. Replay side-swap uses `ReplaySwap` (`replay_mode.cpp:224`) and must swap `dmz[0]` and `dmz[1]`. `RefreshAllCards` must include them.
   - **Spec change:** "preserve the high word: `duel_params = opts | (duel_params & 0xffffffff00000000)`. Add `dmz[]` to `Clear`, `ReplaySwap` and `RefreshAllCards`."

8. **Minor: `MSG_SELECT_EFFECTYN` for a DM in the Deck.**
   - Evidence: `duelclient.cpp:1951-1952` runs `SetCode(code)` on the face-down card at the core's deck sequence, whose identity the client does not track.
   - The case is real: GY→Deck counts as a zone change, so the 7112 prompt can come while the DM is in the Deck.
   - Extra, GY and banished cases are safe; the cards exist and there is no null crash.
   - **Spec change:** "for desc 7112 with location DECK, skip `SetCode`; the fallback text needs no `%ls`."

9. **Minor: error order differs between hosts.**
   - Evidence: the LAN host runs `CheckDeckSize` before content (`generic_duel.cpp:373-381`), and so does Multirole (`Context.cpp:244-266`).
   - An older client with no trailer gets MAINCOUNT (61) or 0x11, depending on where the DM landed.
   - Older clients show 0x11-0x14 through `default` → string 1406. That is acceptable.
   - **Spec change:** "the DM presence check (0x11) runs before the size check in both hosts."

10. **Minor: Domain rooms are listed as "Custom".**
    - Evidence: `GetMasterRule` returns truerule 6 for `DUEL_MODE_DOMAIN`. That affects `server_lobby.cpp:116-126`, `duelclient.cpp:757-781` (room info, which also lists MR5 checkbox rules) and the LAN list at `duelclient.cpp:4722`.
    - **Spec change:** check `DUEL_DOMAIN` first and show 7111 "Domain" in all three places.

11. **Minor: ydk and ydke details.**
    - `LoadCardList` skips every `#` line except `#extra` (`deck_manager.cpp:374-378`), so `#master` must be matched before that `continue`. It must also work when `extralist` is null (the READY path).
    - Export the 4th ydke segment only when a DM exists, so decks without a DM keep the 3-segment form.
    - An older client re-saving a Domain .ydk moves the DM into side and drops `#master`. Document this.
    - The Omega base64 format cannot carry a DM; export should warn.

Points I checked that need no change:
- The trailer passes old parsers. Multirole ignores leftover bytes (`Client.cpp:205-230`), and the LAN host only checks `mainc+sidec ≤ (len-8)/4` (`generic_duel.cpp:416`). A Domain deck is 316 bytes against the 1021 limit.
- Bit 37 survives the transport: HostInfo (`duelclient.cpp:236-237`), `OrDuelFlags`, the listing JSON (u64, `server_lobby.cpp:229-231`) and the YRP `duelFlags` (u64).
- Neither Multirole nor the LAN host supports player reconnect, so spectator catch-up (finding 1) is the only catch-up path.