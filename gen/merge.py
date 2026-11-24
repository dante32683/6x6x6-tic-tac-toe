"""Append harvested templates (harvest.py output files) to data6.json,
skipping duplicates. usage: python gen/merge.py <harvest.json>..."""
import json, sys
import jsonio
D = json.load(open(jsonio.DATA))
have = {tuple(sorted(t)) for t in D["templates"]}
added = 0
cells = [set(b["cells"]) for b in D["blocks"]]
for f in sys.argv[1:]:
    for t in json.load(open(f)):
        # Python would read a negative index as counting from the end
        if not isinstance(t, list) or any(type(b) is not int or not 0 <= b < len(cells) for b in t):
            raise ValueError(f"{f}: bad template {t!r}")
        # a template's blocks must be fully disjoint: a layout found where two
        # blocks share a Breaker-held cell is unsound once that cell is empty
        if sum(len(cells[b]) for b in t) != len(set().union(*(cells[b] for b in t))):
            print("skipped overlapping template", t)
            continue
        k = tuple(sorted(t))
        if k not in have:
            have.add(k); D["templates"].append(sorted(t)); added += 1
jsonio.dump(D, jsonio.DATA)
print("added", added, "templates;", len(D["templates"]), "total")
