---
name: nextsession
description: Use when starting or resuming a work session on the bmlibrarian project, to load current project state and re-establish the coding rules and session workflow before doing any work.
disable-model-invocation: true
allowed-tools: Read, Edit, Bash(git add *), Bash(git commit *), Bash(git push *), Bash(git status *), Bash(git diff *), Bash(gh issue *), Bash(gh pr *), Bash(uv run pytest *), Bash(uv run python -m pytest *), Bash(ruff *), Bash(mypy *)

---

read HANDOVER.md and follow the instructions. Ask me if you have any questions.

Our coding rules live in CLAUDE.md ("golden rules" section) and
doc/llm/golden_rules.md — read and honour both before making changes. On
top of those, follow this session workflow:

1. All tests must pass before committing, unless I explicitly give
   permission otherwise: `uv run python -m pytest tests/`. `ruff check .`
   and `mypy src/` carry pre-existing debt — the gate for those is **no new
   errors**, not a clean run.
2. Before you start working, make sure HANDOVER.md represents the current
   state of progress and is up to date. If not, update it before you start.
3. Avoid technical debt — if you find an error, fix it when possible;
   otherwise lodge it as an issue on GitHub (`gh issue create`), or add it
   to ROADMAP.md if it's structural rather than a discrete bug.
4. Never modify or drop the production database `knowledgebase`. Use
   `bmlibrarian_dev` for any migration/testing work that touches schema.
5. When you are done, update HANDOVER.md to reflect the current state of
   development and progress. Prune it to stay concise and under 500 lines
   if possible: remove sections for slices that have landed, focus on what
   still needs doing, and summarise briefly what has already been done. If
   a "Next up" item turns out to be a bigger structural change than
   expected, move it to ROADMAP.md instead of letting it bloat HANDOVER. If
   you are not sure how to do this, ask me.
6. When the task is complete, commit all changes, push, and open a PR to
   the master branch. Link the PR to the relevant GitHub issue if
   applicable, and include a clear description of the changes made and any
   relevant context for reviewers. If you are not sure how to do this, ask
   me.
