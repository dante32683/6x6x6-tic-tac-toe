"""Write one gen.py template as an explicit static cover: blocks, their claimed lines, and pairs.

usage: python gen/cover_export.py <data<n>.json> <template index> <out.txt>
A template is a set of blocks (gen.py); on its own it needs free Breaker
marks or pairs for the lines no block claims. This finds pairs for all of
them by matching (each unclaimed line gets two cells outside every block,
no cell used twice) and fails if they don't fit, so the output is a cover
with no free marks. Format (one gadget per line, cells as coordinates):
  block x,y,z x,y,z ... | edge x,y,z;x,y,z;... | edge ...
  pair x,y,z x,y,z
Each block edge is the claimed line's cells inside the block. Checked by
`seven cover <out.txt>`, which shares no code with this script.
"""
import json, sys

def main():
    data = json.load(open(sys.argv[1]))
    n, lines, blocks = data["n"], data["lines"], data["blocks"]
    tpl = data["templates"][int(sys.argv[2])]
    coord = lambda c: f"{c // (n * n)},{(c // n) % n},{c % n}"
    used, claimed, out = set(), set(), []
    for bi in tpl:
        b = blocks[bi]
        cells = set(b["cells"])
        assert not cells & used, "blocks overlap"
        used |= cells
        edges = []
        for li in b["lines"]:
            claimed.add(li)
            edges.append(";".join(coord(c) for c in lines[li] if c in cells))
        out.append("block " + " ".join(coord(c) for c in sorted(cells)) + "".join(f" | edge {e}" for e in edges))
    # Pairs for every line no block claims, by augmenting paths over two slots per line.
    todo = [li for li in range(len(lines)) if li not in claimed]
    free = {li: [c for c in lines[li] if c not in used] for li in todo}
    slot_cell, cell_slot = {}, {}
    def augment(s, seen):
        for c in free[s[0]]:
            if c in seen:
                continue
            seen.add(c)
            if c not in cell_slot or augment(cell_slot[c], seen):
                cell_slot[c], slot_cell[s] = s, c
                return True
        return False
    for li in todo:
        for k in (0, 1):
            if not augment((li, k), set()):
                sys.exit(f"no pairing for the unclaimed lines (line {li})")
    for li in todo:
        out.append(f"pair {coord(slot_cell[(li, 0)])} {coord(slot_cell[(li, 1)])}")
    open(sys.argv[3], "w").write(f"# static Breaker cover, n = {n}, template {sys.argv[2]}: "
                                 f"{len(tpl)} blocks, {len(todo)} pairs\n" + "\n".join(out) + "\n")
    print(f"{len(tpl)} blocks claim {len(claimed)} lines; {len(todo)} pairs; "
          f"{n**3 - len(used) - 2 * len(todo)} cells unused")

if __name__ == "__main__":
    main()
