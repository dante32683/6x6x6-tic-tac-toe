"""Re-certify every reached leaf from a reduced catalogue (docs/leaf-catalogue.md).

usage:
  python gen/mincat_rewrite.py fit <reach.npz> <layouts.pkl> <data6.json> <catalogue.json> <out_dir> [<leaf list.npy>]
  python gen/mincat_rewrite.py own <reach.npz> <layouts.pkl> <leaf list.npy> <out_dir>
  python gen/mincat_rewrite.py join <reach.npz> <proof_out.txt> <out_dir> [<out_dir> ...]

`fit` tries the catalogue's layouts (catalogue.json: layout ids into the
layouts.pkl order, tried in that order) on each reached leaf from
gen/mincat_reach.py, in every orientation, with pairs found by matching
(gen/mincat_fit.py), and writes the new L record of each leaf to
<out_dir>/fit-NNNNN.tsv (leaf index, layout id, record) and the leaves no
entry fits to <out_dir>/miss-NNNNN.txt. With a leaf list, only those leaves.

`own` is the fallback for leaves no chosen entry fits: it keeps each listed
leaf's original record, so its own layout joins the catalogue, and writes
<out_dir>/own.tsv in the same form (layout id = its index in layouts.pkl).

`join` writes the proof: the first line of the first proof file (the format
header), then every record of the proof files in order, R records unchanged,
each reached L record replaced by its new one, and every other L record
(duplicates of an earlier record's position, and leaves the tree never
reaches) left out. It fails if a reached leaf has no new record.
"""
import glob, json, os, sys, time
from multiprocessing import Pool
import numpy as np
import mincat_common as K
import mincat_fit as F

WORKERS = 3          # laptop budget for this job
CHUNK = 2000         # leaves per work unit
LAYOUTS_PER_STEP = 4  # catalogue entries screened together before exact tries

_S = {}


def init(npz, pkl, data6, catalogue):
    d = np.load(npz)
    cat, _ = F.load_catalogue(pkl, data6)
    ids = json.load(open(catalogue))["layouts"]
    CAT = F.Catalogue([cat[i] for i in ids])
    _S.update(ids=ids, CAT=CAT, lose=CAT.lose_alone(), cls={}, fid=d["fid"], off=d["off"],
              paths=[str(p) for p in d["paths"]], fh={})


def record_line(i):
    fid = int(_S["fid"][i])
    fh = _S["fh"].get(fid) or _S["fh"].setdefault(fid, open(_S["paths"][fid], "rb"))
    fh.seek(int(_S["off"][i]))
    return fh.readline().decode().rstrip("\r\n")


def cert_text(lay, inv, pairs):
    """Blocks and pairs in the layout frame, mapped back to the record's frame by inv."""
    parts = []
    for j, (cells, ls) in enumerate(lay.blocks):
        claim = []
        for l in ls:
            on = [c for c in F.LINE_CELLS[l] if c in lay.local[j]][:2]
            a, b = sorted(int(inv[c]) for c in on)
            claim.append(f"{a}/{b}")
        parts.append(f"{K.fmt_cells([int(inv[c]) for c in cells])} : {','.join(claim)}")
    ptxt = [f"{min(int(inv[a]), int(inv[b]))}/{max(int(inv[a]), int(inv[b]))}" for _, a, b in pairs]
    return (" ; ".join(parts) or "-"), (" ; ".join(ptxt) or "-")


def fit_leaf(M, B):
    """First catalogue entry (in catalogue order) fitting leaf (M, B).

    The leaf is moved by h so its Breaker set is canonical (B0); the views of
    B0 that fit without Maker (Catalogue.class_views) are computed once per
    B0 and reused by every leaf with that Breaker set up to G. Returns
    (catalogue index, inverse map layout frame -> record frame, pairs)."""
    CAT = _S["CAT"]
    keys, hs = K.canon_batch([B], [()])
    h = int(hs[0])
    cv = _S["cls"].get(keys[0])
    if cv is None:
        B0 = tuple(sorted(int(c) for c in K.G[h][list(B)]))
        cv = _S["cls"][keys[0]] = (B0,) + CAT.class_views(B0)
    B0, g0, k0, live, used = cv
    if not len(g0):
        return None
    hM = [int(c) for c in K.G[h][list(M)]]
    keep, Mimg, minb = CAT.prefilter(hM, g0, k0, ~live)
    vs = np.flatnonzero(keep)
    Mimg, minb = Mimg[keep], minb[keep]
    clear = (minb == 0) & ~used[vs[:, None], Mimg].any(1)   # Maker misses blocks and pairs
    nlose = _S["lose"][k0[vs][:, None], Mimg].sum(1)
    # catalogue order; within an entry, views Maker leaves untouched first,
    # then views whose Maker cells look harmless
    order = np.lexsort((minb, nlose, ~clear, k0[vs]))
    for j in order:
        v = vs[j]
        gg, kk = int(g0[v]), int(k0[v])
        Bg = [int(c) for c in K.G[gg][list(B0)]]
        pairs = CAT.fit(kk, Mimg[j].tolist(), Bg, live[gg])
        if pairs is not None:
            return kk, K.GINV[h][K.GINV[gg]], pairs
    return None


