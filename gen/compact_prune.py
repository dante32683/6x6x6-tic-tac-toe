"""Copy the records a proof's strategy reaches into a pruned proof file.

usage: python gen/compact_prune.py <proof.txt> <used-lines.txt> <pruned.txt>

<used-lines.txt> comes from `verify full <proof.txt> --emit-used <used-lines.txt>`:
the 1-based line numbers of the records the walk reaches, one record per
position. The output is the proof's comment lines (its header) plus those
lines, byte for byte and in file order, so it is a v1 proof
(docs/proof-format.md) that every checker reads unchanged. Streams the proof.
"""
import sys


def main():
    proof, used_path, out_path = sys.argv[1:4]
    with open(used_path, encoding="ascii") as f:
        wanted = sorted(int(x) for x in f)
    if len(set(wanted)) != len(wanted) or (wanted and wanted[0] < 1):
        sys.exit(f"{used_path}: line numbers must be distinct and positive")
    kept = {"#": 0, "R": 0, "L": 0}
    k = 0
    with open(proof, "rb") as src, open(out_path, "wb") as dst:
        for n, line in enumerate(src, 1):
            take = line.startswith(b"#")
            if k < len(wanted) and wanted[k] == n:
                if take:
                    sys.exit(f"line {n} is a comment, not a record")
                take, k = True, k + 1
            if take:
                dst.write(line)
                kept[chr(line[0])] += 1
    if k != len(wanted):
        sys.exit(f"{proof} ends before line {wanted[k]}")
    print(f"{out_path}: {kept['#']} comment lines, {kept['R']} R records, {kept['L']} L records")


if __name__ == "__main__":
    main()
