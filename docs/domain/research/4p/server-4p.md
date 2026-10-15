# Multirole server: what it would take to support a 4-player free-for-all

Multirole only supports two teams. Team indexes 0/1 are built into the room model, how messages are sent out, timers, the turn-order swap, win/match handling and the replay format. A 4-team free-for-all can't be switched on with a setting. About 12 server files need changes, and the client and core must change in step (the start message, replay format, positions and timers).

## 1. Room and duelist model

**Verified:**
- **Positions are a (team, slot) pair.** `Client.hpp:27` has `using PosType = std::pair<uint8_t, uint8_t>;` and spectators are `{UINT8_MAX, UINT8_MAX}` (`Client.hpp:28`). Duelists are stored in `std::map<Client::PosType, Client*> duelists;` (`Context.hpp:152`).
- **Seating only knows team 0 and team 1.** `TryEmplaceDuelist` (`Waiting.cpp:244-270`) fills team 0 up to `hostInfo.t0Count`, then `p.first = 1U; if(EmplaceLoop(p, hostInfo.t1Count))`.
  - Kicking decodes a flat index the same way: `p.first = static_cast<uint8_t>(e.pos >= hostInfo.t0Count);` (`Waiting.cpp:149`).
- **The start check for non-relay rooms** is `duelists.size() == hostInfo.t0Count + hostInfo.t1Count` (`Waiting.cpp:171`). For relay, `TightenTeam(0U); TightenTeam(1U);` (`Waiting.cpp:218-219`).
- **Team sizes are clamped to 1–3** at room creation (`RoomHosting.cpp:203-204`):
  ```cpp
  hi.t0Count = std::clamp(hi.t0Count, 1, 3);
  hi.t1Count = std::clamp(hi.t1Count, 1, 3);
  ```
  The client's local server does the same (`gframe/netserver.cpp:361-362`).
- **Position encoding:** `return (pos.first * t1max) + pos.second;` (`STOCMsgFactory.cpp:224-227`), with `t1max` taken from `t0Count` (`Context.cpp:17`). Spectators are hard-coded as `pos = 7U; // Sum of both teams max player + 1` (`STOCMsgFactory.cpp:20`).
- **Room listing cap:** `MAX_AMOUNT_OF_DUELISTS = 6U` (`DuelistData.hpp:27`), so 4 players fit.
- **Core creation takes exactly two player configs.** `IWrapper::DuelOptions` has `Player team1; Player team2;` (`Core/IWrapper.hpp:51-52`). This mirrors `OCG_DuelOptions { ... OCG_Player team1; OCG_Player team2; ...}` (`multirole/src/ocgapi_types.h:57-61`).
  - `Dueling.cpp:86-101` passes `popt, popt`.
  - The Hornet wrapper copies the struct byte for byte: `Write<OCG_DuelOptions>(wptr, {... opts.team1, opts.team2, ...})` (`HornetWrapper.cpp:158-172`). Any change to the struct layout must be made identically in multirole's own copy of `ocgapi_types.h`, which already differs from MASQPro's: `OCG_VERSION_MAJOR 9` vs `11`, and two extra creation-status enum values.
- **`OCG_NewCardInfo` documents `uint8_t team; /* either 0 or 1 */`** (`ocgapi_types.h:74`). Cards are added in `Dueling.cpp:145-171`:
  ```cpp
  nci.team = nci.con = GetSwappedTeam(t);
  nci.duelist = (kv.first.second + !!s.currentPos[t]) % teamCount[t];
  ```
- **Relay and tag:** several duelists share one core team. The server tracks the active one in `s.currentPos[team]` and rotates it on `MSG_TAG_SWAP` (`Dueling.cpp:338-343`), using `(team == 0U) ? hostInfo.t0Count : hostInfo.t1Count`. `GetCurrentTeamClient` returns `duelists[{team, s.currentPos[team]}]` (`Dueling.cpp:311-314`).
- **Per-duel state is sized for two teams** (`State.hpp:46-53`):
  ```cpp
  std::array<uint8_t, 2U> currentPos;
  std::array<uint8_t, 2U> retryCount;
  std::array<std::chrono::milliseconds, 2U> timeRemaining;
  ```
  Also `std::array<uint8_t, 2U> choices` for rock-paper-scissors (`State.hpp:64`).
