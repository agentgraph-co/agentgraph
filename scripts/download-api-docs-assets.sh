#!/bin/bash
# Download Swagger UI and ReDoc assets for self-hosting.
# Run after `npm run build` in web/ directory.
set -e

DEST="${1:-web/dist/api-docs}"
mkdir -p "$DEST"

CDN="https://cdn.jsdelivr.net/npm"

echo "Downloading Swagger UI 5.18.2..."
curl -sL "$CDN/swagger-ui-dist@5.18.2/swagger-ui-bundle.min.js" \
  -o "$DEST/swagger-ui-bundle.min.js"
curl -sL "$CDN/swagger-ui-dist@5.18.2/swagger-ui.min.css" \
  -o "$DEST/swagger-ui.min.css"

echo "Downloading ReDoc 2.1.5..."
curl -sL "$CDN/redoc@2.1.5/bundles/redoc.standalone.min.js" \
  -o "$DEST/redoc.standalone.min.js"

echo "Done. Assets in $DEST:"
ls -lh "$DEST"
