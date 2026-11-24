"""Append grids gen.py skipped (including all 3x5 grids) to data6.json
(data5.json with CUBE_N=5).
Each is solved exactly with mb.py: a Breaker win from scratch is added as an
ordinary block; a Maker win is added as conditional, usable only where Breaker
already holds some of its lines (the Rust leaf check solves it against the
dead lines). Appending keeps existing block indices, so templates stay valid."""
import itertools, json
import jsonio
from mb import solve
D = json.load(open(jsonio.DATA))
n = jsonio.N
cells = list(itertools.product(range(n), repeat=3))
idx = {c: i for i, c in enumerate(cells)}
line_sets = [set(l) for l in D["lines"]]
have = {frozenset(b["cells"]) for b in D["blocks"]}
all_dirs = [d for d in itertools.product([-1, 0, 1], repeat=3) if any(d)]
new = {}
for a, b in [(3, 3), (3, 4), (4, 4), (3, 5)]:
    for p in cells:
        for u, v in itertools.permutations(all_dirs, 2):
            cr = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            if cr == (0, 0, 0):
                continue
            pts = [tuple(p[k] + i*u[k] + j*v[k] for k in range(3)) for i in range(a) for j in range(b)]
            if not all(0 <= x < n for q in pts for x in q):
                continue
            B = frozenset(idx[q] for q in pts)
            if len(B) != a*b or B in have or B in new:
                continue
            E = [li for li in range(len(line_sets)) if len(B & line_sets[li]) >= 3]
            if len(E) * 2 > len(B):
                new[B] = E
solved = {}
n_cond = 0
for B, E in sorted(new.items(), key=lambda kv: sorted(kv[0])):
    loc = {c: i for i, c in enumerate(sorted(B))}
    key = (len(B), tuple(sorted(tuple(sorted(loc[c] for c in B & line_sets[li])) for li in E)))
    if key not in solved:
        solved[key] = solve(key[0], [list(e) for e in key[1]])
    cond = not solved[key]
    n_cond += cond
    D["blocks"].append({"cells": sorted(B), "lines": E, "conditional": cond})
jsonio.dump(D, jsonio.DATA)
print(len(new), "blocks added,", n_cond, "of them conditional;", len(solved), "distinct sub-games solved;", len(D["blocks"]), "blocks total")
