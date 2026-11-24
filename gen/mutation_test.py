"""Mutation test for the independent verifier: take real leaf (L) records from
a proof the verifier accepts, break each in ways that must be rejected, and
check that `verify certs` accepts every original and rejects every mutant.

usage: python gen/mutation_test.py <verify exe> <proof file> [records=40] [seed=1]
Exit 0 when every original passes and every must-fail mutant is rejected.
"Probable" mutants (a dropped block or pair) usually leave a line uncovered
but can be legitimately valid, so they are counted, not required."""
import os, random, subprocess, sys, tempfile

exe, proof = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
rng = random.Random(int(sys.argv[4]) if len(sys.argv) > 4 else 1)

# reservoir sample of L records, so a large proof file is read once
picked = []
for k, line in enumerate(l for l in open(proof) if l.startswith("L |")):
    if len(picked) < n: picked.append(line.strip())
    elif (j := rng.randrange(k + 1)) < n: picked[j] = line.strip()

def fields(rec):
    _, m, b, r, blocks, pairs = [f.strip() for f in rec.split("|")]
    return m, b, r, ([] if blocks == "-" else blocks.split(" ; ")), ([] if pairs == "-" else pairs.split(" ; "))

def record(m, b, r, blocks, pairs):
    return f"L | {m} | {b} | {r} | {' ; '.join(blocks) or '-'} | {' ; '.join(pairs) or '-'}"

def mutants(rec):
    """(name, must_fail, mutated record); skipped when the record lacks the parts."""
    m, b, r, blocks, pairs = fields(rec)
    out = [("reply on a Maker cell", True, record(m, b, m.split(",")[0], blocks, pairs))]
    if len(pairs) >= 2:
        a0 = pairs[0].split("/")[0]
        p1 = pairs[1].split("/")
        out.append(("two pairs share a cell", True, record(m, b, r, blocks, [pairs[0], f"{p1[0]}/{a0}", *pairs[2:]])))
    if pairs:
        out.append(("pair on Breaker's reply cell", True, record(m, b, r, blocks, [f"{r}/{pairs[0].split('/')[1]}", *pairs[1:]])))
        # usually leaves a live line uncovered, but pairs on lines that are
        # already dead or block-covered would make this legitimately valid
        out.append(("all pairs removed", False, record(m, b, r, blocks, [])))
        out.append(("one pair removed", False, record(m, b, r, blocks, pairs[1:])))
    if len(blocks) >= 2:
        c0, e0 = blocks[0].split(" : ")
        extra = blocks[1].split(" : ")[0].split(",")[0]
        # cells stay sorted, so the verifier rejects the overlap and not the spelling
        cells = ",".join(map(str, sorted(map(int, c0.split(",") + [extra]))))
        out.append(("two blocks share a cell", True, record(m, b, r, [f"{cells} : {e0}", *blocks[1:]], pairs)))
    if blocks:
        out.append(("one block removed", False, record(m, b, r, blocks[1:], pairs)))
    return out

def accepted(records):
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f: f.write("\n".join(records) + "\n")
    try:
        return subprocess.run([exe, "certs", path], capture_output=True).returncode == 0
    finally:
        os.unlink(path)

ok = accepted(picked)
print(f"{len(picked)} original records: {'accepted' if ok else 'REJECTED'}")
tally = {}
for rec in picked:
    for name, must_fail, mut in mutants(rec):
        t = tally.setdefault(name, [must_fail, 0, 0])
        t[1] += 1
        t[2] += not accepted([mut])
for name, (must_fail, tried, rejected) in tally.items():
    flag = "" if not must_fail or rejected == tried else "   <-- ACCEPTED A BROKEN RECORD"
    print(f"{'must fail' if must_fail else 'probable '}  {name}: {rejected}/{tried} rejected{flag}")
bad = not ok or any(mf and rej != tried for mf, tried, rej in tally.values())
print("MUTATION TEST " + ("FAILED" if bad else "OK"))
sys.exit(1 if bad else 0)
