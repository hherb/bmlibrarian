#!/bin/bash
#
# Build the macOS DMG installer for BMLibrarian V2 (the Rust/Tauri app in rust/).
#
# Usage:
#   scripts/build_bmlibrarianV2_installer.sh             # Developer ID sign + notarize + staple
#   scripts/build_bmlibrarianV2_installer.sh --unsigned  # ad-hoc signed, for local testing only
#
# The app bundle carries the `bml` program beside `bml-app` (Contents/MacOS/bml): setup's
# start-at-login entry and the update schedule run it (see doc/developers/bml_app.md).
#
# Signing uses DEVELOPER_ID (default: the first "Developer ID Application" identity in the
# Keychain). Notarization uses the notarytool Keychain profile NOTARY_PROFILE (default
# "bmlibrarian-notarize", shared with BMLibrarian Lite; create it with
# `xcrun notarytool store-credentials`).
#
# Output: rust/target/release/bundle/dmg/BMLibrarian_<version>_<arch>.dmg

set -euo pipefail

SIGN=true
for arg in "$@"; do
    case "$arg" in
        --unsigned) SIGN=false ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

[ "$(uname)" = "Darwin" ] || { echo "Error: macOS only." >&2; exit 1; }
command -v cargo-tauri >/dev/null || cargo tauri --version >/dev/null 2>&1 || {
    echo "Error: tauri-cli missing (cargo install tauri-cli --version '^2')." >&2; exit 1; }

RUST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../rust" && pwd)"
NOTARY_PROFILE="${NOTARY_PROFILE:-bmlibrarian-notarize}"

if [ "$SIGN" = true ]; then
    if [ -z "${DEVELOPER_ID:-}" ]; then
        DEVELOPER_ID=$(security find-identity -v -p codesigning \
            | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)".*/\1/' || true)
    fi
    [ -n "${DEVELOPER_ID:-}" ] || {
        echo "Error: no Developer ID Application certificate; set DEVELOPER_ID or use --unsigned." >&2
        exit 1; }
    # Fail before a long build rather than after it.
    xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1 || {
        echo "Error: notarytool Keychain profile '$NOTARY_PROFILE' not found." >&2
        echo "  xcrun notarytool store-credentials \"$NOTARY_PROFILE\" --apple-id ... --team-id ... --password ..." >&2
        exit 1; }
    IDENTITY="$DEVELOPER_ID"
else
    IDENTITY="-"
fi

TRIPLE=$(rustc -vV | sed -n 's/^host: //p')
SIDECAR_DIR=$(mktemp -d)
trap 'rm -rf "$SIDECAR_DIR"' EXIT

cd "$RUST_DIR"
echo "=== Building bml (release, $TRIPLE) ==="
cargo build --release -p bml-cli
# Tauri's externalBin wants "<name>-<target triple>" and installs it as Contents/MacOS/<name>.
cp target/release/bml "$SIDECAR_DIR/bml-$TRIPLE"

DMG_DIR="$RUST_DIR/target/release/bundle/dmg"
rm -rf "$DMG_DIR"

echo "=== Building the app and DMG (signing identity: $IDENTITY) ==="
# The committed tauri.conf.json keeps bundling off so dev builds stay fast; enable it here.
CONFIG=$(printf '{"bundle":{"active":true,"externalBin":["%s/bml"],"macOS":{"signingIdentity":"%s"}}}' \
    "$SIDECAR_DIR" "$IDENTITY")
tauri_dmg() {
    # Tauri notarizes only from APPLE_* variables; unset them so notarization happens once, below.
    # --verbose: without it a bundle_dmg.sh failure shows no reason.
    (cd bml-app && env -u APPLE_ID -u APPLE_PASSWORD -u APPLE_API_KEY \
        cargo tauri build --verbose --bundles dmg --config "$CONFIG")
}
detach_leftover_images() {
    # A failed bundle_dmg.sh leaves its read-write image (bundle/macos/rw.*.dmg) mounted.
    hdiutil info | awk '/^image-path/ { img = $0; sub(/^image-path *: */, "", img) } /^\/dev\/disk[0-9]+[ \t]/ && img ~ /bundle\/macos\/rw\./ { print $1; img = "" }' \
        | while read -r dev; do hdiutil detach "$dev" -force -quiet || true; done
}
detach_leftover_images
# bundle_dmg.sh's Finder AppleScript fails now and then ("Can't get disk"); one retry.
if ! tauri_dmg; then
    echo "=== DMG step failed; retrying once ==="
    detach_leftover_images
    rm -rf "$DMG_DIR"
    tauri_dmg
fi

DMGS=("$DMG_DIR"/*.dmg)
[ ${#DMGS[@]} -eq 1 ] && [ -f "${DMGS[0]}" ] || { echo "Error: expected one DMG in $DMG_DIR." >&2; exit 1; }
DMG="${DMGS[0]}"

if [ "$SIGN" = true ]; then
    echo "=== Signing the DMG ==="
    codesign --force --timestamp --sign "$DEVELOPER_ID" "$DMG"
    echo "=== Notarizing (several minutes) ==="
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait \
        | tee "$SIDECAR_DIR/notary.log"
    grep -q "status: Accepted" "$SIDECAR_DIR/notary.log" || {
        echo "Error: notarization not accepted; see: xcrun notarytool log <id> --keychain-profile $NOTARY_PROFILE" >&2
        exit 1; }
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
    spctl --assess --type open --context context:primary-signature --verbose "$DMG"
fi

hdiutil verify "$DMG" >/dev/null
echo ""
echo "DMG: $DMG ($(du -h "$DMG" | cut -f1))"
[ "$SIGN" = true ] || echo "Unsigned build: other Macs need right-click > Open the first time."
