"""Fit catalogue layouts to leaf positions (minimum-catalogue job, docs/leaf-catalogue.md).

A catalogue entry is a layout: a set of disjoint blocks, each with the lines
it claims (the block library's claim set, the same for a cell set across the
whole proof). Pairs are not part of an entry: they are recomputed for each
leaf by matching. Layout k fits leaf (M, B) (Maker to move) under map g when,
with the leaf mapped into the layout's frame by g:

1. every live line (no Breaker cell) is claimed by a block or gets a pair:
   two empty cells of the line outside every block, all pairs disjoint
   (a bipartite matching, each line taking two cells);
2. every block is a Breaker win, Maker to move, on its live claimed lines
   restricted to the block, with Maker's cells inside it already taken
   (solved exactly by gen/mbfast.py, cached on the reduced game).

Fast necessary conditions (`views`, `prefilter`) prune the 1,152 maps
before the exact check (`fit`): a live line that no block claims needs two
free cells, so it can hold at most 4 block or Maker cells, and there must be
two free cells per such line in total. Both are implied by condition 1.
"""
import json, pickle
import numpy as np
import cube6 as C
import mincat_common as K
import mbfast

NL, NC = len(C.LINES), C.CELLS
INC = C.INC.astype(bool)                       # (148, 216)
INC_T = np.ascontiguousarray(INC.T)            # (216, 148)
LINE_CELLS = [tuple(cells) for cells, _ in C.LINES]
PAIR_SLOTS = 2                                 # a pair uses two cells of its line
MAX_PAIR_BLOCKERS = 6 - PAIR_SLOTS             # block or Maker cells a paired line can hold


def load_catalogue(layouts_pkl, data6_json):
    """Layouts from gen/mine.py's layouts.pkl (most used orientation), with
    each block's claimed lines from the block library in data6.json."""
    d = pickle.load(open(layouts_pkl, "rb"))
    data = json.load(open(data6_json))
    line_index = {tuple(sorted(c)): i for i, c in enumerate(LINE_CELLS)}
    claims = {}
    for b in data["blocks"]:
        cells = tuple(sorted(b["cells"]))
        claims[cells] = tuple(sorted(line_index[tuple(sorted(data["lines"][l]))] for l in b["lines"]))
    keys = sorted(d["layouts"], key=lambda k: -sum(d["layouts"][k].values()))
    cat, uses = [], []
    for k in keys:
        cat.append([(tuple(b), claims[tuple(b)]) for b in d["sample"][k]])
        uses.append(sum(d["layouts"][k].values()))
    return cat, np.array(uses)


class Layout:
    """Per-layout arrays in its own frame."""

    def __init__(self, blocks):
        self.blocks = blocks
        self.block_of = np.full(NC, -1, np.int16)
        for j, (cells, _) in enumerate(blocks):
            self.block_of[list(cells)] = j
        self.in_block = self.block_of >= 0
        self.claimed = np.zeros(NL, bool)
        for _, ls in blocks:
            self.claimed[list(ls)] = True
        self.blkcnt = INC[:, self.in_block].sum(1).astype(np.int8)   # block cells per line
        self.ncells = int(self.in_block.sum())
        # line l, unclaimed, tolerates (MAX_PAIR_BLOCKERS - blkcnt) Maker cells; < 0 means it must be dead
        self.tol = np.where(self.claimed, 99, MAX_PAIR_BLOCKERS - self.blkcnt).astype(np.int16)
        self.local = [{c: i for i, c in enumerate(cells)} for cells, _ in blocks]
        self.edges = [[(l, sum(1 << self.local[j][c] for c in LINE_CELLS[l] if c in self.local[j]))
                       for l in ls] for j, (cells, ls) in enumerate(blocks)]
        # A block that Breaker wins from empty with every claim live also wins with
        # any claims dead (a sub-hypergraph), so only the others need a check per leaf.
        self.conditional = [j for j in range(len(blocks))
                            if not mbfast.solve([m for _, m in self.edges[j]])]


