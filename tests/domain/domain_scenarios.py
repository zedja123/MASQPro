#!/usr/bin/env python3
"""Scenario tests of the Domain format's Deck Master Zone (ocgcore).

Real duels on the libocgcore.so built from this worktree, driven by the CardScripts duel
tooling (duelsim.py / scenario.py, used unmodified):

  export EDOPRO_CORE=/home/user/wt/core/ocgcore EDOPRO_CACHE=/tmp/claude-0/cache-core \
         EDOPRO_CDB=/tmp/claude-0/genesys/BabelCDB
  python3 tests/domain/build_core.py           # builds $EDOPRO_CACHE/libocgcore.so
  python3 tests/domain/domain_scenarios.py     # every test
  python3 tests/domain/domain_scenarios.py normal_summon_from_dmz ...

EDOPRO_TOOLS can point to another copy of the tools folder.
"""
import os
import struct
import sys
from pathlib import Path

TOOLS = Path(os.environ.get("EDOPRO_TOOLS",
                            "/home/user/zedja123/cardscripts/.claude/skills/edopro-card-scripting/tools"))
sys.path.insert(0, str(TOOLS))
from duelsim import DUEL_ATTACK_FIRST_TURN, DUEL_MODE_MR5, DUEL_PSEUDO_SHUFFLE, Duel, i32  # noqa: E402
from scenario import (Act, Answer, Attack, Phase, Pick, Step, Summon, TestFailure, activatable, begin,  # noqa: E402
                      expect, filler, lua_bool, lua_val, play, prompts, run_tests, test)

DUEL_DOMAIN = 0x2000000000
DUEL_MODE_DOMAIN = DUEL_MODE_MR5 | DUEL_DOMAIN
LOCATION_DECK_MASTER = 0x40000000
DMZ_SEQUENCE = 0xFF
HINT_DMZ, HINT_DMZ_REMOVE = 204, 205
DESC_RETURN = 7112
MSG_PAY_LPCOST = 100
POS_FACEDOWN = 0x0A

# cards
FILLER = 89631139            # Blue-Eyes White Dragon (Level 8 Normal)
GENE_WARPED = 69247929       # Gene-Warped Warwolf (Level 4 Normal)
SUMMONED_SKULL = 70781052    # Level 6 Normal
LINK_SPIDER = 98978921       # 1 Normal Monster
UTOPIA = 84013237            # Number 39: Utopia, 2 Level 4 monsters
UTOPIA_RAY_V = 66970002      # Number C39: Utopia Ray V (Rank 5)
QUICK_CHAOS = 33252803       # Rank-Up-Magic Quick Chaos
ABC = 1561110                # ABC-Dragon Buster
A_CORE, B_DRAKE, C_WYVERN = 30012506, 77411244, 3405259
JESTER = 8487449             # Jester Confit
INSTANT_FUSION = 1845204
POLYMERIZATION = 24094653
FLAME_SWORDSMAN = 45231177   # Level 5 Fusion: Flame Manipulator + Masaki
FLAME_MANIPULATOR, MASAKI = 34460851, 44287299
RELINQUISHED = 64631466      # Level 1 Ritual
BLACK_ILLUSION = 41426869    # its Ritual Spell
ODD_EYES = 16178681          # Odd-Eyes Pendulum Dragon, Level 7, scale 4
STARGAZER, TIMEGAZER = 94415058, 20409757   # scales 1 and 8
SK_GATE_INFINITY = 22211622  # scale 13
WAKING = 10813327            # Waking the Dragon
ANCIENT_RULES = 10667321
MST = 5318639
MAGNAMHUT = 33854624         # Bystial Magnamhut
NEPTUNE = 88071625           # The Tyrant Neptune
DARK_HOLE = 53129443
REBORN = 83764718
SPELL_ECONOMICS = 4259068
CHAIN_ENERGY = 79323590
GRACEFUL_CHARITY = 79571449
DARK_MAGICIAN = 46986414
ODD_EYES_VENOM = 45014450    # Fusion Pendulum, Level 10
TENSU = 10719350             # Fire Formation - Tensu: extra Normal Summon of a Beast-Warrior
FLASH_KNIGHT = 17390179      # Level 4 Normal Pendulum, scale 7
SANGAN = 26202165
CED = 94192409               # Compulsory Evacuation Device
ULTIMATE_OFFERING = 80604091
CHARGING_GAIA = 7841921      # Level 7, can be Normal Summoned without Tributing
CYBER_DRAGON = 70095154
BLACK_ROSE = 73580471         # Level 7 Synchro: 1 Tuner + 1+ non-Tuner
FLAMVELL_GUARD = 21615956     # Level 1 Tuner Normal


# ---------------------------------------------------------------- helpers
def domain_duel(seed=1, lp=8000):
	return Duel(seed=seed, flags=DUEL_MODE_DOMAIN | DUEL_PSEUDO_SHUFFLE, lp=lp)


def add_dm(d, code, player=0):
	d.add(code, player, LOCATION_DECK_MASTER, pos=POS_FACEDOWN)


def setup_lua(d, code):
	d.lua(code, "setup.lua")


def is_dmz(x):
	return x["loc"] == 0 and x["seq"] == DMZ_SEQUENCE


def idle_entries(d, kind, code):
	m = d.pending
	expect(m is not None and m.name == "SELECT_IDLECMD", f"not at an idle prompt: {m and m.name}")
	return [x for x in m.data[kind] if x["code"] == code]


def dmz_entry(d, kind, code):
	"""The idle-command entry of the Deck Master in the Deck Master Zone, or None."""
	for x in idle_entries(d, kind, code):
		if is_dmz(x):
			return x
	return None


def hints(d, htype, start=0):
	return [m for m in d.messages[start:] if m.name == "HINT" and m.data.get("htype") == htype]


def moves(d, code, start=0):
	return [m for m in d.messages[start:] if m.name == "MOVE" and m.data.get("code") == code]


def lp(d, p=0):
	return d.state()["lp"][p]


def lp_costs(d, start=0):
	out = []
	for m in d.messages[start:]:
		if m.type == MSG_PAY_LPCOST:
			out.append((m.raw[0], struct.unpack_from("<I", m.raw, 1)[0]))
	return out


