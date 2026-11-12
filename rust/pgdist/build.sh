#!/usr/bin/env bash
# Build one pgdist bundle: PostgreSQL 18 (theseus-rs) + pgvector (from source)
# + pg_search (ParadeDB) where it exists, every input pinned in inputs.json.
#
#   bash rust/pgdist/build.sh <target>
#
# Output: rust/pgdist/out/bml-pgdist-<version>-<target>.tar.gz (+ .sha256).
# Needs curl, jq, tar, git and gh (for the attestation check), plus make, file,
# otool, xcrun and pkgutil on macOS; make, file, objdump, dpkg-deb and docker
# on Linux; nmake, cl, dumpbin and cygpath on Windows (Git Bash in an
# MSVC developer environment).
# Developer docs: doc/developers/pgdist.md.
set -euo pipefail

TARGET="${1:?usage: build.sh <target>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUTS="$HERE/inputs.json"
OUT="$HERE/out"
WORK="$OUT/work-$TARGET"
THESEUS_REPO="theseus-rs/postgresql-binaries"

die() { echo "build.sh: $*" >&2; exit 1; }

# jq -r without the carriage returns Windows' native jq.exe adds; -e makes a
# missing (null) value an error instead of the text "null".
jqr() { jq -er "$@" | tr -d '\r'; }

need() { for t in "$@"; do command -v "$t" >/dev/null 2>&1 || die "$t is needed"; done; }

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# Download $1 to $2 and refuse it unless its sha256 is $3.
fetch() {
  curl -fsSL --retry 3 -o "$2" "$1"
  local got; got="$(sha256_of "$2")"
  [ "$got" = "$3" ] || die "checksum mismatch for $1: expected $3, got $got"
}

# The minimum macOS version a Mach-O file was built for. awk reads all its
# input: exiting early could SIGPIPE otool under pipefail.
macho_minos() {
  otool -l "$1" | awk '/LC_BUILD_VERSION|LC_VERSION_MIN_MACOSX/ { b = 1 }
    b && !done && ($1 == "minos" || $1 == "version") { print $2; done = 1 }'
}

# Succeeds when version $1 is no newer than version $2.
version_le() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n 1)" = "$2" ]; }
# The OS-floor checks below rest on this ordering.
version_le 2.36 2.36 && version_le 2.4 2.36 && version_le 10.13 11.0 \
  && ! version_le 2.38 2.36 && ! version_le 11.0 10.13 || die "sort -V does not order versions"

need curl jq tar git gh
case "$TARGET" in
  *-apple-darwin) need make file otool xcrun pkgutil ;;
  *-linux-gnu) need make file objdump dpkg-deb docker ;;
  *-windows-msvc) need nmake cl dumpbin cygpath ;;
esac
jq -e --arg t "$TARGET" '.targets[$t]' "$INPUTS" >/dev/null || die "unknown target $TARGET"
VERSION="$(jqr .version "$INPUTS")"
NAME="bml-pgdist-$VERSION-$TARGET"
ROOT="$OUT/$NAME"
input() { jqr --arg t "$TARGET" ".targets[\$t]$1" "$INPUTS"; }
case "$TARGET" in *-linux-gnu) LINUX_IMAGE="$(jqr .linux_build.image "$INPUTS")" ;; esac

rm -rf "$WORK" "$ROOT"
mkdir -p "$WORK" "$ROOT/ext/lib/postgresql" "$ROOT/ext/share/postgresql/extension" "$ROOT/notices"

# --- PostgreSQL --------------------------------------------------------------
PG_ARCHIVE="$WORK/postgresql.tar.gz"
fetch "$(input .postgresql.url)" "$PG_ARCHIVE" "$(input .postgresql.sha256)"
gh attestation verify "$PG_ARCHIVE" --repo "$THESEUS_REPO" >/dev/null \
  || die "theseus build-provenance attestation did not verify"
