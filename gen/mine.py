"""Leaf-certificate statistics over 6x6x6 proof files (docs/proof-format.md).

usage: python gen/mine.py <out_dir> <label>=<proof.txt> [<label>=<proof.txt> ...]

Streams each file once (one process per file), then reduces block layouts
under the full 1,152-element group G (gen/cube6.py) with a process pool.
Writes <out_dir>/leaves.json (per-orbit and combined numbers) and
<out_dir>/layouts.pkl (canonical layout -> leaf count per orbit, and the
canonical blocks) for gen/mine_families.py. Findings: docs/patterns.md.
Breaker's replies are mined separately by gen/mine_replies.py.
"""
import json, os, pickle, sys
from collections import Counter
from multiprocessing import Pool
import numpy as np
import cube6 as C

WORKERS = 6  # laptop budget: 6 of 8 cores


def cells_of(s): return () if s == "-" else tuple(int(x) for x in s.split(","))


def shape(cells):
    pts = [C.xyz(c) for c in cells]
    ext = sorted(len({p[i] for p in pts}) for i in range(3))  # distinct values per axis
    return f"{ext[0]}x{ext[1]}x{ext[2]}"


def scan(arg):
    """One pass over a proof file: counters plus exact layouts by block id."""
    label, path = arg
    st = Counter(); depth = Counter(); nblocks = Counter(); npairs = Counter()
    shapes = Counter(); free = Counter(); cover = Counter(); reply_deg = Counter()
    maker_in_blocks = Counter(); block_cells = Counter()
    block_id = {}; block_lines = Counter(); layouts = Counter()
    for line in open(path, encoding="utf-8"):
        if line[0] != "L":
            if line[0] == "R":
                st["R"] += 1
            continue
        f = line.rstrip("\n").split(" | ")
        M, B, r = cells_of(f[1]), cells_of(f[2]), int(f[3])
        st["L"] += 1; depth[len(M)] += 1; reply_deg[int(C.DEG[r])] += 1
        ids = []; used = set()
        if f[4] != "-":
            for e in f[4].split(" ; "):
                cs, ls = e.split(" : ")
                cells = cells_of(cs); used.update(cells)
                bid = block_id.setdefault(cells, len(block_id)); ids.append(bid)
                claimed = ls.split(",")
                block_lines[bid] += len(claimed)
                shapes[shape(cells)] += 1
                for t in claimed:
                    a, b = (int(x) for x in t.split("/"))
                    cover["block:" + C.LINE_KIND[C.line_of(a, b)]] += 1
        pairs = [] if f[5] == "-" else f[5].split(" ; ")
        for p in pairs:
            a, b = (int(x) for x in p.split("/"))
            cover["pair:" + C.LINE_KIND[C.line_of(a, b)]] += 1
            used.update((a, b))
        Bf = set(B); Bf.add(r)
        cover["dead"] += int((C.INC[:, list(Bf)].sum(1) > 0).sum())
        nblocks[len(ids)] += 1; npairs[len(pairs)] += 1
        free[C.CELLS - len(M) - len(Bf) - len(used - Bf - set(M))] += 1
        maker_in_blocks[len(used & set(M))] += 1
        block_cells[len(used) - 2 * len(pairs)] += 1
        st["reply inside certificate"] += r in used
        layouts[tuple(sorted(ids))] += 1
    blocks = [None] * len(block_id)
    for cells, i in block_id.items():
        blocks[i] = cells
    return label, dict(st=st, depth=depth, nblocks=nblocks, npairs=npairs, shapes=shapes,
                       free=free, cover=cover, reply_deg=reply_deg,
                       maker_in_blocks=maker_in_blocks, block_cells=block_cells,
                       block_lines=block_lines, layouts=layouts, blocks=blocks)


def canon_chunk(chunk):
    return [C.canon_layout(bl)[0] for bl in chunk]


def mean(c): return round(sum(k * v for k, v in c.items()) / max(1, sum(c.values())), 2)


def coverage(counts, total, shares=(0.5, 0.7, 0.9, 0.95, 0.99, 1.0)):
    """Layouts needed (most common first) to cover each share of leaves."""
    out, run, k = {}, 0, 0
    vals = sorted(counts, reverse=True)
    for s in shares:
        while run < s * total - 1e-9:
            run += vals[k]; k += 1
        out[str(s)] = k
    return out


