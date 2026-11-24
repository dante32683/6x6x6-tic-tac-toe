"""Which L records the proof tree reaches (minimum-catalogue job, docs/leaf-catalogue.md).

usage: python gen/mincat_reach.py [--root CELL] <out.npz> <proof.txt> [<proof.txt> ...]

--root walks one first move only (for testing on a single orbit file).

Indexes every record by the canonical form of its position under G, then
walks the tree from the empty board the way docs/proof-format.md describes:
every empty cell for Maker, Breaker's reply from the matching records. A
position can have several records; `verify/` checks every one, so the walk
follows the reply of every R record of a position, not only the first (the
first-only walk, which is what verify_py does, misses subtrees that `verify/`
reaches). It checks no certificate. Writes, for every reached leaf position
(one per canonical form: its first L record), the file index and byte
offset of its record and the leaf position (M, B + r) in the record's own
orientation.

--extend <old.npz> keeps old.npz's leaves first, in the same order, so leaf
indices into it stay valid, and appends the new ones.
"""
import sys, time
from collections import defaultdict
import numpy as np
import mincat_common as K

BATCH = 4096


def index_files(paths):
    index = {}            # key -> [(fid, offset, kind, g, M, B, r), ...] in file order
    dup = 0
    for fid, path in enumerate(paths):
        t0 = time.time()
        pend = defaultdict(list)

        def flush(sz):
            nonlocal dup
            rows = pend.pop(sz)
            keys, gs = K.canon_batch([r[3] for r in rows], [r[4] for r in rows])
            for key, g, (off, kind, rr, M, B) in zip(keys, gs, rows):
                if key in index:
                    dup += 1
                index.setdefault(key, []).append((fid, off, kind, int(g), M, B, rr))

        off = 0
        with open(path, "rb") as f:
            for raw in f:
                start = off
                off += len(raw)
                if raw[:1] not in (b"R", b"L"):
                    continue
                parts = raw.split(b" | ", 4)
                M, B, r = K.cells_of(parts[1].decode()), K.cells_of(parts[2].decode()), int(parts[3])
                sz = (len(M), len(B))
                pend[sz].append((start, parts[0].decode(), r, M, B))
                if len(pend[sz]) >= BATCH:
                    flush(sz)
        for sz in list(pend):
            flush(sz)
        print(f"indexed {path}: {len(index)} keys so far, {dup} duplicates, {time.time() - t0:.0f} s", flush=True)
    return index, dup


def walk(index, root=None):
    done = set()                 # canonical keys of Maker-to-move positions expanded
    reached = {}                 # leaf record key -> (fid, off, M', B'+r') in record orientation
    stack = [((), ())]
    nodes = 0
    while stack:
        M, B = stack.pop()
        if M:
            mk, _ = K.canon_batch([M], [B])
            if mk[0] in done:
                continue
            done.add(mk[0])
        nodes += 1
        occ = set(M) | set(B)
        moves = [c for c in range(216) if c not in occ] if (M or root is None) else [root]
        childM = [tuple(sorted(M + (m,))) for m in moves]
        childB = [B] * len(moves)
        keys, gs = K.canon_batch(childM, childB)
        for m, cM, key, gp in zip(moves, childM, keys, gs):
            ents = index.get(key)
            if ents is None:
                raise SystemExit(f"no record for M={list(cM)} B={list(B)}")
            for fid, off, kind, gr, Mr, Br, rr in ents:
                s = K.map_from_to(gr, gp)
                assert sorted(s[list(Mr)].tolist()) == list(cM) and sorted(s[list(Br)].tolist()) == list(B)
                r = int(s[rr])
                assert r not in occ and r != m
                if kind == "L":
                    reached.setdefault(key, (fid, off, Mr, tuple(sorted(Br + (rr,)))))
                else:
                    stack.append((tuple(int(c) for c in cM), tuple(sorted(B + (r,)))))
        if nodes % 500 == 0:
            print(f"  {nodes} Maker nodes, {len(reached)} leaves", flush=True)
    return nodes, reached


def main():
    args = sys.argv[1:]
    root = old = None
    if args[0] == "--root":
        root, args = int(args[1]), args[2:]
    if args[0] == "--extend":
        old, args = np.load(args[1]), args[2:]
    out, paths = args[0], args[1:]
    t0 = time.time()
    index, dup = index_files(paths)
    nodes, reached = walk(index, root)
    rows = sorted(reached.values(), key=lambda v: (v[0], v[1]))
    if old is not None:
        pos = {(int(f), int(o)): i for i, (f, o) in enumerate(zip(old["fid"], old["off"]))}
        new = {(r[0], r[1]) for r in rows}
        assert set(pos) <= new, "an old leaf is no longer reached"
        rows.sort(key=lambda r: pos.get((r[0], r[1]), len(pos)))
        print(f"extend: {len(pos)} old leaves kept in order, {len(rows) - len(pos)} new")
    nmax = 5
    Ma = np.full((len(rows), nmax), -1, np.int16); Ba = np.full((len(rows), nmax), -1, np.int16)
    for i, (_, _, M, B) in enumerate(rows):
        Ma[i, :len(M)] = M; Ba[i, :len(B)] = B
    np.savez_compressed(out, fid=np.array([r[0] for r in rows], np.int8),
                        off=np.array([r[1] for r in rows], np.int64), M=Ma, B=Ba,
                        paths=np.array(paths))
    print(f"records {len(index) + dup}, distinct {len(index)}, duplicates {dup}, "
          f"Maker nodes {nodes}, reached leaves {len(rows)}, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
