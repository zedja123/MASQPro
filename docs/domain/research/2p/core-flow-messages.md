# ocgcore research for Domain: duel flow, open game state, LP, API and messages

Scope: I read the code and edited nothing. Paths are relative to `/home/user/MASQPro/ocgcore` unless another root is named. **[V]** means I checked it in code; **[I]** means it is my inference.

**Core identity [V]:** The core differs from `/home/user/zedja123/ygopro-core` in only two places:
- `ocgapi_constants.h`: MSG 200–211 (`MSG_RITUALSUMMONING`…`MSG_PENDULUMSUMMONED`) and `DUEL_MODE_GENESYS`.
- `operations.cpp:3143+`: emits those summoning messages.

## 1. Processor model and the open game state

**How the queue works [V]**
- There is no `add_process` and no `PROCESSOR_*` enum any more. A grep finds only a stale comment at `operations.cpp:307`.
- Processes are `std::variant` structs listed in `processor_unit.h:747-764`. Each derives from `Process<needs_answer>` (l.22) and holds a `uint16_t step`.
- Queueing uses `field.h:561-568`:
  ```cpp
  template<typename T, typename... Args>
  constexpr inline void emplace_process(Step step, Args&&... args) {
      Processors::emplace_variant<T>(core.subunits, step.step, ...);
  ```
- The loop is `processor_visit.cpp:9-33`. `core.units.splice(core.units.begin(), core.subunits);` runs first. If `process(arg)` returns TRUE the unit is popped. Otherwise `++arg.step` runs, and the call returns AWAITING when `needs_answer`.
- Units emplaced in one step run in emplace order, before the caller's next step. `arg.step = Processors::restart` (0xFFFF) wraps to step 0.
- The storage is `core.units`, `core.subunits` and `core.reserved` (`field.h:214-216`).
- **Adding a new processor** takes three edits: a struct in `processor_unit.h`, an entry in the `processors` variant (l.747), and `bool process(Processors::X&)` in `field.h`, next to the others at ~l.496-589.

**Where the turn player gets an open game state [V]**
- **Main Phase:** `IdleCommand` case 0 (`processor.cpp:1449-1585`) builds the lists and then calls `emplace_process<Processors::SelectIdleCmd>(infos.turn_player);` (l.1584). Continuous `EVENT_FREE_CHAIN` effects are offered here as ctype 5 (l.1515-1521), and l.1590-1594 resolves them through `solve_continuous`.
  - Every action returns to case 0 via `arg.step = Processors::restart`: chain solve (case 2, l.1660-1669), summon (case 5, l.1680), special summon (case 6), set, and so on.
- **Battle Phase:** `BattleCommand` case 0 (`processor.cpp:1788-1874`) calls `emplace_process<Processors::SelectBattleCmd>(infos.turn_player);` (l.1872).
- **Draw, Standby and End Phase:** `PhaseEvent` case 0 (`processor.cpp:297-450`) offers only chains: `emplace_process<Processors::SelectChain>(check_player, core.spe_effect[check_player], ...)` (l.446). Its case 3 solves the chain and case 4 runs `PointEvent`; both then restart to case 0 (l.501-520).
- **Turn processor:** `Turn` (`processor.cpp:3257+`) only sequences into these: `PhaseEvent(PHASE_DRAW)` at ~l.3391, `PhaseEvent(PHASE_STANDBY)` at ~l.3426, and `IdleCommand` at ~l.3452.

**Chain end and the trigger check [V]**
- `SolveChain` (`processor.cpp:4090`), case 12 (l.4337): `pduel->new_message(MSG_CHAIN_END); reset_chain();`
- Case 13 (l.4347-4359): `raise_event(nullptr, EVENT_CHAIN_END, ...); process_instant_event(); adjust_all();` and then `emplace_process<Processors::PointEvent>(arg.skip_trigger, ...)`.
- `PointEvent` (`processor.cpp:587`) runs in this order:
  - Step 0 splices `new_fchain` / `new_ochain` into the `_s` lists.
  - Steps 2–6 handle mandatory and optional triggers (SEGOC, with `AddChain` per pick).
  - Step 9 (l.838-851): if `core.current_chain.size()==0` it queues `QuickEffect(skip_freechain, infos.turn_player)` (the response window); otherwise `QuickEffect` for the opponent of the last link.
  - Step 10 (l.852-873): solves the chain if one exists (`emplace_process<Processors::SolveChain>`); otherwise `reset_chain(); returns.set<int32_t>(0, FALSE);`.
