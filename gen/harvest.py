"""Learn templates from hard positions: for each `FAIL maker=.. breaker=..`
line, ask CP-SAT for any layout of library blocks and pairs covering every
live line, and append the chosen blocks as a new template.

usage: python gen/harvest.py <fails.txt> <out.json> [seconds] [workers] [--any-reply]
With --any-reply, each leaf position (a FAIL line minus its reply=) is solved
once and CP-SAT picks Breaker's reply as well as the layout.
out.json holds a list of block-index lists; merge.py adds them to data6.json.
Beside it, out.certs.json keeps each find with its FAIL line, for
`cube6 import` to check and add to a proof cache as that leaf's certificate.
Both files are rewritten atomically after each find, so a stopped run keeps
what it found. Each line's status: found (an empty list is a pairs-only layout),
infeasible (no layout of this library's untouched blocks exists), or unknown
(time ran out)."""
import json, sys, itertools, os, time
from ortools.sat.python import cp_model
import jsonio
D = json.load(open(jsonio.DATA))
NCELLS = len({c for l in D["lines"] for c in l})
L = [set(l) for l in D["lines"]]; BL = [(set(b["cells"]), b["lines"]) for b in D["blocks"]]
# --any-reply: solve each leaf position once, letting CP-SAT choose Breaker's
# reply too, instead of one solve per FAIL line's fixed reply (needs reply=)
any_reply = "--any-reply" in sys.argv
args = [x for x in sys.argv if x != "--any-reply"]
src, out = args[1], args[2]
secs = float(args[3]) if len(args) > 3 else 300
workers = int(args[4]) if len(args) > 4 else 8
found = json.load(open(out)) if os.path.exists(out) else []
certs_out = out[:-5] + ".certs.json" if out.endswith(".json") else out + ".certs.json"
certs = json.load(open(certs_out)) if os.path.exists(certs_out) else []

def layout(M, B, choose_reply=False):
    """A block-and-pair layout covering every live line at Maker to move.
    With choose_reply, B is Breaker's cells before his reply and the model
    also picks the reply; returns (status, blocks, reply)."""
    used = M | B; live = [li for li in range(len(L)) if not L[li] & B]
    m = cp_model.CpModel()
    y = {c: m.NewBoolVar("") for c in range(NCELLS) if c not in used} if choose_reply else {}
    if y:
        m.AddExactlyOne(y.values())
    # assignment model: a[l, c] gives cell c to line l's pair; a line needs two
    # cells unless a chosen block covers it. For fixed blocks this is a
    # bipartite b-matching, so the LP is tight and search branches on blocks.
    a = {(li, c): m.NewBoolVar("") for li in live for c in L[li] if c not in used}
    # every non-Maker cell has capacity one: a learned template must stay
    # disjoint when Breaker's cells are empty elsewhere (merge.py checks it)
    load = {c: [] for c in range(NCELLS) if c not in M}
    for (li, c), v in a.items(): load[c].append(v)
    zl = {li: [] for li in live}; zs = []
    for bi, (cells, E) in enumerate(BL):
        if cells & M: continue
        Ei = [li for li in E if li in zl]
        if not Ei: continue
        z = m.NewBoolVar(""); zs.append((bi, z))
        for c in cells: load[c].append(z)
        for li in Ei: zl[li].append(z)
    for li in live:
        # the reply kills every line through it
        killed = 2 * sum(y[c] for c in L[li] if c in y)
        m.Add(sum(v for (l2, c), v in a.items() if l2 == li) + 2 * sum(zl[li]) + killed >= 2)
    for v in load.values():
        if len(v) > 1: m.AddAtMostOne(v)
    # the reply cell can't be a pair cell; a block may hold it (a Breaker mark
    # inside a block only helps Breaker there)
    pair_vars = {}
    for (li, c), v in a.items(): pair_vars.setdefault(c, []).append(v)
    for c, yc in y.items():
        m.AddAtMostOne(pair_vars.get(c, []) + [yc])
    s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = secs; s.parameters.num_workers = workers
    r = s.Solve(m)
    if r in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        reply = next((c for c, yc in y.items() if s.Value(yc)), None)
        return "found", [bi for bi, z in zs if s.Value(z)], reply
    if r == cp_model.INFEASIBLE:
        return "infeasible", None, None
    if r == cp_model.MODEL_INVALID:
        raise RuntimeError("CP-SAT model invalid")
    return "unknown", None, None

done = set()
for i, line in enumerate(open(src)):
    if not line.startswith("FAIL"): continue
    p = dict(x.split("=") for x in line.split()[1:])
    M = set(map(int, p["maker"].split(","))); B = set(map(int, p["breaker"].split(",")))
    fmt = lambda s: ",".join(map(str, sorted(s)))
    if any_reply:
        if "reply" not in p:
            raise SystemExit(f"--any-reply needs reply= on every FAIL line: {line.strip()}")
        B = B - {int(p["reply"])}
        key = (fmt(M), fmt(B))
        if key in done: continue  # the leaf's other written reply
        done.add(key)
    t0 = time.time()
    status, t, reply = layout(M, B, any_reply)
    print(i, status, f"{time.time() - t0:.1f}s", "" if reply is None else f"reply={reply}", flush=True)
    if t is not None:
        found.append(t)
        jsonio.dump(found, out)
        fail = f"FAIL maker={fmt(M)} breaker={fmt(B | {reply})} reply={reply}" if any_reply else line.strip()
        certs.append({"fail": fail, "blocks": t})
        jsonio.dump(certs, certs_out)
print("templates harvested:", len(found))
