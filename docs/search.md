# Iterating on a first-move class

A plain `cube6 prove` run either proves a class or reports "not proven" after
hours, and a rerun with new templates starts over. The iterate workflow keeps
every proven subtree and learns templates between passes instead.

## Pieces

- **Progress.** `prove` prints a `progress` line every `PROGRESS` seconds
  (default 300; 0 turns it off): Breaker nodes searched, certified leaves,
  cache hits, failed or pending leaves, and Maker moves done/started per depth
  (`d1` is Maker's second move, the top branching level under the first
  reply). `d1` done/started is the best single progress figure; "started"
  grows when the search backs up and tries another Breaker reply.
- **Cache (`CACHE=<path>`).** A proof-record file (docs/proof-format.md),
  starting with a `# board 6x6x6` line (a comment to the verifier); a build
  refuses a cache for another board. At
  start every record's Breaker-to-move position, canonicalized under the
  full 1,152-map group, counts as proven; new records are appended as they
  are found. Children always finish before their parent, so the file is in
  children-first order and every prefix is closed under the strategy. A torn
  last line from a stopped run is cut off at load; any other unreadable line
  stops the run. One writer per cache file.
- **Collect mode (`COLLECT=1`).** A last-round leaf with no certificate is
  pending instead of failed: it is written to `FRONTIER` and the search keeps
  going on the same reply instead of backing up. One pass lists every leaf
  that still needs a template, at the cost of one search without backtracking.
  A class that finishes with no pending leaf is proven, and the cache is its
  proof.
- **Hard leaves (`HARD=<path>`).** `FAIL` lines already harvested. In collect
  mode a leaf whose written replies (top `FRONTIER_REPLIES`) are all listed
  fails for real, so the parent tries its other replies within width.

## The loop

`python gen/iterate.py <cube6 exe> <class> [--rounds 4 --width 4 --shards 4
--workers 2 --secs 300 --passes 8]`, run from the folder with `data6.json`:

1. Collect pass with `CACHE=proofs/<name>-cache.txt`, `HARD=logs/<name>-hard.txt`.
2. Exit 0: the class holds. Check the cache with
   `verify full --root <cell>` (class 0 -> 0, 2 -> 2, 4 -> 8, 7 -> 44).
3. "not proven": some Maker line beats every reply within width through hard
   leaves; new templates elsewhere can't fix it. Stop and rethink (more width,
   longer harvests, or blocks that contain Maker's cells).
4. Otherwise harvest the new `FAIL` lines in parallel shards. Each layout
   CP-SAT finds is checked and added to the cache as that leaf's certificate
   (`cube6 import`), so the leaf is proven next pass even if the template
   misses the search's shortlist; the layouts are also merged into
   `data6.json` (backed up first) as templates for other positions. The
   lines go on the hard list, and the next pass runs.

`FAIL` lines carry `reply=<cell>`, Breaker's last reply, so a layout can be
filed under the position before it. Log: `logs/<name>-iterate.log`.
Soundness never rests on the cache or the loop: the proof is whatever
`verify full` accepts.

## Sharing a pass between machines

With `SPLIT=k/n` (collect mode only) a run searches every n-th move class of
Maker's second move, starting at k, and leaves the rest pending. Run
`k = 0..n-1` on n machines, join their caches with
`cube6 merge-cache <new file> <cache>...` (each is children-first, so the
join is too; plain concatenation can keep a torn last record), and let the
next unsplit pass finish from the merged cache. Every share must come from
the same build: a 48-map build and a full-group build list Maker's second
moves differently, so their shares don't line up. A merged cache from any
builds is still a valid seed for one unsplit pass, since each record is a
proven position.

On Windows the search opts out of EcoQoS (`src/qos.rs`), so a run started
without a console window still uses every core.

## Assembling the full proof

Concatenate the caches (or proof files) of one class from each orbit,
{0, 6, 9}, {1, 2, 3, 5, 7, 8}, and {4} (classes 0, 2, and 4), keep one header
line, and run `verify full` with no `--root`; only that prints PROOF OK
(`docs/checking.md`, "The files", gives the exact join).