def fit_chunk(arg):
    c, idx, out_dir = arg
    path = os.path.join(out_dir, f"fit-{c:05d}.tsv")
    if os.path.exists(path):
        return c, 0, 0
    lines, miss = [], []
    for i in idx:
        f = record_line(i).split(" | ")
        M, B, r = K.cells_of(f[1]), K.cells_of(f[2]), int(f[3])
        got = fit_leaf(M, tuple(sorted(B + (r,))))
        if got is None:
            miss.append(i)
            continue
        k, g, pairs = got
        blocks, ptxt = cert_text(_S["CAT"].L[k], g, pairs)
        lines.append(f"{i}\t{_S['ids'][k]}\tL | {f[1]} | {f[2]} | {f[3]} | {blocks} | {ptxt}\n")
    open(os.path.join(out_dir, f"miss-{c:05d}.txt"), "w").write("".join(f"{i}\n" for i in miss))
    open(path + ".part", "w").writelines(lines)
    os.replace(path + ".part", path)
    return c, len(lines), len(miss)


def cmd_fit(npz, pkl, data6, catalogue, out_dir, subset=None):
    os.makedirs(out_dir, exist_ok=True)
    n = len(np.load(npz)["fid"])
    idx = np.load(subset) if subset else np.arange(n)
    chunks = [(c, idx[a:a + CHUNK].tolist(), out_dir) for c, a in enumerate(range(0, len(idx), CHUNK))]
    t0, done, missed = time.time(), 0, 0
    with Pool(WORKERS, init, (npz, pkl, data6, catalogue)) as p:
        for c, ok, ms in p.imap_unordered(fit_chunk, chunks):
            done += ok; missed += ms
            print(f"chunk {c}: fitted {done}, missed {missed}, {time.time() - t0:.0f} s", flush=True)
    print(f"fit done: {done} fitted, {missed} missed, {time.time() - t0:.0f} s")


def cmd_own(npz, pkl, leaf_list, out_dir):
    import pickle
    import cube6 as C
    d = np.load(npz)
    _S.update(fid=d["fid"], off=d["off"], paths=[str(p) for p in d["paths"]], fh={})
    lp = pickle.load(open(pkl, "rb"))
    order = sorted(lp["layouts"], key=lambda k: -sum(lp["layouts"][k].values()))
    lid = {k: i for i, k in enumerate(order)}
    rows = []
    for i in np.load(leaf_list).tolist():
        rec = record_line(i)
        f = rec.split(" | ")
        blocks = [] if f[4] == "-" else [K.cells_of(e.split(" : ")[0]) for e in f[4].split(" ; ")]
        rows.append(f"{i}\t{lid[C.canon_layout(blocks)[0]]}\t{rec}\n")
    open(os.path.join(out_dir, "own.tsv"), "w").writelines(rows)
    print(f"own: kept {len(rows)} original records")


def cmd_join(npz, proof_out, *out_dirs):
    d = np.load(npz)
    paths = [str(p) for p in d["paths"]]
    new, used = {}, {}
    for out_dir in out_dirs:
        for path in sorted(glob.glob(os.path.join(out_dir, "*.tsv"))):
            for row in open(path):
                i, layout, rec = row.rstrip("\n").split("\t", 2)
                if int(i) in new:
                    raise SystemExit(f"leaf {i} has two new records ({path})")
                new[int(i)] = rec
                used[int(layout)] = used.get(int(layout), 0) + 1
    want = {(int(f), int(o)): i for i, (f, o) in enumerate(zip(d["fid"], d["off"]))}
    missing = [i for i in want.values() if i not in new]
    if missing:
        raise SystemExit(f"{len(missing)} reached leaves have no new record (first: {missing[:5]})")
    nR = nL = nDrop = 0
    with open(proof_out, "w", newline="\n") as out:
        out.write(open(paths[0]).readline())
        for fid, path in enumerate(paths):
            off = 0
            with open(path, "rb") as f:
                for raw in f:
                    start = off; off += len(raw)
                    if raw[:1] == b"R":
                        out.write(raw.decode().rstrip("\r\n") + "\n"); nR += 1
                    elif raw[:1] == b"L":
                        i = want.get((fid, start))
                        if i is None:
                            nDrop += 1
                        else:
                            out.write(new[i] + "\n"); nL += 1
    print(f"wrote {proof_out}: {nR} R records, {nL} L records, {nDrop} L records left out; "
          f"catalogue: {len(used)} layouts in use")
    json.dump({"layouts_in_use": dict(sorted(used.items(), key=lambda kv: -kv[1]))},
              open(proof_out + ".catalogue.json", "w"), indent=0)


if __name__ == "__main__":
    {"fit": cmd_fit, "own": cmd_own, "join": cmd_join}[sys.argv[1]](*sys.argv[2:])
