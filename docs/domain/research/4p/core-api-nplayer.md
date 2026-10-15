# ocgcore public API and the duel object for N players: research report

**Scope:** `/home/user/MASQPro/ocgcore` (API and core), plus the points where it meets Multirole (`/home/user/multirole`), the client (`/home/user/MASQPro/gframe`) and the scripts (`/home/user/zedja123/cardscripts`). I read the code but did not edit anything.

## 1. Public API surface (verified)

**Version.** `ocgapi_types.h:10-11` sets `OCG_VERSION_MAJOR 11`, `OCG_VERSION_MINOR 0`. The client and server check this exactly:
- **Client against the core library:** `gframe/dllinterface.cpp:119` has `return (max == OCG_VERSION_MAJOR) && (min == OCG_VERSION_MINOR);`.
- **Client against the server:** `CLIENT_VERSION` packs the OCG version (`gframe/config.h:29`). The server compares it with `SERVER_VERSION = {{41,0},{11,0}}` (`multirole/src/Multirole/YGOPro/Config.hpp:10-20`) and rejects a mismatch (`Endpoint/RoomHosting.cpp:180-182`).

**Duel options.** There are exactly two player slots (`ocgapi_types.h:53-78`):
```c
typedef struct OCG_Player { uint32_t startingLP; uint32_t startingDrawCount; uint32_t drawCountPerTurn; } OCG_Player;
typedef struct OCG_DuelOptions { uint64_t seed[4]; uint64_t flags; OCG_Player team1; OCG_Player team2;
  OCG_DataReader cardReader; void* payload1; ... void* payload4; uint8_t enableUnsafeLibraries; } OCG_DuelOptions;
```
- There is no separate hand-count field. `startingDrawCount` is the opening hand size (`field.h:111-113`: `start_count(team.startingDrawCount), draw_count(team.drawCountPerTurn)`).
- `field::field` builds exactly two `player_info` from team1 and team2: `player({ {options.team1, options.team2} })` (`field.cpp:67`). Storage is `std::array<player_info,2> player;` (`field.h:400`).
- Multirole has its own copy of `ocgapi_types.h`, still marked version 9 but with the same struct layout (`multirole/src/ocgapi_types.h:70` has `enableUnsafeLibraries`). It fills the struct with positional aggregate init (`Core/DLWrapper.cpp:84-99`).
- Multirole's Hornet process copies the raw struct across the process boundary with `Write<OCG_DuelOptions>` (`Core/HornetWrapper.cpp:159-174`) and `Read<OCG_DuelOptions>` (`Hornet/main.cpp:147`).
- The core copies the whole struct at once: `auto options = *options_ptr;` (`ocgapi.cpp:26`). **Inference:** if fields are appended to `OCG_DuelOptions`, the core will read past the end of the shorter struct that Multirole builds. That rules out appending fields as a byte-compatible change.

**`OCG_NewCardInfo`** (`ocgapi_types.h:80-88`) has `uint8_t team; /* either 0 or 1 */ uint8_t duelist; ... uint8_t con;`. In `OCG_DuelNewCard` (`ocgapi.cpp:62-104`):
- With `duelist == 0`, the card goes straight onto the field: `pcard->owner = info.team; game_field.add_card(info.con, ...)`. `team` and `con` are not bounds-checked here. `is_location_useable` and `add_card` then index `player[con]`.
- With `duelist != 0` (extra tag or relay duelists), `if(info.team > 1 || !(info.loc & (LOCATION_DECK | LOCATION_EXTRA))) return;`. The card is pushed into `player[team].extra_lists_main[duelist-1]` or `extra_lists_extra[duelist-1]` (lines 85-102).

**Responses and messages.**
- `OCG_DuelSetResponse` calls `duel::set_response`, which copies the raw bytes into `game_field->returns` (`duel.cpp:128-133`). The response itself carries no player id.
- `OCG_DuelGetMessage` returns a stream of `[u32 len][u8 MSG][payload]` records (`duel.cpp:103-112`).

