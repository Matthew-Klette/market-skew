# Third-party notices

Market Skew is MIT licensed (see LICENSE). It builds on the following.

## JoelLewis/finance_skills (MIT), code ported with changes

Repository: https://github.com/JoelLewis/finance_skills

Ported and simplified (plain Python, different data shapes, extra logic of our own):

- `market_skew/rebalance.py` (drift against targets, cash-flow rebalancing)
- `market_skew/goal.py` (future value with contributions)
- `market_skew/risk.py` (historical VaR and max drawdown)

The original licence text:

```
MIT License

Copyright (c) 2026 Joel Lewis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## himself65/finance-skills (MIT), ideas only

Repository: https://github.com/himself65/finance-skills

The fair-value range (a bear/base/bull discounted-cash-flow approach) re-implements ideas from these prompts. No code
was copied.

## Google TimesFM 2.5 (Apache-2.0), downloaded, not redistributed

`scripts/install-predictor.sh` downloads the TimesFM 2.5 200M weights (`google/timesfm-2.5-200m-pytorch`) from Hugging Face
and installs the `timesfm` Python package on your Mac. Neither is included in this repository. Both are Apache-2.0:
https://github.com/google-research/timesfm

## Python libraries

- yfinance (Apache-2.0) fetches Yahoo Finance data. It is not affiliated with Yahoo; Yahoo's terms apply to the data, which
  is for personal use. https://github.com/ranaroussi/yfinance
- pandas, numpy and scipy (BSD-3-Clause).
- PyTorch (BSD-style) and the other predictor libraries are installed by the predictor script under their own licences.

## Data sources

- Nasdaq's public stock screener (the US stock list).
- SEC EDGAR (company filings). Market Skew follows the SEC's fair-access policy: it identifies itself with a contact
  email that you provide and stays under 10 requests a second. https://www.sec.gov/os/accessing-edgar-data
- Frankfurter (European Central Bank reference rates, USD/ZAR). https://frankfurter.dev
