#!/usr/bin/env bash
# Build the frontend (same-origin API) and copy it into api/static.
set -euo pipefail
cd "$(dirname "$0")/web"
NEXT_PUBLIC_API_BASE="" npm run build
rm -rf ../api/static && cp -r out ../api/static
echo "frontend copied to api/static"
