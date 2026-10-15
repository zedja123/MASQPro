# Domain research: summon candidate gathering in the Lua procedure libraries

## 1. Procedure libraries: how summon candidates are found (verified)

**Fusion by effect** (`proc_fusion_spell.lua`)
- Polymerization-style spells call `Fusion.RegisterSummonEff` / `CreateSummonEff` (L123-141). The default location is `location=location or LOCATION_EXTRA` (L168, L312).
- The check uses `Duel.IsExistingMatchingCard(Fusion.SummonEffFilter,tp,location,0,1,nil,...)` (L251, and L267 for the Chain-material path).
- The operation uses `Duel.GetMatchingGroup(Fusion.SummonEffFilter,tp,location,0,nil,...)` (L396, L416).
- The predicate, L153-154:
  `return c:IsType(TYPE_FUSION) and (not fusfilter or fusfilter(c,tp)) and (nosummoncheck or c:IsCanBeSpecialSummoned(e,value,tp,sumlimit,false,sumpos)) and c:CheckFusionMaterial(mg,gc,chkf)`
  `value` is always OR'ed with `MATERIAL_FUSION` (`value = value|MATERIAL_FUSION`, L175 area). When `nosummoncheck` is set, no summon predicate runs at all.
- The summon itself is `Duel.SpecialSummonStep(tc,value,...)` (L541).
- Materials come from `Duel.GetFusionMaterial(tp)` (L188, L330). Lua already overrides that core function, L45-55: `Duel.GetFusionMaterial=(function() local oldfunc=... res:Merge(Duel.GetMatchingGroup(Card.IsHasEffect,tp,LOCATION_EXTRA,...))`. This is a working precedent for wrapping `Duel.*` in a shared library.
- `CheckFusionMaterial` reaches `Fusion.CheckMixGoal` (`proc_fusion.lua:228`), which picks the zone count by location: `(fc:IsLocation(LOCATION_EXTRA) and Duel.GetLocationCountFromEx(...) or Duel.GetMZoneCount(...))>0`.

**Ritual** (`proc_ritual.lua`)
- `Ritual.Filter` (L97-98) starts with `... or not c:IsCanBeSpecialSummoned(e,SUMMON_TYPE_RITUAL,tp,false,true,sumpos) then return false end`. It then runs the material check through `aux.SelectUnselectGroup`.
- Default location (L126-127): `Duel.IsDuelType(DUEL_EXTRA_DECK_RITUAL) and LOCATION_EXTRA or LOCATION_HAND`. This is a precedent for a duel flag changing a library's behaviour.
- Target uses `Duel.IsExistingMatchingCard(Ritual.Filter,tp,location,...)` (L161). Operation uses `Duel.SelectMatchingCard(tp,aux.NecroValleyFilter(Ritual.Filter),tp,location,...)` (L259), then `Duel.SpecialSummon(tc,SUMMON_TYPE_RITUAL,...)` (L319).
- The zone check in `Ritual.Check` (L202) also branches on `sc:IsLocation(LOCATION_EXTRA)`.
- Materials come from `Duel.GetRitualMaterial` (L135, L229).

**Pendulum** (`proc_pendulum.lua`)
- `EFFECT_SPSUMMON_PROC_G` sits on the scale with `SetRange(LOCATION_PZONE)` (L18-20).
- The Pendulum Spell activation is `EFFECT_TYPE_ACTIVATE` with `SetRange(LOCATION_HAND)` (L27-31).
- `Pendulum.Filter` (L43-45):
  `(c:IsLocation(LOCATION_HAND) or (c:IsFaceup() and c:IsType(TYPE_PENDULUM))) and (...scale...) and c:IsCanBeSpecialSummoned(e,SUMMON_TYPE_PENDULUM,tp,false,false) and not c:IsForbidden()`
- The condition does **not** use a matching query. It uses `g=Duel.GetFieldGroup(tp,loc,0)` and then `g:IsExists(Pendulum.Filter,...)` (L63-65).
- The operation uses `Duel.GetMatchingGroup(Pendulum.Filter,tp,loc,0,...)` (L88). It then splits zone budgets with `IsLocation(LOCATION_HAND)` and treats everything else as Extra (L90-91, L109-113, L138-142).

