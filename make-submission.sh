#!/usr/bin/env bash
# Build the competition package: one zip with the product link, the video link, the technical docs, the business plan,
# the pitch and the complete source code. Needs api/.venv (with `markdown`) and google-chrome. Re-run after any change.
set -euo pipefail
cd "$(dirname "$0")"
OUT=submission
PY=api/.venv/bin/python
rm -rf "$OUT" && mkdir -p "$OUT/06-source-code"

$PY docs/fa/render_md.py docs/fa/technical.fa.md "$OUT/03-technical-docs.pdf" "بات‌یار — مستندات فنی" >/dev/null
$PY docs/fa/render_md.py docs/fa/business-plan.fa.md "$OUT/04-business-plan.pdf" "بات‌یار — بیزینس پلن" >/dev/null
google-chrome --headless=new --no-sandbox --disable-gpu --print-to-pdf="$OUT/05-pitch.pdf" --no-pdf-header-footer \
  --virtual-time-budget=8000 "file://$PWD/docs/fa/pitch/pitch.html" >/dev/null 2>&1
cp docs/fa/technical.fa.md "$OUT/03-technical-docs.md"
cp docs/fa/business-plan.fa.md "$OUT/04-business-plan.md"
cp docs/fa/submission/*.txt "$OUT"/

# the complete source: everything but secrets, databases, dependency folders and build caches
rsync -a --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='.next' --exclude='web/out' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.db' --exclude='.env' --exclude='.claude' --exclude='.liara' --exclude='submission' \
  --exclude='tsconfig.tsbuildinfo' --exclude='*.zip' ./ "$OUT/06-source-code/"

( cd "$OUT" && rm -f ../botyar-buildx-submission.zip && zip -qr ../botyar-buildx-submission.zip . )
echo "wrote botyar-buildx-submission.zip ($(du -h botyar-buildx-submission.zip | cut -f1))"
