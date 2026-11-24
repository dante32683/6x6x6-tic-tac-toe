#!/usr/bin/env python3
"""Mutation check on real leaf records: every record in leaves20.txt must
pass the leaf checks, and each single-cell corruption below must be rejected.

    python test_mutations.py

Each record is looked up the way the tree walk does it (canonical form under
G, then mapped back), so the symmetry path is exercised too."""

import os
import sys

import numpy as np

import check_cube6 as c

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, 'leaves20.txt')


def leaf_records():
    with open(FIXTURE) as f:
        return [ln.rstrip('\n') for ln in f if ln.startswith('L')]


def check_texts(canon, texts):
    """Check each record as a Breaker-to-move position found in the tree.
    Returns None or the first failure reason."""
    path = os.path.join(HERE, '_mutation_tmp.txt')
    with open(path, 'w') as f:
        f.write('\n'.join(texts) + '\n')
    chk = c.Checker(canon, log=lambda s: None)
    try:
        chk.load(path)
        for t in texts:
            _, M, B, _, _ = c.parse_head(t)
            board = c.board_of(M, B)
            key, g = canon.one(board)
            chk.check_child(board, M[-1], key, g)
        return None
    except c.CheckFail as e:
        return e.reason
    finally:
        for _, fh in chk.files:
            fh.close()
        os.unlink(path)


def split(text):
    f = text.split(' | ')
    blocks = [] if f[4] == '-' else [b.split(' : ') for b in f[4].split(' ; ')]
    pairs = [] if f[5] == '-' else [p.split('/') for p in f[5].split(' ; ')]
    return f, blocks, pairs


def join(f, blocks, pairs):
    f = list(f)
    f[4] = ' ; '.join(f"{cells} : {claims}" for cells, claims in blocks) or '-'
    f[5] = ' ; '.join(f"{a}/{b}" for a, b in pairs) or '-'
    return ' | '.join(f)


def ints(s):
    return [] if s == '-' else [int(x) for x in s.split(',')]


def mutations(text):
    """(name, mutated text, expected failure substring)."""
    f, blocks, pairs = split(text)
    M, B, r = ints(f[1]), ints(f[2]), int(f[3])
    marks = set(M) | set(B) | {r}
    out = []

    # A pair cell moved onto a Maker cell of the same line.
    for i, (a, b) in enumerate(pairs):
        line = c.LINES[c.LINE_THROUGH[int(a), int(b)]]
        mk = [x for x in line if x in M]
        if mk:
            p = list(pairs)
            p[i] = sorted((int(a), mk[0]))
            out.append(("pair moved onto a Maker cell", join(f, blocks, p), "marked cell"))
            break
    else:
        # No pair line holds a Maker cell: move a pair cell onto any Maker cell.
        p = list(pairs)
        p[0] = sorted((int(pairs[0][0]), M[0]))
        out.append(("pair moved onto a Maker cell", join(f, blocks, p), ""))

    # A pair cell moved onto Breaker's reply.
    p = list(pairs)
    p[0] = sorted((int(pairs[0][0]), r))
    out.append(("pair moved onto Breaker's reply", join(f, blocks, p), ""))

    # A pair dropped: its line is left uncovered (or another gadget covers it).
    out.append(("pair dropped", join(f, blocks, pairs[1:]), "not covered"))

    # A block's first claimed line dropped.
    if blocks:
        cells, claims = blocks[0]
        bl = list(blocks)
        bl[0] = [cells, ','.join(claims.split(',')[1:])]
        out.append(("block claim dropped", join(f, bl, pairs), "not covered"))
        # A block cell moved onto a pair cell (overlap).
        cl = ints(cells)
        a = int(pairs[0][0])
        if a not in cl:
            cl2 = sorted(set(cl[:-1]) | {a})
            claims2 = ','.join(x for x in claims.split(',') if str(cl[-1]) not in x.split('/'))
            bl = list(blocks)
            bl[0] = [','.join(map(str, cl2)), claims2]
            out.append(("block cell moved onto a pair cell", join(f, bl, pairs), "overlap"))

    # Breaker's reply moved onto a Maker cell.
    g = list(f)
    g[3] = str(M[0])
    out.append(("reply on a Maker cell", ' | '.join(g), "occupied"))

    # A pair cell moved to an empty cell off its line.
    a, b = int(pairs[0][0]), int(pairs[0][1])
    used = {int(x) for pr in pairs for x in pr} | {x for cells, _ in blocks for x in ints(cells)}
    for x in range(c.NCELL):
        if x not in used and x not in marks and c.LINE_THROUGH[a, x] < 0:
            p = list(pairs)
            p[0] = sorted((a, x))
            out.append(("pair cell moved off its line", join(f, blocks, p), "not on a line"))
            break
    return out


def main():
    canon = c.Canon(*c.build_group())
    texts = leaf_records()
    got = check_texts(canon, texts)
    print(f"{len(texts)} real leaf records, unmodified: {'pass' if got is None else 'FAIL ' + got}")
    ok = got is None
    rejected = total = 0
    for i, t in enumerate(texts):
        for name, bad, expect in mutations(t):
            total += 1
            reason = check_texts(canon, [bad])
            good = reason is not None and expect in reason
            if good:
                rejected += 1
            else:
                ok = False
                print(f"  NOT REJECTED as expected: record {i}, {name}: {reason}")
    print(f"mutations rejected: {rejected}/{total}")
    print("MUTATIONS OK" if ok else "MUTATIONS FAILED")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
