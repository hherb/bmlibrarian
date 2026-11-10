#!/usr/bin/env bash
# Build one pgdist bundle: PostgreSQL 18 (theseus-rs) + pgvector (from source)
# + pg_search (ParadeDB) where it exists, every input pinned in inputs.json.
#
#   bash rust/pgdist/build.sh <target>
#
# Output: rust/pgdist/out/bml-pgdist-<version>-<target>.tar.gz (+ .sha256).
# Needs curl, jq, tar, git, gh (for the attestation check), and make, or nmake
# on Windows (run from an MSVC developer environment). Runs on macOS, Linux
# and Git Bash on Windows. Developer docs: doc/developers/pgdist.md.
set -euo pipefail

TARGET="${1:?usage: build.sh <target>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUTS="$HERE/inputs.json"
OUT="$HERE/out"
WORK="$OUT/work-$TARGET"
THESEUS_REPO="theseus-rs/postgresql-binaries"

die() { echo "build.sh: $*" >&2; exit 1; }

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

jq -e --arg t "$TARGET" '.targets[$t]' "$INPUTS" >/dev/null || die "unknown target $TARGET"
VERSION="$(jq -r .version "$INPUTS")"
NAME="bml-pgdist-$VERSION-$TARGET"
ROOT="$OUT/$NAME"
input() { jq -r --arg t "$TARGET" ".targets[\$t]$1" "$INPUTS"; }

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
rm -rf "$PG/lib/Python" "$PG/lib/bitcode" "$PG/lib/postgresql/bitcode"

case "$TARGET" in
  *-apple-darwin)
    while IFS= read -r f; do
      if file -b "$f" | grep -q 'Mach-O'; then
        if otool -L "$f" | tail -n +2 | grep -Eq 'LLVM|[Pp]ython'; then
          die "$f still links a pruned library"
        fi
      fi
    done < <(find "$PG/bin" "$PG/lib" -type f) ;;
  *-linux-gnu)
    while IFS= read -r f; do
      if file -b "$f" | grep -q 'ELF'; then
        if ldd "$f" 2>/dev/null | grep -q 'not found'; then die "$f has a missing library"; fi
      fi
    done < <(find "$PG/bin" "$PG/lib" -type f) ;;
esac

# --- pgvector (from source) --------------------------------------------------
PGV="$WORK/pgvector"
git clone -q --depth 1 --branch "$(jq -r .pgvector.tag "$INPUTS")" "$(jq -r .pgvector.repo "$INPUTS")" "$PGV"
[ "$(git -C "$PGV" rev-parse HEAD)" = "$(jq -r .pgvector.commit "$INPUTS")" ] || die "pgvector tag does not match the pinned commit"
case "$TARGET" in
  *-windows-msvc)
    (cd "$PGV" && PGROOT="$(cygpath -w "$PG")" nmake /nologo /F Makefile.win)
    cp "$PGV/vector.dll" "$ROOT/ext/lib/postgresql/" ;;
  *-apple-darwin)
    # The bundle was configured --with-llvm and against the build machine's
    # SDK; build without bitcode and against this machine's SDK.
    make -C "$PGV" PG_CONFIG="$PG/bin/pg_config" with_llvm=no PG_SYSROOT="$(xcrun --show-sdk-path)"
    cp "$PGV/vector.dylib" "$ROOT/ext/lib/postgresql/" ;;
  *)
    make -C "$PGV" PG_CONFIG="$PG/bin/pg_config" with_llvm=no
    cp "$PGV/vector.so" "$ROOT/ext/lib/postgresql/" ;;
esac
cp "$PGV/vector.control" "$PGV"/sql/vector--*.sql "$ROOT/ext/share/postgresql/extension/"
mkdir -p "$ROOT/notices/pgvector" && cp "$PGV/LICENSE" "$ROOT/notices/pgvector/"

# --- pg_search (ParadeDB release asset) ---------------------------------------
HAS_PG_SEARCH=false
KIND="$(input '.pg_search.kind // empty')"
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
  fetch "$(jq -r .pg_search_license.url "$INPUTS")" "$ROOT/notices/pg_search/LICENSE" "$(jq -r .pg_search_license.sha256 "$INPUTS")"
  printf 'pg_search is licensed under the GNU AGPL-3.0.\nThe exact source of this build: %s\n' \
    "$(jq -r .pg_search_source "$INPUTS")" > "$ROOT/notices/pg_search/SOURCE.txt"
fi

# --- contents manifest and archive -------------------------------------------
(
  cd "$ROOT"
  find . -type f ! -path ./pgdist.json | sed 's|^\./||' | LC_ALL=C sort | while IFS= read -r f; do
    printf '%s\t%s\t%s\n' "$f" "$(wc -c < "$f" | tr -d ' ')" "$(sha256_of "$f")"
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
tar -czf "$ARCHIVE" -C "$OUT" "$NAME"
echo "$(sha256_of "$ARCHIVE")  $NAME.tar.gz" > "$ARCHIVE.sha256"
rm -rf "$WORK"
echo "built $ARCHIVE (pg_search: $HAS_PG_SEARCH)"
