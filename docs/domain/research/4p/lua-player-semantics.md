# Report: making 2-player card scripts work in a 4-player engine without editing them

## 1. How the engine represents players (verified)

**Two-player assumption is built in.**
- `field.h:400` declares `std::array<player_info,2> player;`. `field.h:167` declares `int16_t turn_id_by_player[2]`.
- `PLAYER_NONE 2` and `PLAYER_ALL 3` are defined at `ocgapi_constants.h:376-377`. Scripts also define `PLAYER_EITHER = 4 --Not defined by the core` at `constant.lua:243`.
- `libduel.cpp` contains 89 copies of the guard `if(playerid != 0 && playerid != 1)`. The same guard appears 3 times in libcard.cpp and 5 times in libgroup.cpp. When it fails the function `return 0`, so Lua gets `nil`. Examples: `GetLP` at :32-38, `Draw` :1147-1152, `Damage` :1161-1166, `Recover` :1182-1187, `GetLocationCount` :1685-1690, `SelectTarget` :2681.
- Some APIs have no guard at all. `GetDecktopGroup` indexes `pduel->game_field->player[playerid]` directly (libduel.cpp `GetDecktopGroup`, just after :2220). An out-of-range id there is a memory-safety bug, not just a `nil`.
- `SpecialSummon` rejects `sumplayer >= PLAYER_NONE` (:409) but passes the target player through unchecked (:411). `SendtoHand` accepts values up to `PLAYER_NONE` (:462), where `PLAYER_NONE` means "owner's hand".
- `Destroy` takes no player argument, only an optional reason player (:185).

**Self/opponent location pairs are a two-iteration loop that flips `self`.**
- `filter_matching_card` (used by GetMatchingGroup, IsExistingMatchingCard, Select*, IsExistingTarget) at `field.cpp:1605`: `for(uint32_t p = 0, location = location1; p < 2; ++p, location = location2, self = 1 - self)`.
- `filter_field_card` (GetFieldGroup and GetFieldGroupCount) at `field.cpp:1665`: same loop.
- `filter_affected_cards` and `filter_inrange_cards` at `field.cpp:1503-1520` and `:1553` also use `range = peffect->o_range; self = 1 - self;`.
- So the "o" side always means exactly one player, `1-self`.

**Continuous field effects (`SetTargetRange(s,o)`) already generalise to "all opponents" when deciding whether a card is affected.**
- `effect.cpp:452-457`: `if(pcard->current.controler == get_handler_player()) { if(!pcard->current.is_location(s_range)) return FALSE; } else { if(!pcard->current.is_location(o_range)) ...`
- `EFFECT_FLAG_PLAYER_TARGET` behaves the same way, at `effect.cpp:483-486`: `if(s_range && self == playerid) return TRUE; if(o_range && self != playerid) return TRUE;`.
- Only the enumeration that collects affected cards (`field.cpp:1503`) and `EFFECT_FLAG_ABSOLUTE_TARGET` are tied to two players.
- `SetAbsoluteRange` (41 files) swaps s and o when `playerid != 0` (`libeffect.cpp:88-101`), and `is_target` tests `controler == 0` (`effect.cpp:444-450`).
- `SetTargetRange` simply stores `s_range`/`o_range` and clears ABSOLUTE (`libeffect.cpp:81-87`).

**How scripts receive players.**
- `tp` is a plain Lua integer pushed with `add_param<LuaParam::INT>(triggering_player, true)`. The event fields `ep` and `rp` are pushed the same way (`processor.cpp:33-39` for cost; also :90-96 and :152-158).
- `chain` (`field.h:49-80`) holds `triggering_player`, `target_player` and `disable_player`, but has no field for "which opponent".
- `Duel.SetTargetPlayer` only stores `ch->target_player = playerid` (`libduel.cpp:2845-2852`).
- `Card.GetControler` and `GetOwner` push the raw id (`libcard.cpp:419-426`). `Card.IsControler` compares raw ids (`libcard.cpp:1600-1604`).
- Labels store raw integers (`libeffect.cpp:174-180`).
- Turn and priority order is hard-coded as `1 - infos.turn_player` in processor.cpp (lines 314, 482, 665, 765, 844, 905, 950, 1616, 1645, 1649). Counting simple `1 - `-style idioms in the engine sources: processor.cpp 133, operations.cpp 48, field.cpp 42, card.cpp 27, field.h 27, libduel.cpp 21.
- The condition of a continuous effect is evaluated once per effect and cached as a single flag: `status |= EFFECT_STATUS_AVAILABLE` at `effect.cpp:111-121`. There is no "relative to which opponent" parameter.

