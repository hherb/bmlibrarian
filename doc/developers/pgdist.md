# pgdist: the bundled PostgreSQL

`bml setup` installs a private PostgreSQL 18 from **pgdist**, BMLibrarian's own
bundle of PostgreSQL + pgvector + (where it exists) pg_search. It is built
by a GitHub workflow from pinned upstream inputs and published as a GitHub
Release of this repository, so installs never depend on the upstream
projects' download servers. Until the first release is published and pinned
(Releasing, step 3), `pgdist-release.json` lists no assets and the bundled
default fails with a pointer to `--pg-bindir`/`--existing-server`. Design:
`docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`
(Goal A).

## Sources and why

| Piece | Source | Why |
|---|---|---|
| PostgreSQL 18.6 | [theseus-rs/postgresql-binaries](https://github.com/theseus-rs/postgresql-binaries) release `18.6.1` | Relocatable (`@loader_path`), self-contained, ships `pg_config` and server headers. Each tarball has a `.sha256` and a GitHub build-provenance attestation. `build-manifest.json` inside records the upstream tag and commit (`REL_18_6`) and the configure flags. PostgreSQL licence. |
| pgvector 0.8.7 | built from source (tag `v0.8.7`, commit pinned) | pgvector publishes no binaries. A small C build. |
| pg_search 0.26.6 | ParadeDB release assets: macOS `pg_search-pg18-0.26.6.pkg` (the Postgres.app package), Linux `…-bookworm_{amd64,arm64}.deb` | The macOS dylib is arm64-only and links only system libraries, so it loads into any PostgreSQL 18. AGPL-3.0. |

There is no pg_search for Intel Macs or Windows: ParadeDB ships no build for
them. Those bundles carry pgvector only; the Rust side's fallback to
PostgreSQL's built-in text search there is planned work (design piece 2).

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
2. Unpacks it as `pg/`, then prunes `libLLVM*`, `llvmjit*`, `libpython*`,
   the bundled Python, `lib/bitcode`, `lib/postgresql/bitcode` and every
   `*plpython*` file; on Windows also the CPython theseus copies into `bin/`
   (`python*.exe`, `python*.dll`, `bin/Lib`, `bin/DLLs`) and its notice. The server runs with `jit = off` (`bml-pgserver`
   writes it into `bml.conf`), and fresh installs have no `plpython3u`.
3. Clones pgvector at the tag, checks the pinned commit, and builds it
   against `pg/bin/pg_config`, always with `OPTFLAGS=` (pgvector's default
   is `-march=native`, which would tie the bundle to CPUs like the build
   runner's and crash with "illegal instruction" on older ones):
   - macOS/Linux: `make … with_llvm=no`, because theseus was configured
     `--with-llvm`.
   - macOS also: `PG_SYSROOT=$(xcrun --show-sdk-path)`, because theseus
     recorded its build runner's SDK path, and `MACOSX_DEPLOYMENT_TARGET`
     set to the minimum macOS of `pg/bin/postgres` (else the dylib would
     need the runner's own macOS).
   - Linux: inside the `linux_build.image` container (Debian bookworm,
     pinned by digest), not on the runner. Built against the runner's glibc
     (2.39), pgvector would need glibc 2.38: PGXS passes `-D_GNU_SOURCE`,
     which since glibc 2.38 turns `strtol` into `__isoc23_strtol@GLIBC_2.38`.
   - Windows: `nmake -nologo -f Makefile.win` with `PGROOT` (a Windows
     path) and `MSYS_NO_PATHCONV=1`, from an MSVC developer shell with
     MSVC's `cl`/`link.exe` folder first on `PATH` (Git Bash would otherwise
     find its own `/usr/bin/link` and turn `/F` into a drive path).
4. Where `inputs.json` has a pg_search entry, downloads it, checks its sha256, and extracts it without running
   package scripts: `pkgutil --expand-full` for the `.pkg`, `dpkg-deb -x`
   for the `.deb`.
5. Checks every binary in `pg/` and `ext/`. On macOS: nothing links a
   pruned library, and none needs a newer macOS than `pg/bin/postgres`. On
   Linux: `ldd` reports no missing library, and no file needs a glibc newer
   than `linux_build.glibc` (from `objdump -p`). On Windows: `dumpbin
   -dependents` shows no LLVM or Python DLL.
6. Copies the licence notices, and writes `notices/pg_search/SOURCE.txt`
   linking the exact pg_search source.
7. Writes `pgdist.json`: version, target, inputs, `pg_search` flag, and
   every file with size and sha256, plus symlinks.
8. Packs `bml-pgdist-<version>-<target>.tar.gz` (`COPYFILE_DISABLE=1`, so
   no macOS `._*` entries) with a `.sha256` beside it.

## What the bundles need

| Target | Needs |
|---|---|
| macOS (arm64, Intel) | the minimum macOS of theseus's binaries: 15.0 for 18.6.1 |
| Linux (x86_64, arm64) | glibc 2.36 or newer (`linux_build.glibc`): Debian 12, Ubuntu 23.04, Fedora 37, RHEL 10 or later. Not Ubuntu 22.04 (2.35) or RHEL 9 (2.34): the libraries theseus ships (`libstdc++`, `libcrypt`, `libexpat`) already need 2.36, as does the bookworm pg_search. No musl bundle. |
| Windows (x86_64) | what theseus's build needs; not checked yet (#397) |

Any CPU of the architecture: pgvector is built without `-march=native`.

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
bash rust/pgdist/build.sh aarch64-apple-darwin     # tools: see the script's header
cd rust
R=$PWD/pgdist/out/bml-pgdist-18.6-r1-aarch64-apple-darwin
BML_TEST_PG_BINDIR=$R/pg/bin BML_TEST_PG_EXTENSION_DIRS=$R/ext cargo test -- --include-ignored
```

The smoke test `bml-pgserver/tests/extensions.rs` runs a `halfvec` HNSW
query, and a BM25 query when pg_search is present. On Windows the workflow
runs only that test, because the rest of the ignored suite is not yet
verified there (#397).

## Releasing

1. Pull requests that touch `rust/pgdist/**`, `rust/bml-pgserver/**` or the
   workflow build all five targets and smoke-test each published archive,
   unpacked outside the build folder. They never publish.
2. After merge, run the `pgdist` workflow by hand with `publish=true` on
   `master` (the publish job refuses any other branch). It
   creates the release `pgdist-<version>` with the five tarballs and their
   `.sha256` files. The notes list every input and link the pg_search
   source.
3. Copy each asset's size and sha256 from the published release
   (`gh release view pgdist-<version> --json assets`), not from a local build,
   into `rust/bml-setup/pgdist-release.json`, keyed by target, with `file`
   `bml-pgdist-<version>-<target>.tar.gz`. Its `version` must equal
   `inputs.json`'s and its `base_url` must be
   `…/releases/download/pgdist-<version>/` (the test
   `bundled_release_is_well_formed` checks both). Then commit.

## Bumping an input

Change the pins in `inputs.json`. Fetch the values, never guess them:
- theseus: the `.sha256` release asset
- ParadeDB: `gh release view … --json assets` (`digest`)
- pgvector: `gh api repos/pgvector/pgvector/git/ref/tags/<tag>`

Then raise `version` to the next `-rN`, or a new PostgreSQL minor
(`18.7-r1`), in `inputs.json` and `pgdist-release.json` together (with
`base_url`; assets follow once the new release is published, Releasing
step 3). The new version installs side by side in
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