**Queries.** All are limited to two players:
- `OCG_DuelQueryCount`: `if(team > 1) return 0;` (`ocgapi.cpp:142`).
- `OCG_DuelQueryLocation`: `if(info.con <= 1u && ...)` (`ocgapi.cpp:221`).
- `OCG_DuelQuery`: does **not** check `con`. It calls `get_field_card(info.con, ...)`, which indexes `player[playerid]` directly (`ocgapi.cpp:188,193`; `field.cpp:521-525`). Today a `con` of 2 or more is an out-of-bounds read.
- `OCG_DuelQueryField`: hard-coded `for(int playerid = 0; playerid < 2; ++playerid)` (`ocgapi.cpp:256`). `MSG_RELOAD_FIELD` has the same loop (`field.cpp:78-80`).

## 2. How tag and relay duelists are represented (verified)

- **One shared side per team.** A team is a single `player_info`: one LP value, one field, one Graveyard (GY) and one banished pile. Only the deck, hand and Extra Deck are per-duelist, through `extra_lists_main`, `extra_lists_hand`, `extra_lists_extra`, `extra_extra_p_count` and `tag_index` (`field.h:91,100-103`).
- **Tag swap.** `field::tag_swap` (`field.cpp:1129-1182`) disables field effects on the current lists, does `std::swap(player[p].list_main, player[p].extra_lists_main[player[p].tag_index])` (and the same for hand and Extra Deck), emits `MSG_TAG_SWAP {u8 player, u32 deck, u32 extra, u32 extra_p, u32 hand, u32 topcode, hand/extra codes...}`, then advances `tag_index = (tag_index + 1) % extra_lists_main.size()`.
- **When the swap happens.** It is called only at turn start for the turn player: `if(!is_flag(DUEL_RELAY) && infos.turn_id != 1) tag_swap(turn_player);` (`processor.cpp:3336-3337`). Scripts can also call it via `Duel.TagSwap` (`libduel.cpp:4110`).
- **Relay.** On a loss, `relay_check` sets `recharge` and `force_turn_end` (`field.cpp:1184-1190`). Then `next_player` swaps lists (`field.cpp:1192+`), driven from `processor.cpp:4693-4710` and `RefreshRelay`, which loops over `step` 0 and 1 only (`processor.cpp:5212-5223`).
- **Opening hands.** `Startup` deals hands to `p < 2` and to every extra list (`processor.cpp:5023-5042`).
- **Player constants.** `PLAYER_NONE 2` and `PLAYER_ALL 3` (`ocgapi_constants.h:376-377`), plus `PLAYER_EITHER 4` and `PLAYER_SELFDES 5` (`common.h:49,59`). Scripts mirror these (`cardscripts/constant.lua:241-244`). **Real seat indices 2 and 3 collide with these sentinels.**

**Conclusion (inference):** tag and relay are "N people, 2 sides". They cannot represent 4 independent fields or LP totals. FFA support must add sides, not reuse tag lists.

## 3. Who answers a prompt and who gets priority (verified)

- **The core.** Every `MSG_SELECT_*` and `MSG_ANNOUNCE_*` message writes the answering side as its first byte. Examples: `MSG_SELECT_BATTLECMD` writes `playerid` (`playerop.cpp:21-22`), `MSG_SELECT_CHAIN` writes `playerid` (`playerop.cpp:477-478`), and `MSG_SELECT_PLACE` writes `playerid` (`playerop.cpp:562-563`). The core never identifies a duelist within a team.
- **The server picks the duelist.**
  - `GetMessageReceivingTeam` returns `msg[1]`, or `msg[2]` for `MSG_HINT` (`multirole/.../CoreUtils.cpp:276-288`).
  - On `MSG_TAG_SWAP` it advances `s.currentPos[team] = (s.currentPos[team] + 1U) % (team==0 ? t0Count : t1Count)` (`Room/State/Dueling.cpp:338-342`).
  - The replier is `duelists[{team, s.currentPos[team]}]` (`Dueling.cpp:311-313`, `356-360`).
  - On a disconnect or timeout the winner is computed as `1U - s.replier->Position().first` (`Dueling.cpp:491`).
