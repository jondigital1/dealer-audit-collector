#!/usr/bin/env bash
# Keep the push listener up: started at boot and poked every 5 minutes by cron (SETUP.md, "The push trigger")
cd /home/jonneale83/dealer-audit-collector
if curl -sf -m 5 http://127.0.0.1:${LISTENER_PORT:-8787}/health >/dev/null 2>&1; then exit 0; fi
mkdir -p state
nohup .venv/bin/python3 -m collector listen >> state/listener.log 2>&1 &
echo "$(date '+%b %-d, %Y, %-I:%M %p %Z')  watchdog: listener started" >> state/listener.log
