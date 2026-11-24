"""Faster exact Maker-Breaker solver for blocks (Maker moves first).

solve(edges) takes edges as lists or bitmasks of local cell ids and returns
True when Breaker wins (keeps Maker off every edge). Same game as gen/mb.py,
with three reductions that keep 16 to 20 cell blocks fast in Python:
- a position is only the set of what is left of each live edge (cells not
  yet claimed); edges Breaker touched are gone, and an edge whose remainder
  contains another's is dropped (Maker filling it fills the smaller one);
- Erdos-Selfridge cut-off: Breaker wins when the potential sum 2^-|rest| is
  below 1/2 with Maker to move, or below 1 with Breaker to move;
- moves are tried in order of potential weight, best first.
Cross-checked against mb.py in check_against_mb().
"""


def _reduce(rests):
    """Drop remainders that contain another remainder; return a sorted tuple."""
    rs = sorted(set(rests), key=lambda r: bin(r).count("1"))
    keep = []
    for r in rs:
        if not any(k & r == k for k in keep):
            keep.append(r)
    return tuple(sorted(keep))


def _weights(state):
    w = {}
    for r in state:
        p = 2.0 ** -bin(r).count("1")
        x = r
        while x:
            c = x & -x
            x ^= c
            w[c] = w.get(c, 0.0) + p
    return sorted(w, key=lambda c: -w[c])


def solve(edges, node_limit=None):
    """True if Breaker wins. With node_limit, returns None when exceeded."""
    masks = [e if isinstance(e, int) else sum(1 << c for c in e) for e in edges]
    maker_memo, breaker_memo = {}, {}
    budget = [node_limit if node_limit else float("inf")]

    class Out(Exception):
        pass

    def maker_wins(state):
        # Maker to move
        if not state:
            return False
        if any(r & (r - 1) == 0 for r in state):
            return True  # an edge with one cell left
        if sum(2.0 ** -bin(r).count("1") for r in state) < 0.5:
            return False
        if state in maker_memo:
            return maker_memo[state]
        budget[0] -= 1
        if budget[0] < 0:
            raise Out
        res = False
        for c in _weights(state):
            nxt = _reduce(r & ~c for r in state)
            if not breaker_holds(nxt):
                res = True
                break
        maker_memo[state] = res
        return res

    def breaker_holds(state):
        # Breaker to move; True if Breaker wins
        if not state:
            return True
        threats = {r for r in state if r & (r - 1) == 0}
        if len(threats) >= 2:
            return False
        if sum(2.0 ** -bin(r).count("1") for r in state) < 1.0:
            return True
        if state in breaker_memo:
            return breaker_memo[state]
        budget[0] -= 1
        if budget[0] < 0:
            raise Out
        cand = list(threats) if threats else _weights(state)
        res = False
        for c in cand:
            nxt = tuple(r for r in state if not r & c)
            if not maker_wins(nxt):
                res = True
                break
        breaker_memo[state] = res
        return res

    try:
        return not maker_wins(_reduce(masks))
    except Out:
        return None


def check_against_mb(trials=300, seed=0):
    """Random small hypergraphs: mbfast and mb must agree."""
    import random
    from mb import solve as slow
    rng = random.Random(seed)
    for _ in range(trials):
        k = rng.randint(4, 10)
        E = [rng.sample(range(k), rng.randint(2, min(4, k))) for _ in range(rng.randint(1, 8))]
        assert solve(E) == slow(k, E), (k, E)
    return True


if __name__ == "__main__":
    def grid(k, diag=True):
        L = [[r*k+c for c in range(k)] for r in range(k)] + [[r*k+c for r in range(k)] for c in range(k)]
        if diag:
            L += [[i*k+i for i in range(k)], [i*k+(k-1-i) for i in range(k)]]
        return L
    print("3x3 Breaker wins:", solve(grid(3)), "(expect False)")
    print("3x3 rows+cols:", solve(grid(3, False)), "(expect True)")
    print("4x4 Breaker wins:", solve(grid(4)), "(expect True)")
    print("agrees with mb.py:", check_against_mb())