**Synchro, Xyz, Link and Contact Fusion procedures**
- All of these are `EFFECT_SPSUMMON_PROC` effects with `SetRange(LOCATION_EXTRA)`:
  - `proc_synchro.lua:46-48`, plus the Majestic (L768-770) and Dark (L1026-1028) variants
  - `proc_xyz.lua:58-60`
  - `proc_link.lua:17-19`
  - `proc_fusion.lua:897-899` (Contact Fusion)
- The Synchro, Xyz and Link conditions all start with `if c:IsType(TYPE_PENDULUM) and c:IsFaceup() then return false end` (`proc_synchro.lua:79`, `proc_xyz.lua:257,464`, `proc_link.lua:110`).
- `Fusion.ContactCon` requires `c:IsFacedown()` (`proc_fusion.lua:944-950`).
- Zone checks branch on `IsLocation(LOCATION_EXTRA)` in `proc_synchro.lua:457-458,869,1119` and `proc_xyz.lua:23,171`. Link always uses `GetLocationCountFromEx` (`proc_link.lua:105`).

**Synchro, Xyz or Link Summons performed by card effects** (counted in `official/`)
- `IsSynchroSummonable` appears in 78 files, `IsXyzSummonable` in 31, `IsLinkSummonable` in 21. They are passed straight in as filters, for example 16 times `Duel.GetMatchingGroup(Card.IsSynchroSummonable,tp,LOCATION_EXTRA,0,nil,c)`.
- Xyz-by-effect cards (Rank-Up-Magic style) use `IsCanBeSpecialSummoned(e,SUMMON_TYPE_XYZ` (82 files). The same pattern with `SUMMON_TYPE_SYNCHRO` appears in 32 files, `FUSION` in 21, `RITUAL` in 9 and `LINK` in 3.
- 226 files use the Fusion summon-effect helpers and 115 use the Ritual helpers.

**Normal Summon by effect**
- `Card.CanSummonOrSet` = `Card.IsSummonable(...) or Card.IsMSetable(...)` (`utility.lua:619-620`).
- `Duel.SummonOrSet` (`utility.lua:2644-2651`).
- `proc_normal.lua:2-28` registers a SINGLE effect (`EFFECT_SUMMON_PROC` / `EFFECT_LIMIT_SUMMON_PROC`) with no range set.

**Summon-type values** (`constant.lua:162-173`)
- The proper summon types are `SUMMON_TYPE_FUSION=0x43000000`, `RITUAL=0x45000000`, `SYNCHRO=0x46000000`, `XYZ=0x49000000`, `PENDULUM=0x4a000000` and `LINK=0x4c000000`.
- Custom values are small numbers. Examples: `SUMMON_WITH_MONSTER_REBORN = 1010` (`card_counter_constants.lua:164`) and Jester Confit's `SUMMON_TYPE_SPECIAL+1`.

## 2. Sample cards (verified, `official/` unless stated)

