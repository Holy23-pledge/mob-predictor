#!/bin/bash
# Double-click ONCE to make your Mac run the predictor automatically every
# morning at 10:00 AM. (Right-click -> Open the first time.)
# To change the time: edit HOUR below and double-click this again.
# To turn it off:  launchctl unload ~/Library/LaunchAgents/com.mlb-predictor.daily.plist
HOUR=10
MINUTE=0

cd "$(dirname "$0")"
APPDIR="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.mlb-predictor.daily.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mlb-predictor.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>cd "$APPDIR" &amp;&amp; python3 predict.py --all >> run.log 2>&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"

printf -v HHMM "%d:%02d" "$HOUR" "$MINUTE"
echo ""
echo "Done! Your Mac will now run the predictor every day at $HHMM AM."
echo "  - Open slate_<date>/index.html in this folder for the day's picks"
echo "  - picks_log.csv and calibration.html stay up to date automatically"
echo "  - If the Mac is asleep at $HHMM, it runs when it wakes up"
echo "IMPORTANT: don't move or rename this folder afterward - if you do,"
echo "just double-click this setup file again from the new location."
read -p "Press Enter to close..."