def in_dmz(d, code, player=0):
	"""The last move of `code` brought it into the Deck Master Zone (or it never moved and was loaded there)."""
	mv = moves(d, code)
	if not mv:
		return any(m.data["hdata"] & 0xFFFFFFFF == code and m.data["player"] == player for m in hints(d, HINT_DMZ))
	cur = mv[-1].data["cur"]
	return cur["loc"] == 0 and cur["seq"] == DMZ_SEQUENCE and cur["con"] == player


def selectable_codes(m):
	if m.name == "SELECT_UNSELECT_CARD":
		return [(x["code"], x["loc"], x["seq"]) for x in m.data["select"] + m.data["unselect"]]
	return [(x["code"], x["loc"], x["seq"]) for x in m.data.get("cards", [])]


class PickDMZ(Step):
	"""Pick the Deck Master Zone card `code` (location 0, sequence 0xFF) in a card selection."""
	def __init__(self, code, player=0):
		self.code, self.player = code, player

	def apply(self, duel, m):
		if m.player != self.player or m.name not in ("SELECT_CARD", "SELECT_UNSELECT_CARD"):
			return None
		lst = m.data["cards"] if m.name == "SELECT_CARD" else m.data["select"]
		for i, x in enumerate(lst):
			if x["code"] == self.code and is_dmz(x):
				if m.name == "SELECT_CARD":
					return struct.pack("<iI", 0, 1) + struct.pack("<I", i)
				return struct.pack("<ii", 1, i)
		raise TestFailure(f"Deck Master {self.code} not selectable: {selectable_codes(m)}")


class SummonFrom(Step):
	"""Normal Summon the copy of `code` that is in location `loc` (0 = Deck Master Zone)."""
	def __init__(self, code, loc, player=0):
		self.code, self.loc, self.player = code, loc, player

	def apply(self, duel, m):
		if m.name != "SELECT_IDLECMD" or m.player != self.player:
			return None
		for i, x in enumerate(m.data["summon"]):
			if x["code"] == self.code and x["loc"] == self.loc:
				return struct.pack("<i", (i << 16) | 0)
		raise TestFailure(f"{self.code} not summonable from {self.loc}")


class Finish(Step):
	def __init__(self, player=0):
		self.player = player

	def apply(self, duel, m):
		if m.player == self.player and m.name == "SELECT_UNSELECT_CARD" and m.data["finishable"]:
			return i32(-1)
		return None


def return_prompts(d, player=0, start=0):
	return [m for m in d.messages[start:] if m.name == "SELECT_EFFECTYN" and m.player == player
	        and m.data["desc"] == DESC_RETURN]


def mz(code, seq, player=0, pos="POS_FACEUP_ATTACK", proc=True):
	return f"Debug.AddCard({code},{player},{player},LOCATION_MZONE,{seq},{pos},{'true' if proc else 'false'})\n"


# ---------------------------------------------------------------- loading and hints
@test
def dm_hint_at_start():
	d = domain_duel()
	add_dm(d, GENE_WARPED, 0)
	add_dm(d, SUMMONED_SKULL, 1)
	filler(d, 0); filler(d, 1)
	begin(d)
	h = hints(d, HINT_DMZ)
	got = sorted((m.data["player"], m.data["hdata"]) for m in h)
	expect(got == [(0, GENE_WARPED), (1, SUMMONED_SKULL)], f"HINT_DMZ at start: {got}")
	first_draw_or_turn = next(i for i, m in enumerate(d.messages) if m.name in ("NEW_TURN", "MOVE"))
	expect(all(d.messages.index(m) < first_draw_or_turn for m in h), "HINT_DMZ not sent before the duel starts")
	expect(lua_val(d, "Duel.GetFieldGroupCount(0,LOCATION_HAND,0)") == "0", "DM counted in the hand")
	return d


@test
def dm_ignored_without_domain_flag():
	d = Duel(seed=1, flags=DUEL_MODE_MR5 | DUEL_PSEUDO_SHUFFLE)
	add_dm(d, GENE_WARPED, 0)
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(not hints(d, HINT_DMZ), "HINT_DMZ without DUEL_DOMAIN")
	expect(not idle_entries(d, "summon", GENE_WARPED), "DM summonable without DUEL_DOMAIN")
	return d


@test
def spell_or_second_dm_ignored():
	d = domain_duel()
	add_dm(d, DARK_HOLE, 0)          # not a monster: ignored
	add_dm(d, GENE_WARPED, 0)        # the Deck Master
	add_dm(d, SUMMONED_SKULL, 0)     # a second one: ignored
	filler(d, 0); filler(d, 1)
	begin(d)
	got = [(m.data["player"], m.data["hdata"]) for m in hints(d, HINT_DMZ)]
	expect(got == [(0, GENE_WARPED)], f"HINT_DMZ: {got}")
	return d


# ---------------------------------------------------------------- Normal/Tribute Summon and Set
@test
def normal_summon_from_dmz():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	filler(d, 0); filler(d, 1)
	begin(d)
	x = dmz_entry(d, "summon", GENE_WARPED)
	expect(x is not None and x["con"] == 0, f"DM not in the summon list as (0,0,0xFF): {idle_entries(d, 'summon', GENE_WARPED)}")
	n0 = len(d.messages)
	play(d, [Summon(GENE_WARPED, "summon")])
	expect(GENE_WARPED in d.codes(0, "mzone"), "DM not Normal Summoned")
	mv = moves(d, GENE_WARPED, n0)
	expect(mv and mv[0].data["prev"]["loc"] == 0 and mv[0].data["prev"]["seq"] == DMZ_SEQUENCE,
	       f"MSG_MOVE previous location is not the DMZ: {mv and mv[0].data}")
	rm = hints(d, HINT_DMZ_REMOVE, n0)
	expect(rm and d.messages.index(rm[0]) > d.messages.index(mv[0]), "HINT_DMZ_REMOVE missing or before the MSG_MOVE")
	expect(lp(d) == 8000 and not lp_costs(d, n0), "first summon from the DMZ is not free")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{GENE_WARPED}):IsSummonLocation(LOCATION_HAND)"),
	       "summon location is not the hand")
	expect(not return_prompts(d), "return offered after a summon")
	return d