**Main consequence.** `1-tp` is plain Lua arithmetic, so the engine cannot intercept it. With 4 physical ids (0..3), `1-tp` gives -2..1. Any translation scheme therefore has to show scripts virtual ids, where `0` = self and `1` = the bound opponent B, and translate them to physical ids at every API boundary. A metatable trick (a proxy object for `tp` with `__sub`) does not work: in Lua, `__eq` only fires when both operands are tables, so `Duel.GetTurnPlayer()==tp` would silently become false.

## 2. Survey of the official scripts (verified counts)

Directory: `/home/user/zedja123/cardscripts/official`, 13,541 files.

| Pattern | Files | Occurrences |
|---|---|---|
| `1-tp` | 6030 | 10694 |
| `1-e:GetHandlerPlayer()` | 96 | 98 |
| `1-p` | 58 | 88 |
| `1-ep` | 10 | 10 |
| `1-rp` | 5 | 5 |
| `1-c:GetControler()` | 4 | 4 |
| `PLAYER_ALL` | 226 | 267 |
| `PLAYER_NONE` | 99 | 176 |
| `IsControler(tp)` | 3522 | 4156 |
| `IsControler(1-tp)` | 1653 | 1886 |
| `ConfirmCards(1-tp,` | 2406 | 2643 |
| `EFFECT_FLAG_PLAYER_TARGET` | 2314 | 2636 |
| `,tp,0,LOCATION` (opponent side only) | 2166 | 4495 |
| `,tp,LOCATION_x,LOCATION` (both sides) | 1976 | 4116 |
| `LOCATION_MZONE,LOCATION_MZONE` | 1471 | 2631 |
| `LOCATION_ONFIELD,LOCATION_ONFIELD` | 812 | 1604 |
| `SetTargetRange(1,0)` | 1206 | 1341 |
| `SetTargetRange(0,` | 583 | 648 |
| `SetTargetRange(0,1)` | 297 | 326 |
| `SetTargetRange(1,1)` | 193 | 230 |
| `SetTargetPlayer(tp)` | 567 | 581 |
| `SetTargetPlayer(1-tp)` | 363 | 376 |
| `CHAININFO_TARGET_PLAYER` | 937 | 971 |
| `Damage(1-tp,` | 365 | 380 |
| `Damage(p,` | 375 | 387 |
| `IsTurnPlayer(tp)` | 539 | 587 |
| `IsTurnPlayer(1-tp)` | 500 | 527 |
| `Duel.GetTurnPlayer()~=tp` | 21 | 21 |
| `rp==1-tp` | 420 | 441 |
| `rp~=tp` | 168 | 170 |
| `ep==1-tp` | 212 | 218 |
| `ep~=tp` | 191 | 193 |
| `GetAttacker():IsControler(1-tp)` | 134 | 135 |
| `GetFieldGroupCount(tp,0,` | 378 | 486 |
| `GetFieldGroup(tp,0,` | 191 | 233 |
| `GetFieldGroupCount(1-tp,` | 38 | 49 |
| `GetLocationCount(1-tp,` | 167 | 251 |
| `,tp,1-tp,false,false` (summon to opponent's field) | 103 | 106 |
| `Draw(1-tp,` | 68 | 105 |
| `SelectMatchingCard(1-tp` | 64 | 70 |
| `SelectYesNo(1-tp` | 45 | 45 |
| `GetLP(1-tp)` | 97 | 123 |
| `SetLP(1-tp` | 25 | 25 |
| `Duel.Win` | 20 | 26 |
| `SetLabel(1-tp)` / `SetLabel(tp)` | 3 / 3 | |

The shared libraries also hard-code the two sides. Counts of `1-tp`-style idioms: utility.lua 14, proc_fusion.lua 11, cards_specific_functions.lua 6, proc_skill.lua 4, plus small counts in the other proc_* files.

**Typical patterns** (all checked against the scripts below):
- **Both sides queried:** `(tp,LOCATION_MZONE,LOCATION_MZONE)` (Dark Hole).
- **Opponent side only:** `(tp,0,LOCATION_MZONE)` (Raigeki).
- **Opponent as a raw player value:** `Damage(1-tp)` or `SetTargetPlayer(1-tp)` (Lazion).
- **Comparing counts:** `GetFieldGroupCount(...,LOCATION_MZONE,0)==0 and ...(0,LOCATION_MZONE)>0` (Cyber Dragon).
- **Opponent fixed by the event:** `IsTurnPlayer(1-tp)` on attack (Mirror Force), `rp==1-tp` (Masterflare Hyperion), `ep~=tp` (Lazion).
- **"Each player" marked as `PLAYER_ALL` in `SetOperationInfo`** (Dark World Dealings, Dragged Down into the Grave).

## 3. Proposed scheme: a bound opponent B with virtual ids (design, not yet implemented)

**Virtual-id view.** Every time Lua runs, the engine sets up a view `(S, B)`.
- S is the physical self (the triggering player, or the handler player).
- B is one physical opponent, or ALL (meaning all opponents).
- Ids going from the engine to Lua (tp, ep, rp, GetControler/GetOwner/GetTurnPlayer/GetSummonPlayer, GetHandlerPlayer, chain info) are mapped: S→0, B→1. Any other living player p→`16+p`, a sentinel that keeps that player's identity. In ALL mode every opponent maps to their own sentinel.
- Ids going from Lua to the engine are mapped back: 0→S, sentinel→p.
- Virtual 1 means B. In ALL mode, virtual 1 means "each opponent": counts are summed, actions are applied to each opponent (Draw, Damage, DiscardHand, ConfirmCards), and `IsControler(1)` means "any opponent".

**Location pairs `(s,o)`.**
- If both s and o are nonzero, o expands to every opponent. This covers Dark Hole and the rulebook's "any card on the field".
- If s is 0, o means B only.

**How B is chosen.**
- **Event binding:** for an effect activated by an event, B is the event's rp or ep (tried in that order) if that player is an opponent of S.
- **Enumeration:** otherwise the engine runs `condition` and `target(chk=0)` once per candidate opponent. The candidates are the opponents for which both checks pass. The effect can be activated if at least one candidate exists.
- **Prompt only when needed:** the engine records whether any API call during those checks resolved virtual 1 or a sentinel ("B touched"). If B was touched and there is more than one candidate, S chooses an opponent at activation; this is the rulebook's "Target an opponent". If there is exactly one candidate it is bound automatically. If B was never touched, no prompt is shown and B stays ALL.
- **Continuous effects, procedures (SPSUMMON_PROC), filters and continuous triggers:** B = ALL. For `condition` functions, the existential form can be computed by running the condition per opponent and OR-ing the results.
- **Mixed range bookkeeping:** `(s,o)` effect ranges stay as they are, because `effect.cpp:452` already reads "not controller ⇒ o".

### Card-by-card result (scripts read; outcomes are inferred, not tested)

| Card (file) | Key code | Result under the scheme |
|---|---|---|
| Raigeki (c12580477) | `GetMatchingGroup(aux.TRUE,tp,0,LOCATION_MZONE,nil)` | B touched in chk0, so S picks an opponent with monsters. Matches "Target an opponent". **OK** |
| Dark Hole (c53129443) | `tp,LOCATION_MZONE,LOCATION_MZONE` | Both sides, so all fields. B untouched, no prompt. **OK** |
| Heavy Storm (c19613556) | `tp,LOCATION_ONFIELD,LOCATION_ONFIELD,c` | All fields. **OK** |
| Torrential Tribute (c53582587) | summon events; `MZONE,MZONE` | All fields. **OK** |
| Mirror Force (c44095762) | `return Duel.IsTurnPlayer(1-tp)` and `tp,0,LOCATION_MZONE` | Only B = turn player (the attacker) passes. **OK** ("that opponent") |
| Nibiru (c27204311) | `Duel.GetFlagEffect(1-tp,id)>=5`; global `checkop` uses `RegisterFlagEffect(tc:GetSummonPlayer(),...)`, registered via `Duel.RegisterEffect(ge1,0)` | Sentinels keep the flag on the right player, and enumeration binds B to the player who summoned 5+. Release covers both sides (all fields). Token goes `SpecialSummonStep(token,0,tp,1-tp,...)` to that B. **OK**, provided sentinels round-trip. Note: `RegisterEffect(ge1,0)` puts the global effect's S at physical 0, which is harmless. |
| Lazion (c92435533) | `tdop: tp,0,LOCATION_GRAVE`; `damcon: return ep~=tp`; `SetTargetPlayer(1-tp)` | Draw trigger: event binding gives B = ep = the drawer. **OK.** Battle-phase GY shuffle: the condition `GetBattledGroupCount()>0` does not involve B, so every opponent passes and S chooses. The rulebook says B must be "the opponent it battled". **FAIL** |
| Trishula (c52687916) | chk0 `tp,0,HAND+ONFIELD+GRAVE`; `IsPlayerAffectedByEffect(1-tp,...)` | Prompt at activation. **OK** |
| Dangerous Machine Type-6 (c76895648) | `DiscardHand(1-tp…)`, `Draw(1-tp…)`, `tp,0,LOCATION_MZONE` only in the operation; chk0 returns `true` | B is never touched in chk0, so it stays ALL. The dice result would then apply to all opponents instead of "Target an opponent". **FAIL** |
| Cyber Dragon (c70095154) | `GetFieldGroupCount(c:GetControler(),0,LOCATION_MZONE)>0` in a summon procedure | With the existential OR, or the ALL sum, at least one opponent must control a monster. **OK** |
| Odd-Eyes Advent (c16494704) | `GetFieldGroupCount(tp,0,LOCATION_MZONE)>1` inside `extrafil` (Ritual proc) | Enumeration requires one opponent with 2+ monsters. **OK** with enumeration; would be wrong in ALL-sum mode (1+1 across two opponents would pass). |
| Intimidating Ore – Summonite (c91592030) | `Duel.SelectEffect(1-tp,...)` only in the operation | B is untouched at activation, so it is ALL at resolution, and asking "all opponents" to make one choice is undefined. Rulebook: "an opponent chosen on resolution". **FAIL** |
| Painful Choice (c74191942) | `local opp=1-tp; ConfirmCards(opp,g); g:Select(opp,1,1,nil)` | Same problem as Summonite. **FAIL** |
| Dragged Down into the Grave (c16435215) | each side picks from the other's hand; `PLAYER_ALL` in op-info | Needs a rotation (A picks from B's hand, B from C's, ...). One (S, B) pass cannot produce that. **FAIL** |
| Creature Swap (c31036355) | `SelectMatchingCard(1-tp,...,1-tp,LOCATION_MZONE...)`, `SwapControl` | Needs pass-to-next-player semantics. **FAIL** (a single specific B would give a valid 2-player swap, but not the rulebook result). |
| Interrupted Kaiju Slumber (c99330325) | `GetFieldGroup(tp,MZONE,MZONE)`; `GetLocationCount(1-tp…)`, `SpecialSummonStep(tc2,0,tp,1-tp…)` | B touched in chk0, so S picks the opponent whose field receives the Kaiju at activation. The rulebook allows "an opponent's field of their choice"; the choice comes at activation instead of resolution. **OK** (timing differs) |
| Skill Drain (c82732705) | `SetTargetRange(LOCATION_MZONE,LOCATION_MZONE)` | `effect.cpp:452` gives all fields; only the card enumeration at `field.cpp:1503` needs to cover N players. **OK** |
| Destiny HERO – Plasma (c83965310) | `e4:SetTargetRange(0,LOCATION_MZONE)` EFFECT_DISABLE; equip target `tp,0,LOCATION_MZONE`; equip limit `ec:IsControler(1-tp)` | Negation applies to all opponents. **OK.** Equip: prompt for an opponent, then the target. **OK** |
| Ultimate Conductor Tyranno (c18940556) | `EFFECT_ATTACK_ALL`; `Damage(1-tp,1000)` on battle start; Quick effect `tp,0,LOCATION_MZONE` | Attacking every opponent's monsters is a battle-engine change (EFFECT_ATTACK_ALL), not a scheme issue. Damage needs B = the attack target's controller, but chk0 does not touch B, so B stays ALL. **FAIL** unless "B = controller of the battle opponent" is added. Quick effect gets a prompt. **OK** |
| Relay Soul (c42776960) | `e3:SetLabel(1-tp)` … `Duel.Win(e:GetLabel(),WIN_REASON_RELAY_SOUL)` | The label stores virtual 1. **OK only if** `Duel.Win(p)` with p ≠ S is redefined as "S loses", which matches the rulebook ruling. |
| Archlord Kristya (c59509952) | `PLAYER_TARGET`, `SetTargetRange(1,1)` | `effect.cpp:483-486` gives all players. **OK** |
| Dark World Dealings (c74117290) | `Draw(1-tp,1)`, `DiscardHand(1-tp,...)`, `PLAYER_ALL` op-info | chk0 `IsPlayerCanDraw(1-tp,1)` touches B, so a single opponent would be picked; "each player" needs ALL. **FAIL**, unless `PLAYER_ALL` in SetOperationInfo forces ALL mode (226 files use `PLAYER_ALL`), in which case **OK** |
| Masterflare Hyperion (c63101468) | `rmcon: rp==1-tp`; `SelectTarget(...,tp,LOCATION_ONFIELD,LOCATION_ONFIELD...)` | Event binding gives B = rp. Target can be any player's card. **OK** |
| Evilswarm Exciton Knight (c46772449) | `IsTurnPlayer(1-tp) and IsBattlePhase()`; `GetFieldGroupCount(tp,0,HAND+ONFIELD)>…(tp,HAND+ONFIELD,0)`; destroy `ONFIELD,ONFIELD`; `SetTargetRange(0,1)` damage effects | Enumeration binds one B that must satisfy both clauses. Destroy covers all fields; "opponent takes no damage" covers all opponents. **OK.** Inference: tying both clauses to the same B is stricter than the rulebook's "one opponent suffices" if those clauses could be read independently. |
| Psychic End Punisher (c60465049) | `immcon: Duel.GetLP(tp)<=Duel.GetLP(1-tp)` (cached condition); `atkop: math.abs(GetLP(tp)-GetLP(1-tp))` | ATK gain: prompt for an opponent. **OK.** Immunity must be judged per affecting opponent, but the cached single-flag condition (`effect.cpp:111-121`) cannot do that. **FAIL** |

### Extra engine rules that would fix the failures
1. **Bind B at resolution when still needed.** If B is unbound at resolution and the operation touches it, have S choose an opponent before the operation runs. Fixes Summonite, Painful Choice and Dangerous Machine Type-6. Making individual APIs yield mid-call is impractical: most B-touching APIs are not `yieldk`, and filters run inside `check_matching`, a C-call boundary where yielding is impossible. So this needs prior knowledge that the operation will touch B, from a per-passcode table (see option C below).
2. **Treat `PLAYER_ALL` in `SetOperationInfo`/`SetPossibleOperationInfo` as "each player".** This forces ALL mode. Fixes Dark World Dealings.
3. **Battle binding:** B = controller of `GetAttackTarget()`/`GetAttacker()` or of the battled group. Fixes Tyranno's damage and Lazion's GY shuffle.
4. **Rotation mode for resource-passing cards:** run the operation once per pair (S, next player) in turn order. Not safe in general (S's own actions would repeat), so it needs per-card replacement logic. Fixes Dragged Down into the Grave and Creature Swap.
5. **Per-opponent continuous conditions:** evaluate `condition` with B = owner of the affecting effect, bypassing `EFFECT_STATUS_AVAILABLE`. Fixes Psychic End Punisher.
6. **`Duel.Win(p≠S)` means "S loses".** Fixes Relay Soul.

## Implications for a 4-player Domain mode

**Prerequisite (not covered in detail here).** The engine needs N-player state before any translation is possible: `std::array<player_info,N>`, `turn_id_by_player[N]`, every `p<2` loop and `1 - self` in field.cpp, the `1 - infos.turn_player` priority logic in processor.cpp, client and server protocol changes, player removal at 0 LP, and seating that decides who shares the Extra Monster Zone / Link arrows with whom.

**Design options:**

- **A. Projection with a bound opponent B (section 3)** — the recommended core.
  - Touches: a translation layer applied to every player argument and return value in libduel.cpp (~150 API functions; 89 already pass through the 0/1 guard, which is the natural hook), libcard.cpp (GetControler, GetOwner, IsControler, GetSummonPlayer, GetPreviousControler, ...), libeffect.cpp (GetHandlerPlayer, GetOwnerPlayer, SetAbsoluteRange), the `add_param` sites in processor.cpp (:33-39, :90-96, :152-158) and effect.cpp (:166-172, :311-403, :528-536).
  - Also: `filter_matching_card` and `filter_field_card` (`field.cpp:1605, 1665`) to handle the expansion of o to all opponents; a B field (plus a "B touched" bit) on `chain` (`field.h:49`); enumeration over opponents in the activation checks.
  - Size: about 6-8 files and a few hundred call sites, mostly mechanical.
  - Gets 15 of the 24 rulebook cards checked right outright (Lazion's draw trigger also works, though its GY shuffle fails), plus the Exciton Knight inference.
- **B. Option A plus the heuristic rules 2, 3 and 6.** Low cost (a few functions). Fixes Dark World Dealings, Tyranno and Relay Soul.
- **C. Option A plus a per-passcode override table** — a new data file the engine loads; no c*.lua edits. Entries: `bind=activation|resolution|event|battle|all|rotation`. Can be generated by a static scan (e.g. operation uses `1-tp` while chk0 does not) and then curated by hand. This is the only clean answer for Summonite, Painful Choice, Dangerous Machine Type-6, Psychic End Punisher, Dragged Down into the Grave and Creature Swap. Rotation cards would still need small replacement routines; flag to the user whether those count as "changing scripts".

**Main risks:**
- **Sentinel ids hitting unguarded or 0/1-guarded APIs.** Guarded APIs return `nil`, so a script doing `GetLP(x)>=n` raises a Lua error. Unguarded `player[playerid]` accesses (e.g. `GetDecktopGroup`) can crash the engine.
- **Raw comparisons in Lua inside ALL contexts.** `ep==1-tp` or `c:GetControler()==1-tp` in continuous code compares a sentinel with 1 and silently returns false.
- **Stored virtual ids.** `SetLabel(tp)`/`SetLabel(1-tp)` (6 files), flag values, and `e:SetLabel` used as a player later are read in a different view.
- **Symmetric queries that really meant "you and *this* opponent".** One example: `GetMZoneCount(1-tp,g,tp)` in Nibiru, where g spans all fields.
- **Cost of enumeration.** Running chk0 up to 3 times per effect per priority check multiplies Lua calls by about 3. It is also only correct if conditions are free of side effects, which they are by convention but not by enforcement.
- **Rulebook divergences.** The opponent is chosen at activation where the rulebook says resolution, and conditions with several clauses are tied to one B.
- **Library code.** utility.lua and the proc_* files (Fusion with 11 `1-tp` idioms, Skill, Workaround) need the same audit, because they run inside these views too.