| Card (passcode) | How it finds cards | Would the DM be offered under the hook? |
|---|---|---|
| Polymerization (24094653) | `Fusion.RegisterSummonEff(c)` (L5), so EXTRA plus `SummonEffFilter` | Yes (FUSION) |
| Instant Fusion (1845204) | EXTRA; filter L17-18: `IsType(TYPE_FUSION) and GetLevel()<=5 and Duel.GetLocationCountFromEx(tp,tp,nil,c)>0 and IsCanBeSpecialSummoned(e,SUMMON_TYPE_FUSION,...) and c:CheckFusionMaterial()` | Yes. The zone count is evaluated *before* the predicate. |
| Underworld Ritual of Prediction (8428836) | `Ritual.AddProcGreater{...location=LOCATION_HAND|LOCATION_GRAVE}` (L7) | Yes (RITUAL) |
| Rank-Up-Magic Quick Chaos (33252803) | Nested query: `filter1` on MZONE calls `IsExistingMatchingCard(s.filter2,tp,LOCATION_EXTRA...)`; `filter2` L24-26 checks `IsCanBeSpecialSummoned(e,SUMMON_TYPE_XYZ,...)` | Yes. The DM is the receiver only inside the inner query. |
| Ultimate Offering (80604091) | `GetMatchingGroupCount(Card.CanSummonOrSet,tp,LOCATION_HAND|LOCATION_MZONE,...)` (L30, L37), `SelectMatchingCard` (L46), `Duel.SummonOrSet` (L48) | Yes (Normal Summon predicate) |
| Mausoleum of the Emperor (80921533) | HAND; `IsSummonableCard() and CanSummonOrSet(false,se)` plus `GetTributeRequirement` (L28-31) | Yes |
| Red-Eyes Darkness Metal Dragon (current script at `pre-errata/c88264978.lua`; `official/c88264988.lua` is the pre-errata version) | Its own built-in procedure: `EFFECT_SPSUMMON_PROC` with range HAND (L10). Its effect that summons a Dragon uses `IsCanBeSpecialSummoned(e,0,...)` on GRAVE|HAND (L57-67). | The effect: no (sumtype 0). The procedure is rule 5, so the core must accept range HAND for the DMZ. |
| Waking the Dragon (10813327) | DECK|EXTRA, `IsCanBeSpecialSummoned(e,0,...)` plus `IsLocation` branches (L26-27) | No (sumtype 0) |
| Bystial Magnamhut (33854624) | Its own Ignition/Quick effect with range HAND (L12) and `c:IsCanBeSpecialSummoned(e,0,...)` | Not a query. The core must stop the DM's own effects in the DMZ. |
| Jester Confit (8487449) | `EFFECT_SPSUMMON_PROC` range HAND, value 1 (L9-14) | Built-in procedure (rule 5) |
| Blue-Eyes Alternative White Dragon (38517737) | `EFFECT_SPSUMMON_PROC` range HAND; reveals BEWD from `GetMatchingGroup(s.spcfilter,tp,LOCATION_HAND...)` (L10-12, L46) | Built-in procedure. The DM itself is not BEWD, so it is unaffected by the reveal query. |
| ABC-Dragon Buster (1561110) | `Fusion.AddContactProc` (range EXTRA, needs `IsFacedown()`); summon condition `s.splimit` = `not e:GetHandler():IsLocation(LOCATION_EXTRA)` (L38-39) | Built-in procedure. Risk: outside EXTRA the summon condition returns true for any summon. |
| The Tyrant Neptune (88071625) | `EFFECT_SPSUMMON_CONDITION` `aux.FALSE` (L9-10); Tribute procedure from `proc_normal` | The Pendulum predicate returns false, so it is correctly excluded. |
| Ghostrick Mummy (97584500) | `EFFECT_CANNOT_SUMMON` SINGLE with a condition (L8-9) | `IsSummonable` false, `IsMSetable` true, which matches the ruling |
| Artifact Scythe (20292186) | `EFFECT_MONSTER_SSET` (L8-9); opponent lock `sumlimit` = `c:IsLocation(LOCATION_EXTRA)` (L60-61) | The core must block S/T Set from the DMZ. An Extra Deck DM escapes the lock unless EXTRA is spoofed. |
| Monster Reborn (83764718) | GRAVE only, `SUMMON_WITH_MONSTER_REBORN` (L16) | Not applicable. A summon by the opponent removes the return option (core). |
| Sangan (26202165) | Trigger on `EVENT_TO_GRAVE`; searches DECK (L29) | It goes on a chain before the DMZ-return window opens. |
| Exosister Elis (16474916) | `EVENT_LEAVE_GRAVE` with condition `rp==1-tp` (L23-26); EXTRA with `SUMMON_TYPE_XYZ` (L51-52) | The return to the DMZ must raise `EVENT_LEAVE_GRAVE` with `rp` = the DM's owner |
| Pot of Avarice (67169062) | GRAVE targets; counts `IsLocation(LOCATION_DECK|LOCATION_EXTRA)` (L33) | The DM is shuffled in, then may return. The return must pull it out of the Deck. |
| Toadally Awesome (90809975) | Summons the negated card to its own field: `rc:IsCanBeSpecialSummoned(e,0,tp,...)` (L101) | Summoned by the opponent, so no return option |
| Spell Economics (4259068) | `EFFECT_LPCOST_CHANGE`: `re and re:IsHasType(EFFECT_TYPE_ACTIVATE) and re:GetHandler():IsSpell() and not mustpay` returns 0 (L21) | **Risk:** if the DMZ cost goes through `PayLPCost` while `reason_effect` is a Spell's activation (Polymerization), Spell Economics makes it free. The global `mustpay` is the existing workaround (Gishki Photomirror `official/c9236985.lua:40-42`). |
| Chain Energy (79323590) | Summon, Special Summon, monster Set and S/T Set costs with `SetTargetRange(LOCATION_HAND,LOCATION_HAND)` (L26-38); activation cost when `te:GetHandler():IsLocation(LOCATION_HAND)` (L50) | A DM in the DMZ is not in the hand, so Chain Energy does not apply. If the DMZ were spoofed as HAND, it would apply. |

