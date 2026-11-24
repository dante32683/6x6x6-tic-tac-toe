# Checking the proof

This page lists the proof files with their SHA-256 hashes, the commands that
check them, and what each checker printed. `full-6x6x6.v2.zst` is attached
to the repository's v1.0 release; the other proof files (2.2 to 2.6 GB) will
be deposited with the paper.

## The files

The first proof was searched one first-move orbit at a time (classes 0, 2,
and 4: `docs/proof-format.md`, "Orbits of first moves"). `full-6x6x6.txt`
is the format header (`head -n 1 class4-full.txt`) followed by every
non-`#` line of `class0.txt`, `class2w.txt`, and `class4-full.txt`, in that
order.

| File | What | Bytes | Records | SHA-256 |
| --- | --- | --- | --- | --- |
| `class0.txt` | first proof, orbit of cell 0 (24 cells) | 246,604,134 | 907 R, 173,526 L | `546453B3D8A54BFFEF4C3415DEBCD3387850C3CA3A3EF43C56C4BA5A6DDDE153` |
| `class2w.txt` | first proof, orbit of cell 2 (144 cells) | 699,969,429 | 2,579 R, 493,713 L | `53C1FEAA24B91850FDDFF0940DC978578D398CC68FF9B104EAD18B393C3F9C35` |
| `class4-full.txt` | first proof, orbit of cell 8 (48 cells) | 1,273,967,149 | 4,584 R, 900,806 L | `5CCB4EAFCD1D816819737E865768FFBDCFD429A2AB6637200F2FA9AE69C0CBA1` |
| `full-6x6x6.txt` | **the first proof**, all three orbits | 2,220,540,596 | 1,576,115 | `CAF150B233DACF9304B7B174B683C5FB92567C3F4465F4B35B194A85344B959B` |
| `rule-6x6x6.txt` | rule proof (`docs/rule.md`) | 2,452,094,392 | 8,512 R, 1,729,978 L | `925297C908FD6949F067EC6A153FAFF02D5FCEFB3D47D60033528FCE08E47C22` |
| `rule-6x6x6-ext.txt` | **the extended rule proof**: the rule proof plus 400 records that close the strict replay | 2,570,053,080 | 8,912 R, 1,813,142 L | `861604894B16075AB94BF3700D22A35B6624CA3B472F98621346FB819B97F5F9` |
| `pruned-6x6x6.txt` | first proof, one record per position the first-record walk reaches | 1,489,012,428 | 5,478 R, 1,051,860 L | `2C8A9C68F3B4D49EBC146B0882DF107AB2DE61273C9EDBBDCEAFB3E34DB19178` |
| `full-6x6x6.v2.zst` | `full-6x6x6.v2` compressed with `zstd -19` (the v1.0 release file) | 1,934,246 | | `D8CA97DC7B82A07313DA1D6F2F61A836A4CD9EF23C74C626B499D69A7908EAA8` |
| `full-6x6x6.v2` | the pruned proof as a catalogue of 5,095 layouts, 8 bytes per leaf (`docs/proof-format.md`, "Catalogue format (v2)") | 7,816,925 | | `4FAC9777685663113D5E5A7D086CAA7AAA59DB9C33AE983E10291A8A76D18C1D` |
| `mincat-6x6x6.txt` | first proof with every leaf re-certified from 520 layouts (`docs/leaf-catalogue.md`) | 1,893,104,952 | 8,070 R, 1,338,185 L | `C62C058B845549F73CD88E3F06F717E6E2D2831801C28BCD429D345E4042847D` |
| `mincat-6x6x6.txt.zst` | `mincat-6x6x6.txt` compressed with zstd | 114,660,440 | | `B8EA8181FF2D0B6574208E335868B04A6787CBE85E41476D8DEABC730C12ACE9` |
| `seven/cover7.txt` | the static 7x7x7 cover (`docs/seven.md`), in this repository | 5,700 | | `090090DD08943FD79D567BFDCB9A2F4BE732ABF93A829B9535A5EBD9B6BD255D` |