- Triggers are queued by `raise_event`/`raise_single_event` together with `process_instant_event()`/`process_single_event()` (l.1173-1320). These fill `core.new_fchain`, `new_ochain` and `delayed_*`.

**How a rule step prompts yes/no [V]**
- Rule steps already do this, for example `emplace_process<Processors::SelectYesNo>(infos.turn_player, 30);` (`processor.cpp:2200`), followed by `if(returns.at<int32_t>(0))` in the next step (l.2209).
- `SelectEffectYesNo(player, desc, pcard)` writes `MSG_SELECT_EFFECTYN` with code, `get_info_location()` and a `uint64` description (`playerop.cpp:160-182`).
- `SelectYesNo` writes `MSG_SELECT_YESNO` (`playerop.cpp:184-204`). With `DUEL_SIMPLE_AI`, player 1 is auto-answered 1.

**Recommended insertion point [I]** — a new `Processors::DomainReturn`:
- Hook it at the **top of `IdleCommand` case 0, `BattleCommand` case 0 and `PhaseEvent` case 0**: `if(domain && pending) { emplace DomainReturn; emplace PointEvent(false,false,false); arg.step = restart; return FALSE; }`.
- Why these points work: every return to them happens after `SolveChain`, the post-chain `PointEvent` and its response window have all finished. That matches "after all chain links resolved and no new chain started".
  - It also covers moves made outside chains, such as a Deck Master (DM) tributed for a summon or discarded for hand size.
  - The `PointEvent` queued after the return collects and solves triggers such as Exosister Elis. It solves them itself in step 10.
  - Then the processor restarts at case 0 and checks again. The flag was consumed, so it does not loop.
- `DomainReturn` steps: turn player, then the opponent → `SelectEffectYesNo(p, <new sysstring>, dm)` → on yes, `send_to(dm, nullptr, REASON_RULE, PLAYER_NONE, PLAYER_NONE, 0 /*loc*/, 0, POS_FACEUP)`.
- An alternative is `PointEvent` step 9 when `current_chain` is empty. That point also fires inside the Damage Step (BattleCommand calls `PointEvent` many times, e.g. l.2315, 2356), so it would need a phase gate.
- **"Moved" tracking [I]:** `fieldid` is not usable. It is bumped even for column moves (`field.cpp:343`) and in `add_card` (l.198). A per-player flag set in `field::move_card`/`remove_card` (`field.cpp:208-262, 267+`) is needed. It should be set only when `(old & (LOCATION_ONFIELD|LOCATION_OVERLAY))==0 || (new & same)==0`, and `swap_card` and control changes should be excluded.

## 2. Moving a card to and from location 0

**`Duel.SendtoDeck(c,nil,-2,REASON_RULE)` [V]**
- `libduel.cpp:485`: `uint16_t location = (sequence == -2) ? 0 : LOCATION_DECK;` then `send_to(..., location, sequence, POS_FACEUP)`.
- `send_to` (`operations.cpp:308-336`) forces `pos=POS_FACEUP` for any destination other than banished. With `playerid` nil, `p = owner`.
- `SendTo` processor (`operations.cpp:4505`):
  - **Step 0:** with `REASON_RULE` it skips all "can't be sent" checks and `operation_replace` (l.4514-4535).
  - **Step 3:** `destination_redirect(0)` returns 0 because there is no `else` branch for 0 (`card.cpp:2189-2203`). `leave_field_redirect` applies only from the field.
  - **Step 6 (l.4733-4785):** writes `MSG_MOVE` as code, then the previous `loc_info`. It then calls `move_card(playerid, pcard, 0, seq)`, which reaches `remove_card` and then `add_card(..., 0, ...)`. `is_location_useable` returns TRUE for location 0 (`field.cpp:621-655`). `add_card` sets `current.controler=playerid; current.location=0`, inserts into no list, and still does `apply_field_effect()` and `fieldid=field_id++` (`field.cpp:137-199`). The current `loc_info` written is `{p,0,0,POS_FACEUP}`, followed by the reason.
    - `remove_card` keeps `previous.*`, so `IsPreviousLocation` works (l.250-255).
    - If the card came from the GY, `param->leave_grave.insert` (l.4778).
  - **Step 9 (l.4840-4899):** applies no `RESET_TO*`, because `nloc` is 0. The only reset is `RESET_LEAVE` when it left the field. It raises `EVENT_LEAVE_FIELD` and `EVENT_LEAVE_GRAVE`, both single and group (l.4882, 4893).
  - **Step 10 (l.4900-4990):** raises no `EVENT_TO_DECK`, `TO_HAND` or similar, because they are keyed on `nloc`. It always raises `EVENT_MOVE` (single at l.4972, group at l.4988), and `EVENT_DISCARD`/`RELEASE`/`DESTROYED` only when the reason flags say so.
  - **Summary:** GY→0 raises `EVENT_LEAVE_GRAVE` and `EVENT_MOVE`. Hand, deck or banished →0 raises only `EVENT_MOVE`.