## 3. Metadata as a source of "mentioned" cards (verified counts; quality is a heuristic)

- Of 13,541 `official/` scripts:
  - `s.listed_names`: 3,192
  - `s.listed_series`: 5,600
  - `s.material_setcode`: 265 (e.g. `c10526791.lua:22 {SET_HERO,SET_ELEMENTAL_HERO}`)
  - `s.material=`: 44
  - `s.listed_card_types`: 54
  - race/attribute metadata (`s.material_race`/`attribute`): only 4
- What the 3,866 `listed_names` entries resolve to:
  - 1,214 are the card's own id (e.g. Magnamhut `s.listed_names={id}` L37; D-HERO Malicious)
  - 205 are Tokens
  - 855 are Spells/Traps
  - 1,488 are other monsters
  - 104 could not be resolved
- Coverage heuristic (my own script): monster texts contain 2,191 quoted names of other cards. 291 of them (about 13%) are not in `listed_names`, `material` or the script body. Examples: Legendary Knight Critias → "Legend of Heart"; Labyrinth Heavy Tank → Sanga/Kazejin/Suijin. Some misses are archetype names that equal a card name ("Ancient Gear", "Ice Barrier").
- `listed_series` includes the card's own archetype (Lo: `{SET_VOICELESS_VOICE}`), but no Attribute or Type mentions. For example, Lo's Warrior and Dragon mentions are absent.
- Archetype data:
  - `archetype_setcode_constants.lua` has 615 `SET_*` constants (614 distinct values).
  - The cdb `setcode` follows the OCG definitions: Chronicle Magician = 0x0, Cyber-Stein = 0x0, DMG = 0x30a2, D-HERO Malicious = 0xc008.
  - The core's `card.h:185-186` match is `(set_code & 0xfff)==(to_match & 0xfff) && (set_code & to_match)==set_code`, so querying the base code matches the whole family (HERO 0x8 matches 0xc008).
- **Caveat:** 14 base values have no archetype of their own and pool unrelated sub-archetypes:
  - 0x66: Magnet + "Warrior"/Symphonic Warrior
  - 0x178: Barians + Battleguard
  - 0xa2: Dark Magician + Magician Girl
  - 0xb7: Entities
  - 0x14d: Spiritual Arts
  - and others

  "Base = setcode & 0xfff" is wrong for these. The sub-code must be kept when the base has no constant.
- Conclusion (inferred): the metadata is a useful seed, not a curated source. Names and archetypes need a cdb text parse plus a reviewed override table. Attribute and Type mentions must come from text or a table.

## 4. Skill-card precedent (`proc_skill.lua`; verified)

- At `EVENT_STARTUP`, `Auxiliary.SetSkillOp` (L148-177) registers the skill's behaviour as **player** effects (`Duel.RegisterEffect(e1,e:GetHandlerPlayer())`).
- It then runs `Duel.SendtoDeck(c,tp,-2,REASON_RULE)`. In the core, -2 means location 0, i.e. out of play (`ocgcore/libduel.cpp:485`: `uint16_t location = (sequence == -2) ? 0 : LOCATION_DECK;`).
- It sends `Duel.Hint(HINT_SKILL_COVER,...)` and `Duel.Hint(HINT_SKILL,...)`, and draws a replacement if the card came from the hand.
- Hint ids are 200-203 (L1-4). The client builds a synthetic `ClientCard` with `location = LOCATION_SKILL` (`gframe/duelclient.cpp:1530-1600`, `client_field.h:157` `#define LOCATION_SKILL 0x400`; 0x400 is also `LOCATION_STZONE` in the Lua constants).
- `drawlessop` adjusts the starting hand through `Debug.SetPlayerInfo` (L29-47).
- Inferred: this is display only. A card at location 0 cannot be summoned, because procedure ranges and core queries never see it. The DMZ needs a real core location, but can reuse the hint/`ClientCard` approach for display.