## Commands

Build the Rust checker once (`cd verify && cargo build --release && cd ..`).
The Python checkers need Python 3.10+ and NumPy.

The release file:

    zstd -d full-6x6x6.v2.zst
    verify/target/release/verify full full-6x6x6.v2                     # expect PROOF OK
    python gen/compact_v2.py decode full-6x6x6.v2 full-6x6x6-decoded.txt
    python verify_py/check_cube6.py full-6x6x6-decoded.txt              # expect PROOF OK
    python verify_gpt/check_cube6.py full-6x6x6-decoded.txt             # expect PROOF OK

The Python checkers read only the text format, so they check the file that
`gen/compact_v2.py` decodes. A wrong decoder can only make a check fail.

The full proof files:

    verify/target/release/verify full full-6x6x6.txt            # expect PROOF OK
    python verify_py/check_cube6.py full-6x6x6.txt              # expect PROOF OK
    python verify_gpt/check_cube6.py full-6x6x6.txt             # expect PROOF OK

    verify/target/release/verify full rule-6x6x6-ext.txt
    python verify_py/check_cube6.py rule-6x6x6-ext.txt --all-records
    python verify_gpt/check_cube6.py rule-6x6x6-ext.txt --all-records
    cargo build --release && target/release/cube6 replay rule-6x6x6-ext.txt   # expect REPLAY OK
    python replay_py/replay_rule.py rule-6x6x6-ext.txt                         # same counts

`--root CELL` checks one first-move orbit and prints `ROOT ORBIT OK`, which
is not a proof of the whole game. `verify/` follows every R record of a
position; the Python checkers follow the first in file order unless given
`--all-records`. Both walks are complete strategies, so each `PROOF OK`
proves the theorem on its own; they walk different trees and print
different counts.

## Results

Every run in this table used a 4-core Arm Neoverse-N1 server with 24 GB,
rustc 1.100.0, Python 3.12.3, and NumPy 2.5.0. Times are wall-clock; memory
is peak resident.

| Proof | Checker | Printed | Time | Memory |
| --- | --- | --- | --- | --- |
| first | `verify/` | PROOF OK: 1,466,708 distinct canonical positions among the records, 7,072 positions checked, 1,660,407 leaf certificates, 9,206 block games (largest 16 cells) | 22 min | 9.3 GB |
| first | `verify_py/` | PROOF OK: 5,453 Maker nodes, 1,051,860 distinct leaves, 7,557 block games | 36 min | 791 MB |
| first | `verify_gpt/` | PROOF OK: 1,051,860 distinct leaves reached, 327 block games | 24 min | 391 MB |
| rule, extended | `verify/` | PROOF OK: 7,837 positions, 2,256,632 leaf certificates, 7,901 block games | 23.2 min | 10.7 GB |
| rule, extended | `verify_py/ --all-records` | PROOF OK: 7,838 Maker nodes, 1,813,142 leaves, 7,696 block games | 46.1 min | 1,376 MB |
| rule, extended | `verify_gpt/ --all-records` | PROOF OK: 7,838 Maker nodes, 1,813,142 leaf certificates | 24.5 min | 521 MB |
| rule, extended | `cube6 replay`, `replay_py/` | REPLAY OK: 3 first, 229 second, and 7,945 third rule replies covered | | |

`verify_gpt/` counts block games up to any relabeling of their cells and
lines, so its count is smaller. Without `--all-records` the Python checkers
also pass the extended rule proof (38.6 and 23.2 min), and all three pass
`rule-6x6x6.txt`, `pruned-6x6x6.txt`, the decoded `full-6x6x6.v2`, and
`mincat-6x6x6.txt`. On `mincat-6x6x6.txt`, `verify/` printed 7,072
positions, 1,478,394 leaf certificates, and 9,040 block games (20.1 min,
7.9 GB); `verify_gpt/` took 18.5 min (349 MB) and `verify_py/` 30 min.

