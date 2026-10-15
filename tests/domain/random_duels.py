#!/usr/bin/env python3
"""Seeded random duels for the Domain engine work.

  random_duels.py digest SEEDS [--domain]   # print one digest line per seed (messages + responses)
  random_duels.py compare BASE_LIB NEW_LIB SEEDS
        non-Domain duels must be identical on both libraries (the Deck Master code is inert)
  random_duels.py explore SEEDS
        Domain duels with random Deck Masters on the current library: crashes, engine errors,
        prompts that cannot be answered and Deck Master Zone invariants are reported

SEEDS is a range like 1-50. Uses the CardScripts tools (EDOPRO_TOOLS) and the databases in
EDOPRO_CDB; the library is $OCGCORE or $EDOPRO_CACHE/libocgcore.so.
"""
import hashlib
import os
import random
import sqlite3
import subprocess
import sys
from pathlib import Path

TOOLS = Path(os.environ.get("EDOPRO_TOOLS",
                            "/home/user/zedja123/cardscripts/.claude/skills/edopro-card-scripting/tools"))
SCRIPTS = TOOLS.parents[3]
DUEL_DOMAIN = 0x2000000000
LOCATION_DECK_MASTER = 0x40000000


def card_pool():
	cdb = None
	for item in os.environ.get("EDOPRO_CDB", "").split(os.pathsep):
		p = Path(item)
		if p.is_dir() and (p / "cards.cdb").exists():
			cdb = p / "cards.cdb"
		elif p.name == "cards.cdb":
			cdb = p
	if not cdb:
		sys.exit("cards.cdb not found in EDOPRO_CDB")
	con = sqlite3.connect(f"file:{cdb}?mode=ro", uri=True)
	main, extra, monsters = [], [], []
	for cid, typ, alias in con.execute("select id,type,alias from datas where ot & 3 and alias = 0 order by id"):
		if typ & 0x4000 or typ & 0x8000000 or not (SCRIPTS / "official" / f"c{cid}.lua").exists():
			continue
		(extra if typ & 0x1 and typ & (0x40 | 0x2000 | 0x800000 | 0x4000000) else main).append(cid)
		if typ & 0x1:
			monsters.append(cid)
	return main, extra, monsters


def deck(rng, main, extra):
	return rng.sample(main, 40), rng.sample(extra, 10)


def run(seed, domain, max_prompts=400):
	sys.path.insert(0, str(TOOLS))
	from duelsim import DUEL_MODE_MR5, DUEL_PSEUDO_SHUFFLE, Duel, RandomPolicy
	main, extra, monsters = card_pool()
	rng = random.Random(seed)
	flags = DUEL_MODE_MR5 | DUEL_PSEUDO_SHUFFLE | (DUEL_DOMAIN if domain else 0)
	d = Duel(seed=seed, flags=flags)
	d.lua("Debug.SetPlayerInfo(0,8000,5,1) Debug.SetPlayerInfo(1,8000,5,1)", "hands.lua")
	dms = []
	for p in (0, 1):
		m, e = deck(rng, main, extra)
		for c in m:
			d.add(c, p, "deck")
		for c in e:
			d.add(c, p, "extra")
		if domain:
			dm = rng.choice(monsters)
			dms.append(dm)
			d.add(dm, p, LOCATION_DECK_MASTER, pos=0x0A)
	d.start()
	pol = RandomPolicy(seed)
	err = None
	try:
		n = d.run(pol, max_prompts=max_prompts)
	except Exception as ex:  # DuelError: loops, unanswerable prompts
		err = f"{type(ex).__name__}: {ex}"
		n = -1
	h = hashlib.sha256()
	for m in d.messages:
		h.update(bytes([m.type]) + m.raw)
	for t in d.trace:
		h.update(repr(t).encode())
	problems = []
	if err and d.retry_log and all(x[0] == "ANNOUNCE_CARD" for x in d.retry_log):
		err = None  # the tools' policy cannot answer filtered card announcements
	if err:
		problems.append(err)
	problems += [f"engine: {e[:200]}" for e in d.errors]
	if domain:
		problems += dmz_invariants(d, dms)
	leaves = sum(1 for m in d.messages if m.name == "HINT" and m.data.get("htype") == 205)
	returns = sum(1 for m in d.messages if m.name == "HINT" and m.data.get("htype") == 204 and m.data["hdata"] >> 32)
	return h.hexdigest()[:16], n, problems, (dms, leaves, returns) if domain else dms


def dmz_invariants(d, dms):
	"""Every DM entry in a prompt or message must read (owner, 0, 0xFF) while it is in the zone."""
	out = []
	for m in d.messages:
		if m.name == "HINT" and m.data.get("htype") in (204, 205):
			p = m.data["player"]
			if (m.data["hdata"] & 0xFFFFFFFF) != dms[p]:
				out.append(f"hint {m.data['htype']} for player {p} names {m.data['hdata'] & 0xFFFFFFFF}, DM is {dms[p]}")
		if m.name == "MOVE":
			for k in ("prev", "cur"):
				x = m.data[k]
				if x["loc"] == 0 and x["seq"] == 0xFF and m.data["code"] not in dms:
					out.append(f"non-DM card {m.data['code']} moved through the DMZ marker")
	return out


def child(args):
	mode, seed = args[0], int(args[1])
	digest, n, problems, dms = run(seed, mode == "domain")
	print(f"{seed} {digest} prompts={n} dms={dms} problems={len(problems)}")
	for p in problems[:5]:
		print("   ", p)


def seeds(spec):
	a, _, b = spec.partition("-")
	return range(int(a), int(b or a) + 1)


def spawn(seed, domain, lib=None):
	env = dict(os.environ)
	if lib:
		env["OCGCORE"] = lib
	r = subprocess.run([sys.executable, __file__, "_child", "domain" if domain else "plain", str(seed)],
	                   capture_output=True, text=True, env=env, timeout=600)
	if r.returncode != 0:
		return f"{seed} CRASH rc={r.returncode} {r.stderr[-300:]}"
	return r.stdout.strip()


def main():
	if len(sys.argv) >= 2 and sys.argv[1] == "_child":
		return child(sys.argv[2:])
	cmd = sys.argv[1] if len(sys.argv) > 1 else ""
	if cmd == "digest":
		for s in seeds(sys.argv[2]):
			print(spawn(s, "--domain" in sys.argv))
	elif cmd == "compare":
		base, new, rng_ = sys.argv[2], sys.argv[3], sys.argv[4]
		diff = 0
		for s in seeds(rng_):
			a, b = spawn(s, False, base), spawn(s, False, new)
			same = a.split()[:3] == b.split()[:3]
			diff += not same
			print(("same " if same else "DIFF ") + b.splitlines()[0])
			if not same:
				print("   base:", a.splitlines()[0])
		print(f"{diff} differing duels")
		sys.exit(1 if diff else 0)
	elif cmd == "explore":
		bad = 0
		for s in seeds(sys.argv[2]):
			out = spawn(s, True)
			first = out.splitlines()[0] if out else f"{s} no output"
			if "CRASH" in out or "problems=0" not in first:
				bad += 1
			print(out)
		print(f"{bad} duels with problems")
		sys.exit(1 if bad else 0)
	else:
		print(__doc__)


if __name__ == "__main__":
	main()