- **Priority is binary everywhere.**
  - Chain priority alternates as `emplace_process<Processors::QuickEffect>(false, 1 - priority)`.
  - The pass check is `infos.priorities[priority] = 1; if(!infos.priorities[0] || !infos.priorities[1]) ... QuickEffect(Step{1}, skip_freechain, 1 - priority)` (`processor.cpp:1147-1157`).
  - Turn rotation is `arg.turn_player = 1 - arg.turn_player;` (`processor.cpp:3619`).
  - There is no Battle Phase on turn 1: `infos.turn_id == 1` (`processor.cpp:1463`).
  - There is no draw on turn 1: `is_flag(DUEL_1ST_TURN_DRAW) || (infos.turn_id > 1)` (`processor.cpp:3381`).
  - The win check compares only `player[0]` and `player[1]` (`processor.cpp:4383+`).
- **Scale of the 2-player assumption** (grep counts; the first is an upper bound because the pattern also matches literals like `-1`):
  - Lines containing `1 - ` or `1-`: processor 114, field 50, operations 46, card 24, libduel 18, libcard 9, playerop 2, effect 2.
  - 27 `[2]` arrays in `field.h`, for example `turn_id_by_player[2]`, `priorities[2]`, `hint_timing[2]`, `summon_count[2]`, `battle_damage[2]` (`field.h:167,171,323-365`).
  - More 2-sized arrays elsewhere: `card.h:148,155-156`, `effect.h:46` (`hint_timing[2]` = self/opponent timing), `processor_unit.h:332`.
  - 89 occurrences of `if(playerid != 0 && playerid != 1)` in `libduel.cpp`, plus 3 in `libcard.cpp`.
  - 32 loops of the form `< 2`.
- **Scripts:** 9,446 card scripts use `1-tp` (grep count).

## 4. Message formats that would change for 4 players (verified formats, proposed changes)

| Message | Current format (source) | Problem | Proposal (N-mode only, gated by a flag bit) |
|---|---|---|---|
| `MSG_SELECT_PLACE` / `MSG_SELECT_DISFIELD` | `u8 player, u8 count, u32 flag`: bits 0-6 own monster zones, 8-15 own Spell/Trap zones, 16-31 the opponent's (`playerop.cpp:562-566`; the AI decode at `530-551` shows the bit layout). Response is `count × {u8 player, u8 loc, u8 seq}`, validated with `if(select_player > 1) return retry();` and `if(!isplayerid) to_check <<= 16;` (`playerop.cpp:577-593`). The client mirrors the halves: `if(selecting_player == 1) flag = flag << 16 \| flag >> 16;` (`duelclient.cpp:2236-2243`). | Only one opponent half. | New `MSG_SELECT_PLACE_N`: `u8 player, u8 count, u8 nplayers, u16 flag[nplayers]` (absolute seats, own seat included). Response stays `{u8 seat, loc, seq}`; widen the check to `seat < player_count`. The legacy message is still emitted when `player_count == 2`. |
| `MSG_FIELD_DISABLED` | `u32 dis = p0.disabled_location \| (p1.disabled_location << 16)`. Extra Monster Zone (EMZ) bits 5 and 6 are mirrored between p0 and p1 (`processor.cpp:4472-4477`, `4636-4642`). | Two halves; the EMZ mirror is hard-wired to the 0↔1 pair. | `u8 n, u32 dis[n]`, with the mirror done between each seat and the seat facing it (`facing[seat]`). |
| `MSG_RELOAD_FIELD` and `OCG_DuelQueryField` | `u32 duel_options`, then a fixed 2× per-player block (`field.cpp:78-105`, `ocgapi.cpp:255-283`) | Fixed 2 iterations. | In N-mode, write `u8 n` after `duel_options`, then n blocks. Clients detect it from the flag bit already in the first field. |
| `MSG_SELECT_CHAIN` | `u8 player, u8 spe, u8 forced, u32 hint_timing[player], u32 hint_timing[1-player]`, ... (`playerop.cpp:477-482`) | One "opponent timing". | No format change: send the OR of all opponents' timings. |
| `MSG_WIN` | `u8 winp, u8 reason`; `PLAYER_NONE` = draw (`processor.cpp:4712-4723`) | Elimination of one player is not representable. | New `MSG_PLAYER_ELIMINATED {u8 seat, u8 reason}`. `MSG_WIN` is sent only when the duel ends, and only to the last seat or team standing. |
| `MSG_HAND_RES` / `MSG_ROCK_PAPER_SCISSORS` | `u8 hand0 + (hand1 << 2)`; prompts are written with player 0, then 1 (`playerop.cpp:1132-1151`) | Two players packed into one byte. | `u8 n, u8 hands[n]` in N-mode. Alternatively, keep it pairwise (scripts call RPS between tp and 1-tp). |
| `MSG_START` (built by the server) | `u8 0, u32 lp, u32 lp, u16 t0Deck, u16 t0Extra, u16 t1Deck, u16 t1Extra` (`multirole/.../CoreUtils.cpp:440-447`); the client reads 2 players (`duelclient.cpp:1675-1688`) | Two players. | Add `u8 n` and n×(lp, deck, extra) behind a new protocol minor. |
| `MSG_NEW_TURN`, `MSG_TAG_SWAP`, `MSG_HINT`, `MSG_DRAW`, `MSG_DAMAGE`, ..., and `loc_info` (`duel.cpp:167-171`: `u8 controler`) | Single `u8` player | Format is fine for seats 0-3. | Unchanged, but seat values must not be 2 or 3 where the sentinels are used (for example `MSG_WIN` with `PLAYER_NONE`). In N-mode, move the wire sentinels to `0xFE`/`0xFF`. |
| `MSG_SWAP_GRAVE_DECK`, `MSG_SELECT_*` card lists | `u8` controller per card | Fine | Unchanged |

