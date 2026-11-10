# pgdist: the bundled PostgreSQL

`bml setup` installs a private PostgreSQL 18 from **pgdist**, BMLibrarian's own
bundle of PostgreSQL + pgvector + (where it exists) pg_search. It is built
by a GitHub workflow from pinned upstream inputs and published as a GitHub
Release of this repository, so installs never depend on the upstream
projects' download servers. Design:
`docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`
(Goal A).

## Sources and why

| Piece | Source | Why |
|---|---|---|
| PostgreSQL 18.6 | [theseus-rs/postgresql-binaries](https://github.com/theseus-rs/postgresql-binaries) release `18.6.1` | Relocatable (`@loader_path`), self-contained, ships `pg_config` and server headers. Each tarball has a `.sha256` and a GitHub build-provenance attestation. `build-manifest.json` inside records the upstream tag and commit (`REL_18_6`) and the configure flags. PostgreSQL licence. |
| pgvector 0.8.7 | built from source (tag `v0.8.7`, commit pinned) | pgvector publishes no binaries. A small C build. |
| pg_search 0.26.6 | ParadeDB release assets: macOS `pg_search-pg18-0.26.6.pkg` (the Postgres.app package), Linux `…-bookworm_{amd64,arm64}.deb` | The macOS dylib is arm64-only and links only system libraries, so it loads into any PostgreSQL 18. AGPL-3.0. |

There is no pg_search for Intel Macs or Windows: ParadeDB ships no build for
them. Those bundles carry pgvector only, and BMLibrarian uses PostgreSQL's
built-in text search there.

**Rejected:**
- building pg_search with pgrx (a heavy toolchain to keep current)
- Zonky's embedded binaries (no extensions)
- EDB (Windows installers only)
- Homebrew bottles (hard-coded paths)
- repackaging Postgres.app

**Risk:** theseus is essentially one maintainer. The release copy covers an
outage. Its build scripts are open source under the PostgreSQL licence, so
they can be forked if the project is abandoned.

## Files

| File | Role |
|---|---|
| `rust/pgdist/inputs.json` | Every input, pinned: theseus URL and sha256 per target, the pgvector tag and commit, the pg_search asset URL and sha256 per target (`null` = none), and the pg_search licence text and sha256 |
| `rust/pgdist/build.sh <target>` | Builds one bundle into `rust/pgdist/out/` (git-ignored) |
| `.github/workflows/pgdist.yml` | Runs the build on five runners, smoke-tests each bundle, and publishes the release (manual run with `publish=true`) |
| `rust/bml-setup/pgdist-release.json` | What `bml` installs: release base URL and, per target, the asset file, size and sha256 |
| `rust/bml-setup/src/pgdist.rs` | Download, verify and atomic install (`ensure_pgdist`) |

## What `build.sh` does

1. Downloads the theseus tarball and checks its sha256. Runs
   `gh attestation verify … --repo theseus-rs/postgresql-binaries`.
2. Unpacks it as `pg/`, then prunes `libLLVM*`, `llvmjit*`, the bundled
   Python and every `*plpython*` file. The server runs with `jit = off`
   (`bml-pgserver` writes it into `bml.conf`), and fresh installs have no
   `plpython3u`. On macOS and Linux it fails if anything left links a
   pruned library.
3. Clones pgvector at the tag, checks the pinned commit, and builds it
   against `pg/bin/pg_config`:
   - macOS/Linux: `make … with_llvm=no`, because theseus was configured
     `--with-llvm`. On macOS also `PG_SYSROOT=$(xcrun --show-sdk-path)`,
     because theseus recorded its build runner's SDK path.
   - Windows: `nmake /F Makefile.win` with `PGROOT`, from an MSVC
     developer shell.
4. Downloads pg_search, checks its sha256, and extracts it without running
   package scripts: `pkgutil --expand-full` for the `.pkg`, `dpkg-deb -x`
   for the `.deb`.
5. Copies the licence notices, and writes `notices/pg_search/SOURCE.txt`
   linking the exact pg_search source.
6. Writes `pgdist.json`: version, target, inputs, `pg_search` flag, and
   every file with size and sha256, plus symlinks.
7. Packs `bml-pgdist-<version>-<target>.tar.gz` with a `.sha256` beside it.

## Bundle layout

```
bml-pgdist-18.6-r1-<target>/
  pgdist.json
  pg/                      pruned theseus tree; bin folder pg/bin
  ext/lib/postgresql/      vector.{dylib,so,dll}, pg_search.* where present
  ext/share/postgresql/extension/   vector.control, vector--*.sql, pg_search*
  notices/                 pgvector/, pg_search/ (theseus notices stay in pg/)
```

`ext/` uses the extension-folder layout `bml-pgserver` already understands
(`dynamic_library_path`, `extension_control_path`), so `init` gets
`bindir = pg/bin` and `extension_dirs = [ext]`.

## Building and testing locally

```
bash rust/pgdist/build.sh aarch64-apple-darwin     # needs curl jq tar git gh make
cd rust
R=$PWD/pgdist/out/bml-pgdist-18.6-r1-aarch64-apple-darwin
BML_TEST_PG_BINDIR=$R/pg/bin BML_TEST_PG_EXTENSION_DIRS=$R/ext cargo test -- --include-ignored
```

The smoke test `bml-pgserver/tests/extensions.rs` runs a `halfvec` HNSW
query, and a BM25 query when pg_search is present. On Windows the workflow
runs only that test, because the rest of the ignored suite is not yet
verified there (#397).

## Releasing

1. Pull requests that touch `rust/pgdist/**` or the workflow build and
   smoke-test all five targets. They never publish.
2. After merge, run the `pgdist` workflow by hand with `publish=true`. It
   creates the release `pgdist-<version>` with the five tarballs and their
   `.sha256` files. The notes list every input and link the pg_search
   source.
3. Copy each asset's size and sha256 from the published release
   (`gh release view pgdist-<version> --json assets`), not from a local build,
   into `rust/bml-setup/pgdist-release.json`. Then commit.

## Bumping an input

Change the pins in `inputs.json`. Fetch the values, never guess them:
- theseus: the `.sha256` release asset
- ParadeDB: `gh release view … --json assets` (`digest`)
- pgvector: `gh api repos/pgvector/pgvector/git/ref/tags/<tag>`

Then raise `version` to the next `-rN`, or a new PostgreSQL minor
(`18.7-r1`). The new version installs side by side in
`<config>/pgdist/<version>/`.

An existing private server keeps the binaries it was set up with:
`bml-pgserver.json` records its bin folder. Moving an existing data folder
to a new major version (`pg_upgrade`) or pg_search version is later work.

## Signing (macOS)

The bundle is unsigned. Its binaries run as downloaded because macOS does
not quarantine files a program downloads itself, and arm64 binaries carry
the linker's ad-hoc signature. When the app bundles pgdist (piece 5 of the
design), the owner's release script signs every Mach-O file with the
Developer ID and hardened runtime, pg_search's ParadeDB signature included.
