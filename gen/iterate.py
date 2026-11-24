"""Collect, harvest, merge, repeat: drive one first-move class to a proof.

usage: python gen/iterate.py <cube6 exe> <class> [--rounds 4] [--width 4]
           [--name class2] [--shards 4] [--workers 2] [--secs 300] [--passes 8]
           [--fixed-replies] [--retry-unknown]

Run from the folder holding data6.json (data5.json with CUBE_N=5 and an n5 build). Each pass runs `cube6 prove` in
collect mode with CACHE (proofs/<name>-cache.txt), so subtrees proven in
earlier passes are skipped and the pass writes every leaf still pending to
logs/<name>-front-<pass>.txt. New FAIL lines are harvested in parallel shards
(gen/harvest.py), the templates merged into data6.json (backed up first),
and the lines added to logs/<name>-hard.txt: a harvested leaf that comes back
fails for real, so the next pass tries Breaker's other replies there. Stops
when the class holds (the cache is then its proof: check it with
`verify full --root <cell>`), fails, or a pass finds nothing new to harvest.
A leaf CP-SAT timed out on (status unknown) also goes to HARD, so the search
moves on, and to logs/<name>-unknown.txt; --retry-unknown takes those lines
back out of HARD at the start, for another try with a larger --secs.
Progress: logs/<name>-iterate.log. Workflow: docs/search.md."""
import argparse, hashlib, os, shutil, subprocess, sys, time
import jsonio

ap = argparse.ArgumentParser()
ap.add_argument("exe"); ap.add_argument("cls")
ap.add_argument("--rounds", default="4"); ap.add_argument("--width", default="4")
ap.add_argument("--name"); ap.add_argument("--shards", type=int, default=4)
ap.add_argument("--workers", type=int, default=2); ap.add_argument("--secs", default="300")
ap.add_argument("--passes", type=int, default=8)
ap.add_argument("--fixed-replies", action="store_true", help="harvest each written reply instead of letting CP-SAT pick the reply")
ap.add_argument("--retry-unknown", action="store_true", help="give leaves CP-SAT timed out on another try")
a = ap.parse_args()
# caches, HARD, and logs are per board size (src/search.rs also refuses a cache for another board)
name = a.name or (f"class{a.cls}" if jsonio.N == 6 else f"n{jsonio.N}-class{a.cls}")
os.makedirs("logs", exist_ok=True); os.makedirs("proofs", exist_ok=True)
cache, hard, log = f"proofs/{name}-cache.txt", f"logs/{name}-hard.txt", f"logs/{name}-iterate.log"
unknown = f"logs/{name}-unknown.txt"
# harvest.py resumes from an existing output file, so each run's shard files get their own names
run = time.strftime("%Y%m%d-%H%M%S")
here = os.path.dirname(os.path.abspath(__file__))

