"""Check rewritten leaf records with the independent Python checker (docs/leaf-catalogue.md).

usage: python gen/mincat_selfcheck.py <verify_py/check_cube6.py> <fit-*.tsv> [...] [--every N]

Runs verify_py's certificate check (written without this repo's code) on
each new L record from gen/mincat_rewrite.py fit, or on every Nth one. It
checks certificates only; the tree is checked by `verify full` on the joined
proof. Prints `SELFCHECK OK` and the count, or the first failure.
"""
import importlib.util, sys
import numpy as np


def main():
    args = sys.argv[1:]
    every = 1
    if "--every" in args:
        i = args.index("--every"); every = int(args[i + 1]); del args[i:i + 2]
    spec = importlib.util.spec_from_file_location("check_cube6", args[0])
    V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
    chk = V.Checker(canon=None, log=lambda s: None)
    ident = np.arange(V.NCELL)
    n = 0
    for path in args[1:]:
        for j, row in enumerate(open(path)):
            if j % every:
                continue
            i, layout, rec = row.rstrip("\n").split("\t", 2)
            kind, M, B, r, fields = V.parse_head(rec)
            board = V.board_of(M, list(B) + [r])
            try:
                chk.check_certificate(board, ident, *V.parse_cert(fields))
            except V.CheckFail as e:
                raise SystemExit(f"FAIL leaf {i} (layout {layout}) in {path}: {e}")
            n += 1
    print(f"SELFCHECK OK: {n} records")


if __name__ == "__main__":
    main()
