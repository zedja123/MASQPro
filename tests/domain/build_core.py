#!/usr/bin/env python3
"""Incremental build of libocgcore.so from this worktree's ocgcore/ for the Domain tests.

Same flags as the CardScripts `loadcheck.py setup` build (C++17, -fno-rtti, hidden
visibility), plus the warnings of the client build (-Wall -Wextra -pedantic). Only two
compiler jobs run at a time. Output: $EDOPRO_CACHE/libocgcore.so (default
/tmp/claude-0/cache-core), the library the CardScripts duel tools load.

  build_core.py            # rebuild what changed
  build_core.py --clean    # rebuild everything
"""
import concurrent.futures as cf
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "ocgcore"
CACHE = Path(os.environ.get("EDOPRO_CACHE", "/tmp/claude-0/cache-core"))
OBJ = CACHE / "obj-domain"
LIB = CACHE / "libocgcore.so"
LUA = ROOT / "lua" / "src"
LUA_EXCLUDE = {"lbitlib", "lcorolib", "ldblib", "linit", "loadlib", "loslib", "ltests", "lua", "luac",
               "lutf8lib", "onelua"}
JOBS = 2


def jobs(clean):
	OBJ.mkdir(parents=True, exist_ok=True)
	headers = max(p.stat().st_mtime for p in list(ROOT.glob("*.h")) + list(ROOT.glob("RNG/*.hpp")))
	out = []
	conf = ROOT / "lua" / "luaconf-customize.h"
	for f in sorted(LUA.glob("*.c")):
		if f.stem in LUA_EXCLUDE:
			continue
		o = OBJ / f"lua_{f.stem}.o"
		if clean or not o.exists() or o.stat().st_mtime < f.stat().st_mtime:
			cmd = ["g++", "-x", "c++", "-O2", "-fPIC", "-I", str(LUA)]
			if conf.is_file():
				cmd += ["-include", str(conf)]
			out.append((f, cmd + ["-c", str(f), "-o", str(o)]))
	for f in sorted(list(ROOT.glob("*.cpp")) + list(ROOT.glob("RNG/*.cpp"))):
		o = OBJ / f"core_{f.stem}.o"
		if clean or not o.exists() or o.stat().st_mtime < max(f.stat().st_mtime, headers):
			out.append((f, ["g++", "-std=c++17", "-O2", "-fPIC", "-fno-rtti", "-DOCGCORE_EXPORT_FUNCTIONS",
			                "-fvisibility=hidden", "-Wall", "-Wextra", "-pedantic", "-Wno-unused-parameter",
			                "-I", str(LUA), "-c", str(f), "-o", str(o)]))
	return out


def known_warning(src, line):
	"""Warnings already present before the Domain work (MASQPro summon messages)."""
	return src.name == "operations.cpp" and "unused variable" in line and "message" in line


def main():
	todo = jobs("--clean" in sys.argv)
	warnings = []
	with cf.ThreadPoolExecutor(max_workers=JOBS) as ex:
		for (src, _), r in zip(todo, ex.map(lambda j: subprocess.run(j[1], capture_output=True, text=True), todo)):
			if r.returncode != 0:
				sys.exit(f"compile failed: {src}\n{r.stderr[-4000:]}")
			if src.parent.name != "src":
				warnings += [w for w in r.stderr.splitlines() if "warning:" in w and not known_warning(src, w)]
	subprocess.run(["g++", "-shared", "-o", str(LIB), *map(str, sorted(OBJ.glob("*.o"))),
	                "-static-libgcc", "-static-libstdc++", "-Wl,--no-undefined"], check=True)
	print(f"built {LIB} ({len(todo)} files compiled)")
	if warnings:
		print("NEW WARNINGS:\n" + "\n".join(warnings))
		sys.exit(2)


if __name__ == "__main__":
	main()