@test
def tribute_summon_from_dmz():
	d = domain_duel()
	add_dm(d, SUMMONED_SKULL)
	setup_lua(d, mz(GENE_WARPED, 2))
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "summon", SUMMONED_SKULL), "Level 6 DM not Tribute Summonable")
	play(d, [Summon(SUMMONED_SKULL, "summon"), Pick(GENE_WARPED)])
	expect(SUMMONED_SKULL in d.codes(0, "mzone"), "DM not Tribute Summoned")
	expect(GENE_WARPED in d.codes(0, "grave"), "tribute not in the GY")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{SUMMONED_SKULL}):IsSummonType(SUMMON_TYPE_TRIBUTE)"),
	       "not a Tribute Summon")
	return d


@test
def tribute_summon_needs_tributes():
	d = domain_duel()
	add_dm(d, SUMMONED_SKULL)
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(not dmz_entry(d, "summon", SUMMONED_SKULL), "Level 6 DM summonable with no tribute")
	expect(not dmz_entry(d, "mset", SUMMONED_SKULL), "Level 6 DM settable with no tribute")
	return d


@test
def set_from_dmz():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "mset", GENE_WARPED), "DM not in the Set list")
	expect(not dmz_entry(d, "sset", GENE_WARPED), "DM in the Spell/Trap Set list")
	play(d, [Summon(GENE_WARPED, "mset")])
	st = d.state()
	got = [c for c in st[(0, "mzone")] if c["code"] == GENE_WARPED]
	expect(got and got[0]["pos"] == 8, f"DM not Set face-down: {got}")
	return d


# ---------------------------------------------------------------- own procedures
@test
def link_summon_from_dmz_to_emz():
	d = domain_duel()
	add_dm(d, LINK_SPIDER)
	setup_lua(d, mz(GENE_WARPED, 2))
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "spsummon", LINK_SPIDER), "Link DM not Special Summonable from the DMZ")
	play(d, [Summon(LINK_SPIDER), Pick(GENE_WARPED)])
	st = d.state()
	got = [c for c in st[(0, "mzone")] if c["code"] == LINK_SPIDER]
	expect(got, "Link DM not summoned")
	expect(got[0]["seq"] in (5, 6), f"Link DM not placed in an Extra Monster Zone: seq {got[0]['seq']}")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{LINK_SPIDER}):IsSummonLocation(LOCATION_EXTRA)"),
	       "summon location is not the Extra Deck")
	return d


@test
def xyz_summon_from_dmz_keeps_materials():
	d = domain_duel()
	add_dm(d, UTOPIA)
	setup_lua(d, mz(GENE_WARPED, 1) + mz(GENE_WARPED, 3))
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "spsummon", UTOPIA), "Xyz DM not Special Summonable from the DMZ")
	n0 = len(d.messages)
	play(d, [Summon(UTOPIA), Pick(GENE_WARPED, GENE_WARPED)])
	st = d.state()
	got = [c for c in st[(0, "mzone")] if c["code"] == UTOPIA]
	expect(got and got[0]["overlay"] == 2, f"Xyz DM not summoned with 2 materials: {got}")
	att = [m for m in moves(d, GENE_WARPED, n0) if m.data["cur"]["loc"] & 0x80]
	expect(att and all(m.data["cur"]["con"] == 0 and m.data["cur"]["seq"] == DMZ_SEQUENCE for m in att),
	       f"materials not attached to the DMZ card (0,0x80,0xFF): {[m.data['cur'] for m in att]}")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{UTOPIA}):IsSummonType(SUMMON_TYPE_XYZ)"),
	       "not an Xyz Summon")
	return d


@test
def contact_fusion_abc_from_dmz():
	d = domain_duel()
	add_dm(d, ABC)
	for c in (A_CORE, B_DRAKE, C_WYVERN):
		d.add(c, 0, "grave")
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "spsummon", ABC), "ABC-Dragon Buster not Contact Fusion summonable from the DMZ")
	play(d, [Summon(ABC), Pick(A_CORE, B_DRAKE, C_WYVERN)])
	expect(ABC in d.codes(0, "mzone"), "ABC-Dragon Buster not summoned")
	expect({A_CORE, B_DRAKE, C_WYVERN} <= set(d.codes(0, "removed")), "materials not banished")
	return d


@test
def jester_confit_procedure_from_dmz():
	d = domain_duel()
	add_dm(d, JESTER)
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "spsummon", JESTER), "Jester Confit's hand procedure not available from the DMZ")
	play(d, [Summon(JESTER)])
	expect(JESTER in d.codes(0, "mzone"), "Jester Confit not summoned")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{JESTER}):IsSummonLocation(LOCATION_HAND)"),
	       "summon location is not the hand")
	return d


# ---------------------------------------------------------------- proper summons by effects
@test
def instant_fusion_summons_extra_dm():
	d = domain_duel()
	add_dm(d, FLAME_SWORDSMAN)
	d.add(INSTANT_FUSION, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	expect((INSTANT_FUSION, 0) in [(c, i) for c, i in activatable(d)] or INSTANT_FUSION in [c for c, _ in activatable(d)],
	       f"Instant Fusion not activatable with a Fusion DM: {activatable(d)}")
	play(d, [Act(INSTANT_FUSION), PickDMZ(FLAME_SWORDSMAN)])
	expect(FLAME_SWORDSMAN in d.codes(0, "mzone"), "Fusion DM not summoned by Instant Fusion")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{FLAME_SWORDSMAN}):IsSummonLocation(LOCATION_EXTRA)"),
	       "summon location is not the Extra Deck")
	expect(lp(d) == 7000, f"LP {lp(d)} (expected 7000: Instant Fusion only)")
	return d


