"""Independent checker for the static 7x7x7 Breaker cover (seven/cover7.txt).

Written from the task specification alone, without reading the Rust checker
(`seven cover`) or the generator, so the two checkers share no code or ideas.
Python 3 standard library only.

Usage: python seven/check_cover7.py seven/cover7.txt

Why a valid cover means Breaker wins 7x7x7 Maker-Breaker (Maker first): Breaker
answers each Maker move inside the gadget she played in, using that block's
winning strategy or the pair's other cell, and plays anywhere when she plays a
spare cell or a finished gadget (an extra Breaker mark never hurts him). Every
claimed line then gets a Breaker mark, and every line is claimed.

Checked: cells in range; gadgets pairwise disjoint; each edge (>= 2 cells, all
in its block) and each pair lies on one board line; all 193 lines are claimed;
each block is a Breaker win of its local game (edges are the winning sets,
Maker first, exhaustive memoized minimax).
"""
import itertools
import sys

N = 7
EXPECTED_LINES = 193


class CoverError(Exception):
    pass


def all_lines():
    """All lines as frozensets of cells; d and -d give the same line."""
    lines = set()
    rng = range(N)
    for d in itertools.product((-1, 0, 1), repeat=3):
        if d == (0, 0, 0):
            continue
        for p in itertools.product(rng, repeat=3):
            cells = [tuple(p[i] + k * d[i] for i in range(3)) for k in range(N)]
            if all(0 <= c < N for cell in cells for c in cell):
                lines.add(frozenset(cells))
    return lines


def parse_cell(text):
    parts = text.strip().split(",")
    if len(parts) != 3:
        raise CoverError(f"bad cell {text!r}")
    try:
        cell = tuple(int(v) for v in parts)
    except ValueError:
        raise CoverError(f"bad cell {text!r}")
    if not all(0 <= v < N for v in cell):
        raise CoverError(f"cell {text!r} out of range")
    return cell


def parse(path):
    """Return (blocks, pairs); a block is (cells list, edges list of lists)."""
    blocks, pairs = [], []
    with open(path, encoding="utf-8") as f:
        for no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                if line.startswith("block "):
                    fields = [s.strip() for s in line.split("|")]
                    cells = [parse_cell(t) for t in fields[0][len("block "):].split()]
                    edges = []
                    for fld in fields[1:]:
                        if not fld.startswith("edge "):
                            raise CoverError(f"expected 'edge ...', got {fld!r}")
                        edges.append([parse_cell(t) for t in fld[len("edge "):].split(";")])
                    blocks.append((cells, edges))
                elif line.startswith("pair "):
                    toks = line.split()
                    if len(toks) != 3:
                        raise CoverError("pair needs exactly two cells")
                    pairs.append((parse_cell(toks[1]), parse_cell(toks[2])))
                else:
                    raise CoverError(f"unknown record {line[:20]!r}")
            except CoverError as e:
                raise CoverError(f"line {no}: {e}")
    return blocks, pairs


def line_through(cells, lines):
    """The unique board line containing all cells (>= 2 distinct), or None."""
    found = [ln for ln in lines if all(c in ln for c in cells)]
    return found[0] if len(found) == 1 else None


def breaker_wins_block(cells, edges):
    """Exhaustive minimax: Maker moves first; Breaker wins iff every edge gets a Breaker mark."""
    index = {c: i for i, c in enumerate(cells)}
    masks = [sum(1 << index[c] for c in set(e)) for e in edges]
    full = (1 << len(cells)) - 1
    memo = {}

    def breaker_wins(maker, breaker):
        # Maker completed an edge: she wins (tested before anything else).
        if any(m & maker == m for m in masks):
            return False
        if all(m & breaker for m in masks):
            return True
        key = (maker, breaker)
        if key in memo:
            return memo[key]
        free = full & ~(maker | breaker)
        if free == 0:
            result = True  # board full, no Maker edge: every edge holds a Breaker cell
        else:
            makers_turn = bin(maker).count("1") == bin(breaker).count("1")
            moves = [1 << i for i in range(len(cells)) if free >> i & 1]
            if makers_turn:
                result = all(breaker_wins(maker | m, breaker) for m in moves)
            else:
                result = any(breaker_wins(maker, breaker | m) for m in moves)
        memo[key] = result
        return result

    return breaker_wins(0, 0)


def check(path):
    lines = all_lines()
    if len(lines) != EXPECTED_LINES:
        raise CoverError(f"expected {EXPECTED_LINES} lines, built {len(lines)}")
    blocks, pairs = parse(path)

    seen = {}
    def claim_cell(cell, label):
        if cell in seen:
            raise CoverError(f"cell {cell} in both {seen[cell]} and {label}")
        seen[cell] = label

    for bi, (cells, _) in enumerate(blocks):
        if len(set(cells)) != len(cells):
            raise CoverError(f"block {bi} repeats a cell")
        for c in cells:
            claim_cell(c, f"block {bi}")
    for pi, (a, b) in enumerate(pairs):
        if a == b:
            raise CoverError(f"pair {pi} repeats a cell")
        claim_cell(a, f"pair {pi}")
        claim_cell(b, f"pair {pi}")

    block_lines, pair_lines = set(), set()
    total_edges = full_edges = 0
    for bi, (cells, edges) in enumerate(blocks):
        cellset = set(cells)
        for ei, edge in enumerate(edges):
            if len(set(edge)) < 2 or len(set(edge)) != len(edge):
                raise CoverError(f"block {bi} edge {ei}: needs at least two distinct cells")
            if not set(edge) <= cellset:
                raise CoverError(f"block {bi} edge {ei}: cell outside its block")
            ln = line_through(edge, lines)
            if ln is None:
                raise CoverError(f"block {bi} edge {ei}: cells not on one board line")
            block_lines.add(ln)
            total_edges += 1
            if set(edge) == ln & cellset:
                full_edges += 1
    for pi, (a, b) in enumerate(pairs):
        ln = line_through([a, b], lines)
        if ln is None:
            raise CoverError(f"pair {pi}: cells not on one board line")
        pair_lines.add(ln)

    unclaimed = lines - block_lines - pair_lines
    if unclaimed:
        raise CoverError(f"{len(unclaimed)} lines unclaimed, e.g. {sorted(next(iter(unclaimed)))[:2]}")

    for bi, (cells, edges) in enumerate(blocks):
        if not breaker_wins_block(cells, edges):
            raise CoverError(f"block {bi} is a Maker win in its local game")

    return {
        "lines": len(lines),
        "blocks": len(blocks),
        "pairs": len(pairs),
        "total edges": total_edges,
        "distinct lines claimed by blocks": len(block_lines),
        "lines claimed only by pairs": len(pair_lines - block_lines),
        "unused cells": N ** 3 - len(seen),
        "edges equal to full line-block intersection": full_edges,
    }


def main(argv):
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1])
        return 2
    try:
        stats = check(argv[1])
    except (CoverError, OSError) as e:
        print(f"COVER FAILED: {e}")
        return 1
    print("COVER OK")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
