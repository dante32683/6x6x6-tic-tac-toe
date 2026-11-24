"""Set cover over fit sets (minimum-catalogue job, docs/leaf-catalogue.md).

usage: python gen/mincat_cover.py <out catalogue.json> <scout.json> [<scout.json> ...]
           [--seed <catalogue.json>] [--time <s>]

Each scout file lists leaves with the catalogue layouts that fit them
(gen/mincat_scout.py). Greedy picks the layout fitting the most uncovered
leaves until all are covered (an upper bound on the sample; ties go to the
more used layout, the lower id). CP-SAT then solves the minimum cover of the
same sample exactly or to a proven bound. Any catalogue certifying every
reached leaf also covers the sample, so the sample's optimum is a lower bound
for the whole proof, for catalogues drawn from the same pool of layouts.
--seed puts an earlier catalogue's layouts first and greedy only adds.
"""
import json, sys
from ortools.sat.python import cp_model


def greedy(sets, seed=()):
    chosen = list(seed)
    left = [i for i, s in enumerate(sets) if not set(s) & set(chosen)]
    while left:
        count = {}
        for i in left:
            for k in sets[i]:
                count[k] = count.get(k, 0) + 1
        best = min(count, key=lambda k: (-count[k], k))
        chosen.append(best)
        left = [i for i in left if best not in sets[i]]
    return chosen


def exact(sets, limit):
    m = cp_model.CpModel()
    ks = sorted({k for s in sets for k in s})
    x = {k: m.NewBoolVar(f"x{k}") for k in ks}
    for s in {tuple(sorted(s)) for s in sets}:
        m.AddBoolOr([x[k] for k in s])
    m.Minimize(sum(x.values()))
    sol = cp_model.CpSolver()
    sol.parameters.max_time_in_seconds = limit
    sol.parameters.num_workers = 3
    st = sol.Solve(m)
    best = [k for k in ks if sol.Value(x[k])] if st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    return sol.StatusName(st), int(sol.BestObjectiveBound()), best


def main():
    args = sys.argv[1:]
    seed, limit = [], 120.0
    if "--seed" in args:
        i = args.index("--seed"); seed = json.load(open(args[i + 1]))["layouts"]; del args[i:i + 2]
    if "--time" in args:
        i = args.index("--time"); limit = float(args[i + 1]); del args[i:i + 2]
    out, files = args[0], args[1:]
    rows = [r for f in files for r in json.load(open(f))]
    sets = [r["fits"] for r in rows]
    empty = sum(1 for s in sets if not s)
    sets = [s for s in sets if s]
    g = greedy(sets, seed)
    status, bound, best = exact(sets, limit)
    res = {"layouts": g, "sample_leaves": len(rows), "sample_leaves_without_fit": empty,
           "greedy": len(g), "cpsat_status": status, "cpsat_lower_bound": bound,
           "cpsat_best": len(best) if best else None, "cpsat_layouts": best}
    json.dump(res, open(out, "w"), indent=1)
    print({k: v for k, v in res.items() if k not in ("layouts", "cpsat_layouts")}, "greedy:", g)


if __name__ == "__main__":
    main()
