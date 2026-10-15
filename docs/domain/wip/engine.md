# ENGINE report: Deck Master Zone (branch `domain-core`, `/home/user/wt/core`)

The engine part (§1 plus amendments E0–E8) is implemented and committed. All 42 engine scenario tests pass. 150 seeded non-Domain random duels are identical to the base core, and 300 random Domain duels finished with no crash or engine error. Nothing is pushed.

## Picking up the earlier work
The previous agent's uncommitted changes covered almost the whole engine, plus a test suite. I read the whole diff against the v2 spec and the critique in `critique/engine-rules.md`, rebuilt from clean, and ran the tests. All 34 of its scenarios passed, so I kept the work as it was. I committed it, deleted the stray `__pycache__` files (and added a `.gitignore`), added one missing `#include <optional>`, and wrote 8 more scenarios.

## What is implemented (files under `ocgcore/`)
- **State**
  - `field.h`: `player_info` gains `deck_master`, `dm_returns` and `dm_moved`. `processor` gains `dm_probes` (a probe stack), `dm_cost_check` and `dm_pendulum_proc`. RAII helpers `dm_scope` and `dm_probe_frame`.
  - `card.h/.cpp`: `in_dmz`, `dmz_virtual_location()`, `effective_location()`, `is_deck_master()`, `dmz_cost()`, `is_dmz_cost_payable()`.
- **Loading** (`ocgapi.cpp` `OCG_DuelNewCard`): accepts `LOCATION_DECK_MASTER` only in a `DUEL_DOMAIN` duel, for duelist 0, one per team, and only for a monster that is not a Token, Skill or Action card. `in_dmz` is set before `add_card`. The card sits at (owner, 0, `DMZ_SEQUENCE`), face-down.
- **Start of duel** (`processor.cpp` Startup case 0): one `HINT_DMZ` per player that has a Deck Master, before the opening hands are drawn.
- **Effects in the DMZ** (`card.cpp`, `effect.cpp`):
  - `effect::in_range` lets through only the DM's own FIELD `EFFECT_SPSUMMON_PROC` and the Pendulum activation of a Main Deck Pendulum monster.
  - `enable_field_effect` no longer bails out at location 0, but only for DMZ cards.
  - The hand `TRIGGER_O` exception is skipped for DMZ cards in `add_effect`, `remove_effect`, `apply_field_effect` and `cancel_field_effect`.
  - `is_activateable` blocks every other effect of the DM.
  - `effect::is_target` lets other cards' effects reach the DM, at its virtual location, only for `SUMMON_PROC`, `SET_PROC`, `LIMIT_SUMMON_PROC`, `LIMIT_SET_PROC`, `DECREASE_TRIBUTE`, `DECREASE_TRIBUTE_SET`, `EXTRA_SUMMON_COUNT` and `EXTRA_SET_COUNT`.
- **Normal/Tribute Summon and Set**:
  - The idle summon and Set lists include the DM.
  - `is_can_be_summoned` takes the hand branch for it, and `is_setable_mzone` and `MonsterSet` step 0 use `effective_location()`.
- **Proper summons by card effects**:
  - Probe gate in `field::filter_matching_card`. It applies on the querying player's own side, needs a non-nil filter, is never used for target queries, and needs `reason_player` to be the DM's owner (E8).
  - Predicate hits are recorded in `libcard.cpp`: `IsCanBeSpecialSummoned` (Ritual, Fusion, Synchro, Xyz, Link, and Pendulum for a hand-type DM only), `IsSpecialSummonable`, the `Is*Summonable` rules, `IsSummonable` and `IsMSetable`.
- **Pendulum Summon scope** (E7): a counter around every evaluation of a Pendulum Summon procedure (`EFFECT_SPSUMMON_PROC_G`): the idle list, `filter_spsummon_procedure_g`, `SpSummonRuleGroup`, `ExecuteOperation` and `is_player_can_procedure_summon_group`. While it is active, `filter_field_card` adds a Main Deck DM to `LOCATION_HAND`.
- **Location reporting** (E4): `Card.IsLocation` / `GetLocation` report the virtual location, except while a cost effect is being evaluated (`EFFECT_ACTIVATE_COST`, `SUMMON_COST`, `SPSUMMON_COST`, `MSET_COST`, `SSET_COST`, `FLIPSUMMON_COST`). That covers `ExecuteOperation`, `check_cost_condition`, `is_action_check` and the AddChain cost target.
- **Zones, revive limit, summon location**:
  - `get_useable_count`, `get_spsummonable_count`, and the Extra Monster Zone splits in `SpSummonStep` / `SpSummonRule` group use `effective_location()`.
  - So do the revive-limit checks (`is_can_be_special_summoned`, `SpSummonStep`) and every `summon.location` assignment (operations.cpp 185, 224, 3097, 3404).
  - AddChain places a DMZ Pendulum monster into the Pendulum Zone.
- **Leaving the DMZ** (`field::dmz_leave`, from `MoveToField` step 2, before the `MSG_MOVE`):
  - Pays the rule cost: LP becomes max(0, LP − cost), with `MSG_PAY_LPCOST` for the amount actually paid.
  - Calls `cancel_field_effect` while still in the DMZ, then fixes `previous.*`.
  - `HINT_DMZ_REMOVE` comes after the `MSG_MOVE`, and leaving never sets `dm_moved`.
