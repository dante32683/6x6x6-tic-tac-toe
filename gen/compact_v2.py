"""Proof catalogue format v2: encode a pruned v1 proof, decode it back to v1.

usage: python gen/compact_v2.py encode <pruned-v1.txt> <out.v2>
       python gen/compact_v2.py decode <in.v2> <out-v1.txt>

The format is specified in docs/proof-format.md, "Catalogue format (v2)". In
short: the R records verbatim, a catalogue of leaf layouts (blocks with their
claimed lines) up to G, and per leaf only Maker's move, Breaker's reply, a
layout id, and a symmetry index. A leaf's position is its parent R record's
position plus Maker's move; its pairs are recomputed by bipartite matching.

Trust never rests on this script: the decoded v1 file goes through the
checkers (verify/, verify_py/, verify_gpt/) like any proof. The encoder needs
one record per position up to G and every R record reached, which is what
gen/compact_prune.py writes; it stops with an error on anything else.
"""
import struct, sys, time
import numpy as np
import cube6 as C

MAGIC = b"C6PROOF2"
G = C.G                                   # (1152, 216) uint8, rows sorted: the spec's map order
GINV = np.argsort(G, axis=1).astype(np.uint8)
MAP_INDEX = {G[g].tobytes(): g for g in range(len(G))}
LINE_CELLS = [tuple(sorted(cells)) for cells, _ in C.LINES]
LINE_ORDER = sorted(range(len(LINE_CELLS)), key=lambda li: LINE_CELLS[li])  # matching order
LINE_MASK = [sum(1 << c for c in cells) for cells in LINE_CELLS]
PROGRESS_EVERY = 100_000


def cells_of(s):
    return [] if s == "-" else [int(x) for x in s.split(",")]


def show(cells):
    return ",".join(map(str, cells)) if cells else "-"


def canon_pos(M, B):
    """(key bytes, map index g) with g sending (M, B) to the least sorted image."""
    rows = np.concatenate([np.sort(G[:, M], axis=1), np.sort(G[:, B], axis=1)], axis=1)
    k = rows.shape[1]
    buf = rows.tobytes()
    g = min(range(len(G)), key=lambda i: buf[i * k:(i + 1) * k])
    return buf[g * k:(g + 1) * k], g


def parse_blocks(field):
    """v1 blocks field -> [(cells, [(a, b), ...]), ...]."""
    if field == "-":
        return []
    out = []
    for e in field.split(" ; "):
        cs, ls = e.split(" : ")
        claims = [tuple(int(x) for x in t.split("/")) for t in ls.split(",")] if ls else []
        out.append((cells_of(cs), claims))
    return out


def canon_layout(blocks):
    """Canonical form of blocks with claimed lines under G.

    Returns (layout, hs): layout is a tuple of (cells, claims) with cells
    sorted and each claim written as the two least cells of its line inside
    the block; hs lists every map index sending `blocks` to `layout` (more
    than one when the layout has symmetries). The least cell labelling
    (gen/cube6.py canon_layout) picks the maps that give the least block
    partition; among those, the least claimed-line lists win."""
    label = np.full((len(G), C.CELLS), 255, dtype=np.uint8)
    for cells, _ in blocks:
        img = G[:, cells]
        mn = img.min(axis=1, keepdims=True)
        np.put_along_axis(label, img.astype(np.intp), np.broadcast_to(mn, img.shape), axis=1)
    buf = label.tobytes()
    rows = [buf[i * C.CELLS:(i + 1) * C.CELLS] for i in range(len(G))]
    least = min(rows)
    forms = {}
    for g in (i for i, r in enumerate(rows) if r == least):
        m = G[g]
        form = tuple(sorted((tuple(sorted(int(m[c]) for c in cells)),
                             tuple(sorted({C.line_of(int(m[a]), int(m[b])) for a, b in claims})))
                            for cells, claims in blocks))
        forms.setdefault(form, []).append(g)
    form = min(forms)
    layout = []
    for cells, lines in form:
        inside = set(cells)
        claims = tuple(tuple(sorted(c for c in LINE_CELLS[li] if c in inside)[:2]) for li in lines)
        layout.append((cells, claims))
    return tuple(layout), forms[form]


# ---- binary helpers ----

def put_set(out, cells):
    out.append(len(cells)); out.extend(cells)


class Reader:
    def __init__(self, data):
        self.d, self.i = data, 0

    def take(self, n):
        if self.i + n > len(self.d):
            raise ValueError("v2 file ends early")
        b = self.d[self.i:self.i + n]; self.i += n
        return b

    def u8(self): return self.take(1)[0]
    def u32(self): return struct.unpack("<I", self.take(4))[0]
    def cells(self): return list(self.take(self.u8()))

    def column(self, n, width):
        return np.frombuffer(self.take(n * width), dtype={1: "<u1", 2: "<u2", 4: "<u4"}[width])


# ---- encode ----

