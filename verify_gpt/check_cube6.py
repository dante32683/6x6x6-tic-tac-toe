#!/usr/bin/env python3
"""Independent 6x6x6 Maker-Breaker proof checker. Python 3 + NumPy.

Interpretations: coordinates 0..5; exact field separators, comma-separated
block line witnesses; blank lines/comments ignored; repeated witnesses allowed.
Every record is locally validated, including all leaf certificates, before it
can be used. Among equivalent records, the first is the chosen strategy,
unless --all-records is given: then every record of each reached position
is followed, as verify/ does.
Only reachable R continuations are required. R nodes are expanded even when
all global lines are blocked, unless there are no empty cells.

Canonical positions are lexicographically least (sorted M, sorted B). A
certificate is checked in its original orientation; the canonical reply and
its verified certificate remain valid by the independently checked automorphism.
Block cache keys encode the residual game (remove blocked edges and already
Maker-owned cells, keeping all empty cells). Canonicalize as an abstract
incidence hypergraph, using edge permutations for small cases and exact
partition refinement and exact isomorphism matching for larger cases. This includes
translations, all verified cube symmetries, and arbitrary game isomorphisms.
"""

import argparse
from collections import Counter
from functools import lru_cache
from itertools import permutations, product
import math
import sys
import time

import numpy as np

N = 6
NC = N ** 3
COORD = tuple(product(range(N), repeat=3))
BIT = tuple(1 << i for i in range(NC))
ALL_CELLS = bytes(range(NC))
AXES = tuple(permutations(range(3)))
REFLECT = tuple(product((0, 1), repeat=3))


class Failure(Exception):
    """A rejected proof or failed internal consistency check."""


def require(condition, message):
    # Do not let python -O disable any verification.
    if not condition:
        raise Failure(message)


def cell_id(p):
    return p[0] * 36 + p[1] * 6 + p[2]


def mask(cells):
    return sum(BIT[c] for c in cells)  # callers supply distinct cells


def fmt(cells):
    return ','.join(map(str, cells)) if cells else '-'


def pos(m, b):
    return f'M={fmt(m)} | B={fmt(b)}'


def members(bits):
    while bits:
        bit = bits & -bits
        yield bit.bit_length() - 1
        bits ^= bit


def split_key(key):
    k = (len(key) + 1) // 2
    return key[:k], key[k:]


