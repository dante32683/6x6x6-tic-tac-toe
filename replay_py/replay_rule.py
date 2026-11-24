"""Independent replay of Breaker's five-question rule on the 6x6x6 rule proof.

Written from the task brief, docs/proof-format.md (file format and the group G),
and docs/rule.md sections "The rule" and "What this means for the reply table"
only. Nothing under src/, verify/, verify_py/, verify_gpt/, or gen/ was read.

Usage: python replay_py/replay_rule.py <proof.txt>

Reads only the R records. From the labelled empty board it explores every
labelled history in which Breaker follows the rule, checking that each rule
reply lands in a class that some R record's reply also reaches.
"""
import sys
import time
from itertools import permutations, product
import numpy as np

N = 6
NC = N ** 3
BASE = NC  # digit base for position keys (cell ids are < 216)


def cid(x, y, z):
    return 36 * x + 6 * y + z


def coords(c):
    return c // 36, (c // 6) % 6, c % 6


# ---------------------------------------------------------------- board
def build_lines():
    lines = set()
    for d in product((-1, 0, 1), repeat=3):
        if d == (0, 0, 0):
            continue
        for p in product(range(N), repeat=3):
            end = tuple(p[i] + 5 * d[i] for i in range(3))
            if all(0 <= e < N for e in end):
                lines.add(frozenset(cid(*[p[i] + k * d[i] for i in range(3)]) for k in range(6)))
    return lines


LINES = build_lines()
assert len(LINES) == 148, len(LINES)


def build_group():
    ts = [t for t in permutations(range(N)) if all(t[N - 1 - c] == N - 1 - t[c] for c in range(N))]
    assert len(ts) == 48
    maps = set()
    for p in permutations(range(3)):
        for t in ts:
            for flips in product((0, 1), repeat=3):
                img = []
                for c in range(NC):
                    v = coords(c)
                    w = [t[v[p[i]]] for i in range(3)]
                    w = [N - 1 - w[i] if flips[i] else w[i] for i in range(3)]
                    img.append(cid(*w))
                maps.add(tuple(img))
    maps = sorted(maps)
    assert len(maps) == 1152, len(maps)
    for m in maps:
        assert len(set(m)) == NC
        for ln in LINES:
            assert frozenset(m[c] for c in ln) in LINES
    return np.array(maps, dtype=np.int64)


G = build_group()

# ---------------------------------------------------------------- canonical keys
POW = [BASE ** i for i in range(8)]


def _key(sorted_arr):
    """sorted_arr: (..., k) sorted along the last axis -> int64 key."""
    k = sorted_arr.shape[-1]
    out = np.zeros(sorted_arr.shape[:-1], dtype=np.int64)
    for i in range(k):
        out = out * BASE + sorted_arr[..., i]
    return out


def canon(M, B):
    """Least (over G) key of (s(M), s(B)); tagged with the set sizes."""
    km = _key(np.sort(G[:, list(M)], axis=1)) if M else np.zeros(len(G), np.int64)
    kb = _key(np.sort(G[:, list(B)], axis=1)) if B else np.zeros(len(G), np.int64)
    return (len(M), len(B), int((km * POW[len(B)] + kb).min()))


def canon_with_each(M, B, cells):
    """canon(M + {c}, B) for every c in cells, as an int64 array of keys."""
    cells = np.asarray(cells)
    img_m = G[:, list(M)] if M else np.zeros((len(G), 0), np.int64)
    arr = np.concatenate(
        [np.broadcast_to(img_m[:, None, :], (len(G), len(cells), len(M))),
         G[:, cells][:, :, None]], axis=2)
    km = _key(np.sort(arr, axis=2))  # (1152, n)
    kb = _key(np.sort(G[:, list(B)], axis=1)) if B else np.zeros(len(G), np.int64)
    return (km * POW[len(B)] + kb[:, None]).min(axis=0)


# ---------------------------------------------------------------- the rule
DIAGS = [
    [cid(i, i, i) for i in range(N)],
    [cid(i, i, N - 1 - i) for i in range(N)],
    [cid(i, N - 1 - i, i) for i in range(N)],
    [cid(N - 1 - i, i, i) for i in range(N)],
]
DIAG_OF = {}
for _i, _d in enumerate(DIAGS):
    for _c in _d:
        assert _c not in DIAG_OF
        DIAG_OF[_c] = _i
for _d in DIAGS:  # the four diagonals are lines
    assert frozenset(_d) in LINES


def sqd(a, b):
    return sum((u - v) ** 2 for u, v in zip(coords(a), coords(b)))


def layer(c):
    """0 corner, 1 mid, 2 core (min distance of the coordinate to the border)."""
    x, y, z = coords(c)
    ls = {min(v, N - 1 - v) for v in (x, y, z)}
    assert len(ls) == 1
    return ls.pop()


