# How deeply ocgcore assumes exactly two players (MASQPro)

Everything below was checked in `/home/user/MASQPro/ocgcore` unless marked **[inference]**. Counts are `grep -c` and sometimes overcount, for example when `>>16` is not about zones. Nothing was edited.

## 1. Quantification

### Totals across all `*.cpp`/`*.h`

| Pattern | Hits |
|---|---|
| `\[2\]` | 85 |
| `1 - x` (`\b1 ?- ?[a-z_]`) | 193 |
| `PLAYER_ALL\|PLAYER_NONE` | 180 |
| `x != 0 && x != 1` (player validity checks) | 118 |
| `(p\|i\|playerid) < 2;` loops | 32 |
| `[0]…[1]` pair indexing on one line | 56 |
| `turn_player` | 227 |
| `>>16` / `<<16` (self/opponent zone halves, upper bound) | 86 |
| `player[` | 417 |

### Per file

| File | `[2]` | `1-x` | `PLAYER_ALL/NONE` | `!=0&&!=1` | `<2` loops | `infos.turn_player` | `current.controler` | `player[` | `>>16` |
|---|---|---|---|---|---|---|---|---|---|
| processor.cpp | 5 | 114 | 51 | 1 | 14 | 181 | 63 | 76 | 21 |
| field.cpp | 2 | 28 | 10 | 2 | 16 | 3 | 43 | 260 | 5 |
| operations.cpp | 27 | 19 | 40 | 0 | 1 | 14 | 72 | 30 | 14 |
| libduel.cpp | 4 | 14 | 37 | 103 | 5 | 3 | 18 | 35 | 0 |
| card.cpp | 12 | 12 | 11 | 0 | 3 | 2 | 50 | 5 | 13 |
| libcard.cpp | 0 | 4 | 16 | 3 | 0 | 2 | 14 | 1 | 5 |
| effect.cpp | 0 | 0 | 7 | 0 | 0 | 2 | 9 | 0 | 0 |
| playerop.cpp | 0 | 2 | 1 | 0 | 1 | 0 | 11 | 4 | 5 |
| field.h | 27 | – | 2 | – | – | – | – | – | – |

### Categories (verified)

**1. Player storage.** The per-player state is a fixed two-element array:
- `field.h:400` `std::array<player_info,2> player;`
- `player_info` (`field.h:82-115`) holds LP, the zone vectors and the tag/relay deck lists.

**2. Per-player core counters**, all `[2]`:
- `field.h:167` `turn_id_by_player[2]`; `:171` `priorities[2]`
- `:266` `control_adjust_set[2]`; `:270` `trap_monster_adjust_set[2]`; `:287` `unique_cards[2]`; `:291-292` `spsummon_once_map[2]` and `_rst[2]`; `:295` `pre_field[2]`
- `:323-326` `battle_damage[2]`, `summon_count[2]`, `extra_summon[2]`, `spe_effect[2]`
- `:344-348` `overdraw[2]`, `shuffle_hand_check[2]`, `shuffle_deck_check[2]`
- `:354-363` the seven `*_state_count[2]` arrays plus `battle_phase_count` and `battled_count`
- `:365` `hint_timing[2]`
- `:210` `action_value_t::player_amount[2]`, which backs every activity counter
- `card.h:148,155-156` `unique_pos[2]`, `spsummon_counter[2]`, `spsummon_counter_rst[2]`
- `processor_unit.h:332` `check_decktop_visibility[2]`

**3. Arrays that are not about players** (no change needed):
- `effect.h:41` `flag[2]` is a 64-bit flag word split in two.
- `card.h:91` `counter_map` `std::array<uint16_t,2>` holds two counter kinds.
- `effect.h:46` `hint_timing[2]` is self/opponent timing, so it is two-sided but relative to the effect.