@test
def polymerization_picks_extra_dm():
	d = domain_duel()
	add_dm(d, FLAME_SWORDSMAN)
	for c in (POLYMERIZATION, FLAME_MANIPULATOR, MASAKI):
		d.add(c, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Act(POLYMERIZATION), PickDMZ(FLAME_SWORDSMAN), Pick(FLAME_MANIPULATOR, MASAKI)])
	expect(FLAME_SWORDSMAN in d.codes(0, "mzone"), "Fusion DM not Fusion Summoned")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{FLAME_SWORDSMAN}):IsSummonType(SUMMON_TYPE_FUSION)"),
	       "not a Fusion Summon")
	return d


@test
def ritual_spell_summons_ritual_dm():
	d = domain_duel()
	add_dm(d, RELINQUISHED)
	d.add(BLACK_ILLUSION, 0, "hand")
	d.add(GENE_WARPED, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Act(BLACK_ILLUSION), PickDMZ(RELINQUISHED), Pick(GENE_WARPED)])
	expect(RELINQUISHED in d.codes(0, "mzone"), "Ritual DM not Ritual Summoned")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{RELINQUISHED}):IsSummonType(SUMMON_TYPE_RITUAL)"),
	       "not a Ritual Summon")
	return d


@test
def rank_up_quick_chaos_onto_number():
	d = domain_duel()
	add_dm(d, UTOPIA_RAY_V)
	setup_lua(d, f"local c=Debug.AddCard({UTOPIA},0,0,LOCATION_MZONE,2,POS_FACEUP_ATTACK,true)\nDebug.PreSummon(c,SUMMON_TYPE_XYZ)\n")
	d.add(QUICK_CHAOS, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Act(QUICK_CHAOS), Pick(UTOPIA), PickDMZ(UTOPIA_RAY_V)])
	st = d.state()
	got = [c for c in st[(0, "mzone")] if c["code"] == UTOPIA_RAY_V]
	expect(got and got[0]["overlay"] == 1, f"Number C39 DM not Xyz Summoned onto Utopia: {st[(0, 'mzone')]}")
	return d


# ---------------------------------------------------------------- Pendulum
@test
def pendulum_scale_from_dmz():
	d = domain_duel()
	add_dm(d, ODD_EYES)
	filler(d, 0); filler(d, 1)
	begin(d)
	acts = [x for x in d.pending.data["activate"] if x["code"] == ODD_EYES]
	expect(acts and is_dmz(acts[0]), f"Pendulum activation from the DMZ not offered: {acts}")
	play(d, [Act(ODD_EYES)])
	st = d.state()
	expect(any(c["code"] == ODD_EYES for c in st[(0, "szone")]), "Odd-Eyes not placed in a Pendulum Zone")
	expect(lua_bool(d, f"Duel.GetFieldCard(0,LOCATION_PZONE,0) and Duel.GetFieldCard(0,LOCATION_PZONE,0):IsCode({ODD_EYES})")
	       or lua_bool(d, f"Duel.GetFieldCard(0,LOCATION_PZONE,1) and Duel.GetFieldCard(0,LOCATION_PZONE,1):IsCode({ODD_EYES})"),
	       "not in a Pendulum Zone")
	return d


def pendulum_board(dm, rscale=TIMEGAZER):
	d = domain_duel()
	add_dm(d, dm)
	setup_lua(d, f"Debug.AddCard({STARGAZER},0,0,LOCATION_PZONE,0,POS_FACEUP_ATTACK)\n"
	             f"Debug.AddCard({rscale},0,0,LOCATION_PZONE,1,POS_FACEUP_ATTACK)\n")
	filler(d, 0); filler(d, 1)
	begin(d)
	return d


@test
def pendulum_summon_main_deck_dm():
	d = pendulum_board(ODD_EYES)
	expect(any(x["code"] == STARGAZER for x in d.pending.data["spsummon"]), "Pendulum Summon not available with the DM")
	play(d, [Summon(STARGAZER), PickDMZ(ODD_EYES)])
	expect(ODD_EYES in d.codes(0, "mzone"), "DM not Pendulum Summoned")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{ODD_EYES}):IsSummonType(SUMMON_TYPE_PENDULUM)"),
	       "not a Pendulum Summon")
	return d


@test
def tyrant_neptune_not_pendulum_summonable():
	d = pendulum_board(NEPTUNE, rscale=SK_GATE_INFINITY)
	expect(not any(x["code"] == STARGAZER for x in d.pending.data["spsummon"]),
	       "Pendulum Summon offered with only The Tyrant Neptune as candidate")
	# control: a Main Deck DM within the same scales
	d2 = pendulum_board(ODD_EYES, rscale=SK_GATE_INFINITY)
	expect(any(x["code"] == STARGAZER for x in d2.pending.data["spsummon"]), "control: Pendulum Summon not offered")
	return d


@test
def extra_deck_pendulum_dm_not_pendulum_summoned():
	d = pendulum_board(ODD_EYES_VENOM, rscale=SK_GATE_INFINITY)
	expect(not any(x["code"] == STARGAZER for x in d.pending.data["spsummon"]),
	       "Pendulum Summon offered for an Extra Deck Pendulum DM")
	expect(not any(x["code"] == ODD_EYES_VENOM for x in d.pending.data["activate"]),
	       "Extra Deck Pendulum DM can be activated as a Pendulum Scale")
	return d


