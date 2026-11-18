# Market Skew: notes for Claude Code

A local macOS app (Python engine in `market_skew/`, native Swift window in `app/`), also installable on Windows 10/11
(`install.cmd` -> `install.ps1`, window = Edge app mode via `skew app` in `market_skew/winapp.py`; platform differences live in
`market_skew/system.py`, and the Mac answers there must never change). Personal config and saved data are
gitignored and stay on the user's Mac.

## When the user asks to install it

1. Run `./install.sh` from the project folder. It needs macOS, Apple's Command Line Tools and `uv`; if one is missing it
   stops and prints the exact command for the user to run. Pass that command on; do not install tools behind their back
   and never pipe `curl` into a shell for them.
2. Explain each prompt to the user in plain words before it appears, then let them answer:
   - "Install the Google predictor? [Y/n]" is a 1.4 GB optional download of Google's TimesFM model (free, runs locally).
   - "Email (or press Enter to skip)" is the contact address the US SEC requires for downloads of company filings. It is
     stored only in `config/prefs.json` and sent only to sec.gov.
3. Never type an email address, password or any personal detail for the user. If the prompts can't be answered
   interactively, use `./install.sh --yes --no-predictor` and tell the user they can add the rest later in the app.
4. When it finishes, tell the user the app is in `~/Applications/Market Skew.app` (and the Dock), and that the first
   open asks how much they invest each month.

Useful flags: `--yes`, `--skip-tests`, `--app-dir DIR`, `--no-dock`, `--no-predictor`.

On Windows run `.\install.cmd` instead (flags `-Yes`, `-SkipTests`, `-NoShortcuts`, `-NoPredictor`); if uv is missing it
prints `winget install --id=astral-sh.uv -e` for the user to run. The app lands in the Start menu and on the desktop.

## Updating

`git pull` then `./install.sh` again. It rebuilds the app and leaves `config/` and `data/` alone.

## Working on the code

- Tests: `.venv/bin/python -m pytest -q tests`
- Never commit `config/prefs.json`, `config/holdings.json`, `config/watchlist.txt`, `config/excluded.txt`,
  `config/local.env` or `data/`. They are personal. The `*.example.*` files are the shipped defaults.
- `config/local.env` (optional, gitignored) holds `KEY=VALUE` lines read at startup, e.g. `MARKET_SKEW_FORECASTER` and
  `MARKET_SKEW_FORECASTER_PYTHON` to point at a predictor installed elsewhere.
- The user-visible name for the company score is "Quality score"; the internal module is still `sentinel`.
- Not financial advice: keep that framing in any text you add.
