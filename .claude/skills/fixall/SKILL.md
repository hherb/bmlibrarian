---
name: fixall
description: Use when a code review has produced issues that need to be addressed and the pull request finalized on the bmlibrarian project.
disable-model-invocation: false
allowed-tools: Read, Edit, Bash(git add *), Bash(git commit *), Bash(git push *), Bash(git status *), Bash(git diff *), Bash(gh issue *), Bash(gh pr *), Bash(uv run pytest *), Bash(uv run python -m pytest *), Bash(ruff *), Bash(mypy *)

---

Address all issues identified in the code review one by one. If fixing them
appears manageable within this session, fix them now. If not, lodge the
issue on GitHub (`gh issue create`) — or, if it's a structural/architectural
concern rather than a discrete bug, add it to ROADMAP.md instead. Once all
issues have been addressed, run:

- `uv run python -m pytest tests/` (plus `ruff check .` and `mypy src/` —
  these two carry pre-existing debt; the gate is **no new errors**, not a
  clean run)
- If the PR touches `rust/`, also run from `rust/` what `.github/workflows/rust.yml` runs:
  `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` and `cargo test`
  (plus `cargo test -- --include-ignored` with `BML_TEST_PG_BINDIR` set when a local PG18 exists)

Then review the code changes thoroughly against CLAUDE.md ("golden rules"
section) and doc/llm/golden_rules.md. If satisfied no issues are left open,
update HANDOVER.md ONLY if necessary to reflect these changes. Then commit
and push the changes into the PR.
