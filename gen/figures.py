"""Renders the figures of the paper draft (paper/draft.md).

usage (from the repo root): python gen/figures.py

Writes paper/figures/<name>.svg and .png (200 dpi), one pair per
figure in FIGURES below. Which sketch of the draft each figure replaces, and
its caption, are in paper/figures/README.md. Every figure uses the
numbers its section of the draft uses; the checks in each function (assert)
fail if the geometry in gen/cube6.py and the draft's example disagree.

Board convention (draft section 2): the cube is drawn as six 6x6 slices, x = 0
to 2 in the top row and x = 3 to 5 in the bottom row; inside a slice y runs
down and z runs across. A cell is (x, y, z), id = 36x + 6y + z (gen/cube6.py).
"""
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cube6 as C  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "paper", "figures")
DPI = 200
N = 6
GAP = 1.2                       # space between slices, in cell widths
PITCH = N + GAP
COLS = 3                        # slices per row: x = 0, 1, 2 above and 3, 4, 5 below
ROWS = N // COLS
ROW_PITCH = N + 1.5             # row to row; the gap holds the "x = ..." labels
BOARD_W = COLS * PITCH - GAP    # width of one row of slices, in cells
BOARD_H = ROWS * ROW_PITCH - (ROW_PITCH - N)   # height of the slice grid, in cells
# Six-slice figures are about 6.2 in wide, the PDF's text width, so 8 pt labels
# print at 8 pt.
SLICE_CELL_IN = 0.28

# Palette. Marks are fixed by the project's style; block hues avoid red and blue.
MAKER = (255 / 255, 40 / 255, 40 / 255)
BREAKER = (40 / 255, 110 / 255, 255 / 255)
INK = "#222222"
GRID = "#c4c4c4"
FAINT = "#9a9a9a"
PAIR_FILL = "#e4e4e4"
HUES = ["#e9d68f", "#a9d3a0", "#cdb4e0", "#f2c9a0", "#a8d2cb", "#d5d99a",
        "#d8c0a8"]  # ochre, green, lavender, peach, sage-teal, olive, tan
LINE_HUES = {"axis": "#c98a1b", "face-diag": "#2f9e6b", "space-diag": "#8a4fb3"}

plt.rcParams.update({"font.family": "sans-serif",
                     "font.sans-serif": ["DejaVu Sans", "Arial"],
                     "svg.fonttype": "path", "axes.linewidth": 0,
                     # fixed salt for SVG clip-path ids, so reruns give identical files
                     "svg.hashsalt": "cube6-figures"})


# --- low-level drawing -------------------------------------------------------

def new_axes(width_cells, height_cells, cell_in=0.24):
    """An axes where one unit is one cell and y points down."""
    fig = plt.figure(figsize=(width_cells * cell_in, height_cells * cell_in))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, width_cells)
    ax.set_ylim(height_cells, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def origin(layer, top=0.0, left=0.0, cols=COLS):
    """Top-left corner of slice number `layer` (x = layer), `cols` slices per row."""
    row, col = divmod(layer, cols)
    return left + col * PITCH, top + row * ROW_PITCH


def pos(c, top=0.0, left=0.0, cols=COLS):
    """Center of cell id c in the six-slice picture."""
    x, y, z = C.xyz(c)
    ox, oy = origin(x, top, left, cols)
    return ox + z + 0.5, oy + y + 0.5


def draw_slices(ax, top=0.0, left=0.0, layers=range(N), labels=True, cols=COLS):
    for x in layers:
        ox, oy = origin(x, top, left, cols)
        for i in range(N + 1):
            ax.plot([ox, ox + N], [oy + i, oy + i], color=GRID, lw=0.5, zorder=1)
            ax.plot([ox + i, ox + i], [oy, oy + N], color=GRID, lw=0.5, zorder=1)
        ax.add_patch(Rectangle((ox, oy), N, N, fill=False, ec=INK, lw=0.9, zorder=4))
        if labels:
            ax.text(ox + N / 2, oy - 0.45, f"x = {x}", ha="center", va="bottom",
                    fontsize=8, color=INK)


def axis_hint(ax, top=0.0, left=0.0):
    """Small y and z arrows left of slice 0 and above its label."""
    ax.annotate("", xy=(left - 0.5, top + 2.2), xytext=(left - 0.5, top + 0.2),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.7))
    ax.text(left - 0.5, top + 2.7, "y", ha="center", va="top", fontsize=8, color=INK)
    ax.annotate("", xy=(left + 1.8, top - 0.45), xytext=(left + 0.1, top - 0.45),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.7))
    ax.text(left - 0.3, top - 0.45, "z", ha="center", va="center", fontsize=8, color=INK)