**4. Count limits already support more players.** `field.cpp:1460`: `return static_cast<uint64_t>(code) << 32 | (hopt_index << 16 | flag << 8 | playerid);` gives the player 8 bits.

**5. Sentinel collision.** `ocgapi_constants.h:376-377`: `#define PLAYER_NONE 2` / `#define PLAYER_ALL 3`, mirrored in `cardscripts/constant.lua:241-244`, which also defines `PLAYER_EITHER=4` and `PLAYER_SELFDES=5`. The win sentinel is `5` (`field.h:301` `win_player{ 5 }`), and `field.h:462` has `add_effect(effect*, uint8_t owner_player = 2)`. **In a 4-player game, real player ids 2 and 3 would collide with these sentinels.**

**6. API and ABI.**
- `ocgapi_types.h:67-68` takes `OCG_Player team1; team2;`.
- `:81` `uint8_t team; /* either 0 or 1 */`; `ocgapi.cpp:85,142` reject `team > 1`; `ocgapi.cpp:256` loops `playerid < 2`.
- `card.h:26-31` `loc_info{uint8_t controler; …}` is 8 bits wide, so the message encoding itself does not limit N.
- The engine's tag/relay support swaps several players onto one field (`field.cpp:1192` `next_player`, `extra_lists_main`). It does not give anyone a separate field.

**7. Zone bitmasks.** Self occupies the low 16 bits and "the opponent" the high 16:
- `card.cpp:1389` `get_cards_in_zone(cset, linked_zone >> 16, 1 - p, …)`
- column mirroring at `card.cpp:1515`: `zones |= (1u << s) | (1u << (16 + (4 - s)));`
- SelectPlace flags at `playerop.cpp:519-545` (`0x7f0000` = opponent MZONE)

**8. Self/opponent location masks** (`self, location1, location2`). This is the core loop shape:
`field.cpp:1605` `for(uint32_t p = 0, location = location1; p < 2; ++p, location = location2, self = 1 - self)`.
The same shape appears at `field.cpp:1504-1553`, `1665`, `2060`, `2079` and `2416`. `field.cpp:1573,1661` hard-reject `self != 0 && self != 1`.

**9. Effect ranges already treat "opponent" as "anyone else".**
- `effect.cpp:451-457`: `if(pcard->current.controler == get_handler_player()) { …s_range… } else { …o_range… }`
- `effect.cpp:483-486`: `if(o_range && self != playerid) return TRUE;`
- So a continuous field effect with `o_range` (Skill Drain, Destiny HERO - Plasma) applies to every non-handler player as written. Only the card enumerator `filter_inrange_cards` (`field.cpp:1503-1520`, `self = 1 - self`) is limited to two players.

## 2. The 20 most structurally central sites