class Geometry:
    def __init__(self):
        # Enumerate both directions, then deduplicate unordered lines.
        lines = set()
        directions = [d for d in product((-1, 0, 1), repeat=3) if any(d)]
        for p in COORD:
            for d in directions:
                end = tuple(p[i] + 5 * d[i] for i in range(3))
                if all(0 <= x < N for x in end):
                    line = tuple(sorted(cell_id(tuple(p[i] + k*d[i]
                                                       for i in range(3)))
                                        for k in range(N)))
                    require(len(set(line)) == 6, 'non-simple generated line')
                    lines.add(line)
        self.lines = tuple(sorted(lines))
        require(len(self.lines) == 148, 'expected exactly 148 lines')
        self.line_masks = tuple(mask(line) for line in self.lines)
        self.all_lines = (1 << len(self.lines)) - 1
        self.pair_line = [[-1] * NC for _ in range(NC)]
        self.incident = [0] * NC
        for j, line in enumerate(self.lines):
            for a in line:
                self.incident[a] |= 1 << j
                for b in line:
                    if a != b:
                        require(self.pair_line[a][b] == -1,
                                'two cells occur together on multiple lines')
                        self.pair_line[a][b] = j
        self.maps = self.build_group()
        self.by_cell = np.ascontiguousarray(self.maps.T)
        self.identity = next(i for i, row in enumerate(self.maps)
                             if row.tobytes() == ALL_CELLS)
        self.rep = self.by_cell.min(axis=1)
        self.to_rep = tuple(np.flatnonzero(self.by_cell[c] == self.rep[c])
                            .astype(np.intp) for c in range(NC))
        orbit_counts = Counter(map(int, self.rep))
        require(sorted(orbit_counts.values()) == [24, 48, 144],
                f'wrong orbit sizes: {orbit_counts}')
        require(len({int(self.rep[c]) for c in (0, 2, 8)}) == 3,
                '0, 2, 8 must represent distinct orbits')
        for c in range(NC):
            size = orbit_counts[int(self.rep[c])]
            require(self.incident[c].bit_count() == {24: 7, 144: 4, 48: 3}[size],
                    f'wrong line degree at cell {c}')
        # Bound the cache of Maker-set canonicalizations (hot during traversal).
        self.maker_images = lru_cache(maxsize=65536)(self._maker_images)

    def build_group(self):
        coords = np.array(COORD, dtype=np.int16)
        ts = np.array(list(permutations(range(N))), dtype=np.int16)
        lines = np.array(self.lines, dtype=np.intp)
        powers = np.array([NC**i for i in range(6)], dtype=np.uint64)
        def codes(a):
            return (np.sort(a, axis=-1).astype(np.uint64) * powers).sum(axis=-1)
        valid_codes = np.sort(codes(lines))
        maps = set()
        # Enumerate ALL 6*8*720 candidates, not only the known commuting t's.
        # Filter on all 148 line images using exact integer encodings.
        for axes in AXES:
            base = ts[:, coords[:, axes]]
            for reflect in REFLECT:
                transformed = np.where(np.array(reflect, dtype=bool), 5-base, base)
                candidate = (transformed[..., 0]*36 + transformed[..., 1]*6
                             + transformed[..., 2]).astype(np.uint8)
                image_codes = codes(candidate[:, lines])
                good = np.isin(image_codes, valid_codes).all(axis=1)
                for row in candidate[good]:
                    maps.add(row.tobytes())
        require(len(maps) == 1152, f'expected 1152 maps, got {len(maps)}')
        require(ALL_CELLS in maps, 'group lacks identity')
        group = np.frombuffer(b''.join(sorted(maps)), dtype=np.uint8).reshape(-1, NC)
        for i, row in enumerate(group):
            require(np.array_equal(np.sort(row), np.arange(NC)),
                    f'map {i} is not a permutation')
            # Exhaustive closure: row after every group element.
            composed = row[group]
            require(all(r.tobytes() in maps for r in composed),
                    f'group not closed at map {i}')
        return group

    @staticmethod
    def _least_rows(images, indices):
        """Return all indices whose already-sorted row is lexicographically least."""
        for col in range(images.shape[1]):
            if len(indices) == 1:
                break
            v = images[:, col]
            keep = v == v.min()
            if not keep.all():
                indices = indices[keep]
                images = images[keep]
        return images[0].tobytes(), indices

    def _maker_images(self, m):
        if not m:
            return b'', np.arange(len(self.maps), dtype=np.intp)
        # First coordinate of the least sorted image MUST be the smallest
        # orbit representative of any Maker cell. Every map achieving that
        # is in the union below, and no other map can be canonical.
        smallest = min(int(self.rep[c]) for c in m)
        candidates = [self.to_rep[c] for c in m if self.rep[c] == smallest]
        indices = candidates[0] if len(candidates) == 1 else np.concatenate(candidates)
        cells = np.frombuffer(m, dtype=np.uint8)
        images = np.sort(self.maps[indices[:, None], cells], axis=1)
        return self._least_rows(images, indices)

    def canonical(self, m, b):
        """Return canonical key AND index of a witnessing map, input -> key."""
        cm, indices = self.maker_images(m)
        if not b:
            return cm, int(indices[0])
        cells = np.frombuffer(b, dtype=np.uint8)
        if len(indices) == 1:
            i = int(indices[0])
            return cm + np.sort(self.maps[i, cells]).tobytes(), i
        images = np.sort(self.maps[indices[:, None], cells], axis=1)
        cb, indices = self._least_rows(images, indices)
        return cm + cb, int(indices[0])

    def maker_won(self, m):
        if len(m) < 6:
            return False
        mm = mask(m)
        return any(mm & line == line for line in self.line_masks)

    def live(self, b):
        dead = 0
        for c in b:
            dead |= self.incident[c]
        return self.all_lines ^ dead


