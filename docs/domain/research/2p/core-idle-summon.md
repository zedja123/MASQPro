# Research report: ocgcore summoning and idle commands, and a Deck Master at location 0

All paths below are under `/home/user/MASQPro/ocgcore/` unless marked otherwise. `processor.cpp`, `operations.cpp`, `card.cpp`, `effect.cpp`, `field.cpp` and `playerop.cpp` match `/home/user/zedja123/ygopro-core`. The one difference is a Synchro/Xyz message block in `operations.cpp` around lines 3143–3212.

Labels: **[V]** = I read it in the code. **[I]** = my inference.

## 1. How the idle command lists are built
`field::process(Processors::IdleCommand&)` starts at processor.cpp:1449. Case 0 builds every list for `infos.turn_player`.

- **Activatable (`select_chains`)** [V], processor.cpp:1501–1530. It walks the field effect tables: `effects.activate_effect`, `quick_o_effect` and `continuous_effect` for `EVENT_FREE_CHAIN`, plus every entry in `ignition_effect`. It calls `peffect->set_activate_location()` and then `is_activateable(turn_player, nil_event)`. Pendulum and Field Spell activations come from `activate_effect`. Only effects that were registered in the field tables can show up here (see §3).
- **Summonable** [V], processor.cpp:1531–1538. It only walks `list_hand` and `list_mzone` (the mzone part is for Gemini):
  ```cpp
  for(auto& pcard : player[infos.turn_player].list_hand)
      if(pcard->is_can_be_summoned(infos.turn_player, FALSE, nullptr, 0))
  ```
- **Special Summonable** [V], processor.cpp:1539–1569.
  - `filter_field_effect(EFFECT_SPSUMMON_PROC, &eset)` reads the field's `aura_effect` table and keeps effects where `is_available()` is true (field.cpp:1484–1493). The loop then requires `pcard->current.controler == infos.turn_player && pcard->is_special_summonable(infos.turn_player, 0)` (processor.cpp:1546).
  - `EFFECT_SPSUMMON_PROC_G` (Pendulum Summon) goes through the same table. The only test is the Lua `condition(e,c)` (processor.cpp:1549–1569).
- **Repositionable** [V], processor.cpp:1570–1575. Walks `list_mzone` only.
- **Monster Set / Spell-Trap Set** [V], processor.cpp:1576–1583. Walks `list_hand` only, calling `is_setable_mzone(...)` and `is_setable_szone(...)`.
- **Executing a choice** [V]:
  - case 5 → `summon(turn_player, target, nullptr, FALSE, 0)` (processor.cpp:1660)
  - case 6 → `special_summon_rule(turn_player, target, 0)`
  - case 8 → `mset(target->current.controler, ...)` (1719–1724)
  - case 9 → `SpellSet` (1725–1730)
- **Message to the client** [V], playerop.cpp:72–126. Each card is written as `code, current.controler, current.location, current.sequence`. A card at location 0 would be sent as `(con, 0, 0)`.

Checks used by those lists [V]:
- `card::is_summonable_card` (card.cpp:3092): the card must be a monster and not Ritual / SPSUMMON / Fusion / Synchro / Xyz / Link / Token / Trap-monster, and must not have `EFFECT_UNSUMMONABLE_CARD`.
- `card::is_can_be_summoned` (card.cpp:3167–3219):
  - Checks the summon count, `STATUS_FORBIDDEN` and `EFFECT_SUMMON_COST`.
  - Then branches on location. `LOCATION_MZONE` means Gemini. `LOCATION_HAND` checks `EFFECT_CANNOT_SUMMON` and then `filter_summon_procedure`.
  - **Any other location (including 0) skips the procedure checks and returns TRUE** (card.cpp:3194–3218).
- `card::is_setable_mzone` (card.cpp:3380): `if(current.location != LOCATION_HAND) return FALSE;` at card.cpp:3389.
- `card::is_special_summonable` (card.cpp:3299): checks monster type, `EFFECT_CANNOT_SPECIAL_SUMMON`, `FORBIDDEN` and `SPSUMMON_COST`, then calls `filter_spsummon_procedure`.

## 2. Normal / Tribute Summon and Set
- **`filter_summon_procedure`** (card.cpp:2546–2603) [V]:
  - If the card has any `EFFECT_LIMIT_SUMMON_PROC`, only those count. It returns -1 if one passes and -2 otherwise.
  - Otherwise it collects every passing `EFFECT_SUMMON_PROC`, then checks the ordinary summon: `is_player_can_summon`, unique-on-field, `get_summon_tribute_count`, and `check_tribute(this,min,max,nullptr,current.controler,zone)`.
  - Extra Normal Summons: when `summon_count >= get_summon_count_limit` and `!extra_summon`, it tries each `EFFECT_EXTRA_SUMMON_COUNT` value `{min_tribute, zone, releasable}` (2578–2598).
  - `check_summon_procedure` (2604–2644) checks the count limit, then calls `is_summonable(peffect,...)`, which runs the Lua `condition(e,c,minc,zone,relzone,exeff)` (3142–3165).