- **Client [V]:** for `MSG_MOVE` with `current.location==0`, the client fades out and deletes its `ClientCard` (`gframe/duelclient.cpp:3051+`, the `else if (current.location == 0)` branch).
- **Multirole [V]:** strips the code unless the card is public. `POS_FACEUP` counts as public (`multirole/src/Multirole/YGOPro/CoreUtils.cpp:293-301, 349-358`). It does not query location 0 (l.558-571).

**Moving from location 0 into the duel [V]**
- `MoveToField` step 2 writes `MSG_MOVE` with `get_info_location()` = `{controler,0,0,pos}` (`operations.cpp:5309-5317`, `card.cpp:222-227`).
- The client's `previous.location == 0` branch creates a new `ClientCard` and fades it in.
- `previous.location` becomes 0, so `IsPreviousLocation(HAND/EXTRA)` is false.
- **Risk [V/I]:** Extra Deck zone rules apply only when `pcard->current.location == LOCATION_EXTRA` (`field.cpp:659-660` → `get_useable_count_fromex`). A DM summoned from location 0 therefore escapes the EMZ and Link placement rules, and `SUMMON_LOCATION` checks will see 0.

## 3. LP as a rule cost

**`PayLPCost` (`operations.cpp:696-768`) [V]**
- It applies `EFFECT_LPCOST_CHANGE`, passing `core.reason_effect`.
- It offers `EFFECT_LPCOST_REPLACE` options.
- If cost > LP and there is no replacement, `select_options` is empty and it **silently returns without paying** (l.735-736).
- On payment: `player[p].lp -= cost; MSG_PAY_LPCOST; raise_event(EVENT_PAY_LPCOST)`.
- The pre-check is `field::check_lp_cost` (`field.cpp:2371-2395`), and it uses `core.reason_effect` the same way.

**Spell Economics [V]**
- It sets `EFFECT_LPCOST_CHANGE` to 0 only when `re and re:IsHasType(EFFECT_TYPE_ACTIVATE) and re:GetHandler():IsSpell() and not mustpay` (`cardscripts/official/c4259068.lua:20-26`).
- Gishki Photomirror sets the Lua global `mustpay=true` around its payment (`c9236985.lua:40-42`).
- The other `LPCOST_CHANGE` value functions (`c59913418`, `c61822419`, `c68392533`, `c74936480`, `c98301564`) all return `val` when `re` is nil or is not their own effect.

**Chain Energy model [V]**
- `EFFECT_SUMMON_COST` / `SPSUMMON_COST` operations are run as `ExecuteOperation(peffect, sumplayer)` (`operations.cpp:2020-2026`, 3049, 3375, 3755).
- `ExecuteOperation` sets `core.reason_effect = triggering_effect` (`processor.cpp:107-108`). So Chain Energy's `Duel.PayLPCost` has `re` = the cost effect, not the Spell, and Spell Economics does not apply.

