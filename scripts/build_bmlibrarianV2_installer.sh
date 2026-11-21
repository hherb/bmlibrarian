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
# Output: <cargo target dir>/release/bundle/dmg/BMLibrarian_<version>_<arch>.dmg (with
# --unsigned: ..._unsigned.dmg), where the target dir is CARGO_TARGET_DIR if set, else
# rust/target. Until every check has passed the DMG is named ....incomplete.dmg, so a failed
# run never leaves one under the release name. The build log is kept as
# bundle/installer-build.log, the notarization log as bundle/dmg/notary.log.

set -euo pipefail

SIGN=true
for arg in "$@"; do
    case "$arg" in
        --unsigned) SIGN=false ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

[ "$(uname)" = "Darwin" ] || { echo "Error: macOS only." >&2; exit 1; }
cargo tauri --version 2>/dev/null | grep -q '^tauri-cli 2\.' || {
    echo "Error: tauri-cli 2 missing (cargo install tauri-cli --version '^2')." >&2; exit 1; }

RUST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../rust" && pwd)"
# cargo and cargo-tauri both build into CARGO_TARGET_DIR when it is set; resolve it once, as an
# absolute path (a relative one is taken from the current folder), so every path below agrees.
TARGET_DIR="${CARGO_TARGET_DIR:-$RUST_DIR/target}"
mkdir -p "$TARGET_DIR"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
export CARGO_TARGET_DIR="$TARGET_DIR"
BUNDLE_DIR="$TARGET_DIR/release/bundle"
DMG_DIR="$BUNDLE_DIR/dmg"
NOTARY_PROFILE="${NOTARY_PROFILE:-bmlibrarian-notarize}"

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

