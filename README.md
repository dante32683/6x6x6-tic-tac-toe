# 6x6x6 tic-tac-toe is a draw

In tic-tac-toe on the 6x6x6 cube, two players take turns claiming cells, and
the first to own all six cells of one of the 148 lines wins. This repository
holds a computer-assisted proof that neither player can force a win.

**Status:** the proof is complete. Two checkers written separately from one
specification, one by Claude and one by ChatGPT, accept it (`docs/checking.md`).
No one outside the project has reviewed it yet. A paper is in preparation.

## How the proof works

The proof is about the Maker-Breaker version of the game: Maker moves first
and wins by owning a whole line, and Breaker wins by stopping her. Breaker
wins on 6x6x6, and strategy stealing then makes ordinary 6x6x6 tic-tac-toe a
draw. With 7x7x7 settled in 2025 (Cain, Raymond, and Källersjö,
arXiv:2509.21494), 5x5x5 is the only cube whose outcome is still open.

Breaker's strategy is a tree. For the first three or four moves it gives his
reply to every Maker move, up to the 1,152 symmetries of the cube's lines.
At each leaf it gives a *certificate*: disjoint blocks (small sub-boards on
which Breaker's local game is solved exhaustively) and pairs (two empty
cells of one line; Breaker takes whichever Maker doesn't) that together
cover every line Maker can still complete. Breaker plays each piece on its
own, so a valid certificate is a win.

The tree is stored as a proof file, one record per position.
`docs/proof-format.md` defines the format and shows why a file the checkers
accept gives Breaker a winning strategy. It is the only thing the checkers
share with the search or with each other.

There is a second proof in which every reply before the leaves follows a
fixed five-question rule (`docs/rule.md`). The same kind of certificate also
gives a 7x7x7 strategy with no opening moves at all (`docs/seven.md`).

## Checking it

The smallest form of the proof is `full-6x6x6.v2.zst` (1.9 MB), attached to
the [v1.0 release](https://github.com/dante32683/6x6x6-tic-tac-toe/releases/tag/v1.0).
Decompressed it is `full-6x6x6.v2`, which the Rust checker reads directly:

    curl -LO https://github.com/dante32683/6x6x6-tic-tac-toe/releases/download/v1.0/full-6x6x6.v2.zst
    zstd -d full-6x6x6.v2.zst
    cd verify && cargo build --release && cd ..
    verify/target/release/verify full full-6x6x6.v2      # PROOF OK

On a 4-core server the check took 18 minutes and 3.5 GB. `docs/checking.md`
gives the SHA-256 hashes, the commands for the two Python checkers and for
the full proof files (2.2 to 2.6 GB, to be deposited with the paper), and
what each checker printed.

Each checker rebuilds the lines and the symmetry group itself, tries every
Maker move at every position, solves every block's game exhaustively, and
checks every certificate.

## Layout

| Path | What |
| --- | --- |
| `verify/` | Rust checker |
| `verify_py/` | Python checker, written from `docs/proof-format.md` alone |
| `verify_gpt/` | Python checker written by ChatGPT from the same document (`verify_gpt/prompt.md`) |
| `src/` | the search that found the strategy (binary `cube6`); not part of the trusted base |
| `replay_py/` | replays the five-question rule on a rule proof, independently of `cube6 replay` |
| `seven/` | the 7x7x7 re-check and the static 7x7x7 cover (`cover7.txt`) with two checkers for it |
| `gen/` | Python tools: block library and CP-SAT harvesting for the search, measurements over proof files, figures |
| `data6.json` | blocks and layout templates the search uses |
| `docs/` | the proof format, checking, the rule, Breaker's strategy in plain terms, measurements, the search workflow, and 7x7x7 |
| `paper/figures/` | figures for the paper, drawn by `gen/figures.py` |

The search, the Rust and first Python checkers, and the other tools were
written by Claude (Anthropic) under Dante Martin's direction; `verify_gpt/`
was written by ChatGPT (OpenAI). Each checker's README says how it was
written.

## Building and testing

    cargo build --release                  # the search
    pip install -r gen/requirements.txt    # CP-SAT, for gen/harvest.py

Tests: `cargo test --release` in the root, `verify/`, and `seven/`;
`--selftest` in each Python checker; `python verify_py/test_mutations.py`;
and `python gen/mutation_test.py <verify binary> <proof>` against a real
proof file. The search workflow is in `docs/search.md`.

## License

Code: MIT (`LICENSE`). Proof files, data, documentation, and figures:
CC BY 4.0 (`LICENSE-DATA`).
