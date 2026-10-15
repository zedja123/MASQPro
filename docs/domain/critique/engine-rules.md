1. **Blocker: effects registered in the DMZ are never removed when the DM leaves.**
   - Problem: §1.3.2 registers the DM's `EFFECT_SPSUMMON_PROC` and Pendulum `ACTIVATE` effects while it is in the DMZ (`in_dmz`). Nothing unregisters them when it leaves. `field::remove_card` returns at once for location 0 (field.cpp:208, `if (... || pcard->current.location == 0) return;`), so `cancel_field_effect()` never runs. `move_card` only calls `add_card` (field.cpp:397).
   - Scenario: a Pendulum DM is Normal Summoned from the DMZ. Its `ACTIVATE` entry stays in `effects.activate_effect`. `is_activateable` has no range check for `ACTIVATE` (effect.cpp:150-219), so IdleCommand lists "Activate" for the monster on the field. AddChain step 1 then picks `loc = LOCATION_SZONE`, because the card is not in the hand (processor.cpp:3675-3686), and moves it into a Spell/Trap zone.
   - Second effect: when the card later reaches a real range location, `apply_field_effect` emplaces it a second time into the field multimaps. `effects.indexer` keeps only one entry (field.cpp:1316), so `remove_effect` erases one copy and leaves a stale one: duplicate idle entries, and dangling pointers once the effect is reset.
   - Spec change: define two explicit transitions and flip `in_dmz` only between "cancel" and "apply":
     - **Leave:** in `MoveToField` step 2, before the move, call `target->cancel_field_effect()` while `in_dmz` is still true, then set `in_dmz=false`, then `move_card`.
     - **Enter:** in the DomainReturn move, call `remove_card` (cancels with the real location), set `in_dmz=true`, then `add_card(owner,0)`, then `enable_field_effect(true)`.
     - `add_effect`, `apply_field_effect` and `cancel_field_effect` must skip the hand `TRIGGER_O` exception (card.cpp:1632, 1645, 1777) for `in_dmz` cards.
     - In `OCG_DuelNewCard`, set `in_dmz` before `add_card`. Do not add a second "register effects" step.

2. **Blocker: after its first return, the DM sits face-up in the DMZ.**
   - Problem: `send_to` forces `pos = POS_FACEUP` for every destination except banished unless `ignore` is set (operations.cpp:327-328). §1.5's `send_to(..., POS_FACEDOWN)` therefore leaves the DM face-up. Effects:
     - ABC-Dragon Buster: `Fusion.ContactCon` requires `IsFacedown()`, so Contact Fusion fails.
     - Synchro, Xyz and Link Pendulum DMs: each procedure starts with `if c:IsType(TYPE_PENDULUM) and c:IsFaceup() then return false` (proc_synchro.lua:79, proc_xyz.lua:257, proc_link.lua:110), so they are rejected.
     - Fusion/Synchro/Xyz DMs: `get_rule_zone_fromex` allows any Main Monster Zone only when `is_position(POS_FACEDOWN)` (field.cpp:848). Otherwise they are limited to the Extra Monster Zone or linked zones.
     - Extra Deck Pendulum DMs: they pass `Pendulum.Filter`'s `IsFaceup() and IsType(TYPE_PENDULUM)` branch. The probe in `Pendulum.Operation`'s `GetMatchingGroup` then lets them be Pendulum Summoned from the DMZ, which the rules forbid.
   - Spec change: the return sets `current.position = POS_FACEDOWN` after the move (call `send_to` with `ignore=true`, or do it in the dedicated enter path). §1.1 should state "always POS_FACEDOWN at location 0".

