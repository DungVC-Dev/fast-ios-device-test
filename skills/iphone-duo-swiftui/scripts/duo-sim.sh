#!/bin/zsh
# iPhone Duo simulator helper (Xcode 27.1 + Device Hub).
#
#   duo-sim.sh devices                          booted Duo UDID and its outer/inner display UUIDs
#   duo-sim.sh build-run <xcodeproj> <scheme> <bundle-id>
#   duo-sim.sh launch <bundle-id>
#   duo-sim.sh pose closed|book|flat|rotate
#   duo-sim.sh shot outer|inner <name>          -> $DUO_OUT/<name>.png and <name>_s.png (downscaled for reading)
#   duo-sim.sh calibrate                        captures the Device Hub window for tap-inner calibration
#   duo-sim.sh tap-inner <x> <y> [wait]         inner-display tap in points (real click on Device Hub)
#
# Env: DUO_XCODE (default /Applications/Xcode 27.1.app), DUO_UDID (auto), DUO_OUT (default $TMPDIR/duo),
#      DUO_DD (DerivedData for build-run, default $DUO_OUT/DerivedData), DUO_INNER_RECT (see calibrate).
set -u
DUO_XCODE=${DUO_XCODE:-"/Applications/Xcode 27.1.app"}
export DEVELOPER_DIR="$DUO_XCODE/Contents/Developer"
DUO_OUT=${DUO_OUT:-"${TMPDIR:-/tmp}/duo"}
mkdir -p "$DUO_OUT"
HERE=${0:A:h}

# `simctl io` can hang on unused framebuffers; never let one call block the session.
with_timeout() { local t=$1; shift; perl -e 'alarm shift; exec @ARGV' "$t" "$@"; }

udid() {
  [[ -n "${DUO_UDID:-}" ]] && { echo "$DUO_UDID"; return; }
  xcrun simctl list devices booted | grep -m1 "iPhone Duo" | grep -oE '[0-9A-F-]{36}'
}

# Displays are identified by framebuffer size: outer 1398x2034, inner 2007x2853 (portrait pixels).
display_uuid() {
  with_timeout 10 xcrun simctl io "$(udid)" enumerate 2>/dev/null | awk -v want="$1" '
    /UUID:/ { uuid=$2 }
    /Default width:/ { w=$3 }
    /Default height:/ { if ((want=="outer" && w==1398) || (want=="inner" && w==2007)) { print uuid; exit } }'
}

devicehub_window() {
  swift - <<'EOF' 2>/dev/null
import CoreGraphics
let l = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] ?? []
let w = l.filter { ($0[kCGWindowOwnerName as String] as? String) == "Device Hub" }
  .compactMap { i -> (Int, [String: Double])? in
    guard let n = i[kCGWindowNumber as String] as? Int, let b = i[kCGWindowBounds as String] as? [String: Double] else { return nil }
    return (n, b) }
  .max { ($0.1["Height"] ?? 0) < ($1.1["Height"] ?? 0) }
if let (n, b) = w { print(n, Int(b["X"]!), Int(b["Y"]!), Int(b["Width"]!), Int(b["Height"]!)) }
EOF
}

frontmost() { osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true'; }

# Clicks through Device Hub's own pose buttons via Accessibility; reopens the device window if it went missing.
pose() {
  local n
  case $1 in rotate) n=4;; closed) n=5;; book) n=6;; flat) n=7;; *) echo "pose: closed|book|flat|rotate"; return 1;; esac
  local group='group 3 of splitter group 1 of group 1 of splitter group 1 of group 1 of window 1'
  if ! osascript -e "tell application \"System Events\" to tell process \"DeviceHub\" to click button $n of $group" >/dev/null 2>&1; then
    osascript -e 'tell application "System Events" to tell process "DeviceHub" to click (first menu item of menu 1 of menu bar item "Window" of menu bar 1 whose name contains "iPhone Duo")' >/dev/null 2>&1
    sleep 2
    osascript -e "tell application \"System Events\" to tell process \"DeviceHub\" to click button $n of $group" >/dev/null 2>&1 \
      || { echo "pose: Device Hub window not reachable (open it from Device Hub's Window menu)"; return 1; }
  fi
  sleep 3
}

shot() {
  local which=$1 name=$2 uuid
  uuid=$(display_uuid "$which") || true
  [[ -z "$uuid" ]] && { echo "shot: no $which display found"; return 1; }
  with_timeout 15 xcrun simctl io "$(udid)" screenshot --display="$uuid" "$DUO_OUT/$name.png" >/dev/null 2>&1 \
    || { echo "shot: capture timed out"; return 1; }
  local z=678; [[ "$which" == inner ]] && z=1000
  sips -Z $z "$DUO_OUT/$name.png" --out "$DUO_OUT/${name}_s.png" >/dev/null
  echo "$DUO_OUT/${name}_s.png"
}