- **Turn order is a single XOR bit.** `GetSwappedTeam` is `assert(team <= 1U); return isTeam1GoingFirst ^ team;` (`Context.cpp:80-84`). `GetTeamCounts` returns `std::array<uint8_t, 2U>` (`Context.cpp:86-92`).
- **Rock-paper-scissors and choosing who goes first are two-sided.**
  - `SendRPS` asks only `duelists[{0U,0U}]` and `duelists[{1U,0U}]` (`RockPaperScissor.cpp:65-70`).
  - The result compares `s.choices[0U]` with `s.choices[1U]` (`:20-40`).
  - `ChoosingTurn` sets `isTeam1GoingFirst` from `Position().first == 0U/1U` (`ChoosingTurn.cpp:19-21`).
- **The timer system has two slots.** `TimerAggregator.hpp:33` has `std::array<AsioTimer, 2U> timers;`, with `assert(team <= 1U)` at `TimerAggregator.cpp:18,24,36`. `Finish` cancels `tagg.Cancel(0U); tagg.Cancel(1U);` (`Dueling.cpp:564-565`).

## 2. How core messages reach each player

**Verified:**
- **Destination comes from the message type** (`CoreUtils.cpp:185-274`). Select prompts are `SPECIFIC_TEAM_DUELIST_STRIPPED`. Most prompts and hints 1/2/3/5 are `SPECIFIC_TEAM_DUELIST`. Hint 200 is `SPECIFIC_TEAM`. Hints 4/6/7/8/9/11 are `EVERYONE_EXCEPT_TEAM_DUELIST`. Move, draw, set, summon and shuffle messages are `EVERYONE_STRIPPED`.
- **The receiving player is read from the message:** `msg[2U]` for `MSG_HINT`, otherwise `msg[1U]` (`CoreUtils.cpp:276-289`).
- **Hiding information is done per player and does not assume two teams.** `StripMessageForTeam(team, msg)` compares a card's controller with `team` (for example `if(current.con == team || IsLocInfoPublic(current)) break;`, `CoreUtils.cpp:351-357`). It would work unchanged for player indexes 0–3.
- **The sending code in `Process` (`Dueling.cpp:429-483`) assumes two teams:**
  ```cpp
  const std::array<Msg, 2U> sMsgs = { StripMessageForTeam(0U, msg), StripMessageForTeam(1U, msg) };
  SendToTeam(GetSwappedTeam(0U), ...); SendToTeam(GetSwappedTeam(1U), ...);
  SendToSpectators(SaveToSpectatorCache(s, MakeGameMsg(StripMessageForTeam(1U, sMsgs[0U]))));
  ```
  Query results (card and location updates) go to the owner and to "the other team": `SendToTeam(team, MakeMsg(ownerBuffer)); SendToTeam(1U - team, strippedMsg);` (`Dueling.cpp:389-392, 423-425`).
  - `SendToTeam` itself asserts `team <= 1U` (`Context.cpp:96`).
  - Team chat sends the plain copy to `1U - client.Position().first` (`Context.cpp:158-160`).
- **The start message is two-player only.** `MakeStartMsg` writes 18 bytes: type, viewer byte, LP ×2, then t0 deck/extra and t1 deck/extra sizes (`CoreUtils.cpp:436-449`; struct at `CoreUtils.hpp` lines 31-37). `Dueling.cpp:174-187` sets `msgStart[1]` to 0 or 1 per team, and `0xF0 | isTeam1GoingFirst` for spectators. Decks are recorded and extra decks sent only for `0U` and `1U` (`Dueling.cpp:203-204, 222-223`).
- **Who must answer a prompt:**
  - Before sending, `PreAnalyzeMsg` sets `s.replier = &GetCurrentTeamClient(s, GetSwappedTeam(GetMessageReceivingTeam(msg)))` (`Dueling.cpp:356-360`).
  - A response from anyone else is dropped: `if(s.replier != &e.client) return std::nullopt;` (`Dueling.cpp:263-264`).
  - Everyone else gets `MSG_WAITING` (`Dueling.cpp:501`), and the timer runs for the replier's team (`:505-513`).
  - This is all keyed on the single player byte, so it works for N players once `GetSwappedTeam` and the arrays are generalised.
- **The duel end is two-sided everywhere:**
  - `DuelFinishReason::winner` uses `2 == DRAW` (`Context.hpp:61`).
  - Disconnect, surrender and timeout set `winner = 1U - p.first` / `1U - e.team` and end the whole duel (`Dueling.cpp:246-247, 298-299, 305-306`). The same applies to disconnects during rock-paper-scissors and siding (`RockPaperScissor.cpp:51`, `Sidedecking.cpp:29`).
  - A wrong response gives `1U - s.replier->Position().first` (`Dueling.cpp:491`).
  - `MSG_WIN` is mapped with `(msg[1U] > 1U) ? 2U : GetSwappedTeam(msg[1U])` (`:496`).
  - Match wins are `std::array<int32_t, 2U> wins` (`Context.hpp:159`).
  - The next turn chooser is `duelists[{1U - dfr.winner, 0U}]` (`Dueling.cpp:587-592`).

