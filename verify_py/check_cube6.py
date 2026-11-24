#!/usr/bin/env python3
"""Independent checker for a 6x6x6 Maker-Breaker proof file (Breaker wins).

Written from docs/proof-format.md alone; it shares no code or data with the
search or with verify/. It builds the 148 lines, the symmetry group G, and the
block-game minimax itself, and trusts nothing in the proof file beyond its
records.

Usage:
    python check_cube6.py proof.txt [more.txt ...]     whole game -> PROOF OK
    python check_cube6.py proof.txt --root CELL        one first move -> ROOT ORBIT OK
    python check_cube6.py --selftest                   cases that must fail / pass

Judgment calls about the spec are listed in README.md next to this file.
"""

import argparse
import itertools
import os
import random
import sys
import tempfile
import time

import numpy as np

N = 6                    # cube side
NCELL = N ** 3           # 216 cells, id = x*36 + y*6 + z
NLINE_EXPECTED = 148     # ((N+2)^3 - N^3) / 2
NGROUP_EXPECTED = 1152   # 2^(d-1+k) d! k! with d = 3, k = 3
MAX_BLOCK_CELLS = 16     # spec: "blocks have at most 16 cells"
EMPTY, MAKER, BREAKER = 0, 1, 2
CANON_BATCH = 192        # positions canonicalized per numpy call (memory ~ 192*1152*216 bytes)
KEY_BYTES = 56           # 216 cells * 2 bits = 54 bytes, padded to 7 big-endian uint64 words


class CheckFail(Exception):
    """A proof check failed. `ctx` holds the position and record it failed on."""

    def __init__(self, reason, **ctx):
        super().__init__(reason)
        self.reason = reason
        self.ctx = ctx


# ---------------------------------------------------------------- geometry

def cell_id(x, y, z):
    return x * 36 + y * 6 + z


COORDS = np.array([(x, y, z) for x in range(N) for y in range(N) for z in range(N)], dtype=np.int64)
assert all(cell_id(*COORDS[c]) == c for c in range(NCELL))


def build_lines():
    """Every set p, p+d, ..., p+5d inside the cube, d in {-1,0,1}^3 minus 0."""
    found = set()
    for x, y, z in itertools.product(range(N), repeat=3):
        for d in itertools.product((-1, 0, 1), repeat=3):
            if d == (0, 0, 0):
                continue
            pts = [(x + i * d[0], y + i * d[1], z + i * d[2]) for i in range(N)]
            if all(0 <= a < N for p in pts for a in p):
                found.add(tuple(sorted(cell_id(*p) for p in pts)))
    lines = sorted(found)
    assert len(lines) == NLINE_EXPECTED, len(lines)
    return lines


LINES = build_lines()
LINES_ARR = np.array(LINES, dtype=np.int64)              # (148, 6), rows sorted
LINE_THROUGH = np.full((NCELL, NCELL), -1, dtype=np.int64)  # line id through two cells, or -1
for _li, _line in enumerate(LINES):
    for _a, _b in itertools.combinations(_line, 2):
        assert LINE_THROUGH[_a, _b] == -1, "two cells on two lines"
        LINE_THROUGH[_a, _b] = LINE_THROUGH[_b, _a] = _li
LINES_OF_CELL = [[li for li, line in enumerate(LINES) if c in line] for c in range(NCELL)]
LINE_THROUGH_L = LINE_THROUGH.tolist()