# A residual game consists of edges on n empty cells. Removing the marks from
# this representation is exact: Breaker-marked edges are absent; Maker marks
# are removed from surviving edges. All free cells, including isolated ones,
# remain as legal moves. A zero edge is an immediate Maker win.

def game_key(n, edges):
    """Small exact canonical key, or large-game invariant for exact matching."""
    edges = tuple(sorted(set(edges)))
    # Sort edge classes by cardinality. For a small permutation search,
    # canonicalize via the multiset of incidence signatures of vertices.
    # Matching signatures give a bijection on vertices and matching edges.
    classes = {}
    for e in edges:
        classes.setdefault(e.bit_count(), []).append(e)
    groups = [classes[k] for k in sorted(classes)]
    cost = math.prod(math.factorial(len(g)) for g in groups)
    if cost <= 120 and len(edges) <= 16:
        best = None
        for order in product(*(permutations(g) for g in groups)):
            signatures = [0] * n
            j = 0
            for group in order:
                for e in group:
                    for c in members(e):
                        signatures[c] |= 1 << j
                    j += 1
            candidate = tuple(sorted(signatures))
            if best is None or candidate < best:
                best = candidate
        return (0, n, len(edges), best)

    # Larger games use a cheap isomorphism invariant to find a bucket.
    # It is NEVER sufficient on its own for cache reuse: exact matching
    # against the stored representative is required (see same_game).
    inc = incidence(n, edges)
    _, signature = refine_game(edges, inc, ((1 << n) - 1,))
    return (1, n, signature)


def incidence(n, edges):
    return tuple(tuple(j for j, e in enumerate(edges) if e & (1 << v))
                 for v in range(n))


def refine_game(edges, inc, part):
    """Refine an ordered vertex partition, returning an invariant signature."""
    while True:
        edge_colors = [tuple((e & cell).bit_count() for cell in part) for e in edges]
        new = []
        for cell in part:
            if cell.bit_count() == 1:
                new.append(cell)
                continue
            buckets = {}
            for v in members(cell):
                sig = tuple(sorted(edge_colors[j] for j in inc[v]))
                buckets[sig] = buckets.get(sig, 0) | (1 << v)
            new.extend(buckets[sig] for sig in sorted(buckets))
        new = tuple(new)
        if new == part:
            return new, (tuple(c.bit_count() for c in new), tuple(sorted(edge_colors)))
        part = new


def same_game(n, left, right):
    """Exact hypergraph isomorphism; stop at the first verified bijection."""
    if left == right:
        return True
    if len(left) != len(right):
        return False
    il, ir = incidence(n, left), incidence(n, right)
    right_set = set(right)
    # Prune only proven literal transposition automorphisms of the right game.
    swaps = [0] * n
    for a in range(n):
        for b in range(a):
            ab = (1 << a) | (1 << b)
            if all((e ^ ab) in right_set for e in right
                   if (e & ab).bit_count() == 1):
                swaps[a] |= 1 << b
                swaps[b] |= 1 << a

    def match(pl, pr):
        pl, sl = refine_game(left, il, pl)
        pr, sr = refine_game(right, ir, pr)
        if sl != sr:
            return False
        if len(pl) == n:
            # The only acceptance test: all edges match under this bijection.
            mapped = {sum(rv for lv, rv in zip(pl, pr) if e & lv) for e in left}
            return mapped == right_set
        _, k = min((c.bit_count(), i) for i, c in enumerate(pl) if c.bit_count() > 1)
        a = pl[k] & -pl[k]
        nl = pl[:k] + (a, pl[k] ^ a) + pl[k+1:]
        candidates = pr[k]
        while candidates:
            b = candidates & -candidates
            v = b.bit_length() - 1
            candidates &= ~(b | swaps[v])
            nr = pr[:k] + (b, pr[k] ^ b) + pr[k+1:]
            if match(nl, nr):
                return True
        return False

    return match(((1 << n) - 1,), ((1 << n) - 1,))