calibrate() {
  read -r win x y w h <<< "$(devicehub_window)"
  [[ -z "${win:-}" ]] && { echo "calibrate: Device Hub window not on screen"; return 1; }
  screencapture -x -o -l "$win" "$DUO_OUT/devicehub.png"
  local px; px=$(sips -g pixelWidth "$DUO_OUT/devicehub.png" | awk '/pixelWidth/ {print $2}')
  cat <<EOM
Window $win at ($x,$y) ${w}x${h} pt, capture $DUO_OUT/devicehub.png is ${px}px wide.
Open the capture, find the inner display's top-left corner and its width in CAPTURE PIXELS, then:
  export DUO_INNER_RECT="<left> <top> <width>"
Recalibrate whenever the Device Hub window moves, resizes, zooms, or the pose/orientation changes.
EOM
}

tap_inner() {
  [[ -z "${DUO_INNER_RECT:-}" ]] && { echo "tap-inner: run calibrate and export DUO_INNER_RECT"; return 1; }
  read -r win x y w h <<< "$(devicehub_window)"
  local px left top width
  px=$(sips -g pixelWidth "$DUO_OUT/devicehub.png" 2>/dev/null | awk '/pixelWidth/ {print $2}')
  read -r left top width <<< "$DUO_INNER_RECT"
  # Inner display width in points depends on orientation: 951 landscape, 669 portrait.
  local ptw=951; shot inner _probe >/dev/null && \
    [[ $(sips -g pixelWidth "$DUO_OUT/_probe.png" | awk '/pixelWidth/ {print $2}') -lt 2500 ]] && ptw=669
  local backing; backing=$(echo "$px / $w" | bc -l)
  local gx gy
  gx=$(echo "$x + ($left + $1 * $width / $ptw) / $backing" | bc -l)
  gy=$(echo "$y + ($top + $2 * $width / $ptw) / $backing" | bc -l)
  local prev; prev=$(frontmost)
  osascript -e 'tell application "System Events" to set frontmost of process "DeviceHub" to true'
  sleep 0.5
  if [[ "$(frontmost)" == "DeviceHub" ]]; then
    swift - "$gx" "$gy" <<'EOF' 2>/dev/null
import CoreGraphics
import Foundation
let p = CGPoint(x: Double(CommandLine.arguments[1])!, y: Double(CommandLine.arguments[2])!)
for t in [CGEventType.mouseMoved, .leftMouseDown, .leftMouseUp] {
  CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
  usleep(80_000)
}
EOF
  else
    echo "tap-inner: Device Hub could not come to the front (user busy in $(frontmost)); retry"
  fi
  [[ "$prev" != "DeviceHub" ]] && osascript -e "tell application \"System Events\" to set frontmost of process \"$prev\" to true" >/dev/null 2>&1
  sleep "${3:-2}"
}

build_run() {
  local proj=$1 scheme=$2 bid=$3 dd=${DUO_DD:-"$DUO_OUT/DerivedData"}
  xcodebuild build -project "$proj" -scheme "$scheme" -destination "platform=iOS Simulator,id=$(udid)" \
    -derivedDataPath "$dd" -quiet > "$DUO_OUT/build.log" 2>&1
  local rc=$?
  grep -E " error:" "$DUO_OUT/build.log" | sort -u | head -20
  [[ $rc -ne 0 ]] && { echo "build failed ($DUO_OUT/build.log)"; return $rc; }
  local app; app=$(ls -d "$dd"/Build/Products/*-iphonesimulator/*.app | head -1)
  xcrun simctl install "$(udid)" "$app" && xcrun simctl launch --terminate-running-process "$(udid)" "$bid" >/dev/null && echo "launched $bid"
}

case ${1:-} in
  devices) echo "udid  $(udid)"; echo "outer $(display_uuid outer)"; echo "inner $(display_uuid inner)";;
  build-run) build_run "$2" "$3" "$4";;
  launch) xcrun simctl launch --terminate-running-process "$(udid)" "$2";;
  pose) pose "$2";;
  shot) shot "$2" "$3";;
  calibrate) calibrate;;
  tap-inner) tap_inner "$2" "$3" "${4:-2}";;
  *) sed -n '2,13p' "$0";;
esac