## Implications for Domain

**Hook points**
1. **Detecting a proper-summon predicate.** Mark the DM as a candidate when, *with the DM as the receiver*, one of these returns true:
   - `IsCanBeSpecialSummoned` with `(sumtype & 0xff000000)` in {0x43, 0x45, 0x46, 0x49, 0x4a, 0x4c}<<24 (ignore the `MATERIAL_*` bits)
   - `IsSynchroSummonable`, `IsXyzSummonable` or `IsLinkSummonable`
   - `IsSummonable` or `IsMSetable` (Normal Summon/Set)

   Tracking must be per receiver card, because filters nest (RUM Quick Chaos). The `Fusion.SummonEffFilter` path with `nosummoncheck` evaluates no predicate, so it would miss.
2. **Queries to cover.** `Duel.GetMatchingGroup(Count)`, `IsExistingMatchingCard`, `SelectMatchingCard` and `GetFirstMatchingCard` whenever `LOCATION_HAND` or `LOCATION_EXTRA` is in the mask. This can be done in the core, or in Lua by following the `proc_fusion_spell.lua:45` override pattern and gating it on a new duel flag (precedent: `DUEL_EXTRA_DECK_RITUAL`).
3. **Pendulum needs special handling.** It gathers with `Duel.GetFieldGroup` and then `Group:IsExists`/`Match` (L63-65, L86), and both its filter and its zone accounting test `IsLocation(LOCATION_HAND)`. Patching `proc_pendulum.lua` (`Pendulum.Filter` and the ft1/ft2 split), or adding a core special case, looks unavoidable.
4. **Procedure ranges.** For a DM in the DMZ, the core must accept `EFFECT_SPSUMMON_PROC` and `EFFECT_SPSUMMON_PROC_G` effects with range HAND/EXTRA. This covers Synchro/Xyz/Link/Contact procedures, Jester Confit, BEAWD, REDMD, and the Pendulum activation `ACTIVATE` with range HAND. All other effects of the DM must stay inactive (Magnamhut).
5. **Zone counts.** The libraries call `IsLocation(LOCATION_EXTRA) ? GetLocationCountFromEx : GetMZoneCount` (fusion:228, ritual:202, synchro:457, xyz:23/171), and Instant Fusion calls `GetLocationCountFromEx(...,c)` directly. Either `IsLocation(LOCATION_EXTRA)` must be true for an Extra Deck DM in the DMZ, or EMZ/Link placement will be computed wrongly.

**Risks**
- **Position conflict.**
  - Synchro, Xyz and Link conditions reject a face-up Pendulum, and Contact Fusion needs face-down. So the DM should be face-down in core terms (publicly visible via the client).
  - But `Pendulum.Filter` needs `IsLocation(HAND)` or face-up.
- **Spoofing LOCATION_HAND/EXTRA globally leaks the DM into the wrong places:**
  - materials: `GetFusionMaterial` (hand) and `GetRitualMaterial`
  - discard and cost queries
  - Chain Energy's hand-only costs (L26, L50)
  - "cannot Special Summon from the Extra Deck" locks (Artifact Scythe L61)
  - summon conditions such as ABC-Dragon Buster's `not IsLocation(LOCATION_EXTRA)`

  Spoofing has to be scoped to proper-summon evaluation.
- **Spell Economics.** The DMZ LP cost must not go through `EFFECT_LPCOST_CHANGE` while `reason_effect` is a Spell. Use a rule-level LP payment, or set `mustpay=true` around it.
- **Return to the DMZ.** It must raise the normal leave events with `rp` = owner and `REASON_RULE` (Exosister Elis), pull the DM out of the Main or Extra Deck (Pot of Avarice), and be withheld when the opponent was the summoning player (Monster Reborn, Toadally Awesome).
- **Domain data.** `listed_names` and `listed_series` cover only about 87% of quoted names, contain self-references and Tokens, and have no Attribute or Type mentions. Base-archetype masking is wrong for the 14 pooled bases. A curated table is required.

Files used for the analysis (scratchpad): `/tmp/claude-0/-home-user/748cb8ed-8740-5baf-a166-480b1bf66532/scratchpad/an/meta.py`, `/tmp/claude-0/-home-user/748cb8ed-8740-5baf-a166-480b1bf66532/scratchpad/an/cov.py`