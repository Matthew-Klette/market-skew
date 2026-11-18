# Market Skew

A Mac app that reads the US stock market once a day and tells you, in plain words, which stocks and index funds look
worth adding to this month, and which of your holdings deserve a second look. It is built for a long-term investor in
South Africa who buys US shares through EasyEquities (rand in, dollars out, with the fees included in every number).

It looks at where a stock's price and the options market agree or disagree across the top 2,000 US stocks by dollar
volume, then scores each company on its filings (the "Quality score"), suggests a monthly split between a TFSA and a
dollar account, checks your portfolio's balance, and shows whether your goal is on track. Everything runs on your Mac.

**Not financial advice.** See the section at the bottom.

## Install with Claude Code

Paste this into Claude Code:

    Install https://github.com/Matthew-Klette/market-skew

Claude Code clones the repo and runs `./install.sh`, explaining each question as it comes up. It never types your
email or passwords for you.

## Install by hand

You need a Mac (macOS 13 or later), Apple's Command Line Tools and [uv](https://docs.astral.sh/uv/).

    xcode-select --install                  # once, if you've never installed them
    brew install uv                         # or see docs.astral.sh/uv for the official installer
    git clone https://github.com/Matthew-Klette/market-skew.git
    cd market-skew
    ./install.sh

`./install.sh` is safe to run again. It creates a Python environment, runs a quick self-test, builds the app into
`~/Applications`, adds it to your Dock and then asks two optional questions (the Google predictor, and an email for SEC
downloads). Flags: `--yes`, `--skip-tests`, `--app-dir DIR`, `--no-dock`, `--no-predictor`.

To update: `git pull` and `./install.sh` again. Your own files (holdings, watchlist, settings, saved scans) are not
touched.

## What you will see

Screenshots go here:

- Picks: your monthly plan, Steady picks, swing trades, the stocks you own
- Money: your split across funds, a bad-year check, and whether your goal is on track
- Market: today's read, where money is flowing by theme and sector, a weekly heatmap
- Research: the Quality score board and one card per company, with a fair-value range
- Stocks: every stock in four buckets, filters, and a watchlist
- Track record: how past picks did against the average stock

The first time you open it, Picks asks "Tell me how much you invest each month". Nothing is assumed.

## What data it uses (all free, no accounts)

- Nasdaq's public stock list, for the universe of US stocks.
- Yahoo Finance (through the `yfinance` library) for prices and option chains.
- SEC EDGAR for company filings (revenue, cash flow, debt), used for the Quality score and fair-value range.
- Frankfurter (European Central Bank rates) for the rand-to-dollar rate.
- Optional: Google's TimesFM 2.5 model, downloaded once from Hugging Face, for a one-month price range with a track record.

## What runs when

Nothing runs in the background. There is no scheduler and no login item. The app scans the market once per US trading
day, the first time you open it after the New York close (23:00 in South Africa, 22:00 in US summer), and stops when you
quit it. A full scan takes 10 to 20 minutes. You can also run one by hand: `.venv/bin/python -B skew scan`.

## Costs

The numbers assume EasyEquities in South Africa: about 0.25% brokerage plus 0.31% clearing and 15% VAT on US buys,
about 1.2% to convert rand to dollars, about 0.25% on JSE ETF buys, and the Thrive monthly fee. They are shown as
"about" because brokers change them. If you use another broker, edit `market_skew/costs.py`.

## Privacy

- Everything stays on your Mac: your holdings, amounts, watchlist and saved scans live in `config/` and `data/`, both
  ignored by git.
- The email for SEC downloads (optional) is stored in `config/prefs.json` and sent only to sec.gov, as the SEC requires.
- The "Ask about this page" chat runs `claude -p` with every tool switched off, on your own Claude Code login. The numbers
  on that page are sent to Anthropic (the maker of Claude) under your Claude plan's terms. That can include your holdings
  and monthly amounts if they're on the page. Don't want that? Don't use the chat; nothing else sends your data.
- During a scan, the "counter-argument" step sends public company figures (from SEC filings, nothing about you) to
  Anthropic the same way, on your Claude plan. Without Claude Code it is skipped.
- No analytics, no accounts, no keys.
- To delete everything: remove the project folder, `~/Applications/Market Skew.app` and
  `~/Library/Application Support/MarketSkew` (only there if you installed the Google predictor).

Questions or problems: open an issue on the GitHub repo.

## Using the pieces

    .venv/bin/python -B skew status         # today's read in the terminal
    .venv/bin/python -B skew ui             # the dashboard in a browser at 127.0.0.1
    .venv/bin/python -B skew export         # one self-contained HTML file
    .venv/bin/python -m pytest -q tests     # the tests

Your files: `config/holdings.json` (what you own; edit it on the Money tab), `config/watchlist.txt`,
`config/excluded.txt`, `config/prefs.json`. They are created from the `*.example.*` files the first time you run it.
`config/themes.json` (the stock baskets) is shared and safe to edit.

## Credits

Some features follow public ideas from other people, described generically: a swing-trading creator's public posts
inspired the "His way" swing trades, and a personal-finance creator's rules of thumb inspired the budget checks on the
Money tab. The portfolio maths builds on JoelLewis/finance_skills (MIT); see THIRD_PARTY_NOTICES.md for that and for the
libraries, data sources and the Google TimesFM weights. Matt recommends the Google predictor; it is optional.

## Not financial advice

This is a research tool, not advice. It applies fixed rules to public data and cannot know your situation. Option
prices, filings and Yahoo data can be late or wrong. Scores, fair-value ranges and predictions are not promises and
have not been proven to beat simply buying an index fund. Nothing here buys or sells anything for you. Check the facts
yourself, don't risk money you can't lose, and speak to a licensed adviser for decisions that matter.

MIT licence. See LICENSE.