The client maps every player byte through `LocalPlayer(p) = isFirst ? p : 1 - p` (`game.cpp:3101-3103`). N-mode needs `(p - self + n) % n` plus 4-field rendering. The server's `currentPos[2]`, `retryCount[]`, `GetSwappedTeam` and `StripMessageForTeam` are all per-team-of-2.

## 5. Proposed API extension that keeps 2-player duels byte-compatible

Leave `OCG_DuelOptions` and `OCG_CreateDuel` untouched. Add a new export:
```c
#define DUEL_MULTIPLAYER 0x2000000000ULL           /* next free 64-bit flag (ocgapi_constants.h:428 is 0x1000000000) */
typedef struct OCG_DuelOptionsEx {
    uint32_t   size;            /* sizeof(OCG_DuelOptionsEx), for forward growth */
    uint8_t    player_count;    /* 2..4 seats */
    uint8_t    team_of[4];      /* win-condition teams; FFA = {0,1,2,3}; Team Battle = {0,1,0,1} */
    uint8_t    facing[4];       /* seat sharing the EMZ, Link Arrows and columns: {1,0,3,2} */
    uint8_t    turn_order[4];   /* clockwise seat order */
    OCG_Player players[4];
} OCG_DuelOptionsEx;
OCGAPI int OCG_CreateDuelEx(OCG_Duel*, const OCG_DuelOptions*, const OCG_DuelOptionsEx*); /* NULL ex == OCG_CreateDuel */
OCGAPI uint8_t OCG_DuelGetPlayerCount(OCG_Duel);
```
- `OCG_NewCardInfo.team` and `con`, and the `team`/`con` arguments of the query functions, are already `uint8_t`. Only the range checks at `ocgapi.cpp:85,142,221` change to `< player_count`, and a bounds check should be added to `OCG_DuelQuery` (this also fixes the existing out-of-bounds read).
- For a 2-player duel nothing changes on the wire, so the version can stay at 11.0. The client's export table (`ocgcore_functions.inl`, X-macro) must resolve `OCG_CreateDuelEx` optionally. If it is made mandatory, old core libraries fail to load. Bump the minor version only together with `SERVER_VERSION` and `CLIENT_VERSION`.
- Multirole's DLWrapper and HornetWrapper would need a parallel `CreateDuelEx` path, including Hornet IPC of the extra struct.