# ---------------------------------------------------------------- what may not leave the DMZ
@test
def ancient_rules_does_not_see_dm():
	d = domain_duel()
	add_dm(d, SUMMONED_SKULL)
	d.add(ANCIENT_RULES, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(ANCIENT_RULES not in [c for c, _ in activatable(d)], "Ancient Rules sees the DM as a hand card")
	# control: the same monster in the hand
	d2 = domain_duel()
	d2.add(SUMMONED_SKULL, 0, "hand")
	d2.add(ANCIENT_RULES, 0, "hand")
	filler(d2, 0); filler(d2, 1)
	begin(d2)
	expect(ANCIENT_RULES in [c for c, _ in activatable(d2)], "control: Ancient Rules not activatable with the monster in hand")
	return d


@test
def waking_the_dragon_does_not_see_dm():
	d = domain_duel()
	add_dm(d, FLAME_SWORDSMAN)
	setup_lua(d, f"Debug.AddCard({WAKING},0,0,LOCATION_SZONE,1,POS_FACEDOWN_DEFENSE)\n"
	             f"Debug.AddCard({MST},1,1,LOCATION_SZONE,1,POS_FACEDOWN_DEFENSE)\n")
	d.add(GENE_WARPED, 0, "deck")
	filler(d, 0); filler(d, 1)
	begin(d)
	n0 = len(d.messages)
	play(d, [Phase("ep"), Act(MST, player=1), Pick(WAKING, player=1), Act(WAKING), Pick(GENE_WARPED)],
	     stop="idle", player=1)
	sel = [m for m in d.messages[n0:] if m.name == "SELECT_CARD" and m.player == 0]
	expect(sel, "Waking the Dragon did not resolve")
	expect(all(not any(x["code"] == FLAME_SWORDSMAN for x in m.data["cards"]) for m in sel),
	       f"Waking the Dragon offered the DM: {[selectable_codes(m) for m in sel]}")
	return d


@test
def bystial_cannot_summon_itself_from_dmz():
	d = domain_duel()
	add_dm(d, MAGNAMHUT)
	d.add(DARK_MAGICIAN, 0, "grave")
	setup_lua(d, mz(GENE_WARPED, 2))
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(MAGNAMHUT not in [c for c, _ in activatable(d)], "Bystial Magnamhut's own effect usable from the DMZ")
	expect(dmz_entry(d, "summon", MAGNAMHUT), "Bystial Magnamhut cannot be Tribute Summoned from the DMZ")
	# control: from the hand its effect is usable
	d2 = domain_duel()
	d2.add(MAGNAMHUT, 0, "hand")
	d2.add(DARK_MAGICIAN, 0, "grave")
	filler(d2, 0); filler(d2, 1)
	begin(d2)
	expect(MAGNAMHUT in [c for c, _ in activatable(d2)], "control: Bystial Magnamhut not usable from the hand")
	return d


@test
def extra_deck_lock_applies_to_dm():
	d = domain_duel()
	add_dm(d, LINK_SPIDER)
	setup_lua(d, mz(GENE_WARPED, 2))
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "spsummon", LINK_SPIDER), "control: Link DM not summonable")
	d.lua("""
local e=Effect.GlobalEffect()
e:SetType(EFFECT_TYPE_FIELD)
e:SetCode(EFFECT_CANNOT_SPECIAL_SUMMON)
e:SetProperty(EFFECT_FLAG_PLAYER_TARGET)
e:SetTargetRange(1,0)
e:SetTarget(function(e,c) return c:IsLocation(LOCATION_EXTRA) end)
Duel.RegisterEffect(e,0)
""", "lock.lua")
	play(d, [Phase("ep")], stop="idle", player=1)
	play(d, [Phase("ep", player=1)], stop="idle", player=0)
	expect(not dmz_entry(d, "spsummon", LINK_SPIDER), "\"Cannot Special Summon from the Extra Deck\" does not apply to the DM")
	return d


@test
def extra_normal_summon_reaches_dm():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	setup_lua(d, f"Debug.AddCard({TENSU},0,0,LOCATION_SZONE,2,POS_FACEUP_ATTACK)\n")
	d.add(GENE_WARPED, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	expect([x for x in idle_entries(d, "summon", GENE_WARPED) if x["loc"] == 0x02], "hand copy not summonable")
	play(d, [SummonFrom(GENE_WARPED, 0x02)])
	expect(dmz_entry(d, "summon", GENE_WARPED), "Fire Formation - Tensu's extra Normal Summon does not reach the DM")
	play(d, [Summon(GENE_WARPED, "summon")])
	expect(d.codes(0, "mzone").count(GENE_WARPED) == 2, "DM not summoned with the extra Normal Summon")
	return d


@test
def dm_not_in_hand_and_not_discardable():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	d.add(GRACEFUL_CHARITY, 0, "hand")
	for _ in range(5):
		d.add(SUMMONED_SKULL, 0, "deck")
	filler(d, 1)
	begin(d)
	expect(lua_val(d, "Duel.GetFieldGroupCount(0,LOCATION_HAND,0)") == "1", "DM counted by GetFieldGroupCount(LOCATION_HAND)")
	n0 = len(d.messages)
	play(d, [Act(GRACEFUL_CHARITY)])
	sel = [m for m in d.messages[n0:] if m.name == "SELECT_CARD" and m.player == 0]
	expect(sel, "no discard selection")
	expect(all(not any(x["code"] == GENE_WARPED for x in m.data["cards"]) for m in sel),
	       f"DM offered as a discard: {[selectable_codes(m) for m in sel]}")
	expect(dmz_entry(d, "summon", GENE_WARPED), "DM left the DMZ")
	return d


# ---------------------------------------------------------------- returning to the DMZ
def summon_and_destroy(answer, dm=GENE_WARPED):
	d = domain_duel()
	add_dm(d, dm)
	d.add(DARK_HOLE, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Summon(dm, "summon")])
	n0 = len(d.messages)
	steps = [Act(DARK_HOLE)]
	if answer is not None:
		steps.append(Answer(answer, desc=DESC_RETURN))
	play(d, steps)
	return d, n0


@test
def destroyed_dm_returns_and_costs_500():
	d, n0 = summon_and_destroy(True)
	expect(return_prompts(d, 0, n0), "no return prompt after the DM was destroyed")
	mv = [m for m in moves(d, GENE_WARPED, n0) if m.data["cur"]["loc"] == 0]
	expect(mv and mv[-1].data["prev"]["loc"] == 0x10 and mv[-1].data["cur"]["seq"] == DMZ_SEQUENCE
	       and mv[-1].data["cur"]["pos"] == POS_FACEDOWN and mv[-1].data["cur"]["con"] == 0,
	       f"return MSG_MOVE: {mv and mv[-1].data}")
	h_ret = hints(d, HINT_DMZ, n0)
	expect(h_ret and d.messages.index(h_ret[-1]) > d.messages.index(mv[-1]), "HINT_DMZ not after the MSG_MOVE")
	expect(GENE_WARPED not in d.codes(0, "grave"), "DM still in the GY after returning")
	expect(in_dmz(d, GENE_WARPED), "DM not moved to the DMZ")
	h = hints(d, HINT_DMZ, n0)
	expect(h and h[-1].data["hdata"] == GENE_WARPED | (1 << 32), f"HINT_DMZ with return count 1 missing: {[m.data for m in h]}")
	# the Normal Summon of this turn is used: summon it again next turn
	play(d, [Phase("ep")], stop="idle", player=1)
	play(d, [Phase("ep", player=1)], stop="idle", player=0)
	expect(dmz_entry(d, "summon", GENE_WARPED), "DM not summonable again")
	n1 = len(d.messages)
	play(d, [Summon(GENE_WARPED, "summon")])
	expect(GENE_WARPED in d.codes(0, "mzone"), "DM not summoned again")
	expect(lp_costs(d, n1) == [(0, 500)] and lp(d) == 7500, f"second summon cost {lp_costs(d, n1)}, LP {lp(d)}")
	return d


