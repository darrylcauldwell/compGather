#!/usr/bin/env bash
# Local pre-ship validation for EquiCalendar (iOS).
#   ./Scripts/preflight.sh --quick   # SwiftLint only (~5s)
#   ./Scripts/preflight.sh           # lint + regenerate + build + unit tests
set -euo pipefail

cd "$(dirname "$0")/.."   # -> ios/

QUICK=false
[[ "${1:-}" == "--quick" ]] && QUICK=true

echo "▸ SwiftLint"
swiftlint lint --quiet   # exits non-zero on errors only (warnings allowed)

if $QUICK; then
  echo "✓ quick preflight passed (lint only)"
  exit 0
fi

echo "▸ Regenerate project from project.yml"
xcodegen generate

echo "▸ Build + unit tests (iPhone 17 Pro simulator)"
# Simulator unit tests don't need real signing; disabling it avoids the
# "unsigned library" test-bundle load failure caused by DEVELOPMENT_TEAM.
xcodebuild test \
  -project EquiCalendar.xcodeproj \
  -scheme EquiCalendar \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  -quiet

echo "✓ preflight passed"
