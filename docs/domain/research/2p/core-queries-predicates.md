# ocgcore report: Lua card queries and proper-summon predicates for a location-0 Deck Master

All file:line references are to `/home/user/MASQPro/ocgcore`. Against `/home/user/zedja123/ygopro-core`, `field.cpp`, `libduel.cpp`, `libcard.cpp`, `card.cpp`, `effect.cpp` and `processor.cpp` are identical. Only `operations.cpp` differs (a 299-line diff), so its line numbers here are MASQPro's. **[V]** means I read it in the code. **[I]** means I inferred it and did not run it.

## 1. How the Lua queries build their candidate cards

**The central place is `field::filter_matching_card` (field.cpp:1572-1658) [V].** For each side it walks `player[self].list_*`. The `checkc` lambda (1575) applies `pexception`/`pexgroup`, then `pduel->lua->check_matching(pcard, findex, extraargs)` (only `if findex` is non-zero), then optionally `is_capable_be_effect_target`.

The Hand and Extra Deck branches are:
```cpp
if((location & LOCATION_EXTRA) && check_list(player[self].list_extra, checkc)) return TRUE;   // 1648
if((location & LOCATION_HAND)  && check_list(player[self].list_hand,  checkc)) return TRUE;   // 1650
```
The outer loop is `for(p=0, location=location1; p<2; ++p, location=location2, self=1-self)` (1601), so `p==0` is the `self` side.

Callers [V]:
- `GetMatchingGroup` (libduel.cpp:2273)
- `GetMatchingGroupCount` (2294; returns `pgroup->container.size()`)
- `GetFirstMatchingCard` (2315; uses `pret`, stops at the first hit)
- `IsExistingMatchingCard` (2338; `fcount`, stops early)
- `SelectMatchingCard` (2371; copies the group into `core.select_cards`)
- `DiscardHand` (1332; `LOCATION_HAND` only)
- The target variants `GetTargetCount`, `IsExistingTarget` and `SelectTarget` (≈2634, 2655, 2690; these pass `is_target=true`)

A `nil` filter gives `findex==0` (scriptlib.h:131-135: `if(lua_isnoneornil) return 0`), and then every card passes.

**`field::filter_field_card` (field.cpp:1660-1770) has no filter at all [V].** It backs `Duel.GetFieldGroup` (libduel.cpp:2198) and `GetFieldGroupCount` (2212):
```cpp
if(location & LOCATION_HAND){ pgroup->container.insert(list_hand.begin(), list_hand.end()); count += list_hand.size(); } // 1745
```

Other paths that read the lists directly and never go through the two functions above [V]:
- `filter_inrange_cards` (1529)
- `get_ritual_material` (1984), `get_fusion_material` (2019), `get_release_list` (1790)
- the Idle Command lists (processor.cpp:1531-1581)
- `GetExtraTopGroup`/`GetDecktopGroup` (libduel.cpp ≈2240)

Group methods (`Filter`, `IsExists`, etc., libgroup.cpp:139-768) only re-filter cards that are already in a group.

**One hook point:** inside `filter_matching_card`, right after lines 1648/1650 and only when `p==0`, offer the player's DM once if `location & (HAND|EXTRA)`. Going through `checkc` keeps exceptions, early exit and `pret` working.

## 2. Predicates in libcard.cpp and card.cpp, and where they check location

Lua entry points [V]:
- `IsSpecialSummonable` (libcard:1372) calls `is_special_summonable(core.reason_player, sumtype)`.
- `spsummonable_rule` (1382-1408) backs `IsSynchroSummonable`, `IsXyzSummonable`, `IsLinkSummonable` and `IsProcedureSummonable` (1409-1426). It checks `pcard->data.type & cardtype`, sets `core.must_use_mats`/`only_use_mats`, then calls `is_special_summonable`.
- `IsSummonable` (1427) calls `is_can_be_summoned`.
- `IsMSetable` (1438) calls `is_setable_mzone`.
- `IsCanBeSpecialSummoned` (1455) calls `is_can_be_special_summoned`.