@test
def declined_dm_stays_in_gy():
	d, n0 = summon_and_destroy(False)
	expect(len(return_prompts(d, 0, n0)) == 1, "no single return prompt")
	expect(GENE_WARPED in d.codes(0, "grave"), "declined DM not in the GY")
	n1 = len(d.messages)
	# next open game states (opponent's turn, own next turn): no new prompt
	play(d, [Phase("ep")], stop="idle", player=1)
	play(d, [Phase("ep", player=1)], stop="idle", player=0)
	expect(not return_prompts(d, 0, n1), "return offered again without a new zone change")
	expect(GENE_WARPED in d.codes(0, "grave"), "DM left the GY")
	return d


@test
def declined_dm_offered_again_after_moving():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	d.add(DARK_HOLE, 0, "hand"); d.add(REBORN, 0, "hand"); d.add(DARK_HOLE, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Summon(GENE_WARPED, "summon"), Act(DARK_HOLE), Answer(False, desc=DESC_RETURN)])
	n1 = len(d.messages)
	play(d, [Act(REBORN), Pick(GENE_WARPED)])
	expect(GENE_WARPED in d.codes(0, "mzone"), "Monster Reborn failed")
	expect(not return_prompts(d, 0, n1), "return offered while the DM is on the field")
	play(d, [Act(DARK_HOLE), Answer(True, desc=DESC_RETURN)])
	expect(return_prompts(d, 0, n1), "return not offered after the DM moved again")
	expect(in_dmz(d, GENE_WARPED), "DM not returned")
	return d


@test
def return_raises_leave_grave_for_owner():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	d.add(DARK_HOLE, 0, "hand")
	filler(d, 0); filler(d, 1)
	d.lua("""
local e=Effect.GlobalEffect()
e:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)
e:SetCode(EVENT_LEAVE_GRAVE)
e:SetOperation(function(e,tp,eg,ep,ev,re,r,rp) Debug.Message('LG|'..eg:GetFirst():GetCode()..'|'..rp..'|'..r) end)
Duel.RegisterEffect(e,0)
""", "watch.lua")
	begin(d)
	play(d, [Summon(GENE_WARPED, "summon"), Act(DARK_HOLE), Answer(True, desc=DESC_RETURN)])
	lg = [x for x in d.script_log if x.startswith("LG|")]
	expect(lg == [f"LG|{GENE_WARPED}|0|{0x400}"], f"EVENT_LEAVE_GRAVE of the return: {lg}")
	return d


@test
def opponent_reborn_gives_no_prompt():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	d.add(DARK_HOLE, 0, "hand")
	setup_lua(d, f"Debug.AddCard({REBORN},1,1,LOCATION_SZONE,1,POS_FACEDOWN_DEFENSE)\n")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Summon(GENE_WARPED, "summon"), Act(DARK_HOLE)])
	# the default policy declined; the opponent takes it with Monster Reborn on their turn
	n1 = len(d.messages)
	play(d, [Phase("ep")], stop="idle", player=1)
	play(d, [Act(REBORN, player=1), Pick(GENE_WARPED, player=1)], stop="idle", player=1)
	expect(GENE_WARPED in d.codes(1, "mzone"), "opponent did not Special Summon the DM")
	expect(not return_prompts(d, 0, n1), "return offered after the opponent took the DM")
	return d


@test
def spell_economics_does_not_remove_cost():
	d = domain_duel()
	add_dm(d, FLAME_SWORDSMAN)
	setup_lua(d, f"Debug.AddCard({SPELL_ECONOMICS},0,0,LOCATION_SZONE,2,POS_FACEUP_ATTACK)\n")
	d.add(INSTANT_FUSION, 0, "hand"); d.add(DARK_HOLE, 0, "hand"); d.add(POLYMERIZATION, 0, "hand")
	d.add(FLAME_MANIPULATOR, 0, "hand"); d.add(MASAKI, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Act(INSTANT_FUSION), PickDMZ(FLAME_SWORDSMAN)])
	expect(lp(d) == 8000, f"Spell Economics did not remove Instant Fusion's cost: LP {lp(d)}")
	play(d, [Act(DARK_HOLE), Answer(True, desc=DESC_RETURN)])
	expect(in_dmz(d, FLAME_SWORDSMAN), "DM not returned")
	n1 = len(d.messages)
	play(d, [Act(POLYMERIZATION), PickDMZ(FLAME_SWORDSMAN), Pick(FLAME_MANIPULATOR, MASAKI)])
	expect(FLAME_SWORDSMAN in d.codes(0, "mzone"), "DM not Fusion Summoned")
	expect(lp_costs(d, n1) == [(0, 500)] and lp(d) == 7500, f"DMZ cost with Spell Economics: {lp_costs(d, n1)}, LP {lp(d)}")
	return d


@test
def chain_energy_does_not_apply():
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	setup_lua(d, f"Debug.AddCard({CHAIN_ENERGY},0,0,LOCATION_SZONE,2,POS_FACEUP_ATTACK)\n")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Summon(GENE_WARPED, "summon")])
	expect(lp(d) == 8000, f"Chain Energy charged the DMZ summon: LP {lp(d)}")
	return d