class Catalogue:
    def __init__(self, blocks_list):
        self.L = [Layout(b) for b in blocks_list]
        self.must_dead = np.array([l.tol < 0 for l in self.L], np.float32)     # (K, 148)
        self.claimed = np.array([l.claimed for l in self.L])
        self.ncells = np.array([l.ncells for l in self.L])
        self.in_block = np.array([l.in_block for l in self.L])   # (K, 216)
        self.tol = np.array([l.tol for l in self.L])             # (K, 148)
        self.games = {}   # reduced block game -> Breaker wins
        self.fast = {}    # (layout, block, Maker cells, live claims) -> Breaker wins

    # ---- necessary conditions -------------------------------------------
    def views(self, B, sub=slice(None)):
        """For Breaker set B (any frame), the (g, k) where layout k (of the
        slice `sub`) could fit g(position) ignoring Maker: every line that
        must be dead is dead, and there are free cells for the pairs.
        Returns (g array, k array, dead lines per g)."""
        Bimg = K.G[:, list(B)]                                   # (1152, b)
        dead = INC_T[Bimg].any(1)                                # (1152, 148) dead lines in layout frame
        live = (~dead).astype(np.float32)
        bad = live @ self.must_dead[sub].T                       # (1152, K)
        ok = bad < 0.5
        nunc = live @ (~self.claimed[sub]).T.astype(np.float32)  # unclaimed live lines
        inb = self.in_block[sub].astype(np.float32)              # (K, 216)
        binb = np.zeros((len(Bimg), len(inb)), np.float32)
        for j in range(Bimg.shape[1]):
            binb += inb[:, Bimg[:, j]].T
        free = NC - self.ncells[sub][None, :] - (Bimg.shape[1] - binb)
        ok &= PAIR_SLOTS * nunc <= free
        g, k = np.nonzero(ok)
        return g, k + (sub.start or 0), dead

    def prefilter(self, M, g, k, dead):
        """Keep views where Maker's cells leave every unclaimed live line two free cells."""
        Mimg = K.G[g][:, list(M)]                                # (V, m)
        # Maker cells outside blocks, per line: block cells are already in tol,
        # so a Maker cell inside a block must not be counted again.
        outside = ~self.in_block[k[:, None], Mimg]               # (V, m)
        mcnt = (INC_T[Mimg] & outside[:, :, None]).sum(1)        # (V, 148)
        over = ~dead[g] & (mcnt > self.tol[k])
        keep = ~over.any(1)
        minb = np.zeros(len(g), int)
        for j in range(Mimg.shape[1]):
            minb += self.in_block[k, Mimg[:, j]]
        return keep, Mimg, minb

    # ---- exact check -----------------------------------------------------
    def block_wins(self, lay, j, live, Mset):
        """Breaker wins block j, Maker to move, with Maker's cells Mset taken.
        Cached first on (layout, block, Maker cells inside, live claims),
        then on the reduced game, which is what decides it."""
        loc = lay.local[j]
        mmask = 0
        for c in Mset:
            i = loc.get(c)
            if i is not None:
                mmask |= 1 << i
        lmask = 0
        for t, (l, _) in enumerate(lay.edges[j]):
            if live[l]:
                lmask |= 1 << t
        fast = (id(lay), j, mmask, lmask)
        v = self.fast.get(fast)
        if v is None:
            v = self.fast[fast] = self._solve_block(lay, j, live, Mset)
        return v

    def _solve_block(self, lay, j, live, Mset):
        rem = []
        for l, mask in lay.edges[j]:
            if not live[l]:
                continue
            r = mask
            for c in Mset:
                i = lay.local[j].get(c)
                if i is not None:
                    r &= ~(1 << i)
            rem.append(r)
        key = mbfast._reduce(rem)
        v = self.games.get(key)
        if v is None:
            v = self.games[key] = bool(mbfast.solve(list(key)))
        return v

    def lose_alone(self):
        """(K, 216) bool: a Maker mark on this cell alone, every claim live,
        makes its block a Maker win. Used only to order views (likely fits
        first), never to reject one, since dead claims can save the block."""
        out = np.zeros((len(self.L), NC), bool)
        everything = np.ones(NL, bool)
        for k, lay in enumerate(self.L):
            for c in np.flatnonzero(lay.in_block):
                out[k, c] = not self.block_wins(lay, int(lay.block_of[c]), everything, (int(c),))
        return out

    def fit_map(self, k, g, M, B):
        """fit() for position (M, B) mapped into layout k's frame by G[g]."""
        Bg = [int(c) for c in K.G[g][list(B)]]
        live = ~(INC_T[Bg].any(0) if Bg else np.zeros(NL, bool))
        return self.fit(k, [int(c) for c in K.G[g][list(M)]], Bg, live)

    def fit(self, k, Mg, Bg, live):
        """Exact check of layout k on the position with Maker cells Mg and
        Breaker cells Bg, both in the layout's frame (`live`: the lines with
        no Breaker cell). Returns the pairs [(line, a, b)] or None."""
        lay = self.L[k]
        touched = {int(lay.block_of[c]) for c in Mg if lay.block_of[c] >= 0}
        for j in touched.union(lay.conditional):
            if not self.block_wins(lay, j, live, Mg):
                return None
        occupied = set(Mg) | set(Bg)
        need = [l for l in np.flatnonzero(live & ~lay.claimed)]
        cand = [[c for c in LINE_CELLS[l] if not lay.in_block[c] and c not in occupied] for l in need]
        return match_pairs(need, cand)

    def class_views(self, B0):
        """Views of Breaker set B0 that fit with no Maker cell at all, and the
        cells their pairs use. Maker cells only add constraints, so a leaf
        with Breaker set B0 can fit only these views; when none of its Maker
        cells is a pair cell or inside a block, the same pairs still work.
        Returns (g, k, live per g, pair cells per view as a (V, 216) bool)."""
        g, k, dead = self.views(B0)
        live = ~dead
        keep = np.zeros(len(g), bool)
        used = np.zeros((len(g), NC), bool)
        for v in range(len(g)):
            Bg = [int(c) for c in K.G[g[v]][list(B0)]]
            pairs = self.fit(int(k[v]), [], Bg, live[g[v]])
            if pairs is not None:
                keep[v] = True
                for _, a, b in pairs:
                    used[v, a] = used[v, b] = True
        return g[keep], k[keep], live, used[keep]


def match_pairs(need, cand):
    """Give each line two of its candidate cells, all distinct (Kuhn's
    augmenting paths over two slots per line). Returns [(line, a, b)] or None."""
    owner = {}                                   # cell -> slot index
    slots = [i for i in range(len(need)) for _ in range(PAIR_SLOTS)]

    def augment(s, seen):
        for c in cand[slots[s]]:
            if c in seen:
                continue
            seen.add(c)
            o = owner.get(c)
            if o is None or augment(o, seen):
                owner[c] = s
                return True
        return False

    order = sorted(range(len(slots)), key=lambda s: len(cand[slots[s]]))
    for s in order:
        if not augment(s, set()):
            return None
    got = {}
    for c, s in owner.items():
        got.setdefault(slots[s], []).append(c)
    return [(int(need[i]), *sorted(got[i])) for i in range(len(need))]
