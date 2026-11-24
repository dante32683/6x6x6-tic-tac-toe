"""Shared helpers for the minimum-catalogue job (gen/mincat_*.py; docs/leaf-catalogue.md).

Positions are small cell sets (Maker M, Breaker B), so their canonical form
under G (gen/cube6.py) is computed from the images of those cells only: for
each map g the sorted g(M) then the sorted g(B), packed one byte per cell into
a uint64 (at most 8 cells; leaves have |M| + |B| <= 8), and the least value
over G wins. Two positions get the same key exactly when some g maps one onto
the other, which is the indexing rule of docs/proof-format.md.
"""
import numpy as np
import cube6 as C

G = C.G.astype(np.int64)                 # (1152, 216): G[g, c] = image of c
GINV = np.argsort(G, axis=1)             # GINV[g] is the inverse map of G[g]
MAX_KEY_CELLS = 8                        # one byte per cell in a uint64


def cells_of(s):
    return () if s == "-" else tuple(int(x) for x in s.split(","))


def fmt_cells(cells):
    return ",".join(str(c) for c in sorted(cells)) if len(cells) else "-"


def _pack(img):
    """(..., k) cell images -> (...) uint64, lexicographic in the k bytes."""
    acc = np.zeros(img.shape[:-1], dtype=np.uint64)
    for j in range(img.shape[-1]):
        acc = (acc << np.uint64(8)) | img[..., j].astype(np.uint64)
    return acc


def canon_batch(Ms, Bs):
    """Canonical keys for positions that all have |M| = m and |B| = b.

    Ms: (n, m) ints, Bs: (n, b) ints. Returns (keys, g): keys are Python ints
    tagged with (m, b) so different sizes never collide, g the index of a map
    sending each position to its canonical form."""
    n = len(Ms)
    m, b = len(Ms[0]), len(Bs[0])
    Ms = np.asarray(Ms, dtype=np.int64).reshape(n, m)
    Bs = np.asarray(Bs, dtype=np.int64).reshape(n, b)
    assert m + b <= MAX_KEY_CELLS, (m, b)
    imgM = np.sort(G[:, Ms].transpose(1, 0, 2), axis=2)   # (n, 1152, m)
    imgB = np.sort(G[:, Bs].transpose(1, 0, 2), axis=2)
    vals = _pack(np.concatenate([imgM, imgB], axis=2))    # (n, 1152)
    g = vals.argmin(axis=1)
    best = vals[np.arange(len(vals)), g]
    tag = (m << 4 | b) << 64
    return [tag | int(v) for v in best], g


def map_from_to(g_from, g_to):
    """Map s with s(pos_from) = pos_to, given maps sending each to the same canonical form."""
    return GINV[g_to][G[g_from]]