- **How Lua registers these procedures** [V], `cardscripts/proc_normal.lua:2–28`: `EFFECT_TYPE_SINGLE` with `EFFECT_SUMMON_PROC` or `EFFECT_LIMIT_SUMMON_PROC` and **no `SINGLE_RANGE`**. So their only location-related gate is `is_available()`, which requires `phandler->current.controler != PLAYER_NONE` (effect.cpp:50).
- **`Processors::SummonRule`** (operations.cpp:1775) [V]:
  - Step 0 only tests `current.location == LOCATION_MZONE` (Gemini) and treats every other location as "hand" (1788–1827).
  - Steps 1–8 handle choosing the procedure or extra summon, tributes, cost and operation. They never check the hand.
  - **The summon location is hard-coded**: `target->summon.location = LOCATION_HAND;` at operations.cpp:2088 and 2105.
  - Step 9 calls `move_to_field(target, sumplayer, targetplayer, LOCATION_MZONE, positions, FALSE, 0, zone)`.
- **`Processors::MonsterSet`** (operations.cpp:2432) [V]: `if(target->current.location != LOCATION_HAND) return TRUE;` at 2443. It also hard-codes `summon.location = LOCATION_HAND` (2627, 2674).

## 3. Special Summon procedures, range checks, and the Extra Deck
- **Registration** [V]: in `card::add_effect` (card.cpp:1775–1779), a FIELD effect is added to the field tables only when `peffect->in_range(this)` is true. There is one exception: hand `TRIGGER_O` effects that are not `EVENT_PHASE`. When a card moves, `apply_field_effect` / `cancel_field_effect` re-run the same test (card.cpp:1628–1654). `field::add_card` calls `apply_field_effect` (field.cpp:197). **Both functions return early when `current.controler == PLAYER_NONE`.**
- **`effect::in_range(card*)`** (effect.cpp:784–792) [V]: returns `pcard->current.is_location(real_range)`. The `loc_info::is_location` bit test is at card.h:60–74, so location 0 never matches.
- **`effect::is_available`** for FIELD effects (effect.cpp:88–110) [V] requires all of:
  - `controler != PLAYER_NONE`
  - `in_range(phandler)`
  - `STATUS_EFFECT_ENABLED`, unless the effect has `IMMEDIATELY_APPLY`
  - not forbidden and not disabled
- **`card::enable_field_effect`** starts with `if (current.location == 0) return;` (card.cpp:1658). So `STATUS_EFFECT_ENABLED` cannot be turned on at location 0 [V].
- **`filter_spsummon_procedure`** (card.cpp:2739–2776) [V]: walks the card's own `field_effect` map, not the field table. For each effect it checks `is_available() && check_count_limit`, then `is_spsummonable` (Lua `condition(e,c,must,only[,minc,maxc])`, card.cpp:3117), the zone from the value, and `is_player_can_spsummon`.
- **`Processors::SpSummonRule`** (operations.cpp:2993) [V]:
  - Step 0 re-runs `filter_spsummon_procedure` and `_g`.
  - Steps 1–3 run the Lua target, cost and operation.
  - Step 4 sets `target->summon.location = target->current.location` (3097) and calls `move_to_field(..., LOCATION_MZONE, ..., zone, TRUE)` (3117).
- **Procedure libraries** [V], all `SetType(EFFECT_TYPE_FIELD)`, `SetCode(EFFECT_SPSUMMON_PROC)`, `SetRange(LOCATION_EXTRA)`:
  - Synchro: proc_synchro.lua:44–48
  - Xyz: proc_xyz.lua:56–60
  - Link: proc_link.lua:11–19
  - Pendulum Summon: `EFFECT_SPSUMMON_PROC_G` with range `LOCATION_PZONE` (proc_pendulum.lua:12–20)
- **Extra Deck placement depends on the current location** [V]:
  - `field::get_useable_count`: `if(location == LOCATION_MZONE && pcard && pcard->current.location == LOCATION_EXTRA) return get_useable_count_fromex(...)` (field.cpp:661). The same test is in `get_spsummonable_count` (683).
  - Any other location goes to `get_tofield_count`, which masks out both Extra Monster Zones (`flag |= (1u<<5)|(1u<<6)`, field.cpp:725–726).
  - MoveToField step 0 uses `get_useable_count(target, ...)` (operations.cpp:~5200).
  - Group summons split the counts with `current.location != LOCATION_EXTRA` (operations.cpp:3432–3437, 3783–3788).