How each core function treats a card at location 0:
- **`card::is_can_be_summoned`** (card.cpp:3167-3214) [V] branches only on `MZONE` (3184) and `HAND` (3193). At location 0 it skips the summon-procedure and tribute check and returns TRUE. So `IsSummonable` gives a false positive at location 0.
- **`card::is_setable_mzone`** (3380) [V] has `if(current.location != LOCATION_HAND) return FALSE;` (3388). It always returns FALSE at location 0.
- **`card::is_special_summonable`** (3299) [V] calls `filter_spsummon_procedure`. That walks the card's own `field_effect` and needs `peffect->is_available()` (2756), and `effect::is_available` requires `in_range(phandler)` for FIELD effects (effect.cpp:93). `in_range` is `pcard->current.is_location(real_range)` (effect.cpp:784-792). Procedures registered with `SetRange(LOCATION_EXTRA)` (proc_synchro.lua:48, proc_xyz.lua:60, proc_link.lua:19) or `LOCATION_HAND` are therefore never found at location 0. So **`IsSynchroSummonable`, `IsXyzSummonable`, `IsLinkSummonable` and `IsSpecialSummonable` are always false for a location-0 DM [I, from the code path].**
  - They are also missing from `effects.aura_effect`: `card::add_effect` and `apply_field_effect` only register effects that are `in_range` (card.cpp:≈1777, 1632). That is why the Idle Command `spsummonable_cards` (processor.cpp:1541 `filter_field_effect(EFFECT_SPSUMMON_PROC)`) never lists them.
- **`card::is_can_be_special_summoned`** (3316-3378) [V]:
  - Rejects only `MZONE` and face-down `REMOVED`.
  - The REVIVE_LIMIT block is location-masked:
    ```cpp
    if((current.location & (LOCATION_GRAVE|LOCATION_REMOVED|LOCATION_SZONE)) || (!nocheck && (current.location & (LOCATION_DECK|LOCATION_HAND)))) return FALSE; // 3324
    ```
    So location 0 **bypasses REVIVE_LIMIT**.
  - `EFFECT_SPSUMMON_CONDITION` (a SINGLE effect, available while `controler != PLAYER_NONE`, effect.cpp:50) and `is_player_can_spsummon` still apply.
  - The proper type arrives as given. Lua `SUMMON_TYPE_FUSION=0x43000000`, `RITUAL 0x45`, `SYNCHRO 0x46`, `XYZ 0x49`, `PENDULUM 0x4a`, `LINK 0x4c` (constant.lua:167-172; card.h:375-381). It is then OR'd with `SUMMON_TYPE_SPECIAL` (3340).
- **Material predicates** (`is_can_be_*_material`, card.cpp:3855-3981): not location-gated in a way that matters here. Material groups come from the real lists (§1), so the DM is never offered as material [V]. That matches "cannot be Tributed or discarded".
- **`EFFECT_SUMMON_PROC`**: in the procedure library and the sampled official scripts it is `EFFECT_TYPE_SINGLE` (proc_normal.lua:7), so it stays available at location 0 [V].
- **Field effects granted by other cards** (Mausoleum-style `SetTargetRange(LOCATION_HAND,…)`): these match through `effect::is_target` with `current.is_location(s_range)` (effect.cpp:452-457), so they do **not** reach a location-0 DM [V].

## 3. Effect-driven summons and the processors

- **`Duel.SpecialSummon` and `SpecialSummonStep`** (libduel.cpp:405/426) call `field::special_summon(_step)` (operations.cpp:175/≈200). This sets `summon.location = current.location` (185/224), i.e. 0. `SpSummonStep` case 0 (3714-3730) [V] has no location gate other than `MZONE`. Its REVIVE_LIMIT check uses masks `0x38`/`0x3` (3721), so location 0 passes.
  - **A location-0 card can be Special Summoned.** `Duel.CreateToken` already relies on this: it creates a card with `current.location = 0; current.controler = playerid` (libduel.cpp:389-403).
- **Zone placement keys off `current.location == LOCATION_EXTRA` [V]:**
  - `get_useable_count` (field.cpp:661) and `get_spsummonable_count` (683).
  - The `SpSummonStep` Extra Monster Zone (EMZ) split (operations.cpp:3781-3795) and the `SpSummonRule` group split (3432-3443).
  - The non-Extra path `get_tofield_count` always blocks the EMZ: `flag |= (1u<<5)|(1u<<6)` (field.cpp:726).
  - So **a location-0 Link DM could go to any Main Monster Zone (MMZ) with no arrow needed, and a Fusion/Synchro/Xyz DM could never use the EMZ [I]**.
  - Also, `get_rule_zone_fromex` lets Fusion/Synchro/Xyz monsters use any MMZ only if `pcard->is_position(POS_FACEDOWN)` (field.cpp:848).
