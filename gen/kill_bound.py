"""Most lines k Breaker marks can kill on the n x n x n board (exact).

usage: python gen/kill_bound.py <n> <k_max> [--no-center]
Prints, for k = 1..k_max, the most lines k cells can meet, and the density
of what is left after k rounds: live lines / free cells, with Maker's k marks
also off the board. A pairing needs density 1/2 or less; the 3x4 blocks of
the 6x6x6 proof reach 3/4 locally (docs/strategy.md). --no-center forbids
the center (odd n), as when Maker opened there.

Branch and bound over cells in order of degree: a branch is cut when the
lines it has killed plus the largest k - depth marginal gains still
available can't beat the best set found. That bound never undercounts, so
every printed maximum is exact.
"""
import itertools, sys, time

def board(n):
    cells = list(itertools.product(range(n), repeat=3))
    idx = {c: i for i, c in enumerate(cells)}
    dirs = [d for d in itertools.product([-1, 0, 1], repeat=3) if any(d) and next(x for x in d if x) > 0]
    lines = []
    for d in dirs:
        for p in cells:
            pts = [tuple(p[i] + t * d[i] for i in range(3)) for t in range(n)]
            if all(0 <= x < n for q in pts for x in q):
                lines.append([idx[q] for q in pts])
    return cells, idx, lines

def max_kills(masks, k):
    """Largest number of lines k of the given cells meet. masks: one line
    bitmask per cell, sorted by popcount, highest first."""
    best = 0
    def dfs(start, killed, kills, left):
        nonlocal best
        if left == 0:
            best = max(best, kills)
            return
        gains = sorted(((masks[i] & ~killed).bit_count() for i in range(start, len(masks))), reverse=True)
        if kills + sum(gains[:left]) <= best:
            return
        for i in range(start, len(masks) - left + 1):
            if kills + (masks[i] & ~killed).bit_count() + sum(gains[:left - 1]) <= best:
                continue
            new = killed | masks[i]
            dfs(i + 1, new, new.bit_count(), left - 1)
    dfs(0, 0, 0, k)
    return best

def main():
    n, kmax = int(sys.argv[1]), int(sys.argv[2])
    no_center = "--no-center" in sys.argv
    cells, idx, lines = board(n)
    assert len(lines) == ((n + 2) ** 3 - n ** 3) // 2
    print(f"n={n}: {len(cells)} cells, {len(lines)} lines" + (", center excluded" if no_center else ""))
    masks = [0] * len(cells)
    for li, l in enumerate(lines):
        for c in l:
            masks[c] |= 1 << li
    if no_center and n % 2:
        masks[idx[(n // 2,) * 3]] = 0
    masks = sorted((m for m in masks if m), key=int.bit_count, reverse=True)
    for k in range(1, kmax + 1):
        t = time.time()
        kills = max_kills(masks, k)
        live, free = len(lines) - kills, len(cells) - 2 * k
        print(f"k={k:2d}  kills {kills:3d}  live {live:3d}  free {free:3d}  density {live / free:.3f}  ({time.time() - t:.1f} s)", flush=True)

if __name__ == "__main__":
    main()
