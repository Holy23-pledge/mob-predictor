#!/bin/bash
# Double-click me to predict every MLB game today and open the dashboard.
# First time only: right-click -> Open (macOS security).
cd "$(dirname "$0")"
python3 predict.py --all
TODAY=$(date +%F)
if [ -f "slate_$TODAY/index.html" ]; then
  open "slate_$TODAY/index.html"
fi
read -p "Done. Press Enter to close..."
