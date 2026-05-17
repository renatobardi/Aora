# Automation — Running Aora on a Schedule

This page covers how to run `python3 main.py` automatically every day using the most common AI tools and system schedulers.

## Comparison

| Method | Scheduling | Runs locally | Cloud required | Best for |
|---|---|---|---|---|
| [GitHub Actions](#github-actions) | Cron (YAML) | No | Yes | Repos with committed output |
| [Claude Code](#claude-code) | Cron / natural language | Yes | Optional | Claude Code users |
| [Goose (Block)](#goose-block) | 6-field cron + recipe | Yes | No | Goose users |
| [crontab](#crontab--launchagent-macos--linux) | 5-field cron | Yes | No | Simplest local setup |
| [LaunchAgent](#crontab--launchagent-macos--linux) | Calendar interval | Yes | No | macOS — survives sleep |

> **Recommended for most people:** `crontab` (Linux) or `LaunchAgent` (macOS) — zero extra tooling, runs silently in the background.

---

## GitHub Actions

Best when you want the output file committed back to the repository automatically (e.g. a dedicated `output` branch).

Create `.github/workflows/daily.yml`:

```yaml
name: Daily AI Clipping

on:
  schedule:
    - cron: '0 8 * * *'   # every day at 08:00 UTC
  workflow_dispatch:        # allow manual trigger from GitHub UI

jobs:
  clip:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium --with-deps

      - name: Run
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OUTPUT_DIR: ./output
        run: python3 main.py

      - name: Commit output
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add output/ seen_ids.json
          git diff --cached --quiet || git commit -m "chore: daily clipping $(date -u +%F)"
          git push
```

Add `ANTHROPIC_API_KEY` in **Settings → Secrets and variables → Actions**.

> **Note:** `OUTPUT_DIR` in Actions points to the repo checkout — the output file gets committed back. If you want the file in your Obsidian vault, run locally instead.

---

## Claude Code

Two options: a one-off session schedule (expires in 7 days) or a persistent cloud routine.

### Option A — Session schedule (local machine)

Type in the Claude Code chat:

```
/schedule daily at 8am: cd /Users/you/Projects/Github/Aora && python3 main.py
```

Or use a cron expression directly:

```
Create a daily schedule at 0 8 * * * to run: cd /Users/you/Projects/Github/Aora && python3 main.py
```

The scheduled task fires daily as long as Claude Code is running. It auto-expires after 7 days — re-create it when needed.

### Option B — Cloud routine (persistent, no session required)

```
/schedule
```

Follow the prompts to create a named routine with a cron schedule. Anthropic's infrastructure runs it even when your machine is off.  
> Requires Claude Code with Routines enabled. Minimum interval: 1 hour.

---

## Goose (Block)

[Goose](https://block.github.io/goose) supports scheduled recipes with a 6-field cron (`second minute hour day month weekday`).

### 1. Create the recipe

Save as `.goose/recipes/daily-clipping.yaml` in the project root:

```yaml
name: Daily AI Clipping
version: 1.0.0
description: Runs Aora and generates today's clipping file

extensions:
  - type: shell

instructions: |
  Change directory to the project root and run:
    python3 main.py
  Report the number of items fetched and any errors from the output.
```

### 2. Schedule it

```bash
goose schedule add \
  --schedule-id aora-daily \
  --cron "0 0 8 * * *" \
  --recipe-source .goose/recipes/daily-clipping.yaml
```

```bash
goose schedule list          # confirm it's registered
goose schedule remove aora-daily   # remove when needed
```

---

## crontab / LaunchAgent (macOS / Linux)

### crontab (macOS and Linux)

```bash
crontab -e
```

Add this line (replace the path):

```cron
0 8 * * * cd /Users/you/Projects/Github/Aora && /usr/bin/python3 main.py >> /tmp/aora.log 2>&1
```

Cron format: `minute hour day month weekday`

> Use the full path to `python3` (`which python3`) and make sure `.env` is in the project root — cron doesn't load your shell profile.

### LaunchAgent (macOS — recommended over crontab)

LaunchAgent runs even after the machine wakes from sleep. Save the file as `~/Library/LaunchAgents/com.user.aora.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.aora</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd /Users/you/Projects/Github/Aora &amp;&amp; /usr/bin/python3 main.py</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/aora.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/aora-error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>sk-ant-...</string>
        <key>OUTPUT_DIR</key>
        <string>/Users/you/Vault/AI/raw</string>
    </dict>
</dict>
</plist>
```

Load and test:

```bash
launchctl load   ~/Library/LaunchAgents/com.user.aora.plist
launchctl start  com.user.aora          # run immediately to test
launchctl list | grep aora              # check status (exit code 0 = OK)
tail -f /tmp/aora.log                   # watch output
```

To unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.user.aora.plist
```

---

## Gemini CLI

Gemini CLI has no built-in scheduler. Wrap it in `crontab` or `LaunchAgent` above and call the script directly — no Gemini CLI involvement is needed just to run `main.py`.

If you want Gemini to *analyse* the output after each run, add a second step to your cron/LaunchAgent command:

```bash
cd /path/to/Aora && python3 main.py && \
  gemini -p "Summarise today's AI clipping at output/$(date +%F)-v1.md"
```