1. **`field.h:400`** `std::array<player_info,2> player;` The root. `player[` appears 417 times.
2. **`ocgapi_constants.h:376-377`** `PLAYER_NONE 2` / `PLAYER_ALL 3`: the sentinel collision.
3. **`processor.cpp:3620`** `arg.turn_player = 1 - arg.turn_player;` This is the entire turn rotation.
4. **`processor.cpp:3331-3333`** `++infos.turn_id_by_player[turn_player]; infos.turn_player = turn_player;`
5. **`processor.cpp:3381`** `if(is_flag(DUEL_1ST_TURN_DRAW) || (infos.turn_id > 1))` draws on turns after the first. The 4-player rule ("everyone except the first player draws on their first turn") needs a per-player `turn_id_by_player[p] > 1` check.
6. **`processor.cpp:1463`, `field.cpp:3285`** `infos.turn_id == 1` blocks the Battle Phase. Domain instead gives the first Battle Phase to the last player in the rotation.
7. **`processor.cpp:1143-1153`** chain response passing. After an activation it calls `QuickEffect(false, 1 - priority)`. On a pass it does `infos.priorities[priority] = 1; if(!infos.priorities[0] || !infos.priorities[1]) emplace_process<…QuickEffect>(Step{1}, skip_freechain, 1 - priority);`. The chain resolves when both players have passed in a row. This must become "next seat" plus "all N have passed consecutively".
8. **`processor.cpp:836-849`** opens the response window: `QuickEffect(skip_freechain, infos.turn_player)` or `1 - core.current_chain.back().triggering_player`.
9. **`processor.cpp:1637-1651`, `1884-1890`** idle and battle phase-change windows: `HINT_EVENT` to `1 - infos.turn_player`, then `priorities[1 - turn_player] = 0`.
10. **`processor.cpp:599-787`** SEGOC. Triggers are split into `new_fchain_s`/`new_ochain_s` and handled for the turn player, then `core.current_player = 1 - infos.turn_player` (`:665`, `:765`). This must loop over the seat order.
11. **`processor.cpp:1173-1360`** `process_instant_event`/`process_single_event`. Continuous triggers are split into `chain_list tp; chain_list ntp;`, with `ev.event_player == 0 || ev.event_player == 1` at `:1190`. `delayed_continuous_tp/ntp` (`field.h`; `processor.cpp:4068-4080`, `4262-4268`).
12. **`processor.cpp:2933-2960`** `calculate_battle_damage`. `std::array<bool,2> bd`; `battle_damage[0] = battle_damage[1] = 0`; `pa`/`pd` controllers. The pa/pd logic **[inference]** generalises if `pd` = the target's controller, and on a direct attack = the defending player.
13. **`processor.cpp:2464-2476`** pre-battle-damage events fire only for `turn_player` and `1 - turn_player`.
14. **`field.cpp:2440-2480`** `get_attack_target` builds candidates only from `player[1 - p].list_mzone` (`:2444`, `:2476`). Direct-attack eligibility checks the same single opponent.
15. **`processor.cpp:2007-2065`** attack-target UI: `SelectEffectYesNo(1 - infos.turn_player, 31, …)` asks about a direct attack, and Patrician-of-Darkness hands the selection to `1 - turn_player`. There is no way to pick which player to attack directly.
16. **`processor.cpp:4384-4433`** (in `break_effect`) and **`4658-4723`** (`Adjust`) decide the duel. Hard-coded `player[0].lp <= 0 && player[1].lp > 0 → winp = 1`, then `MSG_WIN` with one `winp`. N players need "eliminate player p" plus "last one standing". `libduel.cpp:1138-1142` (`Duel.Win`) uses `win_player==0 && playerid==1` and sets the draw sentinel `2`.
17. **`field.cpp:621-642`** `is_location_useable`. The Extra Monster Zone is shared by checking `player[1 - playerid]`'s mirrored zone `11 - sequence`. **`field.cpp:856-882`** `get_linked_zone` pulls Link arrows from `player[1 - playerid]` only (`zones |= ((oppzones & 0xffff) << 16) | (oppzones >> 16)`). Domain's "only the player in front of you" rule fits this exactly if `1 - p` becomes `facing(p)`.
18. **`card.cpp:1380-1425`, `1493-1534`** link, mutual-link and column helpers. Self low 16 bits, `1 - p` high 16 bits. Under "facing player only" these become `facing(p)`.
19. **`field.cpp:1572-1680`** `filter_matching_card`/`filter_field_card` back `Duel.GetMatchingGroup`, `IsExistingMatchingCard` and `GetFieldGroup`. They use the `s,o` loop with `self = 1 - self` and reject `self` outside 0/1.
20. **`processor.cpp:4732-4866`** Adjust loops (`for p<2`) for control adjustment, uniqueness and trap monsters. `:4784-4785`, `:4822-4823` `get_control(core.control_adjust_set[1 - infos.turn_player], …, infos.turn_player …)` swap control strictly between the two players.

Related sites: `libduel.cpp:35-255…` holds 103 `playerid != 0 && playerid != 1` guards, and `playerop.cpp:482` sends `message->write<uint32_t>(core.hint_timing[1 - playerid]);` in MSG_SELECT_CHAIN.

