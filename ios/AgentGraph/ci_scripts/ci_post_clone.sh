#!/bin/bash
set -euo pipefail

# Xcode Cloud post-clone script
# Generates .xcodeproj from project.yml since it's gitignored

echo "=== Installing xcodegen ==="
brew install xcodegen

echo "=== Generating Xcode project ==="
cd "$CI_PRIMARY_REPOSITORY_PATH/ios/AgentGraph"
xcodegen generate

echo "=== Project generated successfully ==="
ls -la AgentGraph.xcodeproj/
