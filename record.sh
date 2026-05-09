#!/usr/bin/env bash
# Record `python3 demo.py` with Asciinema, with viewer-friendly pacing.
# Optionally converts the recording to demo.gif if `agg` is present.
#
# Configurable via env vars:
#   RSI_DEMO_PAUSE   seconds to wait between sections (default 1.5)
#   RSI_DEMO_COLS    terminal width for the recording  (default 110)
#   RSI_DEMO_ROWS    terminal height for the recording (default 40)
#   RSI_DEMO_THEME   agg theme for the gif             (default monokai)
#   RSI_DEMO_SPEED   agg speed multiplier              (default 1.2)
#
# Usage:
#   ./record.sh             # records demo.cast (and demo.gif if agg installed)
#   RSI_DEMO_PAUSE=2 ./record.sh
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v asciinema >/dev/null 2>&1; then
    echo "ERROR: asciinema not installed." >&2
    echo "        macOS:   brew install asciinema" >&2
    echo "        Linux:   pipx install asciinema  (or your distro's package)" >&2
    exit 1
fi

CAST="demo.cast"
GIF="demo.gif"
PAUSE="${RSI_DEMO_PAUSE:-1.5}"
COLS="${RSI_DEMO_COLS:-110}"
ROWS="${RSI_DEMO_ROWS:-40}"
THEME="${RSI_DEMO_THEME:-monokai}"
SPEED="${RSI_DEMO_SPEED:-1.2}"

rm -f "$CAST"

echo "==> Recording demo.cast"
echo "    pause=${PAUSE}s   size=${COLS}x${ROWS}"
RSI_DEMO_PAUSE="$PAUSE" asciinema rec "$CAST" \
    --cols "$COLS" \
    --rows "$ROWS" \
    --title "The RSI Loop — v1 to v2 self-improvement + clinical audit" \
    --overwrite \
    -c "python3 demo.py"

echo
echo "==> Wrote $CAST ($(du -h "$CAST" | cut -f1))"

if command -v agg >/dev/null 2>&1; then
    echo
    echo "==> Converting to $GIF (theme=${THEME}, speed=${SPEED})"
    agg "$CAST" "$GIF" --theme "$THEME" --speed "$SPEED"
    echo "==> Wrote $GIF ($(du -h "$GIF" | cut -f1))"
else
    echo
    echo "==> Tip: install 'agg' to also produce demo.gif"
    echo "        macOS:   brew install agg"
fi

# Static OG/social-card image — first frame of the GIF, since most social
# unfurlers (Slack, LinkedIn, Twitter) won't animate GIFs in previews.
OG="og.png"
if [ -f "$GIF" ] && command -v ffmpeg >/dev/null 2>&1; then
    echo
    echo "==> Extracting first frame as $OG (for og:image)"
    ffmpeg -y -loglevel error -i "$GIF" -vframes 1 "$OG"
    echo "==> Wrote $OG ($(du -h "$OG" | cut -f1))"
elif [ -f "$GIF" ]; then
    echo
    echo "==> Tip: install 'ffmpeg' to also produce $OG for social previews"
    echo "        macOS:   brew install ffmpeg"
fi

echo
echo "Next steps:"
echo "  • Inspect locally:        asciinema play $CAST"
echo "  • Upload to asciinema.org: asciinema upload $CAST"
echo "  • Embed GIF in README:    ![demo](demo.gif)"