## 3. Script-side exposure (cardscripts, verified)

- 22,748 `c*.lua` files.
- 9,618 of them contain `1-tp`/`1-p`/`1-rp`/`1-ep`/`1-cp`, with 17,310 occurrences.
  - The most common calls passing `1-tp`: `Duel.ConfirmCards(1-tp` 3,721, `Duel.Damage(1-tp` 824, `Duel.GetLocationCount(1-tp` 395, `Duel.GetLP(1-tp` 248, `Duel.Draw(1-tp` 110.
- 7,782 files pass an opponent location mask (`,0,LOCATION_` or `,LOCATION_X,LOCATION_`).
- 4,717 files call `SetTargetRange(`.
- 402 files use `PLAYER_ALL`, 125 use `PLAYER_NONE`, and only 11 compare `tp` with a literal 0 or 1.
- Procedure libraries, which may be edited, contain 44 `1-x` sites: `utility.lua` 13, `proc_fusion.lua` 10, `cards_specific_functions.lua` 6, others 1-4 each.
- `tp` reaches Lua as a plain `LuaParam::INT` (`effect.cpp:166,311,320,…`). Player arguments are read as plain `lua_get<uint8_t>`; there are 236 such reads in libduel, and not all of them are players. The API is 241 libduel + 262 libcard + 57 libeffect + 45 libgroup functions. **Nothing in the type system marks an integer as a player.**

Consequence **[inference]**: with real ids 2 and 3, `1-tp` evaluates to -1 or -2, and every script breaks. Since the card scripts must not change, the scripts must keep seeing `tp ∈ {0,1}`.

## 4. N-player core designs

### (a) Generalise to N seats in the core
- Replace `[2]` with `std::array<…, MAX_PLAYERS>` (85 sites).
- Add `seat_order`, `alive[]`, `next_seat(p)`, `facing(p)` and `opponents(p)` helpers.
- Rewrite the 193 `1 - x` sites, the 32 two-iteration loops, SEGOC, priority passing (`priorities[N]` + `pass_count`), the win logic and attack targeting.
- Move `PLAYER_NONE`/`PLAYER_ALL` to e.g. `0xfe`/`0xff`. That also means editing `constant.lua`, which is not a `c*.lua` file.
- The s/o location loop becomes "self, then each opponent".
- The 118 Lua guards become `p < player_count`.
- **This alone does not keep scripts working:** `1-tp` still produces invalid ids. So (a) is necessary but not sufficient.

### (b) Per-activation "perspective" (Lua sees 0 = self, 1 = bound opponent)
Mapping at the Lua boundary:
- **Outgoing:** `tp`, `ep`, `rp`, the return values of `GetControler`/`GetOwner`/`GetTurnPlayer`, and so on.
- **Incoming:** every player argument and every `s,o` mask.
- The current perspective `(self, bound_opp)` is stored on the `chain` struct (`field.h:47-80`) and pushed while running condition, cost, target, operation and value callbacks.

Rules mapping onto that design **[inference]**:
- **"Target an opponent" (Raigeki, Trishula).** Choose `bound_opp` when the effect is activated, then let `1` map to it.
- **"That opponent" (Mirror Force → attacker, Nibiru → summoner).** Derive the binding from the event's `ep`/`rp` when that is an opponent.
- **Conditions where one opponent suffices (Cyber Dragon).** With no binding, `o` masks resolve to the union of all opponents' locations.
- **Continuous effects.** `effect::is_target` and `is_target_player` already treat `o_range` as "not the handler" (`effect.cpp:451-486`). They need no perspective; only `filter_inrange_cards` must iterate all opponents.
- **Real players 2 and 3 seen from a perspective in which they are neither self nor bound.** Map their cards' controller to `1`. `IsControler(1-tp)` then means "an opponent", which matches the rulebook's "all opponents" reading.
- **Resource passing (Creature Swap, Dragged Down).** "Next in turn order" can be the binding rule for those effects.