- **Lua conditions branch on `IsLocation(LOCATION_EXTRA)`** [V]:
  - proc_synchro.lua:457–458 and 869
  - proc_xyz.lua:23 and 171
  - If the card is not in the Extra Deck they fall back to `GetMZoneCount`.
  - Link always calls `GetLocationCountFromEx` (proc_link.lua:105).
  - `Card.IsLocation` reads `current.location` directly (libcard.cpp:1620).

## 4. Pendulum Spell activation from the hand
- **Registration** [V]: `EFFECT_TYPE_ACTIVATE`, `EVENT_FREE_CHAIN`, `SetRange(LOCATION_HAND)`, description 1160 (proc_pendulum.lua:27–33). It enters `effects.activate_effect` only while in range (§3).
- **`effect::is_activateable`** for ACTIVATE (effect.cpp:150–219) [V]:
  - Requires `handler->current.controler == playerid` and no unique-on-field conflict in the S/T zone.
  - Outside the S/T zone, for `TYPE_PENDULUM` it requires `is_location_useable(playerid, LOCATION_PZONE, 0||1)` (184–187).
  - The hand-only special codes (Traps / Quick-Play in hand) only apply `if(handler->current.location == LOCATION_HAND)`.
- **Placement**, `Processors::AddChain` step 1 (processor.cpp:3659–3688) [V]:
  ```cpp
  int32_t loc = LOCATION_SZONE;
  ... } else if(phandler->current.location == LOCATION_HAND) {
      if(phandler->data.type & TYPE_PENDULUM) loc = LOCATION_PZONE;
  ...
  move_to_field(phandler, phandler->current.controler, phandler->current.controler, loc, ...)
  ```
  If the card is not in the hand it goes to `LOCATION_SZONE` (not the Pendulum Zone), and it is moved for `current.controler`. `get_active_type` returns `TYPE_PENDULUM+TYPE_SPELL` for this activation (effect.cpp:819).

## 5. What happens to a card at location 0

**The default state at location 0** [V]:
- `field::remove_card` sets `controler = PLAYER_NONE; location = 0` (field.cpp:255–257).
- The card is in no `player[].list_*`, so `filter_field_card` / `GetFieldGroup` never return it (field.cpp:1660–1770).
- Precedent for a location-0 card that has a controller: `Duel.CreateToken` sets `current.location = 0; current.controler = playerid;` (libduel.cpp:400–401). Skills exile themselves to location 0 with `SendtoDeck(c,tp,-2,...)` (proc_skill.lua:164; libduel.cpp:485).

**Moving out of location 0 works** [V]:
- `field::move_card` skips `remove_card` when `current.location == 0` and calls `add_card` directly (field.cpp:276, 397).
- MoveToField has no location precondition.
- SpSummonRuleGroup step 21 only rejects non-monsters, cards in MZONE, unique conflicts and `CANNOT_SPECIAL_SUMMON` (operations.cpp:3363–3380).
- **Caveat:** because `remove_card` is skipped, `previous.*` is **not updated** when a card leaves location 0. It keeps stale values.

**What fails today, path by path** [V]:

| Path | Why it fails at location 0 |
|---|---|
| Idle Summon / Set | The lists only walk `list_hand`. MonsterSet and `is_setable_mzone` require HAND. |
| Summon itself | `EFFECT_SUMMON_PROC` and `check_tribute` need a controller (`is_available` at effect.cpp:50; `current.controler` at card.cpp:2589). |
| Special Summon procedure | The effect is not in `aura_effect`. `is_available` fails on controller, range and `EFFECT_ENABLED`. |
| Pendulum activation | Not in `activate_effect`, and AddChain would place the card in the S/T zone. |
| Pendulum Summon | The Lua gathers candidates with `Duel.GetFieldGroup(tp,loc,0)` and filters with `c:IsLocation(LOCATION_HAND)` (proc_pendulum.lua:47, 62–64, 79–83, 95–98). |
| Revive limit | `is_can_be_special_summoned` only applies `EFFECT_REVIVE_LIMIT` for GRAVE / REMOVED / SZONE / DECK / HAND / EXTRA / OVERLAY (card.cpp:3321–3330). At location 0 the limit is silently skipped. |

**Smallest change that would work** [I]: keep the Deck Master at location 0 but give it `controler = owner`, as tokens do. Add a per-card "virtual location" (`LOCATION_HAND` for a Main Deck monster, `LOCATION_EXTRA` for an Extra Deck monster) that only rule-level summon code consults:

1. `effect::in_range(card*)` (effect.cpp:784): return true for a Deck Master in the DMZ only when the virtual location is in the effect's range **and** the effect is either a FIELD `EFFECT_SPSUMMON_PROC` or an `EFFECT_TYPE_ACTIVATE` effect whose handler is `TYPE_PENDULUM`.
2. Make `enable_field_effect` (card.cpp:1658) and `apply_field_effect` / `cancel_field_effect` (card.cpp:1628–1654) work for the Deck Master. They must exclude the hand `TRIGGER_O` exception so hand-trap triggers are not registered.
3. Use the virtual location wherever the code tests `LOCATION_HAND` / `LOCATION_EXTRA`:
   - card.cpp:3195 and 3389
   - operations.cpp:2443
   - processor.cpp:3681
   - field.cpp:661 and 683
   - operations.cpp:3432–3437 and 3783–3788
   - card.cpp:3321–3332 (revive limit)
4. Add the Deck Master explicitly to the IdleCommand loops (processor.cpp:1531–1583). Summon and Set go through `is_can_be_summoned` / `is_setable_mzone`. Special Summon goes through `is_special_summonable`; the `aura_effect` route also works once step 2 is done.

## Implications for Domain

**Hook points (core):**
- IdleCommand list building (processor.cpp:1531–1583) and the message writer (playerop.cpp:72–126).
- `card::is_can_be_summoned`, `card::is_setable_mzone` and `Processors::MonsterSet` (operations.cpp:2443).
- `effect::in_range`, `card::enable_field_effect`, `card::apply_field_effect` / `cancel_field_effect`.
- `field::get_useable_count`, `field::get_spsummonable_count`, and the group-summon zone split.
- AddChain Pendulum Zone placement (processor.cpp:3681).
- `summon.location` assignments (operations.cpp:2088, 2105, 2627, 2674, 3097, 3404). These control what `IsSummonLocation` reports.
- `previous.*` bookkeeping in `field::move_card` (field.cpp:276).
- The 500 LP leave cost can go where the Deck Master is moved: SummonRule step 9, SpSummonRule step 4, SpSummonRuleGroup step 23, and AddChain step 1 [I].

**Risks:**
- **Pendulum Summon is chosen in Lua.** Without a change to `proc_pendulum.lua` (a shared library), or a new core API that injects the Deck Master into the candidate group, the Deck Master cannot be Pendulum Summoned from the DMZ.
- **Same problem for summoning effects.** Effect-based proper summons (Instant Fusion, Ritual Spells, Rank-Up-Magic) collect candidates through `GetMatchingGroup` over LOCATION_HAND / EXTRA, so they will not see the Deck Master either [I].
- **Location-based restrictions can be bypassed.** Opponent or self restrictions written as `c:IsLocation(LOCATION_EXTRA)`, for example Extra Deck locks via `EFFECT_CANNOT_SPECIAL_SUMMON` target functions, will not match a location-0 Deck Master. They also do not reach it through s/o_range (effect.cpp:440–455). That is correct for "cannot be affected" but wrong for player-wide locks. A possible fix is for `Card.IsLocation` / `GetLocation` (libcard.cpp:487, 1620) to report the virtual location for the Deck Master [I].
- **Single effects become live once a controller is set.** All of the Deck Master's non-SINGLE_RANGE single effects (stat changes, `CANNOT_SPECIAL_SUMMON`, `SPSUMMON_CONDITION`) start to apply (effect.cpp:47–51). That is needed for summon restrictions such as The Tyrant Neptune, but stat or other effects could leak.
- **`is_can_be_summoned` must not use its default branch.** For location 0 it currently returns TRUE without checking any procedure (card.cpp:3194–3218).
- **Corruption risk if the location is faked.** Temporarily setting `current.location` to HAND / EXTRA without list membership would corrupt the lists through `remove_card`, which erases by sequence (field.cpp:217–240). Use a separate virtual field, not real location values.
- **No free location bit.** `current.location` is `uint8_t` and bits 0x01–0x80 are all used (ocgapi_constants.h:12–19), so a real DMZ location needs a protocol change.
- **Wire protocol.** Idle and move messages will carry `(con, 0, 0)`, which the client (and possibly multirole's message filtering, not checked) must map to the DMZ. MSG_MOVE from location 0 is today's token path [I].
- **Duel flag bits.** `duel_options` is 64-bit and is in use up to 0x1000000000 (ocgapi_constants.h:391–429), so a `DUEL_DOMAIN` flag can take a free high bit.