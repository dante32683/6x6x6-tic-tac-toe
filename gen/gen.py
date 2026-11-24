"""Build the data for the n x n x n Maker-Breaker search (default n = 6).

usage: python gen/gen.py [templates] [seconds per template] [n]
Writes data<n>.json with:
  lines:     the ((n+2)^3 - n^3)/2 winning lines (148 for n = 6), each a list of
             n cell ids (id = x*n*n + y*n + z)
  blocks:    small grids where Breaker provably wins the sub-game (exact search in
             mb.py), each with its cells and the lines it covers
  syms:      the 48 symmetries of the cube as cell permutations
  templates: block sets from the "free marks" optimizer, used as starting layouts

The free-mark count of the best template is how many Breaker cells beyond
the blocks and pairs a cover of every line needs on the empty board, a first
measure of how many rounds the opening search must supply.
"""
import itertools, json, os, random, sys
from ortools.sat.python import cp_model
from mb import solve

n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
# the data file also holds templates learned by harvesting (gen/merge.py),
# which this script can't regenerate
if os.path.exists(f"data{n}.json"):
    raise SystemExit(f"data{n}.json exists and may hold learned templates; move it aside to regenerate")
cells = list(itertools.product(range(n), repeat=3))
idx = {c: i for i, c in enumerate(cells)}
line_dirs = [d for d in itertools.product([-1, 0, 1], repeat=3) if any(d) and next(x for x in d if x) > 0]
lines = []
for d in line_dirs:
    for p in cells:
        pts = [tuple(p[i] + k * d[i] for i in range(3)) for k in range(n)]
        if all(0 <= x < n for q in pts for x in q):
            lines.append([idx[q] for q in pts])
line_sets = [set(l) for l in lines]

# cube symmetries: axis permutation then optional reflection of each axis
syms = []
for perm in itertools.permutations(range(3)):
    for flips in itertools.product([False, True], repeat=3):
        m = []
        for c in cells:
            q = [c[perm[k]] for k in range(3)]
            q = [n - 1 - q[k] if flips[k] else q[k] for k in range(3)]
            m.append(idx[tuple(q)])
        syms.append(m)
line_index = {frozenset(l): i for i, l in enumerate(lines)}
for s in syms:  # every symmetry must map lines to lines
    assert all(frozenset(s[c] for c in l) in line_index for l in lines)

# blocks: a x b grids along two directions; edges = lines meeting the grid in >= 3
# cells. Keep the block if Breaker (moving second) wins with all those edges, or
# failing that with only the grid's rows and columns.
all_dirs = [d for d in itertools.product([-1, 0, 1], repeat=3) if any(d)]
solve_cache = {}
def breaker_wins(B, E):
    loc = {c: i for i, c in enumerate(sorted(B))}
    key = (len(B), tuple(sorted(tuple(sorted(loc[c] for c in e)) for e in E)))
    if key not in solve_cache:
        solve_cache[key] = solve(len(B), [list(e) for e in key[1]])
    return solve_cache[key]
blocks = {}
for a, b in [(3, 3), (3, 4), (4, 4)]:
    for p in cells:
        for u, v in itertools.permutations(all_dirs, 2):
            cr = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            if cr == (0, 0, 0):
                continue
            pts = [tuple(p[k] + i*u[k] + j*v[k] for k in range(3)) for i in range(a) for j in range(b)]
            if not all(0 <= x < n for q in pts for x in q):
                continue
            B = frozenset(idx[q] for q in pts)
            if len(B) != a*b or B in blocks:
                continue
            rows = {frozenset(idx[tuple(p[k]+i*u[k]+j*v[k] for k in range(3))] for j in range(b)) for i in range(a)}
            cols = {frozenset(idx[tuple(p[k]+i*u[k]+j*v[k] for k in range(3))] for i in range(a)) for j in range(b)}
            inter = [(li, frozenset(B & line_sets[li])) for li in range(len(lines)) if len(B & line_sets[li]) >= 3]
            rc = [(li, s) for li, s in inter if s in rows or s in cols]
            for E in (inter, rc):
                # only useful if it beats pairs (more than one line per two cells)
                if len(E) * 2 > len(B) and breaker_wins(B, [s for _, s in E]):
                    blocks[B] = sorted(li for li, _ in E)
                    break
block_list = sorted(blocks.items(), key=lambda kv: sorted(kv[0]))
print(len(lines), "lines,", len(block_list), "blocks,", len(solve_cache), "distinct sub-games solved", flush=True)

# templates: minimize free Breaker marks so blocks + pairs cover every line;
# keep the block sets, diversified with random tie-breaking and no-good cuts
def template_model(rng, previous):
    m = cp_model.CpModel()
    x = [m.NewBoolVar("") for _ in cells]
    use = {c: [x[c]] for c in range(len(cells))}
    cover = {li: [x[c] for c in l] for li, l in enumerate(lines)}
    for li, l in enumerate(lines):
        for a_, b_ in itertools.combinations(l, 2):
            y = m.NewBoolVar(""); cover[li].append(y); use[a_].append(y); use[b_].append(y)
    z = []
    for B, E in block_list:
        v = m.NewBoolVar(""); z.append(v)
        for c in B: use[c].append(v)
        for li in E: cover[li].append(v)
    for li in cover: m.AddBoolOr(cover[li])
    for c in use: m.AddAtMostOne(use[c])
    for prev in previous:
        m.Add(sum(z[i] for i in prev) <= len(prev) - 2)
    # main goal: few free marks; small random weights spread the solutions
    m.Minimize(1000 * sum(x) - sum(rng.randint(0, 20) * z[i] for i in range(len(z))))
    return m, x, z

rng = random.Random(1)
templates = []
count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 30
for t in range(count):
    m, x, z = template_model(rng, templates)
    s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = secs; s.parameters.num_workers = 16
    s.parameters.random_seed = t
    r = s.Solve(m)
    if r not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        break
    chosen = [i for i in range(len(z)) if s.Value(z[i])]
    marks = sum(s.Value(v) for v in x)
    templates.append(chosen)
    print(f"template {t}: {len(chosen)} blocks, {marks} free marks", flush=True)

json.dump({
    "n": n, "lines": lines, "syms": syms,
    "blocks": [{"cells": sorted(B), "lines": E} for B, E in block_list],
    "templates": templates,
}, open(f"data{n}.json", "w"))
print(f"wrote data{n}.json")