def solve_game(n, edges):
    """Return True iff Breaker can win, with Maker moving first. Plain minimax."""
    edges = tuple(sorted(set(edges)))
    full = (1 << n) - 1
    memo = {}

    def win(m, b, maker_turn):
        # MUST precede every other end condition, on both turns.
        if any(m & e == e for e in edges):
            return False
        if all(b & e for e in edges):
            return True
        free = full & ~(m | b)
        if not free:
            return False  # logically unreachable for a nonterminal valid game
        key = m | (b << n) | (int(maker_turn) << (2*n))
        cached = memo.get(key)
        if cached is not None:
            return cached
        if maker_turn:
            result = True
            while free:
                c = free & -free
                free ^= c
                if not win(m | c, b, False):
                    result = False
                    break
        else:
            result = False
            while free:
                c = free & -free
                free ^= c
                if win(m, b | c, True):
                    result = True
                    break
        memo[key] = result
        return result

    return win(0, 0, True)


def parse_cell(s):
    if not s or not s.isdigit():
        raise Failure(f'invalid cell id {s!r}')
    try:
        c = int(s)
    except ValueError as exc:
        raise Failure(f'invalid cell id {s!r}') from exc
    if not 0 <= c < NC:
        raise Failure(f'cell out of range: {c}')
    return c


def parse_set(s):
    if s == b'-':
        return b''
    cells = [parse_cell(x) for x in s.split(b',')]
    if not all(a < b for a, b in zip(cells, cells[1:])):
        raise Failure(f'cell set not strictly increasing: {s!r}')
    return bytes(cells)


def parse_pair(s):
    parts = s.split(b'/')
    require(len(parts) == 2, f'invalid line witness {s!r}')
    a, b = map(parse_cell, parts)
    require(a != b, f'repeated cell in line witness {s!r}')
    return a, b