**Inference:**
- **Spectators** could get a fully stripped copy with `StripMessageForTeam(0xFF, msg)`. No controller ever equals 0xFF, so only public information survives.
- **Removing a player at 0 LP.** The core would have to keep the duel running and emit a new message (for example `MSG_PLAYER_REMOVED`), not `MSG_WIN`. The server would mark that seat inactive but keep sending it public messages.
- **Surrender, disconnect and timeout in a 4-player game** must not end the duel. Today nothing in `IWrapper` lets the server tell the core to remove one player (`IWrapper.hpp:56-71` lists every call).
  - One stop-gap would be `s.core->LoadScript(s.duelPtr, "x", "Duel.<RemovePlayer>(p)")` between `Process` calls. `LoadScript` exists at `IWrapper.hpp:63`, but this is a hack that also bypasses replays.
  - A clean fix needs a new core API (an `OCG_DuelRemovePlayer`-style call), a new wrapper method in the dynamic-library wrapper (`DLWrapper`) and the Hornet wrapper, and a matching action in `Hornet/main.cpp`.

## 3. Room settings packet (HostInfo)

**Verified:**
- `HostInfo` (`MsgCommon.hpp:57-84`) contains `uint8_t mode; // NOTE: UNUSED`, `uint8_t duelRule; // NOTE: UNUSED`, `int32_t t0Count; int32_t t1Count; int32_t bestOf; uint32_t duelFlagsLow; uint32_t duelFlagsHigh; uint16_t extraRules;`.
- The client reads `mode` and `duel_rule` only in compatibility mode, when the handshake doesn't match (`gframe/duelclient.cpp:702-725`). Otherwise both are free.
- The duel flags are sent straight to the core as `OCG_DuelOptions.flags` (`Dueling.cpp:98`). The highest flag defined in MASQPro's core is `DUEL_NORMAL_SUMMON_FACEUP_DEF 0x1000000000` (`ocgcore/ocgapi_constants.h:428`), so the higher 64-bit flag bits are unused.
- The lobby listing JSON reports `team1`/`team2` (`LobbyListing.cpp:110-111`).
- Starting LP is derived from the team sizes (`RoomHosting.cpp:239-249`).
- The handshake requires an exact version match: `p->hostInfo.version != YGOPro::SERVER_VERSION` (`RoomHosting.cpp:179-180`, version set at `Config.hpp:10-20`).

**Options for marking a room as a 4-player free-for-all (inference):**
- **(a)** Add a core duel flag, for example `DUEL_FFA = 0x2000000000`, and keep `t0Count=1, t1Count=1`. The player count goes in `mode`, which is unused (2 or 4). The packet layout doesn't change, the core sees the flag directly, and old clients that ignore it get rejected by the handshake once `SERVER_VERSION` is bumped.
- **(b)** Make `t0Count=4` mean "4 teams of 1". This reuses existing fields, but it is ambiguous with tag teams, clashes with the 1–3 clamp, and every `t0Count/t1Count` user would misread it.

I recommend (a), plus a bump to `SERVER_VERSION.client.minor` or `.major`.

## 4. Replays

**Verified:**
- `Replay` stores `std::array<std::map<uint8_t, Duelist>, 2U> duelists;` (`Replay.hpp:51`), filled through `AddDuelist(team, pos, ...)` (`Replay.cpp:122-125`).
- Both formats write exactly two team blocks: `team0Count/team0Names/team1Count/team1Names` (format comments at `Replay.cpp:68-100`; `WriteDuelists` at `:224-236` loops over `duelists.size()`, which is 2).
- The YRP part replays the duel by re-running the core from the stored decks and responses. It writes the starting LP, draw counts and flags, then one deck/extra deck per duelist in team order (`Replay.cpp:269-282`).
- The header is `ExtendedReplayHeader::CURRENT_VERSION = 1U` (`Replay.cpp:61`). The header flags already include `REPLAY_TAG`, `REPLAY_SINGLE_MODE` and so on (`:33-42`).

**Inference:** for 4-player replays, change the array to 4 (or a vector) and write a team count before the team blocks. Gate this behind a new header flag (`REPLAY_MULTI = 0x400`) or extended-header version 2, so old clients reject the file instead of misreading it. The client's replay loader and its local replay server must also be updated. Both re-create the duel from these headers, so the duel flag from option (a) must also be stored there (it already is: `duelFlags`, `Replay.cpp:272`).

## Implications for a 4-player Domain mode

