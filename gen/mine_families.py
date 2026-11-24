"""Relate leaf block layouts to the search's templates and blocks.

usage: python gen/mine_families.py <out_dir> [data6.json]

Reads <out_dir>/layouts.pkl from gen/mine.py. A template (data6.json) is a
block layout the search starts from; at a leaf it may drop blocks Maker
spoiled or add blocks (augment, repair in src/). For each canonical leaf
layout, in its most used orientation, this finds the template view (48
geometric images of each template) sharing the most blocks, and reports how
leaf layouts differ from their nearest template and how many templates
("families") cover the leaves. Also ranks blocks by the lines they claim.
Writes <out_dir>/families.json. Findings: docs/patterns.md.
"""
import json, os, pickle, sys
from collections import Counter
import numpy as np
import scipy.sparse as sp
import cube6 as C


def main():
    out_dir = sys.argv[1]
    data = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "data6.json"))
    d = pickle.load(open(os.path.join(out_dir, "layouts.pkl"), "rb"))
    blocks = [tuple(sorted(b["cells"])) for b in data["blocks"]]
    bid = {b: i for i, b in enumerate(blocks)}
    syms = data["syms"]
    views = []  # (template index, block ids)
    for t, tpl in enumerate(data["templates"]):
        for s in syms:
            ids = [bid.get(tuple(sorted(s[c] for c in blocks[i]))) for i in tpl]
            if None not in ids:
                views.append((t, ids))
    nb = len(blocks)
    V = sp.csr_matrix((np.ones(sum(len(v) for _, v in views), np.float32),
                       ([k for k, (_, v) in enumerate(views) for _ in v], [i for _, v in views for i in v])),
                      shape=(len(views), nb))
    vsize = np.array([len(v) for _, v in views])
    keys = list(d["layouts"])
    leaves = np.array([sum(d["layouts"][k].values()) for k in keys])
    L = leaves.sum()
    lay_ids = [[bid.get(b) for b in d["sample"][k]] for k in keys]
    outside = np.array([sum(i is None for i in ids) for ids in lay_ids])  # blocks not in the library
    rows = [k for k, ids in enumerate(lay_ids) for i in ids if i is not None]
    cols = [i for ids in lay_ids for i in ids if i is not None]
    Lm = sp.csr_matrix((np.ones(len(rows), np.float32), (rows, cols)), shape=(len(keys), nb))
    shared = np.zeros(len(keys), int); best = np.zeros(len(keys), int)
    for a in range(0, len(keys), 500):
        prod = (Lm[a:a + 500] @ V.T).toarray()
        # most shared blocks, then the smallest template view
        score = prod * 1000 - vsize[None, :]
        j = score.argmax(1)
        best[a:a + 500] = j; shared[a:a + 500] = prod[np.arange(len(j)), j]
    size = np.array([len(ids) for ids in lay_ids])
    extra = size - shared            # leaf blocks not in the nearest template
    missing = vsize[best] - shared   # template blocks the leaf dropped
    w = lambda mask: round(float(leaves[mask].sum() / L), 4)
    fam = Counter()
    for k in range(len(keys)):
        fam[views[best[k]][0]] += leaves[k]
    run = 0; need = {}
    for n, (_, v) in enumerate(fam.most_common(), 1):
        run += v
        for s in (0.5, 0.9, 0.99, 1.0):
            if str(s) not in need and run >= s * L - 1e-9:
                need[str(s)] = n
    # block work: share of block-claimed lines per canonical block
    bu, bc = d["block_use"], d["block_claims"]
    claims = sum(bc.values())
    ranked = sorted(bc.items(), key=lambda kv: -kv[1])
    top = []
    for cb, n in ranked[:12]:
        use = sum(bu[cb].values())
        top.append({"cells": len(cb), "lines_claimed_per_use": round(n / use, 2),
                    "uses_per_leaf": round(use / L, 2), "share_of_block_lines": round(n / claims, 4)})
    cum = np.cumsum([n for _, n in ranked]) / claims
    res = {
        "templates": len(data["templates"]), "template_views": len(views),
        "leaf_layout_equals_a_template": w((extra == 0) & (missing == 0)),
        "leaf_layout_is_template_minus_blocks": w((extra == 0) & (missing > 0)),
        "leaf_layout_adds_blocks": w(extra > 0),
        "leaf_blocks_outside_library": w(outside > 0),
        "blocks_added_to_nearest_template": {int(k): w(extra == k) for k in sorted(set(extra))},
        "blocks_dropped_from_nearest_template": {int(k): w(missing == k) for k in sorted(set(missing))},
        "templates_used_as_nearest": len(fam),
        "templates_to_cover_share": need,
        "top_template_share": [round(v / L, 4) for _, v in fam.most_common(5)],
        "blocks_to_cover_share_of_block_lines": {s: int(np.searchsorted(cum, s - 1e-9) + 1) for s in (0.5, 0.9, 0.99)},
        "distinct_blocks": len(ranked),
        "top_blocks_by_lines_claimed": top,
    }
    s = json.dumps(res, indent=1)
    print(s)
    open(os.path.join(out_dir, "families.json"), "w").write(s)


if __name__ == "__main__":
    main()