3. **Major: leaving the DMZ is detected by "location 0", but location 0 is a transit state.**
   - Problem: `draw` (operations.cpp:440-455), `discard_deck` (5070-5080) and Xyz detach (`xyz_remove` sets location 0 at card.cpp:1617, then `move_card` calls `add_card`) all reach `add_card` with `current.location == 0`.
   - Scenario: the DM is shuffled in by Pot of Avarice, the return is declined, and the DM is drawn later. A hook placed "where a card leaves location 0 in move_card/add_card" (§1.4) would charge LP and emit `HINT_DMZ_REMOVE`. Tracking in `add_card` based on the current location would also miss Deck→hand and Deck→GY moves.
   - Message order: `MoveToField` step 2 creates `MSG_MOVE` before calling `move_card` (operations.cpp:5309-5314). Anything emitted inside `move_card` therefore lands after the move message, the opposite of §1.4's "HINT before MSG_MOVE".
   - Spec change:
     - Pay the cost, fix `previous.*` (location, controler, sequence 0, position, pzone=false) and emit `HINT_DMZ_REMOVE` in `MoveToField` step 2, keyed on `target->in_dmz`, before `new_message(MSG_MOVE)`.
     - Compute `dm_moved` from `previous.location` against the new location in `add_card` (that also covers draw and mill). Never set it when the destination is location 0.
     - Also handle `swap_deck_and_grave` (field.cpp:1032-1090), which bypasses `add_card`.
   - Separately: `LP < cost` at move time can still happen, because a summon procedure's own operation can pay LP between the check and the move. Specify "LP becomes max(0, lp−cost)" and send `MSG_LPUPDATE`/`PAY_LPCOST` with the actual amount.

4. **Major: every Xyz Summon of an Xyz DM crashes the client.**
   - Problem: materials are attached to the DM while it is still at location 0:
     - Idle summon: `SpSummonRule` step 3 runs the Xyz procedure's `Duel.Overlay` before the move in step 4 (operations.cpp:3062-3117).
     - Rank-Up-Magic Quick Chaos: `Duel.Overlay(sc,tc)` comes before `Duel.SpecialSummon` (c33252803.lua).
   - The material `MSG_MOVE` targets `(con, 0x80, 0, i)` (card.cpp:224). With §4's `GetCard(con,0,…)` those materials attach to `dmz[con]`. The DM's own `MSG_MOVE` then has `previous.location==0`, which creates a brand-new `ClientCard` (duelclient.cpp:3065-3070). `HINT_DMZ_REMOVE` deletes the old card, so the materials are orphaned. The next detach reads `olcard->overlayed[...]` on the new card and crashes.
   - Spec change: in the client's `previous.location==0` branch, if `dmz[previous.controler]` exists, move that `ClientCard` (keeping its materials) instead of creating one, and clear `dmz[...]`. The engine emits `HINT_DMZ_REMOVE` after the `MSG_MOVE`, and the client ignores it if the card already moved.

5. **Major: `summon.location` stays 0 for summons performed by card effects.**
   - Problem: §1.3 only virtualises `SummonRule`, `MonsterSet` and `SpSummonRule`. `field::special_summon` and `special_summon_step` set `summon.location = current.location` (operations.cpp:185, 224). A Fusion DM summoned by Polymerization, Instant Fusion, a Rank-Up-Magic or a Ritual Spell therefore fails `IsSummonLocation(LOCATION_EXTRA)`.
   - Effect: 37 official activity counters use `not c:IsSummonLocation(LOCATION_EXTRA) or …`, for example Artmage Peripeteia -Turmoil- (c17719582.lua:33). They do not count the DM, so their Extra Deck locks are bypassed.
   - Spec change: list operations.cpp:185, 224 and 3404 explicitly with `effective_location()`.

6. **Major: returning does not reset the card.**
   - Problem: `STATUS_PROC_COMPLETE` is cleared only for destination Hand or Deck (operations.cpp:4744-4750). The `RESET_TO*` resets are keyed on the new location, so a move to location 0 applies none of them.
   - Scenario: a Ritual or other revive-limited Main Deck DM is properly summoned, dies and returns. It keeps `PROC_COMPLETE`, so `is_can_be_special_summoned` skips the revive-limit block (card.cpp:3323). For example, a Ritual Pendulum DM becomes Pendulum Summonable from the DMZ even though it is not from the hand. Effects placed on the card in the GY also linger in the DMZ, such as Peaceful Burial's `EFFECT_CANNOT_TRIGGER`.
   - Spec change: on return, clear `STATUS_PROC_COMPLETE` and run `reset(RESET_TODECK, RESET_EVENT)`, as for Hand/Deck.