class Checker:
    def __init__(self, geometry):
        self.g = geometry
        self.records = {}  # canonical key -> reply (0..215) or 256+reply (L)
        self.block_cache = {}
        self.distinct_games = 0
        # Local relabeling is cheap to recognize and often repeated even when
        # two blocks are not geometrically related. Bounded cache of key results.
        self.local_game_result = lru_cache(maxsize=65536)(self._local_game_result)
        self.done = set()  # canonical Maker positions already fully checked
        self.done_replies = set()  # R records with fully checked continuation
        self.records_read = 0
        self.maker_nodes = 0
        self.leaves = 0
        self.duplicates = 0
        self.reached_leaves = set()
        # --all-records: later records of a position are walked too (as verify/ does);
        # a strategy whose reply depends on move order needs several per position.
        self.all_records = False
        self.extra = {}  # canonical key -> [values after the first]

    def _local_game_result(self, n, edges):
        key = game_key(n, edges)
        if key[0] == 0:
            if key not in self.block_cache:
                self.block_cache[key] = solve_game(n, edges)
                self.distinct_games += 1
            return self.block_cache[key]
        bucket = self.block_cache.setdefault(key, [])
        for representative, result in bucket:
            if same_game(n, edges, representative):
                return result
        result = solve_game(n, edges)
        bucket.append((edges, result))
        self.distinct_games += 1
        return result

    def block_win(self, free, edges):
        return self.local_game_result(len(free), tuple(sorted(set(edges))))

    def validate_position(self, m, b, r):
        require(len(m) == len(b)+1, 'wrong mark counts for Breaker turn')
        require(not (mask(m) & mask(b)), 'Maker and Breaker sets overlap')
        require(r not in m and r not in b, f'Breaker reply {r} is occupied')
        require(not self.g.maker_won(m), 'Maker already owns a whole global line')

    def line_for(self, a, b):
        j = self.g.pair_line[a][b]
        require(j >= 0, f'cells {a}/{b} are not on a common line')
        return j

    def certificate(self, m, b, blocks_field, pairs_field):
        g = self.g
        require(not g.maker_won(m), 'Maker already owns a whole global line')
        mm, bm = mask(m), mask(b)
        covered = used = 0
        live = g.live(b)
        blocks = []
        if blocks_field != b'-':
            for entry in blocks_field.split(b' ; '):
                fields = entry.split(b' : ')
                require(len(fields) == 2, f'invalid block entry {entry!r}')
                cells = parse_set(fields[0])
                require(1 <= len(cells) <= 16, 'block must have 1..16 cells')
                cm = mask(cells)
                require(not used & cm, f'overlapping gadgets at block {fmt(cells)}')
                used |= cm
                claimed = 0
                for witness in fields[1].split(b','):
                    a, c = parse_pair(witness)
                    require(a in cells and c in cells,
                            f'block line witness {a}/{c} not wholly in block')
                    claimed |= 1 << self.line_for(a, c)
                covered |= claimed
                blocks.append((cells, cm, claimed & live))
        if pairs_field != b'-':
            for entry in pairs_field.split(b' ; '):
                a, c = parse_pair(entry)
                pm = BIT[a] | BIT[c]
                require(not pm & used, f'overlapping gadgets at pair {a}/{c}')
                require(not pm & (mm | bm), f'pair {a}/{c} contains occupied cell')
                covered |= 1 << self.line_for(a, c)
                used |= pm
        missing = live & ~covered
        if missing:
            j = next(members(missing))
            raise Failure(f'uncovered live line {fmt(g.lines[j])}')
        for cells, cm, claimed in blocks:
            free = bytes(c for c in cells if not (BIT[c] & (mm | bm)))
            edges = []
            for j in members(claimed):
                residual = g.line_masks[j] & cm & ~mm
                # A live edge cannot contain any Breaker mark. Check explicitly.
                require(not residual & bm, 'internal error: live block edge has Breaker mark')
                e = sum(1 << i for i, c in enumerate(free) if residual & BIT[c])
                edges.append(e)
            if not self.block_win(free, edges):
                raise Failure(f'block is a Maker win: cells={fmt(cells)}, '
                              f'live lines={[g.lines[j] for j in members(claimed)]}')

    def read(self, stream):
        for lineno, raw in enumerate(stream, 1):
            raw = raw.rstrip(b'\r\n')
            if not raw.strip() or raw.startswith(b'#'):
                continue
            self.records_read += 1
            m = b = None
            try:
                f = raw.split(b' | ')
                require((len(f) == 4 and f[0] == b'R') or
                        (len(f) == 6 and f[0] == b'L'), 'invalid record type or field count')
                m, b = parse_set(f[1]), parse_set(f[2])
                r = parse_cell(f[3])
                self.validate_position(m, b, r)
                leaf = f[0] == b'L'
                if leaf:
                    self.certificate(m, bytes(sorted(b + bytes([r]))), f[4], f[5])
                    self.leaves += 1
                key, s = self.g.canonical(m, b)
                value = int(self.g.maps[s, r]) + (256 if leaf else 0)
                if key in self.records:
                    self.duplicates += 1
                    if self.all_records:
                        self.extra.setdefault(key, []).append(value)
                else:
                    self.records[key] = value
            except Failure as exc:
                context = pos(m, b) if m is not None and b is not None else repr(raw[:200])
                raise Failure(f'file line {lineno}: {exc}; {context}') from exc

    def check_maker(self, m=b'', b=b'', root=None):
        """Check every empty cell (root filter applies only to the empty board)."""
        require(root is None or (not m and not b), 'root filter only allowed at empty board')
        require(len(m) == len(b) and not mask(m) & mask(b), 'invalid Maker-turn position')
        if root is None:
            key, _ = self.g.canonical(m, b)
            if key in self.done:
                return
            m, b = split_key(key)
        else:
            key = None
        self.maker_nodes += 1
        require(not self.g.maker_won(m), f'Maker already owns a line; {pos(m, b)}')
        occupied = set(m+b)
        # Even when there are no live lines, literal R traversal continues.
        for c in range(NC):
            if c in occupied or (root is not None and self.g.rep[c] != self.g.rep[root]):
                continue
            after_m = bytes(sorted(m + bytes([c])))
            child, _ = self.g.canonical(after_m, b)
            value = self.records.get(child)
            if value is None:
                raise Failure(f'no matching record for Maker move {c}; {pos(after_m, b)}')
            # Rather than map the record back, continue entirely in its
            # canonical orientation. The map witnessing the lookup is a
            # verified automorphism, so this transports the strategy exactly.
            cm, cb = split_key(child)
            for value in [value] + self.extra.get(child, []):
                r = value & 255
                if r in cm or r in cb:
                    raise Failure(f'occupied canonical reply {r}; {pos(cm, cb)}')
                # Necessary for L as well as R; already checked on file ingestion.
                if value & 256:
                    self.reached_leaves.add(child)
                elif (child, r) not in self.done_replies:
                    self.check_maker(cm, bytes(sorted(cb + bytes([r]))))
                    self.done_replies.add((child, r))
        if key is not None:
            self.done.add(key)

    def summary(self, elapsed):
        print(f'records read: {self.records_read:,}')
        print(f'distinct canonical records: {len(self.records):,}')
        print(f'duplicate canonical records: {self.duplicates:,}')
        print(f'Maker nodes checked: {self.maker_nodes:,}')
        print(f'leaf certificates checked: {self.leaves:,}')
        print(f'distinct leaf records reached: {len(self.reached_leaves):,}')
        print(f'distinct block games solved: {self.distinct_games:,}')
        print(f'seconds taken: {elapsed:.3f}')


