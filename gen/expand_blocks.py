"""Append every block's images under the cube's full automorphism group
(1,152 maps for 6x6x6; docs/proof-format.md) to data6.json (data5.json with
CUBE_N=5). An automorphism maps lines
to lines, so the image of a Breaker-win block is a Breaker-win block on
scattered cells that gen.py's grid search never finds. Appending keeps
existing block indices, so templates stay valid.
usage: python gen/expand_blocks.py   (edits the data file in place; back it up)"""
import itertools, json, math
import jsonio
D = json.load(open(jsonio.DATA))
n = jsonio.N
idx = {c: i for i, c in enumerate(itertools.product(range(n), repeat=3))}
coord = {i: c for c, i in idx.items()}
flip = lambda v: n - 1 - v
# value permutations of 0..n-1 that commute with v -> n-1-v (48 for n = 6)
vals = [p for p in itertools.permutations(range(n)) if all(p[flip(v)] == flip(p[v]) for v in range(n))]
group = set()
for axes in itertools.permutations(range(3)):
    for p in vals:
        for refl in itertools.product([False, True], repeat=3):
            m = []
            for i in range(n ** 3):
                c = coord[i]
                m.append(idx[tuple(flip(p[c[axes[k]]]) if refl[k] else p[c[axes[k]]] for k in range(3))])
            group.add(tuple(m))
lines = [frozenset(l) for l in D["lines"]]
line_id = {l: i for i, l in enumerate(lines)}
# |G| = 2^(2 + n/2) * 6 * (n/2)!, the verifier's GROUP_SIZE (1,152 for n = 6, 192 for n = 5)
assert len(group) == 2 ** (2 + n // 2) * 6 * math.factorial(n // 2) and all(frozenset(g[c] for c in l) in line_id for g in group for l in lines)
have = {frozenset(b["cells"]): sorted(b["lines"]) for b in D["blocks"]}
added = 0
for b in list(D["blocks"]):
    for g in group:
        cells = frozenset(g[c] for c in b["cells"])
        ls = sorted(line_id[frozenset(g[c] for c in lines[li])] for li in b["lines"])
        if cells in have:
            # one block per cell set (the Rust loader indexes blocks by cells)
            continue
        have[cells] = ls
        D["blocks"].append({"cells": sorted(cells), "lines": ls, "conditional": b.get("conditional", False)})
        added += 1
jsonio.dump(D, jsonio.DATA)
print(len(group), "automorphisms;", added, "blocks added;", len(D["blocks"]), "total")
