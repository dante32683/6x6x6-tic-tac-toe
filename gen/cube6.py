"""6x6x6 board geometry for the pattern-mining scripts (gen/mine*.py).

Cells are id = x*36 + y*6 + z (docs/proof-format.md). Builds the 148 lines
and the full 1,152-element automorphism group G of the line hypergraph the
same way the verifier does, plus canonical forms of cell sets and layouts
under G. Numpy only; independent of data6.json.
"""
import itertools
import numpy as np

N = 6
CELLS = N ** 3
CORE = (2, 3)      # coordinate values of the central 2x2x2 core
MID = (1, 4)       # the middle ring of the space diagonals
OUTER = (0, 5)     # the cube's corners


def cid(x, y, z): return x * N * N + y * N + z
def xyz(c): return (c // (N * N), (c // N) % N, c % N)


def _lines():
    out = []
    for d in itertools.product((-1, 0, 1), repeat=3):
        if d == (0, 0, 0) or d < (0, 0, 0):
            continue  # one of each +-d
        for p in itertools.product(range(N), repeat=3):
            if all(0 <= p[i] - d[i] < N for i in range(3)):
                continue  # p is not a line start
            cells = [tuple(p[i] + k * d[i] for i in range(3)) for k in range(N)]
            if all(0 <= v < N for c in cells for v in c):
                out.append(([cid(*c) for c in cells], sum(1 for v in d if v)))
    return out


LINES = _lines()
assert len(LINES) == 148, len(LINES)
LTYPE = {1: "axis", 2: "face-diag", 3: "space-diag"}
LINE_KIND = [LTYPE[k] for _, k in LINES]
PAIR_LINE = {(a, b): li for li, (cells, _) in enumerate(LINES)
             for a, b in itertools.combinations(cells, 2)}
INC = np.zeros((len(LINES), CELLS), dtype=np.int8)  # line x cell incidence
for li, (cells, _) in enumerate(LINES):
    INC[li, cells] = 1
DEG = INC.sum(0)  # lines through a cell: 7 (space diagonals), 4, or 3
CELL_LINES = [np.flatnonzero(INC[:, c]) for c in range(CELLS)]


def line_of(a, b): return PAIR_LINE[(min(a, b), max(a, b))]


def diag_layer(c):
    """'core', 'mid', or 'corner' for a space-diagonal cell, else None."""
    v = xyz(c)
    for name, vals in (("core", CORE), ("mid", MID), ("corner", OUTER)):
        if all(t in vals for t in v):
            return name
    return None


def _group():
    pair_perms = []
    for p in itertools.permutations(range(3)):          # permute {0,5},{1,4},{2,3}
        for sw in itertools.product((0, 1), repeat=3):  # swap inside each pair
            t = [0] * N
            for i in range(3):
                a, b = (i, N - 1 - i)
                c, d = (p[i], N - 1 - p[i])
                if sw[i]:
                    c, d = d, c
                t[a], t[b] = c, d
            pair_perms.append(t)
    lineset = {tuple(sorted(cells)) for cells, _ in LINES}
    maps = set()
    for perm in itertools.permutations(range(3)):
        for t in pair_perms:
            for refl in itertools.product((0, 1), repeat=3):
                m = []
                for c in range(CELLS):
                    v = xyz(c)
                    w = [t[v[perm[i]]] for i in range(3)]
                    w = [N - 1 - w[i] if refl[i] else w[i] for i in range(3)]
                    m.append(cid(*w))
                maps.add(tuple(m))
    maps = sorted(maps)
    for m in maps[:50]:
        assert all(tuple(sorted(m[c] for c in cells)) in lineset for cells, _ in LINES)
    return np.array(maps, dtype=np.uint8)


G = _group()  # (1152, 216): G[g, c] is the image of cell c under map g
assert G.shape == (1152, CELLS), G.shape


def _lexmin_row(a):
    """Index of the lexicographically least row of a 2-D uint8 array."""
    return min(range(len(a)), key=lambda i: a[i].tobytes())


def canon_set(cells):
    """Canonical form of a cell set under G (a sorted tuple)."""
    img = np.sort(G[:, list(cells)], axis=1)
    return tuple(int(v) for v in img[_lexmin_row(img)])


def canon_layout(blocks, maps=None):
    """Canonical form of a set of disjoint cell sets under G.

    Each cell is labelled with the least mapped cell of its block (255 if in
    no block); the least label vector over G identifies the layout. Returns
    (bytes key, index of a map g that sends the layout to that key)."""
    maps = G if maps is None else maps
    label = np.full((len(maps), CELLS), 255, dtype=np.uint8)
    for b in blocks:
        img = maps[:, list(b)]                       # (g, |b|) mapped cells
        mn = img.min(axis=1, keepdims=True)
        np.put_along_axis(label, img.astype(np.intp), np.broadcast_to(mn, img.shape), axis=1)
    i = _lexmin_row(label)
    return label[i].tobytes(), i


def layout_from_key(key):
    """Blocks (sorted cell tuples) of a canonical layout key."""
    lab = np.frombuffer(key, dtype=np.uint8)
    out = {}
    for c, v in enumerate(lab):
        if v != 255:
            out.setdefault(int(v), []).append(c)
    return sorted(tuple(v) for v in out.values())


def stabilizer(M, B):
    """Indices of the maps in G that fix the position (M, B) setwise."""
    ok = np.ones(len(G), dtype=bool)
    for s in (M, B):
        if s:
            ok &= (np.sort(G[:, list(s)], axis=1) == np.array(sorted(s), dtype=np.uint8)).all(1)
    return np.flatnonzero(ok)
