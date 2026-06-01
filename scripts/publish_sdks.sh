#!/usr/bin/env bash
# Publish both SDKs. Needs free auth tokens (see sdk/PUBLISHING.md).
#   PYPI_TOKEN=pypi-...  NPM_TOKEN=npm_...  bash scripts/publish_sdks.sh
# Run with --python-only / --js-only to do one.
set -euo pipefail
cd "$(dirname "$0")/.."

DO_PY=true; DO_JS=true
for a in "$@"; do
  case "$a" in --python-only) DO_JS=false;; --js-only) DO_PY=false;; esac
done

if $DO_PY; then
  : "${PYPI_TOKEN:?set PYPI_TOKEN (pypi-… from pypi.org → API tokens)}"
  echo "==> Building + publishing agentgraph-sdk to PyPI"
  ( cd sdk && rm -rf dist && python3 -m build >/dev/null && \
    TWINE_USERNAME=__token__ TWINE_PASSWORD="$PYPI_TOKEN" python3 -m twine upload dist/* )
  echo "OK: pip install agentgraph-sdk"
fi

if $DO_JS; then
  : "${NPM_TOKEN:?set NPM_TOKEN (Automation token from npmjs.com → Access Tokens)}"
  echo "==> Publishing @agentgraph/trust to npm"
  ( cd sdk/js && \
    echo "//registry.npmjs.org/:_authToken=${NPM_TOKEN}" > .npmrc && \
    npm publish --access public; rm -f .npmrc )
  echo "OK: npm i @agentgraph/trust"
fi