@test
def chain_energy_pendulum_scale():
	d = domain_duel()
	add_dm(d, ODD_EYES)
	setup_lua(d, f"Debug.AddCard({CHAIN_ENERGY},0,0,LOCATION_SZONE,2,POS_FACEUP_ATTACK)\n")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Act(ODD_EYES)])
	expect(lp(d) == 8000, f"Chain Energy charged the Pendulum Scale activation from the DMZ: LP {lp(d)}")
	return d


@test
def not_enough_lp_for_cost():
	d, n0 = summon_and_destroy(True)
	# 500 LP needed; set LP to 400
	d.lua("Duel.SetLP(0,400)")
	play(d, [Phase("ep")], stop="idle", player=1)
	play(d, [Phase("ep", player=1)], stop="idle", player=0)
	expect(not dmz_entry(d, "summon", GENE_WARPED), "DM summonable with less LP than its cost")
	return d


@test
def pendulum_dm_cycle():
	"""Normal Summoned Pendulum DM: no Pendulum activation left on the field; destroyed it goes face-up to the
	Extra Deck, returns from there face-down and can be activated as a Pendulum Scale again for 500 LP."""
	d = domain_duel()
	add_dm(d, FLASH_KNIGHT)
	d.add(DARK_HOLE, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Summon(FLASH_KNIGHT, "summon")])
	expect(not [x for x in d.pending.data["activate"] if x["code"] == FLASH_KNIGHT],
	       f"Pendulum activation still offered after the DM left the DMZ: {d.pending.data['activate']}")
	n0 = len(d.messages)
	play(d, [Act(DARK_HOLE), Answer(True, desc=DESC_RETURN)])
	mv = [m for m in moves(d, FLASH_KNIGHT, n0) if m.data["cur"]["loc"] == 0]
	expect(mv and mv[-1].data["prev"]["loc"] == 0x40 and mv[-1].data["cur"]["pos"] == POS_FACEDOWN,
	       f"Pendulum DM not returned from the Extra Deck face-down: {mv and mv[-1].data}")
	acts = [x for x in d.pending.data["activate"] if x["code"] == FLASH_KNIGHT]
	expect(len(acts) == 1 and is_dmz(acts[0]), f"Pendulum activation from the DMZ after the return: {acts}")
	n1 = len(d.messages)
	play(d, [Act(FLASH_KNIGHT)])
	expect(lua_bool(d, f"Duel.IsExistingMatchingCard(Card.IsCode,0,LOCATION_PZONE,0,1,nil,{FLASH_KNIGHT})"),
	       "not placed in a Pendulum Zone")
	expect(lp_costs(d, n1) == [(0, 500)] and lp(d) == 7500, f"cost {lp_costs(d, n1)}, LP {lp(d)}")
	return d


@test
def dm_trigger_resolves_before_prompt():
	"""Sangan as DM: its GY trigger chains and resolves first, then the return is offered."""
	d = domain_duel()
	add_dm(d, SANGAN)
	d.add(DARK_HOLE, 0, "hand")
	d.add(FLAME_MANIPULATOR, 0, "deck")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Summon(SANGAN, "summon")])
	n0 = len(d.messages)
	play(d, [Act(DARK_HOLE), Pick(FLAME_MANIPULATOR), Answer(True, desc=DESC_RETURN)])
	search = [m for m in moves(d, FLAME_MANIPULATOR, n0) if m.data["cur"]["loc"] == 0x02]
	pr = return_prompts(d, 0, n0)
	expect(search, "Sangan did not resolve")
	expect(pr and d.messages.index(pr[0]) > d.messages.index(search[0]), "return offered before Sangan resolved")
	expect(in_dmz(d, SANGAN), "Sangan not returned")
	return d


@test
def dm_return_offered_before_battle_step():
	"""The DM is destroyed in response to an attack declaration: the return is offered before the Battle
	Step window opens (an open game state), not only after the Damage Step."""
	d = Duel(seed=1, flags=DUEL_MODE_DOMAIN | DUEL_PSEUDO_SHUFFLE | DUEL_ATTACK_FIRST_TURN, lp=8000)
	add_dm(d, GENE_WARPED)
	setup_lua(d, mz(SUMMONED_SKULL, 2))
	filler(d, 0); filler(d, 1)
	d.lua(f"""
local e=Effect.GlobalEffect()
e:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)
e:SetCode(EVENT_ATTACK_ANNOUNCE)
e:SetOperation(function()
	Duel.Destroy(Duel.GetMatchingGroup(Card.IsCode,0,LOCATION_MZONE,0,nil,{GENE_WARPED}),REASON_EFFECT)
end)
Duel.RegisterEffect(e,0)
""", "destroy_on_attack.lua")
	begin(d)
	play(d, [Summon(GENE_WARPED, "summon")])
	n0 = len(d.messages)
	play(d, [Phase("bp"), Attack(SUMMONED_SKULL), Answer(True, desc=DESC_RETURN)], stop="idle", max_prompts=60)
	pr = return_prompts(d, 0, n0)
	battle_step = [m for m in d.messages[n0:] if m.name == "HINT" and m.data.get("htype") == 1 and m.data.get("hdata") == 24]
	expect(pr, "no return prompt")
	expect(battle_step, "no Battle Step window")
	expect(d.messages.index(pr[0]) < d.messages.index(battle_step[0]), "return offered only after the Battle Step window")
	expect(in_dmz(d, GENE_WARPED), "DM not returned")
	return d


@test
def abc_contact_fusion_again_after_return():
	"""After a return the DM is face-down again, so ABC-Dragon Buster's Contact Fusion works a second time."""
	d = domain_duel()
	add_dm(d, ABC)
	for c in (A_CORE, B_DRAKE, C_WYVERN) * 2:
		d.add(c, 0, "grave")
	d.add(DARK_HOLE, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [Summon(ABC), Pick(A_CORE, B_DRAKE, C_WYVERN), Act(DARK_HOLE), Answer(True, desc=DESC_RETURN)])
	expect(in_dmz(d, ABC), "ABC-Dragon Buster not returned")
	expect(dmz_entry(d, "spsummon", ABC), "Contact Fusion not available again after the return")
	n1 = len(d.messages)
	play(d, [Summon(ABC), Pick(A_CORE, B_DRAKE, C_WYVERN)])
	expect(ABC in d.codes(0, "mzone"), "ABC-Dragon Buster not summoned again")
	expect(lp_costs(d, n1) == [(0, 500)], f"second Contact Fusion cost {lp_costs(d, n1)}")
	return d