def fill_cell(ax, c, color, top=0.0, left=0.0, z=2, cols=COLS):
    cx, cy = pos(c, top, left, cols)
    ax.add_patch(Rectangle((cx - 0.5, cy - 0.5), 1, 1, fc=color, ec="none", zorder=z))


def outline_group(ax, cells, top=0.0, left=0.0, lw=0.9):
    """Dark outline around each connected run of `cells` within a slice."""
    cs = set(cells)
    for c in cs:
        x, y, z = C.xyz(c)
        cx, cy = pos(c, top, left)
        for dy, dz, seg in ((-1, 0, ((-.5, -.5), (.5, -.5))), (1, 0, ((-.5, .5), (.5, .5))),
                            (0, -1, ((-.5, -.5), (-.5, .5))), (0, 1, ((.5, -.5), (.5, .5)))):
            ny, nz = y + dy, z + dz
            if 0 <= ny < N and 0 <= nz < N and C.cid(x, ny, nz) in cs:
                continue
            (a, b), (d, e) = seg
            ax.plot([cx + a, cx + d], [cy + b, cy + e], color=INK, lw=lw,
                    solid_capstyle="butt", zorder=3)


def mark(ax, c, who, text=None, top=0.0, left=0.0, ring=False):
    """Maker (red) or Breaker (blue) disc; `ring` draws it hollow."""
    col = MAKER if who == "M" else BREAKER
    cx, cy = pos(c, top, left)
    if ring:
        ax.add_patch(Circle((cx, cy), 0.38, fc="white", ec=col, lw=1.3, zorder=6))
        if text:
            ax.text(cx, cy + 0.02, text, ha="center", va="center", fontsize=6.5,
                    color=INK, zorder=7)
    else:
        ax.add_patch(Circle((cx, cy), 0.38, fc=col, ec="none", zorder=6))
        if text:
            ax.text(cx, cy + 0.02, text, ha="center", va="center", fontsize=7,
                    color="white", fontweight="bold", zorder=7)


def dot(ax, c, color=FAINT, r=0.11, top=0.0, left=0.0):
    cx, cy = pos(c, top, left)
    ax.add_patch(Circle((cx, cy), r, fc=color, ec="none", zorder=5))


def stroke(ax, a, b, color=INK, lw=1.4, top=0.0, left=0.0, z=5):
    (x1, y1), (x2, y2) = pos(a, top, left), pos(b, top, left)
    ax.plot([x1, x2], [y1, y2], color=color, lw=lw, solid_capstyle="round", zorder=z)


def line_cells(p, d):
    return [C.cid(*(p[i] + k * d[i] for i in range(3))) for k in range(N)]


def space_diag_cells():
    return sorted({c for cells, k in C.LINES if k == 3 for c in cells})


def save(fig, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(OUT_DIR, name)
    # No date or software stamps in the files, so reruns give identical output.
    fig.savefig(base + ".svg", bbox_inches="tight", pad_inches=0.06, facecolor="white",
                metadata={"Date": None})
    fig.savefig(base + ".png", dpi=DPI, bbox_inches="tight", pad_inches=0.06,
                facecolor="white", metadata={"Software": None})
    plt.close(fig)
    print("wrote", name)


def six_slice_axes(extra_below=1.6, extra_above=1.3):
    """Axes sized for the six-slice picture; returns fig, ax, top offset."""
    w = BOARD_W + 1.6   # the extra 0.1 keeps the last slice border unclipped
    fig, ax = new_axes(w, BOARD_H + extra_above + extra_below, SLICE_CELL_IN)
    ax.set_xlim(-1.5, w - 1.5)
    return fig, ax, extra_above


# --- figures -----------------------------------------------------------------

def fig_board_lines():
    """Section 1: the board as six slices with one line of each kind."""
    fig, ax, top = six_slice_axes()
    draw_slices(ax, top)
    axis_hint(ax, top)
    examples = {
        "axis": line_cells((1, 2, 0), (0, 0, 1)),         # a row of slice 1, z varies
        "face-diag": line_cells((3, 0, 5), (0, 1, -1)),   # uphill diagonal of slice 3
        "space-diag": line_cells((0, 0, 0), (1, 1, 1)),   # corner to corner
    }
    for kind, cells in examples.items():
        assert sorted(cells) in [sorted(l) for l, _ in C.LINES]
        assert [C.LTYPE[k] for l, k in C.LINES if sorted(l) == sorted(cells)] == [kind]
    # Draw longest first so the short ones stay visible; the space diagonal
    # has one cell per slice, so it is drawn as dots joined slice to slice.
    for kind, cells in examples.items():
        col = LINE_HUES[kind]
        for a, b in zip(cells, cells[1:]):
            if C.xyz(a)[0] == C.xyz(b)[0]:
                stroke(ax, a, b, col, lw=2.2, top=top)
        for c in cells:
            cx, cy = pos(c, top)
            ax.add_patch(Circle((cx, cy), 0.3, fc=col, ec="none", zorder=6))
    handles = [plt.Line2D([], [], color=LINE_HUES[k], lw=2.2, marker="o", ms=5, label=l)
               for k, l in (("axis", "axis line"), ("face-diag", "plane diagonal"),
                            ("space-diag", "space diagonal"))]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 0.0))
    save(fig, "board-six-layers")


