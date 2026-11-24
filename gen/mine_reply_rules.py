"""Test simple rules for Breaker's R replies (depths 2 and 3) in 6x6x6 proof files.

usage: python gen/mine_reply_rules.py <proof.txt> [...]

Two tests, both scored on the R records only:
1. Greedy scores over all empty cells: the reply should maximize the score.
   s1 = live lines through the cell holding a Maker mark; es2, es3 = the
   Erdos-Selfridge potential, sum over live lines through the cell of 2 (or
   3) to the number of Maker marks on the line; live = live lines through it.
2. Lexicographic orders of up to three cell features over the candidates
   (empty cells on diagonals without a Breaker mark); a rule predicts a
   reply when every top-ranked candidate lies in the reply's orbit under the
   position's stabilizer.
Prints shares per depth. Findings: docs/patterns.md, Breaker's replies.
"""
import itertools, sys
from collections import Counter
import numpy as np
import cube6 as C

DIAGS = [cells for cells, k in C.LINES if k == 3]
DIAG_OF = {c: i for i, cells in enumerate(DIAGS) for c in cells}
LAYER_RANK = {"core": 0, "mid": 1, "corner": 2}
XYZ = np.array([C.xyz(c) for c in range(C.CELLS)])
INC = C.INC.astype(np.int64)
FEATURES = ["layer", "-s1", "-s2", "-live", "maker on diagonal", "distance to Maker", "-lines shared with Breaker"]


def cells_of(s): return [] if s == "-" else [int(x) for x in s.split(",")]


def records(paths):
    for path in paths:
        for line in open(path, encoding="utf-8"):
            if line[0] == "R":
                f = line.split(" | ")
                yield cells_of(f[1]), cells_of(f[2]), int(f[3])


def main():
    by_depth = {2: [], 3: []}
    greedy = {d: Counter() for d in by_depth}
    for M, B, r in records(sys.argv[1:]):
        d = len(M)
        if d not in by_depth:
            continue
        live = INC[:, B].sum(1) == 0
        mk = INC[:, M].sum(1)
        empty = np.ones(C.CELLS, bool); empty[M] = False; empty[B] = False
        lv, m = INC[live], mk[live]
        scores = {"s1": (lv * (m > 0)[:, None]).sum(0), "es2": (lv * (2.0 ** m)[:, None]).sum(0),
                  "es3": (lv * (3.0 ** m)[:, None]).sum(0), "live": lv.sum(0)}
        greedy[d]["n"] += 1
        for name, s in scores.items():
            s = np.where(empty, s, -1e18)
            greedy[d][name] += s[r] == s.max()
        bd = {DIAG_OF[b] for b in B if b in DIAG_OF}
        feats = {}
        for x in DIAG_OF:
            if x in M or x in B or DIAG_OF[x] in bd:
                continue
            ls = C.CELL_LINES[x]; lvx = [l for l in ls if live[l]]
            feats[x] = (LAYER_RANK[C.diag_layer(x)], -sum(1 for l in lvx if mk[l]), -sum(mk[l] for l in lvx),
                        -len(lvx), sum(1 for y in M if DIAG_OF.get(y) == DIAG_OF[x]),
                        min(int(np.abs(XYZ[x] - XYZ[y]).max()) for y in M),
                        -sum(1 for l in ls if INC[l, B].any()))
        orbit = {int(C.G[g, r]) for g in C.stabilizer(M, B)}
        by_depth[d].append((feats, orbit, r))
    for d, rows in by_depth.items():
        n = greedy[d]["n"]
        print(f"depth {d}: {n} replies; greedy score maximal at the reply:",
              {k: round(float(v) / n, 3) for k, v in greedy[d].items() if k != "n"})
        best = []
        for k in (1, 2, 3):
            for order in itertools.permutations(range(len(FEATURES)), k):
                for signs in itertools.product((1, -1), repeat=k):
                    ok = 0
                    for feats, orbit, r in rows:
                        if r not in feats:
                            continue
                        key = lambda x: tuple(s * feats[x][i] for i, s in zip(order, signs))
                        top = min(key(x) for x in feats)
                        ok += {x for x in feats if key(x) == top} <= orbit
                    best.append((round(ok / len(rows), 3),
                                 [("" if s > 0 else "reversed ") + FEATURES[i] for i, s in zip(order, signs)]))
        best.sort(reverse=True)
        print(f"depth {d}: best lexicographic rules:", best[:3])


if __name__ == "__main__":
    main()
