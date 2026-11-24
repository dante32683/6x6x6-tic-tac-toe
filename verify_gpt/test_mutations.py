#!/usr/bin/env python3
"""Mutation test on real leaf records, added by Claude (not part of ChatGPT's
checker). Every sampled L record must pass the leaf checks that
`Checker.read` applies to each record it reads, and each corruption below
marked "must fail" must be rejected. "Probable" mutants (a dropped pair,
block, or claim) usually leave a live line uncovered but can be legitimately
valid, so they are counted, not required.

    python test_mutations.py [proof] [records=40] [seed=1]

`proof` defaults to ../verify_py/leaves20.txt (20 real records from
class0.txt). A large proof file is read once, sampling L records uniformly."""

import io
import os
import random
import sys

import check_cube6 as c

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROOF = os.path.join(HERE, '..', 'verify_py', 'leaves20.txt')


def sample_leaves(path, n, rng):
    """Reservoir sample of n L records, so the file is read once."""
    picked = []
    with open(path) as f:
        for k, line in enumerate(ln for ln in f if ln.startswith('L |')):
            if len(picked) < n:
                picked.append(line.strip())
            else:
                j = rng.randrange(k + 1)
                if j < n:
                    picked[j] = line.strip()
    return picked


def ints(s):
    return [] if s == '-' else [int(x) for x in s.split(',')]


def split(rec):
    _, m, b, r, blocks, pairs = [f.strip() for f in rec.split('|')]
    blocks = [] if blocks == '-' else [e.split(' : ') for e in blocks.split(' ; ')]
    pairs = [] if pairs == '-' else [tuple(map(int, p.split('/'))) for p in pairs.split(' ; ')]
    return ints(m), ints(b), int(r), blocks, pairs


def join(m, b, r, blocks, pairs):
    fm = ','.join(map(str, m)) or '-'
    fb = ','.join(map(str, b)) or '-'
    fbl = ' ; '.join(f'{cells} : {claims}' for cells, claims in blocks) or '-'
    fp = ' ; '.join(f'{min(p)}/{max(p)}' for p in pairs) or '-'
    return f'L | {fm} | {fb} | {r} | {fbl} | {fp}'


def line_cells(g, a, b):
    return g.lines[g.pair_line[a][b]]


def mutants(g, rec):
    """(name, must_fail, mutated record); a mutant is skipped when the
    record lacks the parts it needs."""
    m, b, r, blocks, pairs = split(rec)
    out = [('reply on a Maker cell', True, join(m, b, m[0], blocks, pairs))]
    if b:
        out.append(('reply on a Breaker cell', True, join(m, b, b[0], blocks, pairs)))
    block_cells = {x for cells, _ in blocks for x in ints(cells)}
    pair_cells = {x for p in pairs for x in p}
    marks = set(m) | set(b) | {r}
    if len(pairs) >= 2:
        a0 = pairs[0][0]
        out.append(('two pairs share a cell', True,
                    join(m, b, r, blocks, [pairs[0], (pairs[1][0], a0), *pairs[2:]])))
    if pairs:
        a, x = pairs[0]
        out.append(("pair on Breaker's reply cell", True,
                    join(m, b, r, blocks, [(r, x), *pairs[1:]])))
        on_line = [y for y in line_cells(g, a, x) if y in m]
        target = on_line[0] if on_line else m[0]
        if target != a:
            out.append(('pair cell on a Maker cell', True,
                        join(m, b, r, blocks, [(a, target), *pairs[1:]])))
        off = next((y for y in range(c.NC)
                    if y not in marks | block_cells | pair_cells and g.pair_line[a][y] < 0), None)
        if off is not None:
            out.append(('pair cell moved off its line', True,
                        join(m, b, r, blocks, [(a, off), *pairs[1:]])))
        if block_cells:
            out.append(('pair cell inside a block', True,
                        join(m, b, r, blocks, [(a, min(block_cells - {a})), *pairs[1:]])))
        out.append(('one pair removed', False, join(m, b, r, blocks, pairs[1:])))
        out.append(('all pairs removed', False, join(m, b, r, blocks, [])))
    if len(blocks) >= 2:
        c0, e0 = blocks[0]
        extra = ints(blocks[1][0])[0]
        cells = ','.join(map(str, sorted(ints(c0) + [extra])))
        out.append(('two blocks share a cell', True, join(m, b, r, [[cells, e0], *blocks[1:]], pairs)))
    if blocks:
        c0, e0 = blocks[0]
        inside = set(ints(c0))
        w0 = e0.split(',')[0]
        a, x = map(int, w0.split('/'))
        outside = next((y for y in line_cells(g, a, x) if y not in inside), None)
        if outside is not None:
            claims = ','.join([f'{min(a, outside)}/{max(a, outside)}', *e0.split(',')[1:]])
            out.append(('block claim witness outside the block', True,
                        join(m, b, r, [[c0, claims], *blocks[1:]], pairs)))
        if ',' in e0:
            out.append(('block claim dropped', False,
                        join(m, b, r, [[c0, ','.join(e0.split(',')[1:])], *blocks[1:]], pairs)))
        out.append(('one block removed', False, join(m, b, r, blocks[1:], pairs)))
    return out


def accepted(g, records):
    ck = c.Checker(g)
    try:
        ck.read(io.BytesIO(('\n'.join(records) + '\n').encode('ascii')))
        return True
    except c.Failure:
        return False


def main(argv):
    proof = argv[1] if len(argv) > 1 else DEFAULT_PROOF
    n = int(argv[2]) if len(argv) > 2 else 40
    rng = random.Random(int(argv[3]) if len(argv) > 3 else 1)
    g = c.Geometry()
    picked = sample_leaves(proof, n, rng)
    ok = bool(picked) and accepted(g, picked)
    print(f'{len(picked)} original records: {"accepted" if ok else "REJECTED"}')
    tally = {}
    for rec in picked:
        for name, must_fail, mut in mutants(g, rec):
            t = tally.setdefault(name, [must_fail, 0, 0])
            t[1] += 1
            t[2] += not accepted(g, [mut])
    for name, (must_fail, tried, rejected) in tally.items():
        flag = '' if not must_fail or rejected == tried else '   <-- ACCEPTED A BROKEN RECORD'
        print(f"{'must fail' if must_fail else 'probable '}  {name}: {rejected}/{tried} rejected{flag}")
    bad = not ok or any(mf and rej != tried for mf, tried, rej in tally.values())
    print('MUTATION TEST ' + ('FAILED' if bad else 'OK'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