@test
def bounced_dm_declined_is_free_from_hand():
	"""Returned to the hand by the opponent: the return is offered; declined, it is an ordinary hand card
	(summoning it costs nothing and does not touch the DMZ)."""
	d = domain_duel()
	add_dm(d, GENE_WARPED)
	setup_lua(d, f"Debug.AddCard({CED},1,1,LOCATION_SZONE,1,POS_FACEDOWN_DEFENSE)\n")
	filler(d, 0); filler(d, 1)
	begin(d)
	n0 = len(d.messages)
	play(d, [Summon(GENE_WARPED, "summon"), Act(CED, player=1), Pick(GENE_WARPED, player=1),
	         Answer(False, desc=DESC_RETURN)])
	expect(len(return_prompts(d, 0, n0)) == 1, "return not offered once after the bounce")
	expect(GENE_WARPED in d.codes(0, "hand"), "DM not in the hand")
	expect(lua_val(d, "Duel.GetFieldGroupCount(0,LOCATION_HAND,0)") == "1", "hand count")
	play(d, [Phase("ep")], stop="idle", player=1)
	play(d, [Phase("ep", player=1)], stop="idle", player=0)
	n1 = len(d.messages)
	play(d, [SummonFrom(GENE_WARPED, 0x02)])
	expect(GENE_WARPED in d.codes(0, "mzone"), "DM not summoned from the hand")
	expect(not lp_costs(d, n1) and not hints(d, HINT_DMZ_REMOVE, n1), "summon from the hand touched the DMZ")
	return d


@test
def ultimate_offering_normal_summons_dm():
	"""An effect that makes the player Normal Summon (Ultimate Offering) reaches the DM."""
	d = domain_duel()
	add_dm(d, SUMMONED_SKULL)
	setup_lua(d, f"Debug.AddCard({ULTIMATE_OFFERING},0,0,LOCATION_SZONE,2,POS_FACEUP_ATTACK)\n" + mz(GENE_WARPED, 2))
	d.add(GENE_WARPED, 0, "hand")
	filler(d, 0); filler(d, 1)
	begin(d)
	play(d, [SummonFrom(GENE_WARPED, 0x02)])
	expect(not dmz_entry(d, "summon", SUMMONED_SKULL), "Normal Summon not used up")
	n0 = len(d.messages)
	play(d, [Act(ULTIMATE_OFFERING), PickDMZ(SUMMONED_SKULL), Pick(GENE_WARPED)])
	expect(SUMMONED_SKULL in d.codes(0, "mzone"), "Ultimate Offering did not Normal Summon the DM")
	expect(lp_costs(d, n0) == [(0, 500)] and lp(d) == 7500, f"LP costs {lp_costs(d, n0)} (only Ultimate Offering's 500)")
	expect(lua_val(d, "Duel.GetFieldGroupCount(0,LOCATION_EXTRA,0)") == "0", "Extra Deck count")
	return d


@test
def own_summon_proc_without_tributes():
	"""The DM's own SINGLE summon procedure (Normal Summon without Tributing) applies in the DMZ."""
	d = domain_duel()
	add_dm(d, CHARGING_GAIA)
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "summon", CHARGING_GAIA), "Charging Gaia not Normal Summonable without Tributing from the DMZ")
	play(d, [Summon(CHARGING_GAIA, "summon")])
	expect(CHARGING_GAIA in d.codes(0, "mzone"), "Charging Gaia not summoned")
	return d


@test
def cyber_dragon_hand_procedure_condition():
	"""A hand procedure with a condition (Cyber Dragon) follows its condition from the DMZ."""
	d = domain_duel()
	add_dm(d, CYBER_DRAGON)
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(not dmz_entry(d, "spsummon", CYBER_DRAGON), "Cyber Dragon summonable while the opponent controls nothing")
	d2 = domain_duel()
	add_dm(d2, CYBER_DRAGON)
	setup_lua(d2, mz(GENE_WARPED, 2, player=1))
	filler(d2, 0); filler(d2, 1)
	begin(d2)
	expect(dmz_entry(d2, "spsummon", CYBER_DRAGON), "Cyber Dragon not summonable while the opponent controls a monster")
	play(d2, [Summon(CYBER_DRAGON)])
	expect(CYBER_DRAGON in d2.codes(0, "mzone"), "Cyber Dragon not summoned")
	return d2


@test
def synchro_summon_from_dmz():
	d = domain_duel()
	add_dm(d, BLACK_ROSE)
	setup_lua(d, mz(FLAMVELL_GUARD, 1) + mz(SUMMONED_SKULL, 3))
	filler(d, 0); filler(d, 1)
	begin(d)
	expect(dmz_entry(d, "spsummon", BLACK_ROSE), "Synchro DM not Special Summonable from the DMZ")
	play(d, [Summon(BLACK_ROSE), Pick(FLAMVELL_GUARD), Pick(SUMMONED_SKULL)])
	expect(BLACK_ROSE in d.codes(0, "mzone"), "Synchro DM not summoned")
	expect(lua_bool(d, f"Duel.GetFirstMatchingCard(Card.IsCode,0,LOCATION_MZONE,0,nil,{BLACK_ROSE}):IsSummonType(SUMMON_TYPE_SYNCHRO)"),
	       "not a Synchro Summon")
	return d


if __name__ == "__main__":
	res = run_tests(sys.argv[1:] or None)
	w = max(len(n) for n, _, _ in res)
	for name, st, msg in res:
		print(f"{st:5} {name:<{w}} {msg[:900]}")
	print(f"{sum(1 for _, s, _ in res if s == 'PASS')}/{len(res)} passed")
	sys.exit(0 if all(s == "PASS" for _, s, _ in res) else 1)