- **`Duel.SynchroSummon`, `XyzSummon`, `LinkSummon` and `ProcedureSummon`** (libduel.cpp:309-322) go through `spsummon_rule`, then `special_summon_rule`, then the `SpSummonRule` processor. Case 0 (operations.cpp:2993-3022) calls `filter_spsummon_procedure`, which fails at location 0 for the in-range reason in §2, so the summon silently does nothing [I].
- **`Duel.Summon` / `SummonRule`** (operations.cpp:1775-1832) has no `HAND` check. Anything outside `MZONE` goes to `filter_summon_procedure`, so a Normal/Tribute Summon from location 0 should work [I].
- **`Duel.MSet` / `MonsterSet`** case 0 has `if(target->current.location != LOCATION_HAND) return TRUE;` (2443), so Setting from location 0 is impossible [V].
- **`Duel.PendulumSummon` / the Pendulum procedure in Lua** [V]:
  - `Pendulum.Condition` builds candidates with `Duel.GetFieldGroup(tp,loc,0)` (proc_pendulum.lua:63).
  - `Pendulum.Filter` requires `c:IsLocation(LOCATION_HAND) or (c:IsFaceup() and c:IsType(TYPE_PENDULUM))` (43).
  - The operation splits by `Filter(Card.IsLocation, …)` and `tc:IsLocation(LOCATION_HAND)` (90-140).
- **Lua helpers in the procedure libraries pick zone counters by `sc:IsLocation(LOCATION_EXTRA)`** [V]: proc_synchro.lua:457, 869, 1119; proc_xyz.lua:23, 171; proc_fusion.lua:228; proc_ritual.lua:202. At location 0 they fall back to `GetMZoneCount`. `Duel.GetLocationCountFromEx(tp,tp,g,c)` with a real card always uses the from-Extra rules (libduel.cpp:1783), so Instant Fusion (c1845204.lua:17) and Link (proc_link.lua:105) are fine [V].

## 4. Design check: "include the DM only if the filter returns true and a proper-summon predicate on the DM returned true"

**Where the hook goes:**
- In `filter_matching_card`, after the lists are scanned and only when:
  - `p==0`
  - `location & (HAND|EXTRA)` (for an Extra Deck DM only `EXTRA`, for a Main Deck DM only `HAND`)
  - `findex != 0`
  - `!is_target`
- Push a probe frame `{card* dm; bool hit=false}` onto a stack in `core`, run `checkc(dm)`, then pop. It must be a stack, because filters nest queries (Rank-Up-Magic Quick Chaos's `filter1` calls `IsExistingMatchingCard(s.filter2,…LOCATION_EXTRA…)`, c33252803.lua:20).
- Make `checkc` require `frame.hit` for the DM.
- In libcard, after each predicate computes its result, set `hit` when `self == top.dm && result`. For `IsCanBeSpecialSummoned`, also require `((sumtype|0x40000000)&0xff000000) ∈ {0x43,0x45,0x46,0x49,0x4a,0x4c}`. The predicates are:
  - `IsCanBeSpecialSummoned` (1455)
  - `spsummonable_rule` (1382, which covers Synchro, Xyz, Link and Procedure)
  - `IsSpecialSummonable` (1372)
  - `IsSummonable` (1427)
  - `IsMSetable` (1438)

**What stays out correctly [V/I]:**
- `GetFieldGroup(Count)` never sees the DM, so hand-size counts and costs are unaffected.
- `aux.TRUE` or `nil` filters don't set `hit`.
- `DiscardHand` filters (`IsDiscardable`) don't set `hit`.
- Target selection is excluded.
- Non-proper "Special Summon from hand/Deck/Extra Deck" filters use `IsCanBeSpecialSummoned(e,0,…)` and don't set `hit` (for example Underworld Ritual of Prediction's filter, c8428836.lua:34).
- Ritual.Filter evaluates `IsCanBeSpecialSummoned(e,SUMMON_TYPE_RITUAL…)` early (proc_ritual.lua:98), but the whole filter must still be true.
- A heuristic search of official/ found no script that checks `IsCanBeSpecialSummoned(e,SUMMON_TYPE_X…)` but summons with another type, and no line with an `or` next to a proper-type check [V, grep only].