def fig_three_kinds_of_cell():
    """Section 2: cells by how many lines pass through them (7, 4, or 3), with the
    24 cells on 7 lines (the space diagonals' cells) lettered by layer."""
    fig, ax, top = six_slice_axes(extra_below=2.3)
    draw_slices(ax, top)
    fills = {7: "#c9a9e0", 4: "#ffffff", 3: "#a9d3a0"}
    letters = {"corner": "o", "mid": "m", "core": "c"}
    counts, layers = {}, {}
    for c in range(C.CELLS):
        d = int(C.DEG[c])
        counts[d] = counts.get(d, 0) + 1
        fill_cell(ax, c, fills[d], top)
    for c in space_diag_cells():
        assert int(C.DEG[c]) == 7
        kind = C.diag_layer(c)
        layers[kind] = layers.get(kind, 0) + 1
        cx, cy = pos(c, top)
        ax.text(cx, cy + 0.03, letters[kind], ha="center", va="center", fontsize=7,
                color=INK, zorder=7)
    assert counts == {7: 24, 4: 144, 3: 48}, counts   # draft section 2
    assert layers == {"corner": 8, "mid": 8, "core": 8}, layers
    handles = [Rectangle((0, 0), 1, 1, fc=fills[d], ec=INK, lw=0.6,
                         label=f"on {d} lines ({counts[d]} cells)") for d in (7, 4, 3)]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 0.045))
    fig.text(0.5, 0.012, "on the space diagonals:  o corner (coordinates 0 or 5),  "
             "m mid (1 or 4),  c core (2 or 3)", ha="center", va="bottom", fontsize=8, color=INK)
    save(fig, "three-kinds-of-cell")


# Draft section 4 sketch (lines 144-148): the Golomb-Hales pairing on 5x5.
PAIRING_5X5 = ["viaaf", "jbhub", "ci#gc", "duhdf", "jeegv"]


def fig_pairing_5x5():
    """Section 4: each letter marks the two cells of one line."""
    rows = PAIRING_5X5
    assert all(len(r) == 5 for r in rows) and len(rows) == 5
    cells = {}
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            cells.setdefault(ch, []).append((y, x))
    for ch, cs in cells.items():            # each letter: two cells on one line
        if ch == "#":
            assert cs == [(2, 2)]
            continue
        assert len(cs) == 2, ch
        (y1, x1), (y2, x2) = cs
        if ch in "abcde":
            assert y1 == y2 == "abcde".index(ch), ch              # row
        elif ch in "fghij":
            assert x1 == x2, ch                                   # one column
        elif ch == "v":
            assert y1 == x1 and y2 == x2                          # main diagonal
        else:
            assert ch == "u" and y1 + x1 == 4 and y2 + x2 == 4    # anti-diagonal
    assert set(cells) == set("abcdefghijuv#")
    assert sorted(cells[ch][0][1] for ch in "fghij") == list(range(5))   # every column
    fig, ax = new_axes(5.2, 5.95, cell_in=0.42)
    kind_fill = {"row": HUES[0], "col": HUES[1], "diag": HUES[2]}
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == "#":
                ax.add_patch(Rectangle((x + .1, y + .1), 1, 1, fc="#808080", ec="none"))
                continue
            kind = "row" if ch in "abcde" else "col" if ch in "fghij" else "diag"
            ax.add_patch(Rectangle((x + .1, y + .1), 1, 1, fc=kind_fill[kind], ec=GRID, lw=.5))
            ax.text(x + .6, y + .62, ch, ha="center", va="center", fontsize=12, color=INK)
    ax.add_patch(Rectangle((.1, .1), 5, 5, fill=False, ec=INK, lw=1.2))
    handles = [Rectangle((0, 0), 1, 1, fc=kind_fill[k], ec=GRID, lw=.5, label=l)
               for k, l in (("row", "row (a to e)"), ("col", "column (f to j)"),
                            ("diag", "diagonal (u, v)"))]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 0.0))
    save(fig, "pairing-5x5")