def build_group():
    """All maps (x,y,z) -> reflect(t(x_p), t(y_p), t(z_p)) over 6*8*720 candidates
    that send every line to a line; distinct maps only. Asserts order 1152 and closure."""
    perms_t = np.array(list(itertools.permutations(range(N))), dtype=np.int64)  # (720, 6)
    weights = np.array([36, 6, 1], dtype=np.int64)
    keep = {}
    for p in itertools.permutations(range(3)):
        base = COORDS[:, list(p)]                                   # (216, 3)
        for refl in range(8):
            img = perms_t[:, base]                                  # (720, 216, 3)
            for axis in range(3):
                if refl >> axis & 1:
                    img[:, :, axis] = (N - 1) - img[:, :, axis]
            maps = img @ weights                                    # (720, 216)
            lim = maps[:, LINES_ARR]                                # (720, 148, 6)
            lid = LINE_THROUGH[lim[:, :, 0], lim[:, :, 1]]          # (720, 148)
            ok = (lid >= 0).all(axis=1)
            lim_sorted = np.sort(lim, axis=2)
            same = (lim_sorted == LINES_ARR[np.maximum(lid, 0)]).all(axis=2).all(axis=1)
            for i in np.nonzero(ok & same)[0]:
                m = maps[i]
                assert len(set(m.tolist())) == NCELL
                keep.setdefault(m.astype(np.int16).tobytes(), m)
    group = np.array(sorted(keep.values(), key=lambda m: m.tolist()), dtype=np.int64)
    assert len(group) == NGROUP_EXPECTED, len(group)
    ident = np.arange(NCELL, dtype=np.int64)
    members = set(keep)
    assert ident.astype(np.int16).tobytes() in members
    g16 = group.astype(np.int16)
    for f in g16:
        comp = f[group]                                             # f o h for every h
        raw = comp.tobytes()
        step = NCELL * 2
        for j in range(len(group)):
            if raw[j * step:(j + 1) * step] not in members:
                raise AssertionError("group not closed under composition")
    inv = np.argsort(group, axis=1)
    return group, inv


# --------------------------------------------------------------- canonical form