def encode(src, dst):
    t0 = time.time()
    header, rrec, rkeys, leaf_of, leaf_grec = [], [], set(), {}, []
    with open(src, encoding="ascii") as f:      # pass 1: positions only
        for n, line in enumerate(f, 1):
            if line[0] == "#":
                header.append(line.rstrip("\n")); continue
            f_ = line.rstrip("\n").split(" | ", 4)
            M, B, r = cells_of(f_[1]), cells_of(f_[2]), int(f_[3])
            key, g = canon_pos(M, B)
            if key in rkeys or key in leaf_of:
                sys.exit(f"line {n}: second record for one position; prune the proof first (gen/compact_prune.py)")
            if f_[0] == "R":
                rrec.append((M, B, r)); rkeys.add(key)
            else:
                leaf_of[key] = len(leaf_grec); leaf_grec.append(g)
    nleaf = len(leaf_grec)
    print(f"pass 1: {len(rrec)} R, {nleaf} L records, {time.time() - t0:.0f}s", flush=True)

    # walk: each leaf goes to the first (R record, Maker move) that reaches it
    assign = [None] * nleaf
    seen_nodes = set()
    for i, (M, B, r) in enumerate(rrec):
        B2 = sorted(B + [r])
        nk, _ = canon_pos(M, B2)
        if nk in seen_nodes:
            continue
        seen_nodes.add(nk)
        taken = set(M) | set(B2)
        for m in range(C.CELLS):
            if m in taken:
                continue
            key, g = canon_pos(sorted(M + [m]), B2)
            lo = leaf_of.get(key)
            if lo is not None:
                if assign[lo] is None:
                    assign[lo] = (i, m, g)
            elif key not in rkeys:
                sys.exit(f"no record for M={show(sorted(M + [m]))} B={show(B2)}: not a complete proof")
    if any(a is None for a in assign):
        sys.exit(f"{sum(a is None for a in assign)} L records are never reached; prune the proof first")
    del leaf_of
    print(f"walk: {len(seen_nodes)} Maker positions, {time.time() - t0:.0f}s", flush=True)

    node = np.array([a[0] for a in assign], dtype=np.uint32)
    mv = np.array([a[1] for a in assign], dtype=np.uint8)
    gpos = np.array([a[2] for a in assign], dtype=np.uint16)
    del assign
    reply = np.zeros(nleaf, dtype=np.uint8)
    lid = np.zeros(nleaf, dtype=np.uint32)
    sym = np.zeros(nleaf, dtype=np.uint16)
    layouts, layout_id, field_cache = [], {}, {}  # ids here are provisional, in order of first use
    lo = 0
    with open(src, encoding="ascii") as f:      # pass 2: certificates
        for line in f:
            if line[0] != "L":
                continue
            f_ = line.rstrip("\n").split(" | ")
            r, bf = int(f_[3]), f_[4]
            hit = field_cache.get(bf)
            if hit is None:
                layout, hs = canon_layout(parse_blocks(bf))
                k = layout_id.setdefault(layout, len(layouts))
                if k == len(layouts):
                    layouts.append(layout)
                hit = field_cache[bf] = (k, [GINV[h] for h in hs])
            k, hinvs = hit
            s = GINV[gpos[lo]][G[leaf_grec[lo]]]          # record -> leaf position
            reply[lo] = s[r]
            lid[lo] = k
            # catalogue -> leaf position; the least index when the layout has symmetries
            sym[lo] = min(MAP_INDEX[s[hinv].tobytes()] for hinv in hinvs)
            lo += 1
            if lo % PROGRESS_EVERY == 0:
                print(f"  {lo} leaves, {len(field_cache)} distinct blocks fields, {len(layouts)} layouts, {time.time() - t0:.0f}s", flush=True)
    print(f"pass 2: {len(layouts)} layouts from {len(field_cache)} distinct blocks fields, {time.time() - t0:.0f}s", flush=True)
    # final ids: most used first, ties by canonical form, so the output does not
    # depend on record order and small ids (which compress well) dominate
    uses = np.bincount(lid, minlength=len(layouts))
    rank = sorted(range(len(layouts)), key=lambda k: (-uses[k], layouts[k]))
    new_id = np.empty(len(layouts), dtype=np.uint32)
    new_id[rank] = np.arange(len(layouts), dtype=np.uint32)
    layouts = [layouts[k] for k in rank]
    lid = new_id[lid]

    order = np.lexsort((mv, node))                 # leaves grouped by R record, by Maker move
    counts = np.bincount(node, minlength=len(rrec))
    if counts.max(initial=0) > 255:
        sys.exit("more than 255 leaves under one R record")
    id_width = 2 if len(layouts) <= 1 << 16 else 4
    out = bytearray(MAGIC)
    text = "\n".join(header).encode("ascii")
    out += struct.pack("<IIIIB", len(text), len(layouts), len(rrec), nleaf, id_width) + text
    for layout in layouts:
        out.append(len(layout))
        for cells, claims in layout:
            put_set(out, cells)
            out.append(len(claims))
            for a, b in claims:
                out += bytes((a, b))
    for M, B, r in rrec:
        put_set(out, M); put_set(out, B); out.append(r)
    out += counts.astype(np.uint8).tobytes()
    out += mv[order].tobytes() + reply[order].tobytes()
    out += lid[order].astype("<u2" if id_width == 2 else "<u4").tobytes()
    out += sym[order].astype("<u2").tobytes()
    with open(dst, "wb") as fh:
        fh.write(out)
    print(f"{dst}: {len(out)} bytes, {len(layouts)} layouts, {len(rrec)} R, {nleaf} leaves, {time.time() - t0:.0f}s")