def fig_slab_placements():
    """Section 5: the two commonest 3x4 placements (draft lines 207-213)."""
    panels = [
        ("claims 9 lines", range(1, 5), range(1, 4)),   # rows y=1..4, columns z=1..3
        ("claims 8 lines", range(0, 3), range(0, 4)),   # rows y=0..2, columns z=0..3
    ]
    fig, ax = new_axes(2 * N + 2, N + 1.4, cell_in=0.36)
    ax.set_xlim(-0.4, 2 * N + 1.6)
    claimed = []
    for p, (label, ys, zs) in enumerate(panels):
        ox, oy = p * (N + 1.2), 0.2
        block = {(y, z) for y in ys for z in zs}
        for i in range(N + 1):
            ax.plot([ox, ox + N], [oy + i, oy + i], color=GRID, lw=.5, zorder=1)
            ax.plot([ox + i, ox + i], [oy, oy + N], color=GRID, lw=.5, zorder=1)
        for y, z in block:
            ax.add_patch(Rectangle((ox + z, oy + y), 1, 1, fc=HUES[0], ec="none", zorder=2))
        # outline of the block
        for y, z in block:
            for dy, dz, (a, b, c, d) in ((-1, 0, (0, 0, 1, 0)), (1, 0, (0, 1, 1, 1)),
                                         (0, -1, (0, 0, 0, 1)), (0, 1, (1, 0, 1, 1))):
                if (y + dy, z + dz) not in block:
                    ax.plot([ox + z + a, ox + z + c], [oy + y + b, oy + y + d],
                            color=INK, lw=1.1, zorder=4, solid_capstyle="butt")
        ax.add_patch(Rectangle((ox, oy), N, N, fill=False, ec=INK, lw=.9, zorder=4))
        # Claimed lines: the block's rows and columns, plus each slice diagonal
        # that meets the block in three cells.
        nrows, ncols = len(ys), len(zs)
        diags = 0
        for name, hit in (("main", [(y, z) for y, z in block if y == z]),
                          ("anti", [(y, z) for y, z in block if y + z == N - 1])):
            if len(hit) == 3:
                diags += 1
                if name == "main":
                    ax.plot([ox, ox + N], [oy, oy + N], color=INK, lw=.9, ls=(0, (4, 2)), zorder=5)
                else:
                    ax.plot([ox, ox + N], [oy + N, oy], color=INK, lw=.9, ls=(0, (4, 2)), zorder=5)
        claimed.append(nrows + ncols + diags)
        ax.text(ox + N / 2, oy + N + 0.35, label, ha="center", va="top", fontsize=9, color=INK)
    assert claimed == [9, 8], claimed      # the draft's two captions
    save(fig, "slab-placements")


