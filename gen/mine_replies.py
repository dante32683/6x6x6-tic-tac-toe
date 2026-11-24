"""Breaker's replies in 6x6x6 proof files: where they go and which rules predict them.

usage: python gen/mine_replies.py <out_dir> <label>=<proof.txt> [...]

Every record (R and L) holds one Breaker reply r at a position (M, B) with
Breaker to move. For each reply this counts, by depth |M|:
- whether r is on a space diagonal, and on which layer ("core" = coordinates
  in {2,3}, "mid" = {1,4}, "corner" = {0,5}) in the file's orientation;
- whether r's diagonal had no Breaker mark yet ("new diagonal") and no
  Maker mark;
- three candidate rules, each a set of cells: A = empty cells on new
  diagonals; B = A on the depth's usual layer (LAYER_RULE); C = B on
  diagonals without Maker marks. A rule "determines" the reply when r is in
  the set and the set is one orbit of the position's stabilizer in G.
For leaves it also counts Breaker's final marks B + r up to G.
Writes <out_dir>/replies.json. Findings: docs/patterns.md.
"""
import json, os, sys
from collections import Counter
from multiprocessing import Pool
import cube6 as C

WORKERS = 6
LAYER_RULE = {1: "core", 2: "mid", 3: "core", 4: "core"}  # most common layer per depth
DIAGS = [cells for cells, k in C.LINES if k == 3]
DIAG_OF = {c: i for i, cells in enumerate(DIAGS) for c in cells}


def cells_of(s): return [] if s == "-" else [int(x) for x in s.split(",")]


def scan(arg):
    label, path = arg
    by = {}  # (kind, depth) -> Counter
    finals = Counter(); canon = {}; dead = Counter()
    for line in open(path, encoding="utf-8"):
        kind = line[0]
        if kind not in "RL":
            continue
        f = line.split(" | ", 4)
        M, B, r = cells_of(f[1]), cells_of(f[2]), int(f[3])
        d = len(M)
        c = by.setdefault(f"{kind}{d}", Counter())
        c["n"] += 1
        layer = C.diag_layer(r)
        c[f"layer {layer}"] += 1
        bd = {DIAG_OF[b] for b in B if b in DIAG_OF}
        md = {DIAG_OF[m] for m in M if m in DIAG_OF}
        taken = set(M) | set(B)
        A = [x for x in DIAG_OF if x not in taken and DIAG_OF[x] not in bd]
        Bset = [x for x in A if C.diag_layer(x) == LAYER_RULE[d]]
        Cset = [x for x in Bset if DIAG_OF[x] not in md]
        if layer:
            c["new diagonal"] += DIAG_OF[r] not in bd
            c["diagonal without Maker mark"] += DIAG_OF[r] not in md
        stab = None
        for name, cand in (("A", A), ("B", Bset), ("C", Cset)):
            if r not in cand:
                continue
            c[f"rule {name} contains reply"] += 1
            if stab is None:
                stab = C.stabilizer(M, B)
            orbit = {int(C.G[g, r]) for g in stab}
            if set(cand) <= orbit:
                c[f"rule {name} determines reply"] += 1
        if kind == "L":
            Bf = tuple(sorted(B + [r]))
            if Bf not in canon:
                canon[Bf] = C.canon_set(Bf)
            finals[canon[Bf]] += 1
            dead[int((C.INC[:, list(Bf)].sum(1) > 0).sum())] += 1
    return label, by, finals, dead


def main():
    out_dir, specs = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
    with Pool(min(WORKERS, len(specs))) as p:
        parts = p.map(scan, specs)
    res = {}
    allf = Counter(); alld = Counter(); allby = {}
    for label, by, finals, dead in parts:
        allf += finals; alld += dead
        for k, c in by.items():
            allby.setdefault(k, Counter()).update(c)
        res[label] = {k: {a: (v if a == "n" else round(v / c["n"], 4)) for a, v in sorted(c.items())}
                      for k, c in sorted(by.items())}
        L = sum(finals.values())
        res[label]["final_breaker_sets_G"] = {"distinct": len(finals),
                                              "top": [round(v / L, 4) for _, v in finals.most_common(10)]}
    L = sum(allf.values())
    run = 0; need = {}
    for k, (_, v) in enumerate(allf.most_common(), 1):
        run += v
        for s in (0.5, 0.9, 0.99, 1.0):
            if str(s) not in need and run >= s * L - 1e-9:
                need[str(s)] = k
    res["all"] = {k: {a: (v if a == "n" else round(v / c["n"], 4)) for a, v in sorted(c.items())}
                  for k, c in sorted(allby.items())}
    res["all"]["final_breaker_sets_G"] = {
        "distinct": len(allf), "sets_to_cover_share": need,
        "top": [[[C.xyz(x) for x in k], round(v / L, 4)] for k, v in allf.most_common(10)]}
    res["all"]["dead_lines_at_leaf"] = dict(sorted(alld.items()))
    s = json.dumps(res, indent=1)
    print(s)
    open(os.path.join(out_dir, "replies.json"), "w").write(s)


if __name__ == "__main__":
    main()