def main():
    out_dir, specs = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
    os.makedirs(out_dir, exist_ok=True)
    with Pool(min(WORKERS, len(specs))) as p:
        scans = dict(p.map(scan, specs))
    # canonical blocks and layouts under G
    canon_block = {}
    exact = []  # (label, tuple of cell tuples, count)
    for label, s in scans.items():
        for k, n in s["layouts"].items():
            exact.append((label, tuple(s["blocks"][i] for i in k), n))
        for cells in s["blocks"]:
            if cells not in canon_block:
                canon_block[cells] = C.canon_set(cells)
    uniq = sorted({bl for _, bl, _ in exact})
    chunks = [uniq[i:i + 500] for i in range(0, len(uniq), 500)]
    with Pool(WORKERS) as p:
        keys = [k for part in p.map(canon_chunk, chunks) for k in part]
    key_of = dict(zip(uniq, keys))
    per_layout = {}  # canonical key -> Counter(label -> leaves)
    sample = {}      # canonical key -> its most used exact orientation (blocks)
    for label, bl, n in sorted(exact, key=lambda e: -e[2]):
        per_layout.setdefault(key_of[bl], Counter())[label] += n
        sample.setdefault(key_of[bl], bl)
    block_use = {}  # canonical block -> Counter(label -> leaves using it)
    block_claims = Counter()
    for label, s in scans.items():
        use = Counter()
        for k, n in s["layouts"].items():
            for i in k:
                use[i] += n
        for i, n in use.items():
            cb = canon_block[s["blocks"][i]]
            block_use.setdefault(cb, Counter())[label] += n
            block_claims[cb] += s["block_lines"][i]

    labels = [l for l, _ in specs]
    res = {}
    for label in labels + ["all"]:
        sel = labels if label == "all" else [label]
        tot = lambda key: sum((scans[l][key] for l in sel), Counter())
        st = tot("st"); L = st["L"]
        lay = [sum(c[l] for l in sel) for c in per_layout.values()]
        lay = [n for n in lay if n]
        cover = tot("cover")
        blocks_used = {b: sum(c[l] for l in sel) for b, c in block_use.items()}
        blocks_used = {b: n for b, n in blocks_used.items() if n}
        res[label] = {
            "leaves": L, "replies_R": st["R"],
            "leaf_depth": dict(sorted(tot("depth").items())),
            "blocks_per_leaf_mean": mean(tot("nblocks")), "blocks_per_leaf": dict(sorted(tot("nblocks").items())),
            "pairs_per_leaf_mean": mean(tot("npairs")),
            "pairs_per_leaf_range": [min(tot("npairs")), max(tot("npairs"))],
            "unused_empty_cells_mean": mean(tot("free")),
            "block_cells_mean": mean(tot("block_cells")),
            "maker_marks_inside_blocks": {k: round(v / L, 4) for k, v in sorted(tot("maker_in_blocks").items())},
            "leaf_reply_lines_through_cell": dict(tot("reply_deg")),
            "leaf_reply_inside_certificate": round(st["reply inside certificate"] / L, 4),
            "block_shapes_distinct_values": dict(tot("shapes").most_common()),
            "lines_per_leaf": {k: round(v / L, 2) for k, v in sorted(cover.items())},
            "distinct_blocks_G": len(blocks_used),
            "distinct_layouts_G": len(lay),
            "layouts_to_cover_share": coverage(lay, L),
            "share_top_layouts": {k: round(sum(sorted(lay, reverse=True)[:k]) / L, 4)
                                  for k in (1, 10, 100, 1000, 10000)},
            "layouts_used_once": sum(1 for n in lay if n == 1),
        }
    shared = Counter(frozenset(l for l in labels if c[l]) for c in per_layout.values())
    res["cross_orbit"] = {
        "layouts_by_orbits_using_them": {"+".join(sorted(k)): v for k, v in shared.items()},
        "leaves_whose_layout_is_used_in_another_orbit": {
            l: round(sum(c[l] for c in per_layout.values() if c[l] and len([m for m in labels if c[m]]) > 1)
                     / res[l]["leaves"], 4) for l in labels},
        "blocks_by_orbits_using_them": {"+".join(sorted(k)): v for k, v in
                                        Counter(frozenset(l for l in labels if c[l]) for c in block_use.values()).items()},
    }
    s = json.dumps(res, indent=1)
    print(s)
    open(os.path.join(out_dir, "leaves.json"), "w").write(s)
    with open(os.path.join(out_dir, "layouts.pkl"), "wb") as fh:
        pickle.dump({"labels": labels, "layouts": per_layout, "sample": sample, "block_use": block_use,
                     "block_claims": block_claims}, fh)


if __name__ == "__main__":
    main()