def fig_relabeling():
    """Section 7: relabeling 1<->2, 3<->4 acts on two lines of the draft."""
    t = [0, 2, 1, 4, 3, 5]
    assert all(t[5 - v] == 5 - t[v] for v in range(N))      # keeps the pairs together
    assert t[1] == 2 and t[2] == 1                          # (0,1,2) -> (0,2,1)
    # The two states side by side, each as three rows of two slices, so the figure
    # is as wide as the text (6.2 in) and its labels print at their own size.
    cols = 2
    state_w = cols * PITCH - GAP
    state_h = (N // cols) * ROW_PITCH - (ROW_PITCH - N)
    state_gap = 2.5
    top = 2.4                               # room for the state title and the x labels
    w = 2 * state_w + state_gap + 0.1       # the extra 0.1 keeps the last border unclipped
    fig, ax = new_axes(w, top + state_h + 0.3, cell_in=6.2 / w)
    lines = {
        "space": [C.cid(k, k, k) for k in range(N)],           # (0,0,0) ... (5,5,5)
        "uphill": [C.cid(0, k, 5 - k) for k in range(N)],      # slice x = 0, y + z = 5
    }
    image = {name: [C.cid(*(t[v] for v in C.xyz(c))) for c in cells]
             for name, cells in lines.items()}
    # the draft's example: the diagonal lands on the same six cells, reordered
    assert sorted(image["space"]) == sorted(lines["space"])
    assert sorted(image["uphill"]) == sorted(lines["uphill"])
    assert [C.xyz(c) for c in image["space"]] == [(0, 0, 0), (2, 2, 2), (1, 1, 1),
                                                   (4, 4, 4), (3, 3, 3), (5, 5, 5)]
    assert C.xyz(image["uphill"][1]) == (0, 2, 3) and C.xyz(image["uphill"][2]) == (0, 1, 4)
    hue = {"space": LINE_HUES["space-diag"], "uphill": LINE_HUES["face-diag"]}
    for k, (src, label) in enumerate(((lines, "before"), (image, "after"))):
        left = k * (state_w + state_gap)
        draw_slices(ax, top, left, cols=cols)
        ax.text(left + state_w / 2, 0.55, label, ha="center", va="center", fontsize=9,
                fontweight="bold", color=INK)
        for name, cells in src.items():
            for step, c in enumerate(cells):
                fill_cell(ax, c, hue[name] + "55", top, left, cols=cols)
                cx, cy = pos(c, top, left, cols)
                ax.add_patch(Circle((cx, cy), .36, fc="white", ec=hue[name], lw=1.4, zorder=5))
                ax.text(cx, cy + .02, str(step), ha="center", va="center", fontsize=7,
                        color=INK, zorder=7)
    save(fig, "relabeling-layers")


# The leaf of the draft's section 8 ("One line of play"), copied from the
# L record at line 4 of class0.txt (docs/checking.md; format: docs/proof-format.md).
LEAF_RECORD = (
    "L | 0,88,134,164 | 128,129,154 | 151 | 7,8,9,10,13,14,15,16,19,20,21,22 : 7/8,13/14,"
    "19/20,10/15,7/13,8/14,9/15,10/16,7/14 ; "
    "37,38,39,73,74,75,109,110,111,145,146,147 : 37/38,73/74,109/110,145/146,75/110,"
    "37/73,38/74,39/75,37/74 ; "
    "44,45,46,80,81,82,116,117,118 : 44/45,80/81,116/117,44/80,45/81,46/82 ; "
    "47,53,59,83,89,95,119,125,131,155,161,167 : 47/53,83/89,119/125,155/161,95/125,"
    "47/83,53/89,59/95,47/89 ; "
    "55,61,67,91,97,103,127,133,139 : 55/61,91/97,127/133,55/91,61/97,67/103 ; "
    "56,57,58,62,63,64,68,69,70 : 56/57,62/63,68/69,56/62,57/63,58/64 ; "
    "72,78,84,108,114,120,144,150,156,180,186,192 : 72/78,108/114,144/150,180/186,"
    "120/150,72/108,78/114,84/120 ; "
    "85,86,87,121,122,123,157,158,159 : 85/86,121/122,157/158,85/121,86/122,87/123 ; "
    "92,93,94,98,99,100,104,105,106 : 92/93,98/99,104/105,92/98,93/99,94/100 ; "
    "140,141,142,143,176,177,178,179,212,213,214,215 : 140/141,176/177,212/213,140/176,"
    "141/177,142/178,143/179,141/178 ; "
    "187,188,189,190,193,194,195,196,199,200,201,202 : 187/188,193/194,199/200,190/195,"
    "187/193,188/194,189/195,190/196,187/194 | 2/3 ; "
    "24/25 ; "
    "30/31 ; "
    "49/50 ; "
    "132/137 ; "
    "162/163 ; "
    "168/173 ; "
    "181/184 ; "
    "205/207 ; "
    "41/51 ; "
    "77/102 ; "
    "6/18 ; "
    "11/23 ; "
    "36/48 ; "
    "112/136 ; "
    "152/170 ; "
    "153/165 ; "
    "185/191 ; "
    "43/71 ; "
    "79/107 ; "
    "32/182 ; "
    "33/183 ; "
    "17/52 ; "
    "29/204 ; "
    "35/175 ; "
    "40/76 ; "
    "5/113 ; "
    "124/160 ; "
    "54/90 ; "
    "130/166 ; "
    "60/96 ; "
    "26/206 ; "
    "27/171 ; "
    "28/208 ; "
    "65/101 ; "
    "66/138 ; "
    "12/197 ; "
    "135/209 ; "
    "42/126 ; "
    "1/169 ; "
    "4/172"
)


def fig_line_of_play():
    """Section 8: the four rounds of the line of play, as numbered marks."""
    maker = [0, C.cid(2, 2, 4), C.cid(3, 4, 2), C.cid(4, 3, 2)]
    breaker = [C.cid(3, 3, 3), C.cid(4, 1, 4), C.cid(3, 3, 2), C.cid(4, 1, 1)]
    assert maker == [0, 88, 134, 164] and breaker == [129, 154, 128, 151]  # leaf record
    diag = space_diag_cells()
    # each Breaker mark is on a different space diagonal
    diag_of = {}
    for i, (cells, k) in enumerate(C.LINES):
        if k == 3:
            for c in cells:
                diag_of[c] = i
    assert len({diag_of[c] for c in breaker}) == 4
    fig, ax, top = six_slice_axes()
    draw_slices(ax, top)
    for c in diag:
        dot(ax, c, top=top)
    for i, (m, b) in enumerate(zip(maker, breaker), 1):
        mark(ax, m, "M", str(i), top)
        mark(ax, b, "B", str(i), top)
    handles = [plt.Line2D([], [], marker="o", ls="", color=MAKER, ms=7, label="Maker, round number"),
               plt.Line2D([], [], marker="o", ls="", color=BREAKER, ms=7, label="Breaker, round number"),
               plt.Line2D([], [], marker="o", ls="", color=FAINT, ms=3, label="cell of a space diagonal")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 0.0))
    save(fig, "line-of-play")