def note(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M')} {msg}"
    print(line, flush=True)
    with open(log, "a") as f: f.write(line + "\n")

def fail_lines(path):
    return [l.strip() for l in open(path) if l.startswith("FAIL")] if os.path.exists(path) else []

def leaf(l):
    """The position before Breaker's reply: a leaf's written replies share it."""
    f = dict(x.split("=") for x in l.split()[1:])
    return f["maker"], tuple(sorted(set(f["breaker"].split(",")) - {f["reply"]}))

def unknown_hint():
    n = len(fail_lines(unknown))
    return f" ({n} HARD lines only timed out: rerun with --retry-unknown and a larger --secs)" if n else ""

def sha(path):
    with open(path, "rb") as f: return hashlib.sha256(f.read()).hexdigest()[:16]

# provenance for comparing runs: settings, inputs, and the code that ran
commit = subprocess.run(["git", "-C", here, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
note(f"start: {' '.join(sys.argv[1:])}; {jsonio.DATA} sha256 {sha(jsonio.DATA)}; exe sha256 {sha(a.exe)}; "
     f"gen commit {commit}; RAYON_NUM_THREADS={os.environ.get('RAYON_NUM_THREADS', 'all')}")
open(hard, "a").close()
if a.retry_unknown and os.path.exists(unknown):
    retry = set(fail_lines(unknown))
    keep = [l for l in fail_lines(hard) if l not in retry]
    with open(hard, "w") as f: f.write("".join(l + "\n" for l in keep))
    os.remove(unknown)
    note(f"retrying {len(retry)} timed-out lines: removed from {hard}")
for p in range(1, a.passes + 1):
    front = f"logs/{name}-front-{p}.txt"
    env = dict(os.environ, COLLECT="1", CACHE=cache, HARD=hard, FRONTIER=front)
    note(f"pass {p}: collect run")
    with open(f"logs/{name}-pass-{p}.log", "w") as out:
        code = subprocess.run([a.exe, "prove", a.rounds, a.width, a.cls], env=env, stdout=out, stderr=subprocess.STDOUT).returncode
    out_lines = open(f"logs/{name}-pass-{p}.log").read().strip().splitlines()
    verdict = out_lines[-1]
    # the search prints its board first; a build for another board would
    # harvest and merge against the wrong data file
    board = f"{jsonio.N}x{jsonio.N}x{jsonio.N} board"
    if not out_lines[0].startswith(board):
        note(f"{a.exe} does not play a {board} ({jsonio.DATA}): {out_lines[0][:60]}"); sys.exit(2)
    note(f"pass {p}: exit {code}: {verdict}")
    if code == 0:
        note(f"HOLDS: {cache} is the proof for class {a.cls}; check it with verify full --root")
        sys.exit(0)
    if code != 1:
        note("search error; stopping"); sys.exit(2)
    # only harvested leaves (HARD) fail for real, so a failed class means a
    # line of play where every reply within width reached one; new templates
    # elsewhere cannot rescue it
    if "not proven" in verdict:
        note("failed for real: a Maker line beats every reply within width, through leaves already harvested" + unknown_hint()); sys.exit(1)
    done = set(fail_lines(hard))
    new = [l for l in dict.fromkeys(fail_lines(front)) if l not in done]
    if not new:
        note("nothing new to harvest; stopping" + unknown_hint()); sys.exit(1)
    if not a.fixed_replies:
        # one solve per leaf: its written replies share the position before the reply
        work = list({leaf(l): l for l in reversed(new)}.values())[::-1]
    else:
        work = new
    note(f"pass {p}: harvesting {len(work)} of {len(new)} FAIL lines in {a.shards} shards")
    procs = []
    for i in range(a.shards):
        part = work[i::a.shards]
        if not part: continue
        base = f"logs/{name}-{run}-h{p}-{i}"
        src, dst = base + ".txt", base + ".json"
        with open(src, "w") as f: f.write("\n".join(part) + "\n")
        mode = [] if a.fixed_replies else ["--any-reply"]
        procs.append((dst, subprocess.Popen([sys.executable, "-u", os.path.join(here, "harvest.py"), src, dst, a.secs, str(a.workers), *mode],
                                            stdout=open(base + ".log", "w"), stderr=subprocess.STDOUT)))
    for _, pr in procs: pr.wait()
    if any(pr.returncode for _, pr in procs):
        note("a harvest shard failed; stopping (see its log)"); sys.exit(2)
    # harvest.py prints "<input line index> <found|infeasible|unknown> ..." per solve
    status = {}
    for i in range(a.shards):
        part, slog = work[i::a.shards], f"logs/{name}-{run}-h{p}-{i}.log"
        if not part or not os.path.exists(slog): continue
        for l in open(slog):
            w = l.split()
            if len(w) >= 2 and w[0].isdigit() and w[1] in ("found", "infeasible", "unknown"):
                status[part[int(w[0])]] = w[1]
    # the FAIL lines a solve covered: with --any-reply a solve covers its
    # leaf's every written reply; fixed-reply lines may lack reply=
    def covered(kind):
        solved = [l for l, s in status.items() if s == kind]
        if a.fixed_replies: return set(solved)
        keys = {leaf(l) for l in solved}
        return {l for l in new if leaf(l) in keys}
    timed_out = [l for l, s in status.items() if s == "unknown"]
    if timed_out:
        lines = sorted(covered("unknown"))
        with open(unknown, "a") as f: f.write("\n".join(lines) + "\n")
        note(f"pass {p}: CP-SAT timed out on {len(timed_out)} leaves; their lines are in {unknown}")
    outs = [d for d, _ in procs if os.path.exists(d)]
    cert_files = [d[:-5] + ".certs.json" for d in outs if os.path.exists(d[:-5] + ".certs.json")]
    if cert_files:
        # leaf layouts go straight into the cache, so the next pass finds
        # those leaves proven even if a merged template misses the shortlist
        imp = subprocess.run([a.exe, "import", *cert_files], env=dict(os.environ, CACHE=cache), capture_output=True, text=True)
        if imp.returncode != 0:
            note(f"import failed: {imp.stderr.strip()[-300:]}"); sys.exit(2)
        note(f"pass {p}: {imp.stdout.strip().splitlines()[-1]}")
    shutil.copy(jsonio.DATA, f"{jsonio.DATA[:-5]}-before-{name}-pass{p}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    merged = subprocess.run([sys.executable, os.path.join(here, "merge.py"), *outs], capture_output=True, text=True, check=True).stdout.strip()
    note(f"pass {p}: {merged}")
    # a found leaf is in the cache now; only the rest must fail for real next
    # pass (and a leaf a crashed shard never reported stays out, to come back)
    found = covered("found")
    failed = covered("infeasible") | covered("unknown")
    still = [l for l in new if l in failed and l not in found]
    with open(hard, "a") as f: f.write("".join(l + "\n" for l in still))
    note(f"pass {p}: {len(found)} FAIL lines solved, {len(still)} added to HARD")
note(f"stopped after {a.passes} passes" + unknown_hint())
sys.exit(1)