**Options for Domain [I]**
- Queue `PayLPCost` with `core.reason_effect` explicitly saved and set to `nullptr` (or a dedicated rule effect), then restore it. Otherwise a DM summoned during Instant Fusion's resolution would have `re` = Instant Fusion, and Spell Economics would make the cost 0.
- Alternatively, subtract directly and write `MSG_PAY_LPCOST`. This skips `LPCOST_CHANGE` / `REPLACE` and `EVENT_PAY_LPCOST`.
- Use `check_lp_cost` (also with a nil `reason_effect`) to gate summonability.
- Do not use `damage()` (`operations.cpp:153`): it brings damage-change and reverse effects and `EVENT_DAMAGE`.
- Do not use `Debug.SetPlayerInfo` (`libdebug.cpp:97-111`): it sets LP and start LP and sends **no message**, so the client desyncs.
- `Duel.SetLP` writes `MSG_LPUPDATE` (`libduel.cpp:40-52`).

## 4. API

**`OCG_DuelOptions.flags` [V]**
- It is `uint64_t` (`ocgapi_types.h`).
- Used bits run 0x1 through 0x1000000000 (bit 36), at `ocgapi_constants.h:392-428`. **Bits 37–63 (`0x2000000000` and up) are free.**
- `is_flag` is `(core.duel_options & flag) == flag` (`field.cpp:1248`). Lua sees it through `Duel.IsDuelType` (`libduel.cpp:3568`).
- `constant.lua:957-958` mirrors the flags.
- Transport: `HostInfo.duel_flag_high/low` (`gframe/network.h:51,57`), and multirole `OrDuelFlags` (`LobbyListing.cpp:113`, `Replay.cpp:113`).
- **Caveat [V]:** `OCG_DuelQueryField` writes `insert_value<uint32_t>(query, core.duel_options)` (`ocgapi.cpp:251`), so high bits are truncated in field reloads.

**`OCG_DuelNewCard` (`ocgapi.cpp:62-104`) [V]**
- With `duelist==0`: rejects only when `popcnt(loc)>1`. If `is_location_useable` passes (always TRUE for location 0), it calls `add_card(con,pcard,loc,seq)`. **So loc=0 is accepted**: the card exists with `initial_effect` run (`duel.cpp:75-83`, `interpreter.cpp:~157`) and sits in no list.
- With `duelist>0`: only DECK or EXTRA.
- **Precedent [V]:** multirole adds the extra-rule cards with a zero-initialised `nci` (team 0, con 0, loc 0) (`multirole/src/Multirole/Room/State/Dueling.cpp:119-127`). These include `EXTRA_RULE_DECK_MASTER → 153999999` (l.54-69).

**Queries [V]**
- `OCG_DuelQuery` and `QueryLocation` require `popcnt(loc & ~OVERLAY)==1` (`ocgapi.cpp:183, 220`). `QueryField` covers only the lists (l.246-290).
- **A card at location 0 cannot be queried.** The client learns about it only from messages (`MSG_MOVE` code, `MSG_HINT`).

## 5. Messages

**Used IDs [V]** (`ocgapi_constants.h:207-314`; `common.h` defines none):
- 1–8, 10–16, 18–26, 30–42, 50, 53–56, 60–65, 70–76, 80, 81, 83, 90–97, 100–102, 110–114, 120–123, 130–133, 140–143, 160–165, 170, 180, 190, and 200–211 (MASQPro).
- Multirole also defines `MSG_ANNOUNCE_CARD_FILTER 144`.

**Unused IDs:** 0, 9, 17, 27–29, 43–49, 51–52, 57–59, 66–69, 77–79, 82, 84–89, 98–99, 103–109, 115–119, 124–129, 134–139, 145–159, 166–169, 171–179, 181–189, 191–199, 212–255.
- Multirole's `DoesMessageRequireAnswer` and `GetMessageDistributionType` (`CoreUtils.cpp:149-271`) whitelist known IDs. Unknown IDs go to everyone and **are never treated as prompts**, so any prompt must reuse `MSG_SELECT_*`.