# ---- decode ----

def pairs_for(M2, B2, blocks):
    """Pairs covering every live line no block claims: two empty cells outside
    every block per line, disjoint. Kuhn's augmenting paths, lines in the
    spec's order, cells ascending; stops with an error if none exists."""
    bmask = sum(1 << c for c in B2)
    used = bmask | sum(1 << c for c in M2)
    claimed = set()
    for cells, claims in blocks:
        for c in cells:
            used |= 1 << c
        for a, b in claims:
            claimed.add(C.line_of(a, b))
    need = [li for li in LINE_ORDER if not LINE_MASK[li] & bmask and li not in claimed]
    cand = [[c for c in LINE_CELLS[li] if not used >> c & 1] for li in need]
    slots = [k for k in range(len(need)) for _ in (0, 1)]
    owner = {}                                     # cell -> slot

    def augment(s, seen):
        for c in cand[slots[s]]:
            if c in seen:
                continue
            seen.add(c)
            if c not in owner or augment(owner[c], seen):
                owner[c] = s
                return True
        return False

    for s in range(len(slots)):
        if not augment(s, set()):
            raise ValueError(f"no pairing for M={show(M2)} B={show(B2)}")
    by_slot = sorted((s, c) for c, s in owner.items())
    pairs = [tuple(sorted((by_slot[2 * k][1], by_slot[2 * k + 1][1]))) for k in range(len(need))]
    return sorted(pairs)


def decode(src, dst):
    t0 = time.time()
    rd = Reader(open(src, "rb").read())
    if rd.take(len(MAGIC)) != MAGIC:
        sys.exit(f"{src}: not a v2 proof (magic)")
    tlen, nlay, nr, nleaf, idw = struct.unpack("<IIIIB", rd.take(17))
    header = rd.take(tlen).decode("ascii")
    layouts = []
    for _ in range(nlay):
        bl = []
        for _ in range(rd.u8()):
            cells = rd.cells()
            claims = [tuple(rd.take(2)) for _ in range(rd.u8())]
            bl.append((cells, claims))
        flat = np.array([c for cells, _ in bl for c in cells] + [c for _, cl in bl for p in cl for c in p], dtype=np.intp)
        layouts.append((bl, flat))
    rrec = [(rd.cells(), rd.cells(), rd.u8()) for _ in range(nr)]
    counts = rd.column(nr, 1)
    mv, reply = rd.column(nleaf, 1), rd.column(nleaf, 1)
    lid, sym = rd.column(nleaf, idw), rd.column(nleaf, 2)
    if rd.i != len(rd.d) or int(counts.sum()) != nleaf:
        sys.exit(f"{src}: sizes do not add up")
    lo = 0
    with open(dst, "w", encoding="ascii", newline="\n") as out:
        if header:
            out.write(header + "\n")
        for M, B, r in rrec:
            out.write(f"R | {show(M)} | {show(B)} | {r}\n")
        for i, (M, B, r) in enumerate(rrec):
            B2 = sorted(B + [r])
            for _ in range(int(counts[i])):
                m, rep = int(mv[lo]), int(reply[lo])
                bl, flat = layouts[int(lid[lo])]
                img = G[int(sym[lo])][flat].tolist()
                k, blocks = 0, []
                for cells, _ in bl:
                    blocks.append([sorted(img[k:k + len(cells)]), None]); k += len(cells)
                for b, (_, claims) in zip(blocks, bl):
                    b[1] = [tuple(sorted(img[k + 2 * j:k + 2 * j + 2])) for j in range(len(claims))]
                    k += 2 * len(claims)
                blocks.sort()
                M2 = sorted(M + [m])
                pairs = pairs_for(M2, B2 + [rep], blocks)
                bf = " ; ".join(f"{show(c)} : " + ",".join(f"{a}/{b}" for a, b in cl) for c, cl in blocks) or "-"
                pf = " ; ".join(f"{a}/{b}" for a, b in pairs) or "-"
                out.write(f"L | {show(M2)} | {show(B2)} | {rep} | {bf} | {pf}\n")
                lo += 1
                if lo % PROGRESS_EVERY == 0:
                    print(f"  {lo} leaves, {time.time() - t0:.0f}s", flush=True)
    print(f"{dst}: {nr} R, {nleaf} L records, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("encode", "decode"):
        sys.exit(__doc__)
    (encode if sys.argv[1] == "encode" else decode)(sys.argv[2], sys.argv[3])