mkdir -p "$WORK/pg"
tar -xzf "$PG_ARCHIVE" -C "$WORK/pg"
TOPS=("$WORK"/pg/*)
[ "${#TOPS[@]}" -eq 1 ] && [ -d "${TOPS[0]}" ] || die "expected one top-level folder in the PostgreSQL archive"
mv "${TOPS[0]}" "$ROOT/pg"
PG="$ROOT/pg"

# Prune what fresh installs never use: LLVM (the server runs with jit = off)
# and Python (fresh installs have no plpython3u).
find "$PG" \( -name 'libLLVM*' -o -name 'llvmjit*' -o -name '*plpython*' -o -name 'libpython*' \) -prune -exec rm -rf {} +
# lib/python3.* is the CPython standard library theseus ships with it.
rm -rf "$PG/lib/Python" "$PG"/lib/python3* "$PG/lib/bitcode" "$PG/lib/postgresql/bitcode"
# On Windows theseus copies a whole CPython into bin/ for plpython3u; bin/ is
# where Windows looks for DLLs, never bin/DLLs, so the server needs none of it.
case "$TARGET" in
  *-windows-msvc)
    rm -rf "$PG"/bin/python*.exe "$PG"/bin/python*.dll "$PG/bin/Lib" "$PG/bin/DLLs" "$PG/dependency-notices/python"
    # The globs match nothing if theseus renames its CPython; say so.
    ! compgen -G "$PG/bin/[Pp]ython*" >/dev/null || die "CPython is still in $PG/bin" ;;
esac

# --- pgvector (from source) --------------------------------------------------
PGV="$WORK/pgvector"
git clone -q --depth 1 --branch "$(jqr .pgvector.tag "$INPUTS")" "$(jqr .pgvector.repo "$INPUTS")" "$PGV"
[ "$(git -C "$PGV" rev-parse HEAD)" = "$(jqr .pgvector.commit "$INPUTS")" ] || die "pgvector tag does not match the pinned commit"
# On macOS and Linux, OPTFLAGS= drops pgvector's default -march=native, so it
# runs on any CPU of its architecture, not only ones like the build machine's
# (Makefile.win sets no such flag). Its dry run (make -n) is checked, so a
# future pgvector that stops honouring OPTFLAGS= fails the build instead of
# silently going back to -march=native, which the smoke test (same CPU as
# the build) would not notice.
PGV_DRY_RUN=make-n.txt
case "$TARGET" in
  *-windows-msvc)
    # MSVC's link.exe must come before Git's /usr/bin/link; nmake's switches
    # are written with '-' and path conversion is off, or Git Bash would turn
    # '/F' into a drive path.
    PATH="$(dirname "$(command -v cl)"):$PATH"
    (cd "$PGV" && PGROOT="$(cygpath -w "$PG")" MSYS_NO_PATHCONV=1 nmake -nologo -f Makefile.win)
    cp "$PGV/vector.dll" "$ROOT/ext/lib/postgresql/" ;;
  *-apple-darwin)
    # The bundle was configured --with-llvm and against the build machine's
    # SDK; build without bitcode, against this machine's SDK, for the oldest
    # macOS the PostgreSQL binaries run on (else the runner's own).
    MIN_OS="$(macho_minos "$PG/bin/postgres")"
    [ -n "$MIN_OS" ] || die "cannot read the minimum macOS version of $PG/bin/postgres"
    # bml refuses to install on an older macOS than inputs.json (and
    # pgdist-release.json) say, so a new theseus floor must be written there.
    [ "$MIN_OS" = "$(jqr .macos_build.min_os "$INPUTS")" ] \
      || die "$PG/bin/postgres needs macOS $MIN_OS; set macos_build.min_os in inputs.json (and requires.macos in pgdist-release.json) to it"
    MACOSX_DEPLOYMENT_TARGET="$MIN_OS" \
      make -n -C "$PGV" PG_CONFIG="$PG/bin/pg_config" with_llvm=no OPTFLAGS= PG_SYSROOT="$(xcrun --show-sdk-path)" >"$PGV/$PGV_DRY_RUN"
    MACOSX_DEPLOYMENT_TARGET="$MIN_OS" \
      make -C "$PGV" PG_CONFIG="$PG/bin/pg_config" with_llvm=no OPTFLAGS= PG_SYSROOT="$(xcrun --show-sdk-path)"
    cp "$PGV/vector.dylib" "$ROOT/ext/lib/postgresql/" ;;
  *)
    # In an old-glibc container: built against the runner's glibc (2.38 or
    # newer), pgvector would need it (_GNU_SOURCE turns strtol into
    # __isoc23_strtol@GLIBC_2.38). The files are handed back to this user.
    docker run --rm -v "$PG:$PG:ro" -v "$PGV:$PGV" -w "$PGV" "$LINUX_IMAGE" sh -c '
      apt-get update -qq && apt-get install -y -qq --no-install-recommends gcc make libc6-dev >/dev/null \
        && make -n PG_CONFIG="$1" with_llvm=no OPTFLAGS= >"$3" \
        && make PG_CONFIG="$1" with_llvm=no OPTFLAGS=
      status=$?; chown -R "$2" .; exit $status' sh "$PG/bin/pg_config" "$(id -u):$(id -g)" "$PGV_DRY_RUN"
    cp "$PGV/vector.so" "$ROOT/ext/lib/postgresql/" ;;
esac
if [ "${TARGET%-windows-msvc}" = "$TARGET" ]; then
  [ -s "$PGV/$PGV_DRY_RUN" ] || die "the pgvector dry run left no $PGV_DRY_RUN"
  ! grep -e '-march=native' "$PGV/$PGV_DRY_RUN" >/dev/null \
    || die "pgvector was built with -march=native: OPTFLAGS= no longer drops it"
fi
cp "$PGV/vector.control" "$PGV"/sql/vector--*.sql "$ROOT/ext/share/postgresql/extension/"
mkdir -p "$ROOT/notices/pgvector" && cp "$PGV/LICENSE" "$ROOT/notices/pgvector/"

# --- pg_search (ParadeDB release asset) ---------------------------------------
HAS_PG_SEARCH=false
# Plain jq -r: a null pg_search (no build for this target) yields no output.
KIND="$(jq -r --arg t "$TARGET" '.targets[$t].pg_search.kind // empty' "$INPUTS" | tr -d '\r')"
if [ -n "$KIND" ]; then
  HAS_PG_SEARCH=true
  ASSET="$WORK/pg_search.$KIND"
  fetch "$(input .pg_search.url)" "$ASSET" "$(input .pg_search.sha256)"
  EXT="$ROOT/ext/share/postgresql/extension"
  case "$KIND" in
    pkg)  # expanding a .pkg runs none of its scripts
      pkgutil --expand-full "$ASSET" "$WORK/pkg"
      cp "$WORK"/pkg/*/Payload/lib/postgresql/pg_search.dylib "$ROOT/ext/lib/postgresql/"
      cp "$WORK"/pkg/*/Payload/share/postgresql/extension/pg_search* "$EXT/" ;;
    deb)  # dpkg-deb -x runs no maintainer scripts
      dpkg-deb -x "$ASSET" "$WORK/deb"
      cp "$WORK/deb/usr/lib/postgresql/18/lib/pg_search.so" "$ROOT/ext/lib/postgresql/"
      cp "$WORK"/deb/usr/share/postgresql/18/extension/pg_search* "$EXT/" ;;
    *) die "unknown pg_search kind $KIND" ;;
  esac
  mkdir -p "$ROOT/notices/pg_search"
  fetch "$(jqr .pg_search_license.url "$INPUTS")" "$ROOT/notices/pg_search/LICENSE" "$(jqr .pg_search_license.sha256 "$INPUTS")"
  SOURCE="$(jqr .pg_search_source "$INPUTS")"
  printf 'pg_search is licensed under the GNU AGPL-3.0.\nThe exact source of this build: %s\n' \
    "$SOURCE" > "$ROOT/notices/pg_search/SOURCE.txt"
fi

# --- link checks over the whole bundle ---------------------------------------
# grep without -q reads all its input: under pipefail, grep -q quitting early
# can SIGPIPE the writer and turn a match into "no match".
case "$TARGET" in
  *-apple-darwin)
    while IFS= read -r f; do
      if file -b "$f" | grep 'Mach-O' >/dev/null; then
        deps="$(otool -L "$f")" || die "otool failed on $f"
        if tail -n +2 <<<"$deps" | grep -E 'LLVM|[Pp]ython' >/dev/null; then
          die "$f still links a pruned library"
        fi
        minos="$(macho_minos "$f")"
        [ -n "$minos" ] || die "cannot read the minimum macOS version of $f"
        version_le "$minos" "$MIN_OS" || die "$f needs macOS $minos, newer than the bundle's $MIN_OS"
      fi
    done < <(find "$PG/bin" "$PG/lib" "$ROOT/ext" -type f) ;;
  *-linux-gnu)
    GLIBC_FLOOR="$(jqr .linux_build.glibc "$INPUTS")"
    ELFS=()
    while IFS= read -r f; do
      if file -b "$f" | grep 'ELF' >/dev/null; then
        ELFS+=("$f")
        refs="$(objdump -p "$f")" || die "objdump failed on $f"
        # No GLIBC reference at all (a static file) needs no glibc.
        newest="$({ grep -o 'GLIBC_[0-9][0-9.]*' <<<"$refs" || true; } | sed 's/^GLIBC_//' | sort -uV | tail -n 1)"
        version_le "${newest:-0}" "$GLIBC_FLOOR" || die "$f needs glibc $newest, newer than the bundle's $GLIBC_FLOOR"
      fi
    done < <(find "$PG/bin" "$PG/lib" "$ROOT/ext" -type f)
    [ "${#ELFS[@]}" -gt 0 ] || die "no ELF files found in $ROOT"
    # Resolved on the oldest supported system, not the runner: its loader
    # reports a missing library and a too-new symbol version (GLIBC_*,
    # GLIBCXX_*) alike as "not found". ldd fails on a static file; only
    # "not found" counts.
    deps="$(docker run --rm -v "$ROOT:$ROOT:ro" "$LINUX_IMAGE" \
      sh -c 'for f; do echo "$f:"; ldd "$f" 2>&1 || :; done' sh "${ELFS[@]}")" \
      || die "running ldd in $LINUX_IMAGE failed"
    missing="$(awk '/:$/ { f = $0 } /not found/ { print f, $0 }' <<<"$deps")"
    [ -z "$missing" ] || die "libraries missing on glibc $GLIBC_FLOOR:"$'\n'"$missing" ;;
  *-windows-msvc)
    while IFS= read -r f; do
      out="$(dumpbin -nologo -dependents "$(cygpath -w "$f")")" || die "dumpbin failed on $f"
      if tr -d '\r' <<<"$out" | sed '/Dump of file/d' | grep -Ei 'LLVM|python' >/dev/null; then
        die "$f still links a pruned library"
      fi
    done < <(find "$PG/bin" "$PG/lib" "$ROOT/ext" -type f \( -iname '*.exe' -o -iname '*.dll' \)) ;;
esac

# --- contents manifest and archive -------------------------------------------
(
  cd "$ROOT"
  find . -type f ! -path ./pgdist.json | sed 's|^\./||' | LC_ALL=C sort | while IFS= read -r f; do
    size="$(wc -c < "$f" | tr -d ' ')"
    sum="$(sha256_of "$f")"
    printf '%s\t%s\t%s\n' "$f" "$size" "$sum"
  done > "$WORK/files.tsv"
  find . -type l | sed 's|^\./||' | LC_ALL=C sort | while IFS= read -r f; do
    printf '%s\t%s\n' "$f" "$(readlink "$f")"
  done > "$WORK/links.tsv"
)
jq -n --arg version "$VERSION" --arg target "$TARGET" --argjson pg_search "$HAS_PG_SEARCH" \
  --slurpfile inputs "$INPUTS" \
  --rawfile files "$WORK/files.tsv" --rawfile links "$WORK/links.tsv" '
  { schema_version: 1, version: $version, target: $target, pg_search: $pg_search,
    inputs: { postgresql: $inputs[0].targets[$target].postgresql,
              pgvector: $inputs[0].pgvector,
              pg_search: $inputs[0].targets[$target].pg_search },
    files: [ $files | split("\n")[] | select(length > 0) | split("\t")
             | { path: .[0], size: (.[1] | tonumber), sha256: .[2] } ],
    links: [ $links | split("\n")[] | select(length > 0) | split("\t")
             | { path: .[0], target: .[1] } ] }' > "$ROOT/pgdist.json"

ARCHIVE="$OUT/$NAME.tar.gz"
# COPYFILE_DISABLE: no AppleDouble ._* entries from macOS's tar.
COPYFILE_DISABLE=1 tar -czf "$ARCHIVE" -C "$OUT" "$NAME"
# The installer refuses an archive with anything beside the bundle folder.
stray="$(tar -tzf "$ARCHIVE" | { grep -Ev "^$NAME(/|\$)" || true; })"
[ -z "$stray" ] || die "unexpected entries in $ARCHIVE:"$'\n'"$stray"
echo "$(sha256_of "$ARCHIVE")  $NAME.tar.gz" > "$ARCHIVE.sha256"
rm -rf "$WORK"
echo "built $ARCHIVE (pg_search: $HAS_PG_SEARCH)"
