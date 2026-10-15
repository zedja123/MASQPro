# Domain Format v1.4 — rules digest (source: user's rulebook PDF)

Unofficial Yu-Gi-Oh! format. The rulebook targets 2+ players around a table; the EDOPro core
only supports two sides, so the port targets a 2-player duel (1v1). In a 2-player duel the
multiplayer rulings ("each player" -> "all players", "your opponent" -> "an opponent", etc.)
reduce to the normal rules and need no engine change.

## Deck building
- Exactly 1 Deck Master (DM): any Main Deck or Extra Deck MONSTER (never a Spell/Trap).
- Main Deck: exactly 60 cards (DM not counted).
- Extra Deck: up to 15 cards (DM not counted).
- Singleton: only 1 copy of each card across DM + Main + Extra.
  - Applies to "always treated as" cards too: Umi, A Legendary Ocean, Pacifis are all "Umi",
    so a deck can use only 1 of them. (Sea Stealth II only changes name on field/GY -> separate.)
- Every Main/Extra card must be within the DM's Domain.
- Banlist: "Forbidden Deck Masters" (currently none) and "Forbidden Cards" (currently none).
  Cards normally banned in TCG/OCG are allowed.

## Domain of a DM (card pool)
A monster is within the DM's domain if ANY of:
1. It is directly mentioned in the DM's effect box (card name). E.g. Incredible Ecclesia mentions Fallen of Albaz.
2. It belongs to the same archetype as the DM, or to an archetype mentioned in the DM's effect box.
   - Japanese (OCG) archetype definitions are used (e.g. most "Monarch" monsters are not Monarch archetype).
   - Archetypes inside "This card is not treated as ..." reminder text are removed (Cyber-Stein has no "Cyber").
   - The BASE archetype is used: Destiny HERO - Malicious -> the whole "HERO" archetype.
   - All archetypes of the DM count (Dark Magician Girl -> "Dark Magician" and "Magician Girl").
   - If the DM mentions a MONSTER that belongs to an archetype, that archetype is mentioned
     (Chronicle Magician mentions Dark Magician and Blue-Eyes White Dragon -> "Dark Magician" and "Blue-Eyes").
3. Same Attribute as the DM, or an Attribute mentioned in its effect box (including token definitions).
4. Same monster Type (race) as the DM, or a Type mentioned in its effect box (including token definitions).
Always in every domain: all Spells and Traps; DIVINE-Attribute and Divine-Beast monsters.
NOT considered even if mentioned: abilities (Spirit, Gemini, Flip...), monster card types
(Ritual, Fusion, Synchro...), Level/Rank/Link/Scale, ATK/DEF values, Card Series.
Examples:
- Chronicle Magician (DARK Spellcaster; mentions Dark Magician, Blue-Eyes White Dragon):
  DARK, Spellcaster, "Dark Magician" archetype, "Blue-Eyes" archetype, Divine. (It is not "Magician" archetype in OCG.)
- Lo, the Prayers of the Voiceless Voice (LIGHT Fairy, "Voiceless Voice", mentions Warrior and Dragon):
  LIGHT, Fairy, Warrior, Dragon, "Voiceless Voice", Divine.

## Deck Master Zone (DMZ)
- DM starts the duel in the DMZ (a separate zone; official position center below the S/T zones,
  but any placement separated from other zones and clear for all players is fine, e.g. left or right of the EMZ).
- DMZ is NOT hand/field/GY/etc. The DM is not in any of those zones while in the DMZ.
- DM in DMZ: cannot be discarded or Tributed; cannot activate or apply any of its effects;
  cannot be targeted or affected by other cards.

## Leaving the DMZ — ONLY these methods ("from the hand"/"from the Extra Deck" clauses are ignored for these):
1. Normal / Tribute Summon or Set (not if the DM can't be Normal Summoned; e.g. Ghostrick Mummy needs another Ghostrick
   to be Normal Summoned but can still be Set; Ritual/Extra Deck monsters can't). Effects that make the player
   perform a Normal Summon/Set are valid (Ultimate Offering; Mausoleum of the Emperor's tribute-less summon).
2. Its summon mechanic (Ritual, Fusion, Synchro, Xyz, Link) or an effect that is a proper summon:
   Underworld Ritual of Prediction can Ritual Summon it; Instant Fusion can Fusion Summon a Level 5- Fusion DM;
   Rank-Up-Magic Quick Chaos can Xyz Summon it onto a "Number" you control.
3. Main Deck monster: Pendulum Summon (unless the DM has restrictions on being Special Summoned,
   e.g. The Tyrant Neptune cannot be Pendulum Summoned from the DMZ).
4. Main Deck Pendulum monster: activated as a Pendulum Spell (placed in a Pendulum Zone).
5. Its non-activating summon method (built-in procedure): Jester Confit; Blue-Eyes Alternative Dragon by revealing
   BEWD in hand; ABC-Dragon Buster by banishing its materials from field/GY.
NOT valid:
- Effects that Special Summon "from the hand/Deck/Extra Deck" that are not a proper summon
  (Red-Eyes Darkness Metal Dragon, Waking the Dragon).
- Its own activated effect (Bystial Magnamhut can't Special Summon itself from the DMZ; it can still be Tribute or Pendulum Summoned).
- Setting it in the S/T Zone (Artifact Scythe can't be Set in S/T from the DMZ).
Extra Deck DM summoned from the DMZ: non-Link -> Main Monster Zone or Extra Monster Zone; Link -> EMZ or a
Main Monster Zone a Link Monster points to (i.e. the normal Extra Deck placement rules).

## Returning to the DMZ
- Condition: since the last open game state, the DM changed zone TYPES at least once, except being placed on/within
  the field (field->GY, GY->Deck, hand->banished... count; changing columns, monster zone->S/T zone, attached as
  material, placed in S/T as a Continuous Spell by the opponent do NOT count).
  If your DM in the GY is Special Summoned by an opponent (e.g. Monster Reborn, or Toadally Awesome destroying it and
  Setting it on the opponent's field), you do not get the option.
- Timing: right before the game state is open again (after all chain links resolved and no new chain started), each
  duelist, in turn order starting with the turn player, may choose to return their DM to the DMZ or leave it.
  - If not returned, it can't be returned later unless it changes zones again.
  - Only DMs that changed zones may be returned.
  - All chain links must be resolved and no new chain created first (a trigger caused by the DM moving
    to the GY, e.g. Sangan, must chain and resolve first; then the option comes).
- The option cannot be negated or interrupted. Returning does not start a chain.
- If returning the DM triggers a card effect (e.g. Exosister Elis on a card leaving the GY), that effect can be
  activated and starts a new chain; nothing else can be chained to the return itself.

## Cost to summon from the DMZ
- Cumulative 500 LP per previous return to the DMZ: first time leaving is free, second 500, third 1000, ...
- Like Chain Energy / Masquerade the Blazing Dragon: a cost to perform the action, NOT the activation cost of a
  spell (Spell Economics does not prevent paying it).
- Paid only when the DM leaves the DMZ (if the DM is added to the hand, summoning it from there costs nothing extra).
- Paying it does not start a chain.

## Gameplay (2 players)
- Each player starts with 5 cards; turn player of a 2-player game does not draw on the first turn.
- Usual rules otherwise ("Your opponent wins the Duel" effects -> "you lose the Duel", identical in 1v1).
- Field: current Master Rule field (Extra Monster Zones and Pendulum Zones exist; Link placement rules apply).