if [ "$SIGN" = true ]; then
    if [ -z "${DEVELOPER_ID:-}" ]; then
        DEVELOPER_ID=$(security find-identity -v -p codesigning \
            | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)".*/\1/' || true)
    fi
    [ -n "${DEVELOPER_ID:-}" ] || {
        echo "Error: no Developer ID Application certificate; set DEVELOPER_ID or use --unsigned." >&2
        exit 1; }
    # Fail before a long build rather than after it. A test signature catches a wrong name, an
    # expired certificate, a locked keychain and an unreachable timestamp server.
    touch "$WORK_DIR/probe"
    if ! out=$(codesign --force --timestamp --sign "$DEVELOPER_ID" "$WORK_DIR/probe" 2>&1); then
        echo "Error: cannot sign with '$DEVELOPER_ID':" >&2
        echo "$out" >&2
        exit 1
    fi
    if ! out=$(xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" 2>&1); then
        echo "Error: notarytool cannot use the Keychain profile '$NOTARY_PROFILE':" >&2
        echo "$out" >&2
        echo "If the profile is missing, create it:" >&2
        echo "  xcrun notarytool store-credentials \"$NOTARY_PROFILE\" --apple-id ... --team-id ... --password ..." >&2
        exit 1
    fi
    IDENTITY="$DEVELOPER_ID"
else
    IDENTITY="-"
fi

TRIPLE=$(rustc -vV | sed -n 's/^host: //p')

cd "$RUST_DIR"
echo "=== Building bml (release, $TRIPLE) ==="
cargo build --release -p bml-cli
# Tauri's externalBin wants "<name>-<target triple>" and installs it as Contents/MacOS/<name>.
cp "$TARGET_DIR/release/bml" "$WORK_DIR/bml-$TRIPLE"

rm -rf "$DMG_DIR"

echo "=== Building the app and DMG (signing identity: $IDENTITY) ==="
# The committed tauri.conf.json keeps bundling off so dev builds stay fast; enable it here.
CONFIG=$(printf '{"bundle":{"active":true,"externalBin":["%s/bml"],"macOS":{"signingIdentity":"%s"}}}' \
    "$WORK_DIR" "$IDENTITY")
BUILD_LOG="$BUNDLE_DIR/installer-build.log"
tauri_dmg() {
    # Tauri notarizes only from APPLE_ID/APPLE_API_KEY variables, and APPLE_SIGNING_IDENTITY or
    # APPLE_CERTIFICATE (say, left over from a BMLibrarian Lite build) would override the identity
    # chosen above; unset them all so signing follows $IDENTITY and notarization happens once, below.
    # --verbose: without it a bundle_dmg.sh failure shows no reason.
    mkdir -p "$BUNDLE_DIR"
    (cd bml-app && env -u APPLE_ID -u APPLE_PASSWORD -u APPLE_API_KEY \
        -u APPLE_SIGNING_IDENTITY -u APPLE_CERTIFICATE -u APPLE_CERTIFICATE_PASSWORD \
        cargo tauri build --verbose --bundles dmg --config "$CONFIG") 2>&1 | tee "$BUILD_LOG"
}
mkdir -p "$BUNDLE_DIR"
# hdiutil reports resolved paths (/private/tmp, not /tmp).
RW_PREFIX="$(cd "$BUNDLE_DIR" && pwd -P)/macos/rw."
detach_leftover_images() {
    # A failed bundle_dmg.sh leaves its read-write image (bundle/macos/rw.*.dmg) mounted. Only
    # this build's: another project's DMG build may be running.
    hdiutil info | awk -v prefix="$RW_PREFIX" '/^image-path/ { img = $0; sub(/^image-path *: */, "", img) } /^\/dev\/disk[0-9]+[ \t]/ && index(img, prefix) == 1 { print $1; img = "" }' \
        | while read -r dev; do
            hdiutil detach "$dev" -force || echo "Warning: could not detach $dev (a leftover DMG image)." >&2
        done
    rm -f "$BUNDLE_DIR"/macos/rw.*.dmg
}
detach_leftover_images
rm -f "$BUNDLE_DIR/installer-build.first-attempt.log"
if ! tauri_dmg; then
    # bundle_dmg.sh's Finder AppleScript fails now and then ("Can't get disk"); retry that once.
    # Any other failure (compile, app signing) would only fail again.
    grep -q "bundle_dmg" "$BUILD_LOG" || { echo "Error: the build failed; log: $BUILD_LOG" >&2; exit 1; }
    cp "$BUILD_LOG" "$BUNDLE_DIR/installer-build.first-attempt.log"
    echo "=== DMG step failed (log: $BUNDLE_DIR/installer-build.first-attempt.log); retrying once ==="
    detach_leftover_images
    rm -rf "$DMG_DIR"
    tauri_dmg || { echo "Error: the DMG step failed twice; log: $BUILD_LOG" >&2; exit 1; }
fi

DMGS=("$DMG_DIR"/*.dmg)
[ ${#DMGS[@]} -eq 1 ] && [ -f "${DMGS[0]}" ] || {
    echo "Error: expected one DMG in $DMG_DIR, found: ${DMGS[*]}" >&2; exit 1; }
FINAL="${DMGS[0]}"
[ "$SIGN" = true ] || FINAL="${FINAL%.dmg}_unsigned.dmg"
DMG="${DMGS[0]%.dmg}.incomplete.dmg"
mv "${DMGS[0]}" "$DMG"

if [ "$SIGN" = true ]; then
    echo "=== Signing the DMG ==="
    codesign --force --timestamp --sign "$DEVELOPER_ID" "$DMG"
    echo "=== Notarizing (several minutes) ==="
    NOTARY_LOG="$DMG_DIR/notary.log"
    # No exit on a notarytool failure here: the log below says what happened either way.
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait 2>&1 \
        | tee "$NOTARY_LOG" || true
    if ! grep -q "status: Accepted" "$NOTARY_LOG"; then
        echo "Error: notarization not accepted; log: $NOTARY_LOG" >&2
        SUBMISSION=$(sed -n '/^ *id: /{s/^ *id: *//p;q;}' "$NOTARY_LOG")
        if [ -n "$SUBMISSION" ]; then
            xcrun notarytool log "$SUBMISSION" --keychain-profile "$NOTARY_PROFILE" >&2 \
                || echo "(Apple's log for $SUBMISSION is not available yet.)" >&2
            echo "If it is still in progress: xcrun notarytool wait $SUBMISSION --keychain-profile $NOTARY_PROFILE" >&2
        fi
        exit 1
    fi
    { xcrun stapler staple "$DMG" && xcrun stapler validate "$DMG"; } || {
        echo "Error: stapling failed, though Apple accepted the DMG (the ticket can take a few" >&2
        echo "minutes to appear). Retry without rebuilding:" >&2
        echo "  xcrun stapler staple '$DMG' && mv '$DMG' '$FINAL'" >&2
        exit 1; }
    spctl --assess --type open --context context:primary-signature --verbose "$DMG" || {
        echo "Error: Gatekeeper rejects the stapled DMG: $DMG" >&2; exit 1; }
fi

hdiutil verify "$DMG" >/dev/null
mv "$DMG" "$FINAL"
DMG="$FINAL"
echo ""
echo "DMG: $DMG ($(du -h "$DMG" | cut -f1))"
[ "$SIGN" = true ] || echo "Unsigned build: on another Mac, open it once, then allow it in System Settings > Privacy & Security > Open Anyway."