- **Entering the DMZ and the return flow**:
  - `dm_moved` is computed in `add_card` from the previous location; `swap_deck_and_grave` is handled too.
  - `field::dmz_enter`: `remove_card`, clear `STATUS_PROC_COMPLETE`, reset as for a card sent to the Deck, `add_card(owner, 0)`, sequence 0xFF, face-down, then re-enable its effects.
  - `Processors::DomainReturn` runs at IdleCommand, BattleCommand and PhaseEvent case 0. It goes turn player first, asks with `SELECT_EFFECTYN` (desc 7112), and clears `dm_moved` for every player it examines.
  - On a return it sends `MSG_MOVE` then `HINT_DMZ` with the new count, raises `EVENT_LEAVE_GRAVE` / `EVENT_MOVE` (reason rule, reason player = owner), and queues `PointEvent(false, true, false)`.
- **Discard**: `Duel.DiscardHand` never takes the DM.

## Testing
```
export EDOPRO_CORE=/home/user/wt/core/ocgcore EDOPRO_CACHE=/tmp/claude-0/cache-core EDOPRO_CDB=/tmp/claude-0/genesys/BabelCDB
cd /home/user/wt/core
python3 tests/domain/build_core.py [--clean]   # 2 jobs, -Wall -Wextra -pedantic, fails on new warnings
python3 tests/domain/domain_scenarios.py       # -> 42/42 passed
python3 tests/domain/random_duels.py compare <base lib> $EDOPRO_CACHE/libocgcore.so 1-150   # -> 0 differing duels
python3 tests/domain/random_duels.py explore 1-300   # -> 0 duels with problems
```
- **Base library**: built from 7fbe9527 (base sources exported to the scratchpad), at `/tmp/claude-0/-home-user/748cb8ed-8740-5baf-a166-480b1bf66532/scratchpad/cache-base/libocgcore.so`.
- **Random Domain duels**: the 300 duels included 697 departures from the DMZ and 419 returns.
- **Other build**: I also ran `taskset -c 0,1 python3 $T/loadcheck.py setup --force` with `EDOPRO_CACHE=/tmp/claude-0/cache-core-lc`; the 42 scenarios pass on that library too.
- **Warnings**: a clean `-Wall -Wextra` build has no new warnings with g++, and the changed files are clean under clang++ syntax-only. The only warnings are the existing unused `message` variables in operations.cpp. The clang check briefly ran 8 jobs at once.

**All 42 scenarios pass**:
- **Loading and hints**: `HINT_DMZ` at start; DM ignored without the Domain flag; a Spell or a second DM ignored.
- **Normal Summon and Set**: Normal Summon (checks the move, hint order, free first summon and hand summon location); Tribute Summon; no summon without tributes; Set; no Spell/Trap Set; no-tribute procedure (Charging Gaia); Fire Formation - Tensu's extra Normal Summon; Ultimate Offering.
- **Own procedures**: Link (placed in an Extra Monster Zone); Xyz (materials attached at (0, 0x80, 0xFF)); Synchro (Black Rose Dragon); ABC-Dragon Buster Contact Fusion, and again after a return; Jester Confit; Cyber Dragon's condition.
- **Summons by effects**: Instant Fusion; Polymerization; Ritual Spell (Black Illusion Ritual); Rank-Up-Magic Quick Chaos.
- **Pendulum**: Scale activation from the DMZ; Pendulum Summon of a Main Deck DM; Tyrant Neptune excluded; Extra Deck Pendulum DM excluded; the full Pendulum cycle (no stale activation on the field, return from the Extra Deck face-down, re-activation for 500 LP).
- **What must not see the DM**: Waking the Dragon; Ancient Rules; Bystial Magnamhut's own effect; hand count and Graceful Charity discard.
- **Restrictions that must apply to it**: the "cannot Special Summon from the Extra Deck" lock.
- **Returning**: destroyed → prompt → return → next summon costs 500; declining keeps it in the GY with no later offer; offered again after it moves again; `EVENT_LEAVE_GRAVE` with reason player = owner; opponent's Monster Reborn gives no prompt; Sangan's trigger resolves before the prompt; bounced to hand and declined, then summoned from the hand for free.
- **Cost**: Spell Economics keeps the cost; Chain Energy charges neither the summon nor the Scale activation; not summonable with less LP than the cost.

## Deviations from the spec
1. `EFFECT_EXTRA_SET_COUNT` is also among the codes that reach the DM, to match `EXTRA_SUMMON_COUNT` for Sets.
2. If something other than `MoveToField` moves a DMZ card, `move_card` falls back to the leave without the cost. No current path does this; the fallback keeps the card out of limbo.
3. A Pendulum Scale activated from the DMZ does not get `STATUS_ACT_FROM_HAND`, because it was not activated from the hand.
4. The DM is matched by `info.team`; `info.con` is ignored.

## Known gaps
- `OCG_DuelQuery` and `OCG_DuelQueryField` do not return the DMZ card (location 0 is rejected). The client depends on `HINT_DMZ`, so reconnect or field reload has to re-create the zone some other way.
- Untested in real duels: Exosister Elis (only the event and its reason player are checked), Mausoleum of the Emperor, and a revive-limited Main Deck DM after a return.

## Commits
- cebdb720 Domain: Deck Master Zone in the engine
- 946a3f6f Domain: engine scenario tests for the Deck Master Zone
- 589b6ae4 Domain tests: Pendulum cycle, GY trigger order, second Contact Fusion, bounce, Ultimate Offering
- d56c7e4c Domain: include `<optional>` where it is used; Synchro and own-procedure tests

The tests are in `/home/user/wt/core/tests/domain/`: `domain_scenarios.py`, `random_duels.py` and `build_core.py`.