class Canon:
    """Canonical form of a board under G: the least 2-bit-per-cell packing of
    g(board) over g in G. Returns the key and the index of a g achieving it."""

    def __init__(self, group, inv):
        self.G = group
        self.GINV = inv
        self.calls = 0

    def batch(self, boards):
        boards = np.asarray(boards, dtype=np.uint8)
        k = len(boards)
        ng = len(self.GINV)
        self.calls += k
        mapped = boards[:, self.GINV]                   # g(board)[j] = board[g^-1(j)]
        v = mapped.reshape(k, ng, NCELL // 4, 4)
        packed = (v[..., 0] << 6) | (v[..., 1] << 4) | (v[..., 2] << 2) | v[..., 3]
        buf = np.zeros((k, ng, KEY_BYTES), dtype=np.uint8)
        buf[..., :NCELL // 4] = packed
        words = buf.view('>u8').astype(np.uint64)       # (k, ng, 7), big-endian = lexicographic
        cand = np.ones((k, ng), dtype=bool)
        sentinel = np.uint64(0xFFFFFFFFFFFFFFFF)        # unreachable: no cell packs to 3
        for c in range(words.shape[2]):
            vals = np.where(cand, words[:, :, c], sentinel)
            cand &= vals == vals.min(axis=1)[:, None]
        g = cand.argmax(axis=1)
        keys = buf[np.arange(k), g]
        return [keys[i].tobytes() for i in range(k)], g.tolist()

    def one(self, board):
        keys, g = self.batch(board[None, :])
        return keys[0], g[0]


# ----------------------------------------------------------------- parsing

def parse_cell(tok, what):
    if not tok.isdigit() or (len(tok) > 1 and tok[0] == '0'):
        raise CheckFail(f"bad cell id {tok!r} in {what}")
    c = int(tok)
    if c >= NCELL:
        raise CheckFail(f"cell id {c} out of range in {what}")
    return c


def parse_set(tok, what, allow_empty=True):
    if tok == '-':
        if not allow_empty:
            raise CheckFail(f"empty set not allowed in {what}")
        return []
    cells = [parse_cell(t, what) for t in tok.split(',')]
    if any(a >= b for a, b in zip(cells, cells[1:])):
        raise CheckFail(f"cell set not strictly increasing in {what}")
    return cells


def parse_pair(tok, what):
    parts = tok.split('/')
    if len(parts) != 2:
        raise CheckFail(f"bad pair {tok!r} in {what}")
    a, b = parse_cell(parts[0], what), parse_cell(parts[1], what)
    if a == b:
        raise CheckFail(f"pair {tok!r} has two equal cells in {what}")
    return a, b


def parse_head(text):
    """Kind, M, B, r and the raw certificate fields of one record line."""
    fields = text.split(' | ')
    kind = fields[0]
    if kind == 'R':
        if len(fields) != 4:
            raise CheckFail("R record needs 4 fields")
    elif kind == 'L':
        if len(fields) != 6:
            raise CheckFail("L record needs 6 fields")
    else:
        raise CheckFail(f"unknown record kind {kind!r}")
    M = parse_set(fields[1], "M", allow_empty=False)
    B = parse_set(fields[2], "B")
    r = parse_cell(fields[3], "r")
    if len(M) != len(B) + 1:
        raise CheckFail("record has |M| != |B| + 1")
    if set(M) & set(B):
        raise CheckFail("record has a cell in both M and B")
    if r in M or r in B:
        raise CheckFail("Breaker reply is on an occupied cell (in the record itself)")
    return kind, M, B, r, fields[4:]


def parse_cert(fields):
    """(blocks, pairs): blocks = [(cells, [(a, b), ...])], pairs = [(a, b)]."""
    blocks_tok, pairs_tok = fields
    blocks = []
    if blocks_tok != '-':
        for entry in blocks_tok.split(' ; '):
            parts = entry.split(' : ')
            if len(parts) != 2:
                raise CheckFail(f"bad block entry {entry[:60]!r}")
            cells = parse_set(parts[0], "block cells", allow_empty=False)
            claims = [parse_pair(t, "block lines") for t in parts[1].split(',')]
            blocks.append((cells, claims))
    pairs = []
    if pairs_tok != '-':
        pairs = [parse_pair(t, "pairs") for t in pairs_tok.split(' ; ')]
    return blocks, pairs


def fmt_set(cells):
    cells = sorted(int(c) for c in cells)
    return ','.join(map(str, cells)) if cells else '-'


def board_of(M, B):
    b = np.zeros(NCELL, dtype=np.uint8)
    b[list(M)] = MAKER
    b[list(B)] = BREAKER
    return b


def board_sets(board):
    return np.nonzero(board == MAKER)[0].tolist(), np.nonzero(board == BREAKER)[0].tolist()


# ---------------------------------------------------------------- block game

class BlockSolver:
    """Exact Maker-Breaker minimax on one block, Maker to move.

    The game is abstracted to its empty cells (local bits 0..k-1 in cell-id
    order) and its edges' empty parts, which determines the outcome exactly;
    results are memoized on that abstraction."""

    def __init__(self):
        self.results = {}

    def breaker_wins(self, block_cells, edges_cells, board):
        """block_cells: cell ids; edges_cells: list of cell lists (line ∩ block, live lines)."""
        empty = [c for c in block_cells if board[c] == EMPTY]
        local = {c: i for i, c in enumerate(empty)}
        edges = set()
        for e in edges_cells:
            mask = 0
            for c in e:
                v = board[c]
                if v == BREAKER:          # cannot happen for a live line; kept as a guard
                    mask = None
                    break
                if v == EMPTY:
                    mask |= 1 << local[c]
            if mask is None:
                continue
            if mask == 0:
                return False              # Maker already owns a whole edge
            edges.add(mask)
        # An edge that contains another edge never decides anything: Maker
        # owning it means owning the smaller one, and a Breaker mark in the
        # smaller one is also in it. Dropping it is exact.
        edges = sorted(edges, key=lambda m: (bin(m).count('1'), m))
        minimal = []
        for e in edges:
            if not any(f & e == f for f in minimal):
                minimal.append(e)
        key = (len(empty), tuple(sorted(minimal)))
        res = self.results.get(key)
        if res is None:
            res = not _maker_wins_game(len(empty), key[1])
            self.results[key] = res
        return res


def _maker_wins_game(k, edges):
    full = (1 << k) - 1
    degree = [sum(1 for e in edges if e >> i & 1) for i in range(k)]
    order = sorted(range(k), key=lambda i: -degree[i])
    bits = [1 << i for i in order]
    memo = {}

    def solve(mm, bm, maker_turn):
        key = (mm, bm, maker_turn)
        hit = memo.get(key)
        if hit is not None:
            return hit
        live = [e for e in edges if not e & bm]
        # Completed Maker edge first, on both turns.
        if any(e & ~mm == 0 for e in live):
            res = True
        elif not live:
            res = False
        else:
            free = full & ~(mm | bm)
            threats = set()
            for e in live:
                rest = e & ~mm
                if rest & (rest - 1) == 0:
                    threats.add(rest)
            if free == 0:
                res = False
            elif maker_turn:
                if threats:
                    res = True    # Maker completes that edge now
                else:
                    res = any(solve(mm | c, bm, False) for c in bits if free & c)
            else:
                if len(threats) >= 2:
                    res = True    # Breaker can block only one
                elif threats:
                    res = solve(mm, bm | threats.pop(), True)
                else:
                    res = all(solve(mm, bm | c, True) for c in bits if free & c)
        memo[key] = res
        return res

    return solve(0, 0, True)


# ----------------------------------------------------------------- checker

class Checker:
    def __init__(self, canon, log=print, all_records=False):
        self.canon = canon
        self.log = log
        self.index = {}          # canonical key of a Breaker-to-move position -> (file, offset, g, lineno)
        # --all-records: later records of a position, all walked too (as verify/ does).
        # A strategy whose reply depends on move order needs several records per position.
        self.all_records = all_records
        self.extra = {}          # canonical key -> [entries after the first]
        self.files = []
        self.nrecords = 0
        self.nduplicates = 0
        self.maker_done = set()  # canonical keys of verified Maker-to-move positions
        self.child_done = set()  # canonical keys of verified Breaker-to-move positions
        self.nleaves = 0
        self.solver = BlockSolver()

    # -- index -------------------------------------------------------------
    def load(self, path):
        fid = len(self.files)
        fh = open(path, 'rb')
        self.files.append((path, fh))
        pending = []             # (board, offset, lineno)
        offset = 0
        t0 = time.time()
        with open(path, 'rb') as f:
            for lineno, raw in enumerate(f, 1):
                start = offset
                offset += len(raw)
                text = raw.decode('ascii').rstrip('\r\n')
                if text.startswith('#'):
                    continue
                if text == '':
                    raise CheckFail("blank line in proof file", record=f"{path}:{lineno}")
                try:
                    kind, M, B, r, _ = parse_head(text)
                except CheckFail as e:
                    e.ctx.setdefault('record', f"{path}:{lineno}")
                    raise
                self.nrecords += 1
                pending.append((board_of(M, B), start, lineno))
                if len(pending) >= CANON_BATCH:
                    self._index_batch(fid, pending)
                    pending = []
                if self.nrecords % 100000 == 0:
                    self.log(f"  indexed {self.nrecords} records ({time.time() - t0:.0f} s)")
        if pending:
            self._index_batch(fid, pending)

    def _index_batch(self, fid, pending):
        keys, gs = self.canon.batch(np.stack([p[0] for p in pending]))
        for key, g, (_, off, lineno) in zip(keys, gs, pending):
            if key in self.index:
                self.nduplicates += 1       # first record for a position wins, unless --all-records
                if self.all_records:
                    self.extra.setdefault(key, []).append((fid, off, g, lineno))
                continue
            self.index[key] = (fid, off, g, lineno)

    def read_record(self, entry):
        fid, off, g, lineno = entry
        path, fh = self.files[fid]
        fh.seek(off)
        text = fh.readline().decode('ascii').rstrip('\r\n')
        return text, g, f"{path}:{lineno}"

    # -- tree --------------------------------------------------------------
    def check_root(self, root_cell=None):
        board = np.zeros(NCELL, dtype=np.uint8)
        self.check_maker(board, only=root_cell)

    def check_maker(self, board, only=None):
        if only is None:
            key, _ = self.canon.one(board)
            if key in self.maker_done:
                return
        # 1. No Maker line.
        if (board[LINES_ARR] == MAKER).all(axis=1).any():
            M, B = board_sets(board)
            raise CheckFail("Maker owns a whole line", M=M, B=B)
        # 2. Every empty cell (or only the --root cell).
        if only is None:
            moves = np.nonzero(board == EMPTY)[0].tolist()
        else:
            if board[only] != EMPTY:
                raise CheckFail("root cell not empty")
            moves = [only]
        for i in range(0, len(moves), CANON_BATCH):
            chunk = moves[i:i + CANON_BATCH]
            children = np.repeat(board[None, :], len(chunk), axis=0)
            children[np.arange(len(chunk)), chunk] = MAKER
            keys, gs = self.canon.batch(children)
            for m, child, ckey, gq in zip(chunk, children, keys, gs):
                if ckey in self.child_done:
                    continue
                self.check_child(child, m, ckey, gq)
                self.child_done.add(ckey)
        if only is None:
            self.maker_done.add(key)
            if len(self.maker_done) % 200 == 0:
                self.log(f"  {len(self.maker_done)} Maker nodes, {self.nleaves} leaves, "
                         f"{len(self.solver.results)} block games")

    def check_child(self, child, m, ckey, gq):
        """Position (M + m, B), Breaker to move: its first record, and with
        --all-records every later one too."""
        entry = self.index.get(ckey)
        if entry is None:
            M, B = board_sets(child)
            raise CheckFail("no record for this position", M=M, B=B, maker_move=m)
        for e in [entry] + self.extra.get(ckey, []):
            self.check_record(child, m, gq, e)

    def check_record(self, child, m, gq, entry):
        M, B = board_sets(child)
        text, grec, where = self.read_record(entry)
        ctx = dict(M=M, B=B, maker_move=m, record=where)
        try:
            kind, Mr, Br, rr, cert_fields = parse_head(text)
            s = self.canon.GINV[gq][self.canon.G[grec]]     # record orientation -> this position
            if sorted(s[Mr].tolist()) != M or sorted(s[Br].tolist()) != B:
                raise CheckFail("internal: symmetry does not map the record onto the position")
            r = int(s[rr])
            ctx['reply'] = r
            if child[r] != EMPTY:
                raise CheckFail("Breaker reply is on an occupied cell")
            after = child.copy()
            after[r] = BREAKER
            if kind == 'R':
                pass
            else:
                blocks, pairs = parse_cert(cert_fields)
                self.check_certificate(after, s, blocks, pairs)
                self.nleaves += 1
                return
        except CheckFail as e:
            for k, v in ctx.items():
                e.ctx.setdefault(k, v)
            raise
        self.check_maker(after)

    # -- certificate -------------------------------------------------------
    def check_certificate(self, board, s, blocks, pairs):
        """Position `board`, Maker to move; certificate given in record orientation, mapped by s."""
        smap = s.tolist()
        if (board[LINES_ARR] == MAKER).all(axis=1).any():
            raise CheckFail("Maker owns a whole line at the leaf")
        used = [False] * NCELL
        covered = [False] * NLINE_EXPECTED
        mblocks = []
        # 1-2. Disjoint gadgets, valid claims and pairs.
        for bi, (cells, claims) in enumerate(blocks):
            if len(cells) > MAX_BLOCK_CELLS:
                raise CheckFail(f"block {bi} has {len(cells)} cells (> {MAX_BLOCK_CELLS})")
            mcells = [smap[c] for c in cells]
            for c in mcells:
                if used[c]:
                    raise CheckFail(f"gadgets overlap at cell {c} (block {bi})")
                used[c] = True
            cellset = set(mcells)
            lids = []
            for a, b in claims:
                a, b = smap[a], smap[b]
                if a not in cellset or b not in cellset:
                    raise CheckFail(f"block {bi} claims {a}/{b} with a cell outside the block")
                li = LINE_THROUGH_L[a][b]
                if li < 0:
                    raise CheckFail(f"block {bi} claim {a}/{b} is not on a line")
                lids.append(li)
                covered[li] = True
            mblocks.append((mcells, lids))
        for a, b in pairs:
            a, b = smap[a], smap[b]
            for c in (a, b):
                if used[c]:
                    raise CheckFail(f"gadgets overlap at cell {c} (pair {a}/{b})")
                if board[c] != EMPTY:
                    raise CheckFail(f"pair {a}/{b} has a marked cell {c}")
                used[c] = True
            li = LINE_THROUGH_L[a][b]
            if li < 0:
                raise CheckFail(f"pair {a}/{b} is not on a line")
            covered[li] = True
        # 3. Every live line covered.
        live = ~(board[LINES_ARR] == BREAKER).any(axis=1)
        for li in np.nonzero(live)[0].tolist():
            if not covered[li]:
                raise CheckFail(f"live line {fmt_set(LINES[li])} is not covered")
        # 4. Each block a Breaker win.
        for bi, (mcells, lids) in enumerate(mblocks):
            cellset = set(mcells)
            edges = [[c for c in LINES[li] if c in cellset] for li in sorted(set(lids)) if live[li]]
            if not self.solver.breaker_wins(sorted(mcells), edges, board):
                raise CheckFail(f"block {bi} ({fmt_set(mcells)}) is a Maker win")


# ------------------------------------------------------------------- output

def peak_rss_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except ImportError:
        return None


def report_fail(e):
    print(f"FAIL: {e.reason}")
    for k in ('record', 'M', 'B', 'maker_move', 'reply'):
        if k in e.ctx:
            v = e.ctx[k]
            print(f"  {k}: {fmt_set(v) if isinstance(v, list) else v}")


def print_counts(chk, t0):
    fate = "all walked" if chk.all_records else "ignored"
    print(f"records read: {chk.nrecords}  (duplicate positions {fate}: {chk.nduplicates})")
    print(f"Maker nodes checked: {len(chk.maker_done)}")
    print(f"leaves checked: {chk.nleaves}")
    print(f"distinct block games solved: {len(chk.solver.results)}")
    print(f"seconds: {time.time() - t0:.1f}")
    mb = peak_rss_mb()
    if mb is not None:
        print(f"peak RSS MB: {mb:.0f}")


def run(paths, root, all_records=False):
    t0 = time.time()
    canon = Canon(*build_group())
    print(f"built {len(LINES)} lines and group of {len(canon.G)} maps (closed) in {time.time() - t0:.1f} s",
          flush=True)
    chk = Checker(canon, log=lambda s: print(s, flush=True), all_records=all_records)
    try:
        for p in paths:
            chk.load(p)
        print(f"indexed {len(chk.index)} positions from {chk.nrecords} records in "
              f"{time.time() - t0:.0f} s", flush=True)
        chk.check_root(root)
    except CheckFail as e:
        report_fail(e)
        print_counts(chk, t0)
        return 1
    print("ROOT ORBIT OK" if root is not None else "PROOF OK")
    print_counts(chk, t0)
    return 0


# ----------------------------------------------------------------- selftest

def greedy_reply(board):
    """Breaker cell hitting the most live lines, weighted by Maker marks on them."""
    best, best_score = None, -1
    live_maker = {}
    for li, line in enumerate(LINES):
        vals = board[list(line)]
        if not (vals == BREAKER).any():
            live_maker[li] = int((vals == MAKER).sum())
    for c in np.nonzero(board == EMPTY)[0].tolist():
        score = sum(1 + 4 * live_maker[li] ** 2 for li in LINES_OF_CELL[c] if li in live_maker)
        if score > best_score:
            best, best_score = c, score
    return best


def pair_cover(board):
    """Disjoint empty pairs covering every live line, or None."""
    used = set()
    live = [li for li, line in enumerate(LINES) if not (board[list(line)] == BREAKER).any()]
    live.sort(key=lambda li: int((board[list(LINES[li])] == EMPTY).sum()))
    pairs = []
    for li in live:
        free = [c for c in LINES[li] if board[c] == EMPTY and c not in used]
        if len(free) < 2:
            return None
        pairs.append((free[0], free[1]))
        used.update(free[:2])
    return pairs


def build_pass_position():
    """Play a dumb Maker against a greedy Breaker until every Maker move has a
    pair-cover leaf after Breaker's greedy reply. Returns the Maker-to-move
    board and the leaf data for each move."""
    board = np.zeros(NCELL, dtype=np.uint8)
    while True:
        live = [li for li, line in enumerate(LINES) if not (board[list(line)] == BREAKER).any()]
        empties = np.nonzero(board == EMPTY)[0].tolist()
        leaves = {}
        for m in empties:
            child = board.copy()
            child[m] = MAKER
            r = greedy_reply(child)
            after = child.copy()
            after[r] = BREAKER
            pairs = pair_cover(after)
            if pairs is None:
                break
            leaves[m] = (child, r, pairs)
        else:
            return board, leaves
        # Maker: the empty cell on the fewest live lines; Breaker: greedy.
        m = min(empties, key=lambda c: (sum(1 for li in LINES_OF_CELL[c] if li in live), c))
        board[m] = MAKER
        board[greedy_reply(board)] = BREAKER


def selftest():
    t0 = time.time()
    canon = Canon(*build_group())
    print(f"group: {len(canon.G)} maps, closed; lines: {len(LINES)}")
    rng = random.Random(6)

    # Block solver sanity on tiny games.
    sv = BlockSolver()
    b = np.zeros(NCELL, dtype=np.uint8)
    assert sv.breaker_wins([0, 1], [[0, 1]], b)                    # pair: Breaker wins
    assert not sv.breaker_wins([0, 1, 2], [[0, 1], [0, 2]], b)    # fork: Maker wins
    b2 = b.copy(); b2[0] = MAKER
    assert not sv.breaker_wins([0, 1], [[0, 1]], b2)               # Maker to move completes
    b3 = b.copy(); b3[0] = MAKER; b3[1] = MAKER
    assert not sv.breaker_wins([0, 1, 2], [[0, 1]], b3)            # already complete

    board, leaves = build_pass_position()
    M0, B0 = board_sets(board)
    print(f"pass position: |M| = |B| = {len(M0)}, {len(leaves)} Maker moves")
    # Records, each written in a random orientation.
    records = {}
    for m, (child, r, pairs) in leaves.items():
        g = canon.G[rng.randrange(len(canon.G))]
        Mc, Bc = board_sets(child)
        Mg, Bg = sorted(g[Mc].tolist()), sorted(g[Bc].tolist())
        pr = [tuple(sorted((int(g[a]), int(g[b])))) for a, b in pairs]
        records[m] = dict(M=Mg, B=Bg, r=int(g[r]), blocks=[], pairs=pr, g=g)

    def text_of(rec):
        blocks = ' ; '.join(f"{fmt_set(c)} : " + ','.join(f"{a}/{b}" for a, b in cl)
                            for c, cl in rec['blocks']) or '-'
        pairs = ' ; '.join(f"{a}/{b}" for a, b in rec['pairs']) or '-'
        return f"L | {fmt_set(rec['M'])} | {fmt_set(rec['B'])} | {rec['r']} | {blocks} | {pairs}"

    def run_case(recs, extra=(), all_records=False):
        """Check `board` against `recs` plus raw record lines written after them."""
        chk = Checker(canon, log=lambda s: None, all_records=all_records)
        fd, path = tempfile.mkstemp(suffix='.txt')
        with os.fdopen(fd, 'w') as f:
            f.write("# selftest\n")
            for rec in recs.values():
                f.write(text_of(rec) + "\n")
            for line in extra:
                f.write(line + "\n")
        try:
            chk.load(path)
            chk.check_maker(board.copy())
            return None
        except CheckFail as e:
            return e.reason
        finally:
            for _, fh in chk.files:
                fh.close()
            os.unlink(path)

    def mutated(m, fn):
        recs = {k: dict(v, pairs=list(v['pairs']), blocks=list(v['blocks'])) for k, v in records.items()}
        fn(recs[m])
        return recs

    m1 = sorted(records)[len(records) // 2]
    rec1 = records[m1]
    g1 = rec1['g']
    ginv1 = np.argsort(g1)
    child1 = leaves[m1][0]

    def occupied(rec):
        rec['r'] = int(g1[m1])                     # the Maker move itself
    def overlap(rec):
        a, b = rec['pairs'][0]
        c, d = rec['pairs'][1]
        rec['pairs'][1] = tuple(sorted((a, d))) if a != d else tuple(sorted((a, c)))
    def off_line(rec):
        a, b = rec['pairs'][0]
        used = {c for p in rec['pairs'] for c in p}
        after = child1.copy(); after[leaves[m1][1]] = BREAKER
        for c in range(NCELL):
            gc = int(ginv1[c])
            if c not in used and after[gc] == EMPTY and LINE_THROUGH[a, c] < 0:
                rec['pairs'][0] = tuple(sorted((a, c)))
                return
        raise AssertionError("no off-line cell")
    def uncovered(rec):
        rec['pairs'].pop()
    def maker_win_block(rec):
        # Two pairs (a, b) on line L1 and (c, d) on L2, where L1 and L2 meet in
        # an empty cell x outside every gadget, become the block {a, c, x}
        # claiming a/x and c/x: Maker takes x and threatens a and c at once.
        used = {c for p in rec['pairs'] for c in p}
        after = child1.copy(); after[leaves[m1][1]] = BREAKER
        free = {c for c in range(NCELL) if after[int(ginv1[c])] == EMPTY and c not in used}
        prs = rec['pairs']
        for i, j in itertools.combinations(range(len(prs)), 2):
            (a, b), (c, d) = prs[i], prs[j]
            l1, l2 = set(LINES[LINE_THROUGH[a, b]]), set(LINES[LINE_THROUGH[c, d]])
            for x in sorted(l1 & l2 & free):
                rec['pairs'] = [p for k, p in enumerate(prs) if k not in (i, j)]
                rec['blocks'].append((sorted((a, c, x)), [(a, x), (c, x)]))
                return
        raise AssertionError("no two pair lines meeting in a free cell")

    cases = [
        ("reply on an occupied cell", mutated(m1, occupied), "occupied"),
        ("overlapping gadgets", mutated(m1, overlap), "overlap"),
        ("pair not on one line", mutated(m1, off_line), "not on a line"),
        ("uncovered live line", mutated(m1, uncovered), "not covered"),
        ("block that is a Maker win", mutated(m1, maker_win_block), "Maker win"),
        ("Maker move with no record", {k: v for k, v in records.items() if k != m1}, "no record"),
    ]
    ok = True
    for name, recs, expect in cases:
        got = run_case(recs)
        good = got is not None and expect in got
        ok &= good
        print(f"  {'ok ' if good else 'BAD'} must fail: {name}: {got}")
    got = run_case(records)
    ok &= got is None
    print(f"  {'ok ' if got is None else 'BAD'} must pass: valid Maker node, records in random orientations: {got}")

    # --all-records: a second record of a position is checked too. After
    # m1's valid L record comes an R record for the same position whose
    # continuation has no records: the first-record walk never reads it,
    # and the all-records walk must reject it.
    spare = next(c for c in range(NCELL)
                 if c not in rec1['M'] and c not in rec1['B'] and c != rec1['r'])
    bad_r = f"R | {fmt_set(rec1['M'])} | {fmt_set(rec1['B'])} | {spare}"
    got = run_case(records, extra=[bad_r])
    ok &= got is None
    print(f"  {'ok ' if got is None else 'BAD'} must pass: bad second record, first record only: {got}")
    got = run_case(records, extra=[bad_r], all_records=True)
    good = got is not None and "no record" in got
    ok &= good
    print(f"  {'ok ' if good else 'BAD'} must fail: bad second record, --all-records: {got}")
    print(f"seconds: {time.time() - t0:.1f}")
    print("SELFTEST OK" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('proof', nargs='*', help="proof file(s); records from all are merged")
    ap.add_argument('--root', type=int, help="check only Maker's first move at this cell")
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--all-records', action='store_true',
                    help="check every record of a reached position, not only the first in file order")
    args = ap.parse_args()
    sys.setrecursionlimit(20000)
    if args.selftest:
        return selftest()
    if not args.proof:
        ap.error("give a proof file or --selftest")
    if args.root is not None and not 0 <= args.root < NCELL:
        ap.error("--root must be a cell id 0..215")
    return run(args.proof, args.root, args.all_records)


if __name__ == '__main__':
    sys.exit(main())