**Skill hints [V]**
- `Duel.Hint` writes `MSG_HINT` as type u8, player u8, data u64 (`libduel.cpp:3054-3068`). The core has no special handling for type ≥200.
- `proc_skill.lua:1-4` defines `HINT_SKILL=200`, `HINT_SKILL_COVER=201`, `HINT_SKILL_FLIP=202`, `HINT_SKILL_REMOVE=203`.
- `SetSkillOp` does: `Duel.SendtoDeck(c,tp,-2,REASON_RULE)`, then `Hint(HINT_SKILL_COVER,p,coverid|(coverid<<32))`, then `Hint(HINT_SKILL,p,code)` (l.162-167).
- Client handling (`gframe/duelclient.cpp:1530-1604`):
  - It keeps one `dField.skills[player]` `ClientCard` at `LOCATION_SKILL` 0x400.
  - `FLIP` takes the code from the low 32 bits; bit 32 means face-up and bit 33 means face-down.
  - `REMOVE` fades and deletes the card.
  - Hints ≥200 are processed even during catch-up (l.1402).
- **Multirole [V]:** `HINT_SKILL` (200) goes **only to the owner's team**. Types 201–203 go to everyone (`CoreUtils.cpp:218-236`).
- **Existing Deck Master precedent [V]:** `cardscripts/unofficial/c153000000.lua:30-41` puts a DM "in the zone" with `SendtoDeck(c,nil,-2,REASON_RULE)` + `Hint(HINT_SKILL_FLIP,p,code|(1<<32))`, and removes it with `HINT_SKILL_REMOVE`. It summons through a FIELD+CONTINUOUS `EVENT_FREE_CHAIN` effect (l.92-98) and `Duel.SpecialSummon` from location 0.

## Implications for Domain

**Hook points**
1. **Return step:** add a new `Processors::DomainReturn`. Call it at the start of `IdleCommand`, `BattleCommand` and `PhaseEvent` case 0 (`processor.cpp:1451`, `1790`, `300`), gated by a new duel flag bit (≥ `0x2000000000`). Follow it with `PointEvent(false,false,false)` and restart.
   - Prompt with `SelectEffectYesNo` (DM in GY/hand/banished, so the location is valid). This needs a new system string.
   - Move with `send_to(..., dest 0, REASON_RULE)`. That gives `EVENT_LEAVE_GRAVE` / `EVENT_MOVE` for free, and `MSG_MOVE` → 0.
   - Then emit `HINT_SKILL_FLIP|(1<<32)` so both players see the DMZ, because `HINT_SKILL` is team-only in multirole.
2. **Tracking:** add a per-player `dm` pointer, a `moved` flag and a `return_count` to `player_info`. Set `moved` in `move_card`/`remove_card` on zone-type changes. Clear it whenever the prompt is evaluated, whatever the answer.
3. **Initial placement:** the client and server add the DM with `OCG_DuelNewCard` at loc 0, which is already supported. The core needs a way to identify it: either a new `OCG_NewCardInfo` convention, a flag, or a new API function.
4. **Cost:** pay through the `PayLPCost` processor with `core.reason_effect=nullptr` (a rule cost, which Spell Economics does not affect), or by subtracting directly with `MSG_PAY_LPCOST`. Pre-check with `check_lp_cost`, because `PayLPCost` silently pays nothing when LP is too low.

**Risks**
- **Stale effects:** cards moved to location 0 get no `RESET_TODECK`/`TOGRAVE`/`REMOVE` resets (`operations.cpp:4845-4859`), so flag effects can survive the move. `add_card` still runs `apply_field_effect` and `enable_field_effect(true)`, so the card's SINGLE effects without a range stay active in the DMZ.
- **Wrong summon semantics from location 0:** Extra Deck placement, `IsSummonLocation`, hand-only summon procedures and `previous.location==0` all break for DM summons. The summon rules need a real "DMZ" check: either a new location bit (popcnt-checked in the API/client/multirole) or special-casing in `get_useable_count`.
- **Cards at location 0 are unqueryable:** after a reconnect the client rebuilds the DMZ only from replayed hints. `QueryField` truncates the flags to 32 bits.
- **Prompts must reuse existing IDs:** new message IDs are not routed as prompts by multirole.
- **Simple AI:** `DUEL_SIMPLE_AI` auto-answers yes for player 1.
- **Edge cases [I], unhandled:**
  - `force_turn_end`, and `EFFECT_SKIP_*` phases (those jump to step 24).
  - Hooking at `PhaseEvent` case 0 fires once per priority pass, so it needs a guard.