The cost is mapping roughly 500-600 player-valued Lua entry and exit points; that number is inferred from the 605 API functions, and the exact count needs an audit. In return, no card script changes.

### Verdict
(b) is less invasive **for scripts**, and it is the only way to keep 22,748 scripts unchanged. It still requires (a) underneath, because the core must actually hold four fields, rotate turns, pass priority and eliminate players. The realistic design is **(a) inside the core plus (b) at the Lua boundary**. Pure (a) breaks every script, and pure (b) has no four-field core to sit on.

## Implications for a 4-player Domain mode

**Design options**
1. **Two-player only.** No core changes. The ruleset reduces to standard one-opponent behaviour (verified by the rules digest premise).
2. **Full N-seat core (a) plus Lua perspective layer (b).** This is the only faithful 4-player free-for-all.
3. **Hybrid shortcut.** Keep the core two-sided and run 4 players as two facing pairs, reusing tag/relay (`next_player`, `field.cpp:1192`). **This is not Domain:** pairs would share one field, LP and deck rotation, which contradicts the rule that players are independent opponents. Use it only for Team Battle, and only if each player keeps a separate field, which the relay model does not provide.

**Effort for option 2 [inference]**

*Core*
- `field.h`: about 30 member declarations.
- `processor.cpp`: Turn (`3257-3625`), PointEvent/SEGOC (`587-940`), QuickEffect priority (`943-1160`), instant and single events (`1173-1400`), IdleCommand/BattleCommand windows, attack and damage (`1788-2960`), SolveChain continuous ordering (`4060-4300`), win checks (`4384-4433`, `4658-4723`), Adjust (`4732-4866`), Startup (`5009-5043`).
- `field.cpp`: zone usability, linked zone, filters, counters, attack target, about 60 functions.
- `card.cpp`: link, column and control helpers.
- `operations.cpp`: control swap, damage, draw and move-to-field, plus about 40 `PLAYER_*` sites.
- `effect.cpp`: `filter_inrange_cards` and the hint path.
- `libduel.cpp`, `libcard.cpp`, `libgroup.cpp`, `libeffect.cpp`, `libdebug.cpp`: 118 guards and every player argument/return value, for the perspective mapping.
- `ocgapi*`: N teams, `team > 1` checks.
- Player-elimination logic (new): remove chain links, banish owned cards, return borrowed cards, run skeleton turns.

*Lua support*
- Edit `constant.lua` for the sentinel values.
- Audit the 44 `1-x` sites in the procedure libraries.

*Client and server* (outside this area)
- Client: `gframe/client_field.h:30-36` `deck[2]…extra[2]`, plus 103 `LocalPlayer` uses in gframe.
- Server: multirole `team1`/`team2` hosting and the replay format.

*Size*: roughly 12-15 core files and 150-250 functions. Weeks of work, not days.

**Main risks**
- **Sentinel collision.** `PLAYER_NONE=2` and `PLAYER_ALL=3` equal real seat ids. Every literal `2`, `3` or `5` in core and Lua must be audited.
- **Perspective leaks.** Any API that returns a player id or a self/opponent zone bitmask (`>>16`, 86 sites) without mapping silently misbehaves. Delayed and continuous effects created in one perspective and run later need a stored binding.
- **Ambiguous binding.** Picking "that opponent" versus "target an opponent" automatically from event data works for Mirror Force and Nibiru, but some cards will need per-card overrides. Card scripts cannot change, so those overrides need a data table in the core or a procedure library.
- **Rules timing.** Priority order, SEGOC across four players and elimination mid-chain have no counterpart in the current two-player code, so they need fresh tests.
- **Client and server rework** is at least as large as the core change: four fields on screen, MSG location encoding, and replays.