def selftest(g):
    from io import BytesIO
    import random

    def rejects(label, fn, fragment):
        try:
            fn()
        except Failure as exc:
            require(fragment in str(exc), f'{label}: wrong failure: {exc}')
            print(f'PASS (rejected): {label}')
        else:
            raise Failure(f'selftest failed to reject: {label}')

    def read_one(record):
        Checker(g).read(BytesIO(record + b'\n'))

    rejects('occupied reply', lambda: read_one(b'R | 0 | - | 0'), 'occupied')
    rejects('overlapping gadgets',
            lambda: read_one(b'L | 215 | - | 214 | 0,1 : 0/1 | 1/2'), 'overlapping')
    rejects('pair not on a line',
            lambda: read_one(b'L | 215 | - | 214 | - | 0/8'), 'not on a common line')
    rejects('uncovered live line',
            lambda: read_one(b'L | 0 | - | 1 | - | -'), 'uncovered live line')

    # Construct a position with exactly one live line. Mark its first two
    # cells Maker, and claim it using a block consisting of those two cells.
    # Complete the mark counts without touching that line or making a win.
    target = g.lines[0]
    outside = set(range(NC)) - set(target)
    remaining = g.all_lines ^ 1
    bs = set()
    while remaining:
        c = max(outside - bs, key=lambda c: ((g.incident[c] & remaining).bit_count(), -c))
        require(g.incident[c] & remaining, 'selftest could not block other lines')
        bs.add(c)
        remaining &= ~g.incident[c]
    ms = set(target[:2])
    for c in sorted(outside - bs):
        if len(ms) == len(bs):
            break
        proposed = bytes(sorted(ms | {c}))
        if not g.maker_won(proposed):
            ms.add(c)
    require(len(ms) == len(bs), 'selftest could not balance marks')
    m, b = bytes(sorted(ms)), bytes(sorted(bs))
    require(g.live(b) == 1 and not g.maker_won(m), 'invalid selftest position')
    a, c = target[:2]
    block = f'{a},{c} : {a}/{c}'.encode()
    # A real L record, before the last Breaker mark was played.
    r = b[-1]
    record = f'L | {fmt(m)} | {fmt(b[:-1])} | {r} | '.encode() + block + b' | -'
    rejects('Maker-winning block (pre-completed edge)', lambda: read_one(record), 'block is a Maker win')
    # A different block on the same live line, with two free cells, is valid.
    a, c = target[-2:]
    good = f'{a},{c} : {a}/{c}'.encode()
    read_one(f'L | {fmt(m)} | {fmt(b[:-1])} | {r} | '.encode() + good + b' | -')
    print('PASS (accepted): winning block with exactly one live line')
    rejects('missing Maker move', lambda: Checker(g).check_maker(root=0), 'no matching record')
    rejects('Maker already won before reply',
            lambda: read_one(b'L | 0,1,2,3,4,5 | 6,7,8,9,10 | 11 | - | -'),
            'Maker already owns')
    rejects('unsorted cells', lambda: read_one(b'R | 2,0 | 1 | 3'), 'not strictly increasing')
    rejects('overlapping marks', lambda: read_one(b'R | 0,1 | 1 | 2'), 'sets overlap')
    require(not solve_game(1, (1,)), 'singleton edge must be Maker win')
    require(not solve_game(2, (0,)), 'empty edge must be Maker win')
    require(solve_game(2, (3,)), 'two-cell edge must be Breaker win')
    require(not solve_game(3, (3, 6)), 'two edges sharing center must be Maker win')
    require(solve_game(4, (3, 12)), 'disjoint pairs must be Breaker win')
    require(solve_game(0, ()), 'empty hypergraph must be Breaker win')
    print('PASS: six independent tiny minimax cases')
    # Equal coarse invariants are NOT sufficient to reuse a large game:
    # a 6-cycle and two triangles are regular but non-isomorphic.
    cycle = tuple(sorted((1 << i) | (1 << ((i+1) % 6)) for i in range(6)))
    triangles = tuple(sorted((1 << i) | (1 << (3*(i//3)+(i+1)%3)) for i in range(6)))
    require(game_key(6, cycle) == game_key(6, triangles), 'wrong cache collision fixture')
    require(not same_game(6, cycle, triangles), 'nonisomorphic games were conflated')
    relabel = (3, 0, 5, 1, 4, 2)
    mapped_cycle = tuple(sorted(sum(1 << relabel[i] for i in members(e)) for e in cycle))
    require(same_game(6, cycle, mapped_cycle), 'isomorphic games were not recognized')
    ck = Checker(g)
    ck.block_win(bytes(range(6)), cycle)
    ck.block_win(bytes(range(6)), mapped_cycle)
    require(ck.distinct_games == 1, 'isomorphic game was solved twice')
    ck.block_win(bytes(range(6)), triangles)
    require(ck.distinct_games == 2, 'distinct games were conflated')
    print('PASS: exact block cache matching and invariant collision rejection')

    # Compare canonicalizer with a deliberately simple exhaustive implementation
    # and check mapping direction; use independent random positions.
    rng = random.Random(81062)
    for k in (0, 1, 2, 4, 8, 16, 32):
        for _ in range(4):
            cells = rng.sample(range(NC), 2*k)
            m, b = bytes(sorted(cells[:k])), bytes(sorted(cells[k:]))
            expected = min(bytes(sorted(int(row[c]) for c in m)) +
                           bytes(sorted(int(row[c]) for c in b)) for row in g.maps)
            actual, s = g.canonical(m, b)
            row = g.maps[s]
            mapped = bytes(sorted(int(row[c]) for c in m)) + bytes(sorted(int(row[c]) for c in b))
            require(expected == actual == mapped, 'canonicalization or witness mismatch')
    print('PASS: canonical forms and witnesses vs exhaustive enumeration')

    # A positive traversal test on an almost-full board: find a fixed-seed
    # balanced coloring where both sides have no complete Maker line, even
    # if Maker takes either of the two free cells. The leaves need no gadgets.
    for _ in range(10000):
        cells = rng.sample(range(NC), NC)
        m, b = bytes(sorted(cells[:107])), bytes(sorted(cells[107:214]))
        free = cells[214:]
        if g.live(b) == 0 and all(not g.maker_won(bytes(sorted(m+bytes([c])))) for c in free):
            break
    else:
        raise Failure('selftest could not generate positive traversal fixture')
    lines = []
    for c, r in (free, free[::-1]):
        after = bytes(sorted(m+bytes([c])))
        lines.append(f'L | {fmt(after)} | {fmt(b)} | {r} | - | -')
    ck = Checker(g)
    ck.read(BytesIO(('\n'.join(lines)+'\n').encode()))
    ck.check_maker(m, b)
    require(ck.maker_nodes == 1 and ck.leaves == 2, 'positive traversal counts wrong')
    print('PASS (accepted): both Maker continuations on a two-empty-cell board')
    # Move one leaf to another orientation and ensure lookup still works.
    row = g.maps[-1]
    def mapped(cells):
        return bytes(sorted(int(row[c]) for c in cells))
    c, r = free
    lines[0] = f'L | {fmt(mapped(bytes(sorted(m+bytes([c])))))} | {fmt(mapped(b))} | {int(row[r])} | - | -'
    ck = Checker(g)
    ck.read(BytesIO(('\n'.join(lines)+'\n').encode()))
    ck.check_maker(m, b)
    print('PASS (accepted): traversal using a differently oriented record')
    # Positive R recursion from a four-empty-cell board, with all global
    # lines already blocked; the literal R contract still requires replies.
    for _ in range(10000):
        cells = rng.sample(range(NC), NC)
        m, b = bytes(sorted(cells[:106])), bytes(sorted(cells[106:212]))
        free = cells[212:]
        if g.live(b) == 0 and not g.maker_won(bytes(sorted(m+bytes(free)))):
            break
    else:
        raise Failure('selftest could not generate R traversal fixture')
    lines = []
    for c in free:
        rest = [x for x in free if x != c]
        r = rest.pop(0)
        mm = bytes(sorted(m+bytes([c])))
        lines.append(f'R | {fmt(mm)} | {fmt(b)} | {r}')
        bb = bytes(sorted(b+bytes([r])))
        for c2, r2 in (rest, rest[::-1]):
            m2 = bytes(sorted(mm+bytes([c2])))
            lines.append(f'L | {fmt(m2)} | {fmt(bb)} | {r2} | - | -')
    ck = Checker(g)
    ck.read(BytesIO(('\n'.join(lines)+'\n').encode()))
    ck.check_maker(m, b)
    require(ck.maker_nodes >= 2, 'R traversal failed to recurse')
    print('PASS (accepted): recursive R traversal to L records')
    # --all-records: a second R record for the first R position, replying
    # with a cell whose continuation has no records, is never read by the
    # first-record walk and must be rejected by the all-records walk.
    c = free[0]
    rest = [x for x in free if x != c]
    bad = f'R | {fmt(bytes(sorted(m+bytes([c]))))} | {fmt(b)} | {rest[1]}'
    text = ('\n'.join(lines + [bad]) + '\n').encode()
    ck = Checker(g)
    ck.read(BytesIO(text))
    ck.check_maker(m, b)
    print('PASS (accepted): bad second record, first record only')
    ck = Checker(g)
    ck.all_records = True
    ck.read(BytesIO(text))
    rejects('bad second record with --all-records', lambda: ck.check_maker(m, b), 'no matching record')
    print('SELFTEST OK')


def root_cell(s):
    try:
        return parse_cell(s.encode('ascii'))
    except (Failure, UnicodeEncodeError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('proof', nargs='?', help='proof text file')
    parser.add_argument('--root', type=root_cell, metavar='CELL',
                        help='check only the first-move orbit of CELL')
    parser.add_argument('--selftest', action='store_true', help='run built-in checks')
    parser.add_argument('--all-records', action='store_true',
                        help='check every record of a reached position, not only the first')
    args = parser.parse_args(argv)
    if args.selftest and (args.proof is not None or args.root is not None):
        parser.error('--selftest cannot be combined with a proof file or --root')
    if not args.selftest and args.proof is None:
        parser.error('a proof file or --selftest is required')
    start = time.monotonic()
    ck = None
    try:
        g = Geometry()
        if args.selftest:
            selftest(g)
            print(f'seconds taken: {time.monotonic()-start:.3f}')
            return 0
        ck = Checker(g)
        ck.all_records = args.all_records
        with open(args.proof, 'rb', buffering=1024*1024) as stream:
            ck.read(stream)
        ck.check_maker(root=args.root)
    except (Failure, OSError, MemoryError, RecursionError) as exc:
        print(f'FAILED: {exc or type(exc).__name__}')
        if ck is not None:
            ck.summary(time.monotonic()-start)
        else:
            print(f'seconds taken: {time.monotonic()-start:.3f}')
        return 1
    ck.summary(time.monotonic()-start)
    print('PROOF OK' if args.root is None else 'ROOT ORBIT OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
