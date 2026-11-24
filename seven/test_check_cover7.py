"""Mutation tests for check_cover7.py: each corrupted copy of cover7.txt must fail.

Run: python seven/test_check_cover7.py
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_cover7 as cc  # noqa: E402

REAL = os.path.join(HERE, "cover7.txt")


def real_lines():
    with open(REAL, encoding="utf-8") as f:
        return f.read().splitlines()


def grid3(z):
    """3x3 grid in plane z claiming 3 rows, 3 columns, and the main diagonal: Maker wins.

    (The anti-diagonal is not a full board line in 7x7x7, so it is left out.)"""
    cell = lambda x, y: f"{x},{y},{z}"
    cells = [cell(x, y) for x in range(3) for y in range(3)]
    edges = [[cell(i, j) for j in range(3)] for i in range(3)]
    edges += [[cell(j, i) for j in range(3)] for i in range(3)]
    edges += [[cell(i, i) for i in range(3)]]
    return "block " + " ".join(cells) + "".join(" | edge " + ";".join(e) for e in edges)


class CoverMutations(unittest.TestCase):
    def run_lines(self, lines):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mutant.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return cc.check(path)

    def assertFails(self, lines, text=None):
        with self.assertRaises(cc.CoverError) as ctx:
            self.run_lines(lines)
        if text:
            self.assertIn(text, str(ctx.exception))

    def first(self, prefix, lines):
        return next(i for i, l in enumerate(lines) if l.startswith(prefix))

    def test_real_file_passes(self):
        stats = self.run_lines(real_lines())
        self.assertEqual(stats["lines"], 193)

    def test_dropped_pair(self):
        lines = real_lines()
        del lines[self.first("pair ", lines)]
        self.assertFails(lines, "unclaimed")

    def test_dropped_edge(self):
        # Drop each block edge in turn. Removing an edge whose line no other gadget
        # claims must fail; only edges duplicating another edge's line may pass.
        base = real_lines()
        failed = passed = 0
        for i, line in enumerate(base):
            if not line.startswith("block "):
                continue
            parts = line.split(" | ")
            for e in range(1, len(parts)):
                lines = list(base)
                lines[i] = " | ".join(parts[:e] + parts[e + 1:])
                try:
                    self.run_lines(lines)
                    passed += 1
                except cc.CoverError:
                    failed += 1
        self.assertEqual(failed + passed, 116)
        self.assertGreaterEqual(failed, 108)  # 116 edges, 112 distinct lines: at most 8 are redundant

    def test_shared_cell(self):
        lines = real_lines()
        i, j = self.first("block ", lines), self.first("pair ", lines)
        a, b = lines[j].split()[1:]
        first_cell = lines[i].split()[1]
        lines[j] = f"pair {first_cell} {b}"
        self.assertFails(lines, "in both")

    def test_edge_not_on_one_line(self):
        lines = real_lines()
        i = self.first("block ", lines)
        parts = lines[i].split(" | ")
        parts[1] = "edge 0,0,1;1,0,1;2,1,1"  # inside the block but not collinear
        lines[i] = " | ".join(parts)
        self.assertFails(lines, "not on one board line")

    def test_edge_cell_outside_block(self):
        lines = real_lines()
        i = self.first("block ", lines)
        parts = lines[i].split(" | ")
        parts[1] = parts[1] + ";6,6,6"
        lines[i] = " | ".join(parts)
        self.assertFails(lines, "outside its block")

    def test_out_of_range_cell(self):
        lines = real_lines()
        j = self.first("pair ", lines)
        lines[j] = "pair 0,0,7 0,0,6"
        self.assertFails(lines, "out of range")

    def test_maker_win_block(self):
        # Swap the 3x3 plane block at z=2 for one that also claims the main diagonal.
        lines = real_lines()
        i = next(k for k, l in enumerate(lines) if l.startswith("block 0,0,2 "))
        lines[i] = grid3(2)
        self.assertFails(lines, "Maker win")

    def test_solver_on_small_blocks(self):
        g = grid3(0).split(" | ")
        cells = [tuple(int(v) for v in c.split(",")) for c in g[0].split()[1:]]
        edges = [[tuple(int(v) for v in c.split(",")) for c in e[len("edge "):].split(";")] for e in g[1:]]
        self.assertFalse(cc.breaker_wins_block(cells, edges))
        # Rows and columns only: Breaker pairs up and wins.
        self.assertTrue(cc.breaker_wins_block(cells, edges[:6]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