**Design (assuming the core exposes 4 player indexes, 0–3):**
1. **Keep the seat number equal to the core player index.** Build the room as `Pos{seat, 0}` with seats 0–3, and treat each seat as a team of one. Replace `isTeam1GoingFirst`/`GetSwappedTeam` with `uint8_t firstSeat` and a rotation: `core = (seat - firstSeat) & 3` for clockwise order. Alternatively leave seats unrotated and pass the first player to the core.
2. **Generalise two-slot arrays to `std::array<..., 4U>` plus an `nTeams` member:** `currentPos`, `retryCount`, `timeRemaining`, `TimerAggregator::timers`, `wins` and `Replay::duelists`. Drop the `team <= 1U` asserts.
3. **Sending:** replace each `1U - team` with a loop over every other active seat in `SendToTeam`. `EVERYONE_STRIPPED` strips once per seat, plus once with 0xFF for spectators. Team chat follows the same rule.
4. **Start-of-duel messages:** add a new free-for-all start message carrying the player count, each player's LP and deck sizes, and the viewer's seat. Record and send decks for all seats in loops.
5. **Order and match flow:** replace rock-paper-scissors with a server die roll from `rng` (or rock-paper-scissors among four with re-rolls), and keep `ChoosingTurn` for the winner. For free-for-all rooms, force best-of-1 at creation or define match points per player.
6. **Elimination:** handle a new core "player removed" message by marking the seat eliminated (it stays connected and sees only public information), and end the duel only on `MSG_WIN`. Surrender, disconnect and timeout call a new wrapper method (`RemovePlayer`) on the core instead of `Finish`.
7. **Settings and listing:** add the free-for-all flag and `mode`, clamp the team counts to 1 in free-for-all, list `players: 4` in the room listing, and bump `SERVER_VERSION`.

**Effort (server only):**
- `Room/State/Dueling.cpp` is about 60% of the work: `operator()(Dueling&)`, `Process` (all four lambdas), `Finish`, and the ConnectionLost/Surrender/TimerExpired handlers.
- `Room/Context.hpp/.cpp`: `GetSwappedTeam`, `GetTeamCounts`, `SendToTeam`, `MakeAndSendChat`, members.
- `Room/State.hpp`.
- `Room/State/Waiting.cpp`: `TryEmplaceDuelist`, `TryKick`, `TryStart`.
- `RockPaperScissor.cpp`, `ChoosingTurn.cpp`, the disconnect handlers in `Sidedecking.cpp` and `Rematching.cpp`.
- `Room/TimerAggregator.hpp/.cpp` and `Event.hpp` (fine as is).
- `STOCMsgFactory.cpp`: `EncodePosition` and the spectator value 7.
- `YGOPro/CoreUtils.hpp/.cpp`: `MakeStartMsg` and the new message type in the routing table.
- `YGOPro/Replay.hpp/.cpp`, `YGOPro/MsgCommon.hpp`, `YGOPro/Config.hpp`, `Endpoint/RoomHosting.cpp`, `Endpoint/LobbyListing.cpp`.
- If player removal gets a core API: `Core/IWrapper.hpp`, `DLWrapper.cpp`, `HornetWrapper.cpp`, `Hornet/main.cpp`, `ocgapi_funcs.inl`, `ocgapi_types.h`.

Roughly 15–20 files and 600–1,000 changed lines. The client's local-hosting server (`gframe/generic_duel.cpp`, 1,594 lines, built on `players.home`/`players.opposing` at `generic_duel.h:133-134`) needs a parallel rewrite or a separate free-for-all class.

The 2-player Domain mode needs no server changes beyond possibly a flag or banlist marker, the way Genesys is handled at `RoomHosting.cpp:219-229`.

**Main risks:**
- **Core ABI drift.** Multirole ships its own `ocgapi_types.h`, already behind MASQPro's (version 9 vs 11), and Hornet copies `OCG_DuelOptions` byte for byte. Any new free-for-all fields must stay in sync or there will be silent memory corruption.
- **Message format coupling.** Every message carrying a player byte must use 0–3. The client parses `MSG_START` and others assuming two players (`duelclient.cpp:1645-1667`).
- **Elimination semantics.** The rule "their turn still happens", with a removed seat still in the turn order, requires the core never to prompt a removed player. Otherwise the server waits for a response from a dead seat (`Dueling.cpp:263`) until the timer runs out.
- **Hidden information.** Leaks become possible when the stripped copy for "the other team" is replaced by per-seat copies. Spectator caching must use the fully stripped variant.
- **Replay compatibility** needs a new header flag and an updated client loader. Old clients must be blocked by the version bump.