ROOT_CELLS = (0, 2, 8)
LAYER_ORDER = {1: {1: 0, 0: 1, 2: 2},   # second reply: mid, corner, core
               2: {2: 0, 1: 1, 0: 2}}   # third reply: core, mid, corner


def rule_reply(M, B):
    if not B:
        assert len(M) == 1
        (m,) = M
        core = [c for c in range(NC) if all(v in (2, 3) for v in coords(c))]
        return max(core, key=lambda c: (sqd(c, m), -c))
    nb = len(B)
    order = LAYER_ORDER[nb]  # KeyError past the third reply: the rule is undefined
    taken = set(M) | set(B)
    bd = {DIAG_OF[c] for c in B if c in DIAG_OF}
    md = {DIAG_OF[c] for c in M if c in DIAG_OF}
    best = None
    for c in range(NC):
        if c in taken:
            continue
        d = DIAG_OF.get(c)
        if d is None:
            key = (0, 0, 0, 0, 0)
        else:
            key = (1, d not in bd, d not in md, -order[layer(c)], sum(sqd(c, m) for m in M))
        key = key + (-c,)
        if best is None or key > best[0]:
            best = (key, c)
    return best[1]


# ---------------------------------------------------------------- proof file
def parse_set(s):
    s = s.strip()
    return [] if s == "-" else [int(v) for v in s.split(",")]


def load_r_records(path):
    """canon(M,B) -> set of canon(M, B+r) over all R records; also the record count."""
    index = {}
    n = 0
    with open(path, "rb", buffering=1 << 24) as f:
        for line in f:
            if line[:1] != b"R":
                continue
            parts = line.decode().split(" | ")
            M, B, r = parse_set(parts[1]), parse_set(parts[2]), int(parts[3])
            index.setdefault(canon(M, B), set()).add(canon(M, B + [r]))
            n += 1
    return index, n


# ---------------------------------------------------------------- replay
def replay(index):
    stats = {}  # depth -> dict
    failures = []
    level = {((), ()): 1}  # labelled (M, B), Maker to move -> number of histories
    depth = 1
    while level:
        st = stats.setdefault(depth, dict(met=set(), cov=set(), fail=set(), leaf=set(),
                                          met_n=0, cov_n=0, fail_n=0, leaf_n=0))
        nxt = {}
        for (M, B), mult in level.items():
            empty = [c for c in range(NC) if c not in M and c not in B]
            keys = canon_with_each(list(M), list(B), empty)
            _, first = np.unique(keys, return_index=True)
            reps = sorted(empty[i] for i in first)
            if not M:
                # The brief fixes Maker's first move to 0, 2, or 8 (the search frame's
                # three first-move classes). Cells 1 and 2 are one class under G, so
                # "lowest id" alone would give 1; check the brief's cells are one per class.
                assert sorted(keys[[empty.index(c) for c in ROOT_CELLS]]) == sorted(keys[first])
                reps = list(ROOT_CELLS)
            for c in reps:
                M2 = tuple(sorted(M + (c,)))
                key = canon(M2, B)
                P = (M2, B)
                if key not in index:
                    st["leaf"].add(P)
                    st["leaf_n"] += mult
                    continue
                st["met"].add(P)
                st["met_n"] += mult
                x = rule_reply(M2, B)
                assert x not in M2 and x not in B
                B2 = tuple(sorted(B + (x,)))
                if canon(M2, B2) in index[key]:
                    st["cov"].add(P)
                    st["cov_n"] += mult
                    nxt[(M2, B2)] = nxt.get((M2, B2), 0) + mult
                else:
                    st["fail_n"] += mult
                    if P not in st["fail"]:
                        st["fail"].add(P)
                        failures.append((depth, M2, B, x))
                        print(f"FAIL depth {depth}: M={list(M2)} B={list(B)} rule reply {x}", flush=True)
        # dedupe happened via dict keys; the sum of multiplicities is the undeduplicated count
        print(f"depth {depth}: labelled positions explored {len(level)}, "
              f"histories {sum(level.values())}", flush=True)
        level = nxt
        depth += 1
    return stats, failures


def main():
    path = sys.argv[1]
    t0 = time.time()
    index, n = load_r_records(path)
    print(f"{path}: {n} R records, {len(index)} position classes, "
          f"read in {time.time() - t0:.0f}s", flush=True)
    stats, failures = replay(index)
    print("Per Breaker reply (deduplicated labelled positions; without deduplication in brackets):")
    for d in sorted(stats):
        s = stats[d]
        print(f"  reply {d}: rule positions met {len(s['met'])} [{s['met_n']}], "
              f"covered {len(s['cov'])} [{s['cov_n']}], "
              f"failures {len(s['fail'])} [{s['fail_n']}], "
              f"leaf stops {len(s['leaf'])} [{s['leaf_n']}]")
    print(f"total failures {len(failures)}; {time.time() - t0:.0f}s")
    if not failures:
        print("REPLAY OK")


if __name__ == "__main__":
    main()
