---
name: finalcheck
description: final pre-merge pass on the current bmlibrarian PR — review, fix everything, then drive the GitHub checks to green
disable-model-invocation: false
allowed-tools: Bash(git *), Bash(gh *), Bash(uv *), Bash(ruff *), Bash(mypy *)
---
Run these steps in order on the PR for the current branch. Sessions here can span several `git worktree`s,
so first run `pwd && git branch --show-current && git worktree list` and `cd` into the PR's worktree (they
live under `.claude/worktrees/`). Then find the PR with `gh pr view --json number,url,headRefOid`. If there
is none, stop and tell me.

1. **Review.** Invoke the `pr-review-toolkit:review-pr` skill via the Skill tool and let it finish.
2. **Fix.** Invoke the `fixall` skill via the Skill tool on that review's findings. It runs the test suite,
   checks the golden rules and ends by committing and pushing into the PR. Before moving on, confirm the
   push landed: `git fetch origin && git status -sb` must show no `ahead`, and the PR's `headRefOid` must
   equal `git rev-parse HEAD`. Any edit to the baton goes into `HANDOVER.md`.
3. **Drive the checks to green.** Two sources of checks:
   - GitHub's default CodeQL setup: `Analyze (actions)`, `Analyze (python)`, `Analyze (rust)` (up to
     ~10 min) and the `CodeQL` summary.
   - `.github/workflows/rust.yml`, only when the PR touches `rust/**` or that file: `check (<os>)` on five
     runners (`cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, all from
     `rust/`) and `integration-linux`/`integration-macos` (`cargo test -- --include-ignored` against a
     real PG18). Each job can appear twice (push and pull_request runs); both must pass. Reproduce a
     failure locally with the failing step's command from `rust/`.

   Loop:
   - Watch the checks for the pushed head commit with `gh pr checks --watch --fail-fast`. Checks can take a
     minute to register, so wait if it reports none yet. `CodeQL` shows `skipping` until the analyses
     finish. That is normal, not a failure.
   - All green → done. Report the PR URL and the final check list. The `master` ruleset
     (`gh api repos/hherb/bmlibrarian/rules/branches/master`) only blocks deletion and force-pushes and
     requires no status checks, so "all green" means every check the PR reports passed.
     `branches/master/protection` returns 404 by design.
   - **CodeQL failed** → list the new alerts from the failing `CodeQL` check run's annotations (the
     code-scanning alerts API with `ref=refs/pull/<N>/merge` can return nothing even when alerts exist):
     take the run id from the `CodeQL` row's URL in `gh pr checks`, then
     `gh api repos/hherb/bmlibrarian/check-runs/<id>/annotations --jq '.[] | "\(.path):\(.start_line) \(.title) — \(.message)"'`.
     Fix the root cause in the code (golden rule 1: validate untrusted input). Use TDD where it is a code
     bug. Rerun the local gate (below), commit with a message naming the alert, push, and loop again.
   - **An `Analyze` job failed without alerts** (extraction/build error) → read it:
     `gh run list --branch "$(git branch --show-current)" --limit 5`, then `gh run view <run-id> --log-failed`.
   - If the failure is not caused by the code (runner/infra outage, network flake), rerun once with
     `gh run rerun <run-id> --failed`. If it fails the same way again, stop and report rather than changing
     code to work around it. The Actions API returns empty or stale data during an outage, so re-query
     before concluding a run never happened.
   - Never "fix" a check by dismissing or suppressing a CodeQL alert (`# codeql[...]`, `lgtm` comments,
     the dismiss API), by skipping, deleting or `xfail`-ing tests, or by adding entries to a guard or
     allowlist (`tests/test_llm_layer_boundary.py`, `src/bmlibrarian/db_test_guard.py`) without my explicit permission.
     Those lists may only shrink. If the same failure survives three fix attempts, stop and report what
     you tried.
4. **Not covered by CI.** No CI job runs the Python test suite, ruff or mypy, so the local gate is the
   real one for Python. If step 3 changed Python code, rerun it before the final push (if it changed only
   `rust/`, the `rust.yml` jobs cover it; still run `cargo fmt --check`, `cargo clippy --all-targets -- -D
   warnings` and `cargo test` from `rust/` before pushing):
   - `QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ -p no:cacheprovider --no-cov -q`. It takes
     7–17 min: run it in the background, save the full output to a file in the scratchpad, and don't edit
     or `git stash` the tree while it runs. Any failure is a regression.
   - `ruff check .` and `mypy src/` carry pre-existing debt; the gate is **no new errors**. Compare the
     counts against the PR's base commit.

   Judge each command by its **exit code** or the full saved output, never by filtered output:
   `cmd | tail` reports `tail`'s status. Include the local gate results in the report.