## Implications for a 4-player Domain mode

**Verified constraints**
- The core has exactly two sides (`std::array<player_info,2>`, binary priority and turn rotation).
- Tag and relay share one side per team, so they cannot model an FFA.
- Seat indices 2 and 3 collide with `PLAYER_NONE` and `PLAYER_ALL` in both C++ and Lua.
- Scripts hard-code `1-tp` (9,446 files) and 32-bit self/opponent zone masks (66 scripts call `SelectFieldZone`/`SelectDisableField`; 29 use `<<16`/`>>16`).
- Card scripts must not change.

**Design options**

1. **True N-seat core.** Use `player_info` for 4 seats and replace every `1 - x` with `opponent_of(x)`.
   - This breaks script semantics: `1-tp` would return the wrong seat, or `-1`/`-2` for seats 2 and 3, and zone-mask halves stop meaning anything.
   - It would require a Lua-facing translation layer anyway.
   - **Not viable** without changing scripts.
2. **"Perspective" core (recommended).** Store 4 seats internally, but expose to Lua and to all 2-sided internals a *pair* `(self, current opponent)` mapped to 0 and 1, so `1-tp` and the 16-bit halves keep working.
   - The "current opponent" is resolved per effect from the rulebook: the targeted opponent ("Target an opponent"), "that opponent" (the attacker or summoner), or the facing seat for zones and columns.
   - "All fields" or "all players" effects (Dark Hole, Skill Drain, Heavy Storm) need group and location queries that iterate every seat. That means `filter_field_card`, `get_field_card` and the `location`/`location2` pair semantics, where `location2` means "every opponent".
   - The chain gets an N-way priority ring (`priorities[N]`, `QuickEffect` → `next_in_turn_order`). Turn order follows `turn_order[]`. Neither turn 1 draws nor Battle Phase is allowed until the last seat's first turn.
   - On elimination, add `MSG_PLAYER_ELIMINATED`, cleanup per the rules digest, and turns that auto-pass.
3. **2-player only.** No API or message change at all. The existing rules digest notes that the multiplayer rulings reduce to the normal rules for 2 players.

**Effort estimate (option 2, inference)**
- **API:** `ocgapi.h`, `ocgapi_types.h`, `ocgapi.cpp` (new export plus 5 functions); `duel.cpp` and `field.cpp` constructors.
- **Core structures:** `field.h` (`player` → `std::array<player_info,4>` plus `player_count`; 27 `[2]` arrays to `[4]`), and `card.h`, `effect.h`, `processor_unit.h`.
- **Core logic:** about 250 `1 - x` sites, mostly in `processor.cpp`, `field.cpp` and `operations.cpp`. Each must be classified as next-in-turn-order, facing, chosen-opponent or every-opponent.
- **Lua API:** 92 player validations in `libduel.cpp` and `libcard.cpp`, plus the new perspective mapping.
- **Messages:** 7 formats from section 4.
- **Client:** `duelclient.cpp` (109 message cases; about 10 change), `LocalPlayer`, and 4-field drawing.
- **Server:** Multirole `CoreUtils.cpp`, `Dueling.cpp`, `Context.hpp`, the replay format (`team0Count`/`team1Count` at `Replay.cpp:72-85`), and both core wrappers plus Hornet IPC.
- **Overall:** realistically 25-40 files and several thousand changed lines.

**Main risks**
1. Silent rules errors where `1 - x` should mean "every opponent" rather than "one opponent".
2. Sentinel collisions (`PLAYER_NONE`/`PLAYER_ALL`) leaking into scripts or the wire.
3. Zone and column logic (`get_linked_zone` mirrors only `1-playerid` halves, `field.cpp:856-875`) for non-facing seats.
4. ABI drift: Multirole's copy of the header is stale (version 9) and Hornet does a raw struct copy.
5. Replays and spectators, which assume 2 teams.
6. Determinism and test coverage: there are no 4-player test fixtures today.