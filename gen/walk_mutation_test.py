"""Walk-level mutation test: break R records and remove records in a proof
where every record is reached, and check that both checkers reject every
mutant. Leaf certificates have their own mutation tests (gen/mutation_test.py,
verify_py/test_mutations.py, verify_gpt/test_mutations.py); this one covers
the tree walk.

usage: python gen/walk_mutation_test.py <proof> <verify exe> <verify_gpt dir> [count=3] [seed=1]

The test first cuts <proof> down to the orbit O7 walk: `verify full <proof>
--root 0 --emit-used` lists the records the walk from first move 0 reaches,
one per position, and the header plus those lines make `walk-orbit0.txt`
beside <proof>, a proof of O7 in which every record is reached and every
class has exactly one record. O7 is the smallest orbit (about 92,000 leaves),
so each check takes minutes. Every check then runs with --root 0. Mutant
kinds, `count` of each:
  changed reply  an R record's reply moved to another empty cell
  R removed      an R record deleted, so its class has no record
  L removed      an L record deleted, so its class has no record
Every mutant must be rejected; a changed reply could in principle land on a
recorded class, which the report would show as an accepted mutant to look
at by hand."""
import os, random, subprocess, sys, time

ROOT = "0"  # first move 0 is orbit O7, the smallest of the three

proof, verify_exe, gpt_dir = sys.argv[1:4]
count = int(sys.argv[4]) if len(sys.argv) > 4 else 3
rng = random.Random(int(sys.argv[5]) if len(sys.argv) > 5 else 1)
work = os.path.dirname(os.path.abspath(proof))
used_path = os.path.join(work, "walk-orbit0-used.txt")
orbit_path = os.path.join(work, "walk-orbit0.txt")
mpath = os.path.join(work, "walk-mutant.txt")

t = time.time()
cut = subprocess.run([verify_exe, "full", proof, "--root", ROOT, "--emit-used", used_path],
                     capture_output=True, text=True)
if cut.returncode != 0:
    sys.exit(f"verify/ rejects the unmodified proof at --root {ROOT}:\n{cut.stdout}{cut.stderr}")
with open(used_path, encoding="ascii") as f:
    wanted = {int(x) for x in f}
lines = []
with open(proof) as f:
    for n, ln in enumerate(f, 1):
        if ln.startswith("#") or n in wanted:
            lines.append(ln)
with open(orbit_path, "w", newline="\n") as f:
    f.writelines(lines)
os.remove(used_path)
r_idx = [i for i, ln in enumerate(lines) if ln.startswith("R ")]
l_idx = [i for i, ln in enumerate(lines) if ln.startswith("L ")]
print(f"orbit O7 walk: {len(r_idx):,} R and {len(l_idx):,} L records reached "
      f"({time.time() - t:.0f} s)", flush=True)

def changed_reply(i):
    kind, m, b, r = [x.strip() for x in lines[i].split("|")]
    used = {int(x) for s in (m, b) if s != "-" for x in s.split(",")} | {int(r)}
    new = rng.choice([c for c in range(216) if c not in used])
    return f"R | {m} | {b} | {new}\n", f"reply {r} -> {new} in R | {m} | {b}"

def checks(path):
    """(verify/ accepted, verify_gpt/ accepted, seconds, verify/ output, verify_gpt/ output)."""
    t = time.time()
    v = subprocess.run([verify_exe, "full", path, "--root", ROOT], capture_output=True, text=True)
    g = subprocess.run([sys.executable, "-I", "check_cube6.py", path, "--root", ROOT],
                       cwd=gpt_dir, capture_output=True, text=True)
    return v.returncode == 0, g.returncode == 0, time.time() - t, v.stdout + v.stderr, g.stdout + g.stderr

def last(s):
    """The verdict line (FAIL or OK), else the last line."""
    out = s.strip().splitlines() or [""]
    return next((ln for ln in out if "FAIL" in ln or " OK" in ln), out[-1])[:110]

def write(path, i, replacement):
    with open(path, "w", newline="\n") as f:
        f.writelines(lines[:i])
        if replacement is not None:
            f.write(replacement)
        f.writelines(lines[i + 1:])

va, ga, secs, vout, gout = checks(orbit_path)
print(f"unmodified: verify/ {'accepts' if va else 'REJECTS'} ({last(vout)})\n"
      f"  verify_gpt/ {'accepts' if ga else 'REJECTS'} ({last(gout)})  [{secs:.0f} s]", flush=True)
bad = not (va and ga)
plan = ([("changed reply", i) for i in rng.sample(r_idx, count)]
        + [("R removed", i) for i in rng.sample(r_idx, count)]
        + [("L removed", i) for i in rng.sample(l_idx, count)])
for kind, i in plan:
    if kind == "changed reply":
        repl, what = changed_reply(i)
    else:
        repl, what = None, f"deleted {lines[i][:60].strip()}..."
    write(mpath, i, repl)
    va, ga, secs, vout, gout = checks(mpath)
    bad |= va or ga
    print(f"{kind}: {what}\n  verify/ {'rejects' if not va else 'ACCEPTS'} ({last(vout)})\n"
          f"  verify_gpt/ {'rejects' if not ga else 'ACCEPTS'} ({last(gout)})  [{secs:.0f} s]", flush=True)
os.remove(mpath)
print("WALK MUTATION TEST " + ("FAILED" if bad else "OK"))
sys.exit(1 if bad else 0)