7. **Major: making `Card.IsLocation` virtual everywhere contradicts "Chain Energy must not apply".**
   - Problem: Chain Energy's `EFFECT_ACTIVATE_COST` target is `te:GetHandler():IsLocation(LOCATION_HAND)` (c79323590.lua:49-51). AddChain step 1 evaluates it while the Pendulum DM is still at location 0 (processor.cpp:3641-3650). With §1.3.4 the DM reports HAND, so its Pendulum Scale activation pays Chain Energy's cost.
   - Spec change: suspend virtual `IsLocation`/`GetLocation` while evaluating `EFFECT_ACTIVATE_COST` and `EFFECT_*_COST` target or cost functions. Alternatively, record explicitly that costs keyed on "from the hand" via `IsLocation` do apply.

8. **Major: extra Normal Summons cannot be used for the DM.**
   - Problem: `EFFECT_EXTRA_SUMMON_COUNT` is missing from §1.3.1's virtual `is_target` list. 73 official cards grant extra Normal Summons with `SetTargetRange(LOCATION_HAND|LOCATION_MZONE,0)`, for example Fire Formation - Tensu. Once the normal summon is used, `is_can_be_summoned` returns FALSE for the DM (card.cpp:3175).
   - Also: Mausoleum of the Emperor does not use `EFFECT_DECREASE_TRIBUTE`. It passes a SINGLE code-80921533 effect as the `peffect` argument, so it only needs the HAND branch.
   - Spec change: add `EFFECT_EXTRA_SUMMON_COUNT` to the list (or state that it is excluded on purpose), and fix the Mausoleum note.

9. **Major: the hook guard and the follow-up event are wrong.**
   - Problem 1: PhaseEvent case 0 runs again after every chain (case 3 restart, processor.cpp:505-510). A guard that runs DomainReturn "once per entry" would skip the prompt after an End Phase chain and push it into the next turn, after the draw. That breaks "right before the game state is open again".
   - Problem 2: by §1.5's own move-tracking rule, the return itself (destination location 0) sets `dm_moved` again.
   - Problem 3: `PointEvent(false,false,false)` with an empty chain opens a free-chain QuickEffect window (processor.cpp:841-846). Every return, even one with no triggers, would give both players a new priority window.
   - Spec change:
     - Drop the per-entry guard and rely on clearing `dm_moved` (with item 3, a move to location 0 never sets it).
     - Queue `PointEvent(false, true, false)` only when the return raised events.
     - Leave the Damage Step untouched (its processors never reach these case-0 hooks; verified).

10. **Minor: the §3a Pendulum scope needs an exact flag.**
    - The PROC_G condition is called directly by IdleCommand (processor.cpp:1549-1565), by `filter_spsummon_procedure_g` (card.cpp:2779+), and by `SpSummonRule` step 19+ through `ExecuteOperation`, which yields during `SelectUnselect`.
    - Spec change: set a counter around each of these. Only proc_pendulum.lua registers `EFFECT_SPSUMMON_PROC_G` (verified), so scoping to it is safe.

11. **Minor: the probe gate keys on the query's own side only.**
    - Problem: a query made by an opponent's effect on the DM owner's side can probe our DM.
    - Spec change: also require `core.reason_player == DM owner`.

12. **Minor: `enable_field_effect` relaxation is too broad.**
    - Spec change: relax it for `in_dmz` cards only, not for every card at location 0, so Skills and tokens are unchanged.

Verified as OK:
- Sangan, Exosister Elis (event `rp` = owner), Pot of Avarice, Monster Reborn or Toadally Awesome by the opponent (the "on field" check is enough), and banished face-down.
- Hand `TRIGGER_O` effects stay inert at location 0, because their link to the chain needs the raw `range & location` match (processor.cpp:1270, 697).
- Tyrant Neptune (`SPSUMMON_CONDITION`), Ghostrick Mummy, Instant Fusion's `GetLocationCountFromEx(…,c)` and Ultimate Offering work as written.