On the same server `verify full full-6x6x6.v2` printed PROOF OK: 1,057,338
distinct canonical positions among the records, 5,452 positions checked,
1,138,474 leaf certificates, and 7,822 block games (17.6 min including the
decode, 3.5 GB).

`pruned-6x6x6.txt` can be rebuilt from the full proof (`verify full
full-6x6x6.txt --emit-used lines.txt`, then `gen/compact_prune.py`,
`docs/proof-format.md`, "Pruned proofs"); the rebuild has the same SHA-256.
On it `verify/` printed 5,452 positions and 1,138,474 leaf certificates
(15.7 min, 6.3 GB), and `verify_gpt/` 1,057,338 records, no duplicate
classes, and 1,051,860 leaves reached (14.8 min, 321 MB).

**One orbit at a time** (`--root`):

| Checker | `class0.txt --root 0` | `class2w.txt --root 2` |
| --- | --- | --- |
| `verify/` | 878 positions, 194,359 leaf checks, 141 s | 2,495 positions, 556,990 leaf checks, 466 s |
| `verify_py/` | 91,382 leaves reached, 223 s, 224 MB | 315,573 leaves reached, 618 s, 358 MB |
| `verify_gpt/` | 91,382 leaves reached, 233 s, 135 MB | 315,573 leaves reached, 474 s, 198 MB |

`verify/ --root 8` on `class4-full.txt`: 3,732 positions, 881,312 leaf
checks, 313 s.

**Clean rooms.** Each started from an archive holding a proof file and a
git bundle of this repository, cloned the repository from the bundle,
checked the proof's SHA-256, built `verify/` from source, and ran all three
checkers.

- A fresh `rust:1-bookworm` container with only the first proof's archive
  and standard Debian packages: all three printed `PROOF OK` (21, 20, and 53
  minutes). It ran on the server above, so it shows the archive is enough
  to reproduce the check, not independence of hardware.
- A desktop (Intel Core i7-14700F, 32 GB, Windows 11; rustc 1.99.1, Python
  3.14.10, NumPy 2.5.4), each part in a fresh folder with a fresh clone and
  a fresh cargo target folder:

| Part | Results |
| --- | --- |
| first proof | SHA-256 matches; `verify/` 14.0 min, 8.6 GB; `verify_gpt/` 11.9 min; `verify_py/` 26.2 min; all PROOF OK |
| extended rule proof | SHA-256 matches; `verify/` 16.4 min, 9.7 GB; `verify_gpt/ --all-records` 13.2 min; `verify_py/ --all-records` 34.6 min; all PROOF OK |
| 7x7x7 cover | `cover7.txt` hash matches; `seven` tests 7/7; `seven cover` and `check_cover7.py` COVER OK; `test_check_cover7.py` OK |
| mutation tests | both MUTATION TEST OK (below) |

**Tests of the checkers.** `verify_py/test_mutations.py` corrupts 20 real
leaf records in 140 ways and every corruption is rejected;
`gen/mutation_test.py` does the same for `verify/` on 40 sampled records;
each Python checker's `--selftest` runs hand-built cases that must fail.
`verify_gpt/test_mutations.py full-6x6x6.txt 200` makes 13 kinds of
corruption of 200 sampled leaf records: all 1,800 copies of the nine
must-fail kinds are rejected, and 798 of 800 of the four kinds that need
not break a certificate (198/200 with one block claim dropped).
`gen/walk_mutation_test.py full-6x6x6.txt <verify> verify_gpt` cuts the
proof to the walk of the orbit of cell 0 (467 R, 91,382 L records, one per
class), then
changes three replies and deletes three R and three L records: both
checkers reject all nine (26.5 min on the desktop).