def parse_leaf(record):
    f = [s.strip() for s in record.strip().split(" | ")]
    ints = lambda s: [int(v) for v in s.split(",")]
    blocks = []
    for e in f[4].split(" ; "):
        e = e.strip().rstrip(";").strip()
        if e and e != "-":
            cells, _lines = e.split(" : ")
            blocks.append(ints(cells))
    pairs = [tuple(int(v) for v in p.split("/")) for p in
             f[5].replace(";", " ; ").split(" ; ") if p.strip() and p.strip() != "-"]
    return ints(f[1]), ints(f[2]), int(f[3]), blocks, pairs


def block_colors(blocks):
    """Greedy hue per block so blocks that touch inside a slice differ."""
    def touch(a, b):
        for c in a:
            x, y, z = C.xyz(c)
            for dy, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= y + dy < N and 0 <= z + dz < N and C.cid(x, y + dy, z + dz) in b:
                    return True
        return False
    sets = [set(b) for b in blocks]
    out = []
    for i, s in enumerate(sets):
        used = {out[j] for j in range(i) if touch(s, sets[j])}
        out.append(next(k for k in range(len(HUES)) if k not in used))
    return out


def fig_leaf_certificate():
    """Section 8: the certificate at the leaf of the line of play.

    Blocks are lettered A, B, ... in record order (the draft's letters),
    pairs are grey cells joined by a stroke when both cells lie in one slice
    at most two cells apart, and otherwise carry the same small number, and unused cells are white."""
    M, B, r, blocks, pairs = parse_leaf(LEAF_RECORD)
    B = B + [r]                  # the leaf position includes Breaker's reply r
    assert (len(blocks), len(pairs)) == (11, 41)        # draft section 8
    assert sum(len(b) for b in blocks) == 117 and 2 * len(pairs) == 82
    pair_cells = {c for p in pairs for c in p}
    block_cells = {c for b in blocks for c in b}
    assert not (block_cells & pair_cells) and not ((set(M) | set(B)) & (block_cells | pair_cells))
    unused = set(range(C.CELLS)) - block_cells - pair_cells - set(M) - set(B)
    assert len(unused) == 9
    fig, ax, top = six_slice_axes(extra_below=2.4)
    draw_slices(ax, top)
    colors = block_colors(blocks)
    for i, b in enumerate(blocks):
        for c in b:
            fill_cell(ax, c, HUES[colors[i]], top)
        for x in sorted({C.xyz(c)[0] for c in b}):
            part = [c for c in b if C.xyz(c)[0] == x]
            outline_group(ax, part, top)
            ys = [C.xyz(c)[1] for c in part]
            zs = [C.xyz(c)[2] for c in part]
            ox, oy = origin(x, top)
            ax.text(ox + (min(zs) + max(zs) + 1) / 2, oy + (min(ys) + max(ys) + 1) / 2,
                    chr(ord("A") + i), ha="center", va="center", fontsize=8.5,
                    color="#555555", zorder=3)
    for c in pair_cells:
        fill_cell(ax, c, PAIR_FILL, top)
    tag = 0
    for a, b in pairs:
        (xa, ya, za), (xb, yb, zb) = C.xyz(a), C.xyz(b)
        if xa == xb and max(abs(ya - yb), abs(za - zb)) <= 2:
            stroke(ax, a, b, "#707070", lw=1.2, top=top, z=3)
            for c in (a, b):
                dot(ax, c, "#707070", r=0.17, top=top)
        else:
            tag += 1
            for c in (a, b):
                cx, cy = pos(c, top)
                ax.text(cx, cy + .02, str(tag), ha="center", va="center", fontsize=6,
                        color=INK, zorder=7)
    for i, m in enumerate(M):
        mark(ax, m, "M", top=top)
    for b in B:
        mark(ax, b, "B", top=top)
    handles = [Rectangle((0, 0), 1, 1, fc=HUES[0], ec=INK, lw=.7, label="block (lettered)"),
               Rectangle((0, 0), 1, 1, fc=PAIR_FILL, ec="#707070", lw=.7,
                         label="pair (joined, or same number at both cells)"),
               Rectangle((0, 0), 1, 1, fc="white", ec=GRID, lw=.7, label="unused"),
               plt.Line2D([], [], marker="o", ls="", color=MAKER, ms=7, label="Maker"),
               plt.Line2D([], [], marker="o", ls="", color=BREAKER, ms=7, label="Breaker")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 0.0))
    save(fig, "leaf-certificate")


