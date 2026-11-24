"""Fit sets on a sample of reached leaves (minimum-catalogue job, docs/leaf-catalogue.md).

usage: python gen/mincat_scout.py <reach.npz> <layouts.pkl> <data6.json> <out.json>
                                  <n_leaves | leaves.npy> <pool> [seed] [--workers N]

Draws n_leaves reached leaves at random (gen/mincat_reach.py output), or
takes the leaf indices in leaves.npy, and,
for each, the exact set of the first <pool> catalogue layouts (most used
first) that fit it in some orientation (gen/mincat_fit.py). Three worker
processes (the laptop budget for this job).
"""
import json, sys, time
from multiprocessing import Pool
import numpy as np
import mincat_fit as F

WORKERS = 3
_CAT = None


def init(pkl, data6, pool):
    global _CAT
    cat, _ = F.load_catalogue(pkl, data6)
    _CAT = F.Catalogue(cat[:pool])


def fit_set(leaf):
    M, B = leaf
    t0 = time.time()
    g, k, dead = _CAT.views(B)
    keep, _, _ = _CAT.prefilter(M, g, k, dead)
    fits, tries = [], 0
    g, k = g[keep], k[keep]
    order = np.argsort(k, kind="stable")
    g, k = g[order], k[order]
    starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    ends = np.r_[starts[1:], len(k)]
    for a, b in zip(starts, ends):
        for gg in g[a:b]:
            tries += 1
            if _CAT.fit_map(int(k[a]), int(gg), M, B) is not None:
                fits.append(int(k[a]))
                break
    return {"M": list(M), "B": list(B), "fits": fits, "tries": tries, "s": round(time.time() - t0, 2)}


def leaves_of(npz):
    d = np.load(npz)
    return [(tuple(int(c) for c in m if c >= 0), tuple(int(c) for c in b if c >= 0)) for m, b in zip(d["M"], d["B"])]


def main():
    args = sys.argv[1:]
    workers = WORKERS
    if "--workers" in args:
        i = args.index("--workers"); workers = int(args[i + 1]); del args[i:i + 2]
    npz, pkl, data6, out, n, pool = args[:6]
    seed = int(args[6]) if len(args) > 6 else 0
    leaves = leaves_of(npz)
    if n.endswith(".npy"):
        pick = np.load(n)
    else:
        pick = np.random.default_rng(seed).choice(len(leaves), int(n), replace=False)
    with Pool(workers, init, (pkl, data6, int(pool))) as p:
        res = []
        for i, r in enumerate(p.imap(fit_set, [leaves[i] for i in pick])):
            r["index"] = int(pick[i]); res.append(r)
            if i % 20 == 0:
                print(i, len(r["fits"]), r["tries"], r["s"], flush=True)
    json.dump(res, open(out, "w"))
    nf = [len(r["fits"]) for r in res]
    print(f"leaves {len(res)}, fits per leaf min {min(nf)} median {int(np.median(nf))} max {max(nf)}")


if __name__ == "__main__":
    main()