**Leaks and breakage:**
1. **Pendulum is not reached by the gate.** Its condition uses `GetFieldGroup` and `IsLocation(HAND)`, so a DM is never Pendulum-Summonable unless `proc_pendulum.lua` changes or `Card.IsLocation` is virtualised.
2. **The gate fires, but the predicates are wrong at location 0:**
   - `IsSummonable` returns TRUE without checking tributes.
   - `IsMSetable` always returns FALSE.
   - `IsSynchroSummonable`, `IsXyzSummonable`, `IsLinkSummonable` and `IsSpecialSummonable` always return FALSE (procedures out of range).
   - `IsCanBeSpecialSummoned` ignores REVIVE_LIMIT. For example, a nomi monster such as one using EnableReviveLimit could be Pendulum Summoned, or effect-summoned with `nocheck=false`.
   - Ultimate Offering uses `Card.CanSummonOrSet = IsSummonable or IsMSetable` (utility.lua:619; c80604091.lua:46). It would see a false positive, and then `MSet` fails at operations.cpp:2443.
3. **Location-based restrictions are skipped:**
   - `AddMustFirstBe*Summoned` tests `not IsLocation(LOCATION_EXTRA) or …` (utility.lua:1313-1353), so a location-0 DM passes.
   - "Cannot Special Summon from the Extra Deck" locks test `c:IsLocation(LOCATION_EXTRA)` in their target functions [I, a common pattern: 178 official files match `c:IsLocation(LOCATION_EXTRA) and not`].
   - `IsSummonLocation(LOCATION_EXTRA)` (145 official files) sees `summon.location=0`, so activity counters and "if Summoned from the Extra Deck" effects behave differently.
4. **Zone placement** is wrong for Link and EMZ (§3).
5. **Selection messages** write `get_info_location()` = `{controler, 0, seq, pos}` (card.cpp:222-227; playerop.cpp:172, 315, 421). The client must render a location-0 card in a select list [I].
6. **A predicate true while the filter is true for some other reason:** a filter like `IsSynchroSummonable(nil) and X` used for a reveal or cost rather than a summon would still let the DM in. None was found, but this was not checked exhaustively [I].
7. **Opponent's DM:** offering it on `location2` would let opponent-side queries see it. Restrict the hook to `p==0` [I].

## Implications for Domain

- **H1 (gate).** Put it in `field::filter_matching_card` (field.cpp:1648-1650). Use a probe stack, apply it only when `p==0`, `findex != 0` and `!is_target`, and pass the DM through `checkc`. Do not touch `filter_field_card`, so plain counts stay clean.
- **H2 (predicate marks).** In libcard.cpp at 1372, 1382-1408, 1427, 1438 and 1455, mark `hit` on the top probe frame, masked to the proper summon types.
- **H3 (a card-level virtual location; needed for correctness).** Add a field such as `card::dmz_virtual_loc` (HAND for a Main Deck DM, EXTRA for an Extra Deck DM, and `POS_FACEDOWN` for the `get_rule_zone_fromex` check). Honour it in:
  - `effect::in_range` (effect.cpp:784), only for `EFFECT_SPSUMMON_PROC` and `_G`, so the DM's own activated or ignition effects stay off.
  - The REVIVE_LIMIT masks at card.cpp:3324 and operations.cpp:3721.
  - The location branches in `is_can_be_summoned` (3193) and `is_setable_mzone` (3388), and `MonsterSet` (operations.cpp:2443).
  - `get_useable_count` and `get_spsummonable_count` (field.cpp:661, 683) and the EMZ splits (operations.cpp:3432-3443, 3781-3795).
  - The `summon.location` assignments (operations.cpp:185, 224, 3404).
  - Lua `Card.IsLocation` (libcard.cpp:1620), so the procedure-library and extra-lock checks behave. Gate it so it only reports virtually while the DM is in the DMZ.
  - Field effects from other cards that target by range (effect.cpp:452) need an opt-in for Mausoleum-style summon procedures, without making the DM "affected" by other cards in general.
- **H4 (Idle Command).** Add the DM to `summonable_cards`, `msetable_cards` and `spsummonable_cards` (processor.cpp:1531-1581). Its Special Summon procedures are not in `aura_effect`.
- **H5 (Pendulum).** Unavoidable: either change `proc_pendulum.lua:63` to a gated `GetMatchingGroup`, or have the core include the DM in `filter_field_card` only during a `PROC_G` condition. The first is simpler.
- **Risks:**
  - The 500 LP DMZ cost must be paid at the summon processors, not in the probe.
  - Nested probes and Lua errors must always pop the frame (RAII).
  - Client rendering of location-0 select entries.
  - Testing should cover Instant Fusion, Rank-Up-Magic Quick Chaos, Ultimate Offering, Synchro/Xyz/Link via `Duel.*Summon`, Pendulum, a Link DM's zones, and a nomi DM with REVIVE_LIMIT.