def _reply_figure(name, maker, breaker, candidates, chosen):
    """Section 9 worked examples: candidate cells labelled by the summed
    squared distance to Maker's marks (question 5 of the rule)."""
    fig, ax, top = six_slice_axes(extra_below=2.4)
    draw_slices(ax, top)
    for c in space_diag_cells():
        dot(ax, c, top=top)
    for m in maker:
        mark(ax, C.cid(*m), "M", top=top)
    for b in breaker:
        mark(ax, C.cid(*b), "B", top=top)
    for cell, total in candidates.items():
        got = sum(sum((u - v) ** 2 for u, v in zip(cell, m)) for m in maker)
        assert got == total, (cell, got, total)             # the draft's table
        mark(ax, C.cid(*cell), "B", str(total), top=top, ring=(cell != chosen))
    assert max(candidates, key=candidates.get) == chosen
    handles = [plt.Line2D([], [], marker="o", ls="", color=MAKER, ms=7, label="Maker"),
               plt.Line2D([], [], marker="o", ls="", color=BREAKER, ms=7, label="Breaker"),
               plt.Line2D([], [], marker="o", ls="", mfc="white", mec=BREAKER, mew=1.3, ms=7,
                          label="candidate, with its summed squared distance"),
               plt.Line2D([], [], marker="o", ls="", color=BREAKER, ms=7, label="the rule's reply"),
               plt.Line2D([], [], marker="o", ls="", color=FAINT, ms=3,
                          label="cell of a space diagonal")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 0.0))
    save(fig, name)


def fig_reply_second():
    """Section 9, example (second reply); table in the draft."""
    _reply_figure(
        "reply-rule-second",
        maker=[(0, 0, 0), (1, 2, 5)], breaker=[(3, 3, 3)],
        candidates={(4, 4, 1): 62, (4, 1, 1): 44, (4, 1, 4): 44,
                    (1, 4, 1): 38, (1, 4, 4): 38, (1, 1, 4): 20},
        chosen=(4, 4, 1))


FIGURES = [fig_board_lines, fig_three_kinds_of_cell, fig_pairing_5x5, fig_slab_placements,
           fig_relabeling, fig_line_of_play, fig_leaf_certificate, fig_reply_second]

if __name__ == "__main__":
    for f in FIGURES:
        f()
