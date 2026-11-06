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
3. **Drive the checks to green.** This repo has no workflows in `.github/workflows/`. The only checks are
   GitHub's default CodeQL setup: `Analyze (python)`, `Analyze (rust)` (the crates under `spikes/`, up to
   ~10 min) and the `CodeQL` summary. Loop:
   - Watch the checks for the pushed head commit with `gh pr checks --watch --fail-fast`. Checks can take a
     minute to register, so wait if it reports none yet. `CodeQL` shows `skipping` until the analyses
     finish. That is normal, not a failure.
   - All green → done. Report the PR URL and the final check list. The `master` ruleset
     (`gh api repos/hherb/bmlibrarian/rules/branches/master`) only blocks deletion and force-pushes and
     requires no status checks, so "all green" means every check the PR reports passed.
     `branches/master/protection` returns 404 by design.
   - **CodeQL failed** → list the PR's open alerts:
     `gh api "repos/hherb/bmlibrarian/code-scanning/alerts?ref=refs/pull/<N>/merge&state=open" --jq '.[] | "\(.rule.id) \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line) \(.rule.description)"'`.
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
4. **Not covered by CI.** No CI job runs the test suite, ruff or mypy, so the local gate is the real one.
   If step 3 changed any code, rerun it before the final push:
   - `QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ -p no:cacheprovider --no-cov -q`. It takes
     7–17 min: run it in the background, save the full output to a file in the scratchpad, and don't edit
     or `git stash` the tree while it runs. Any failure is a regression.
   - `ruff check .` and `mypy src/` carry pre-existing debt; the gate is **no new errors**. Compare the
     counts against the PR's base commit.

   Judge each command by its **exit code** or the full saved output, never by filtered output:
   `cmd | tail` reports `tail`'s status. Include the local gate results in the report.
