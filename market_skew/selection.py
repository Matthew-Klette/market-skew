"""Picking both lists with the quality-score gates, from what is already saved. Used by the scan and by `skew picks`.
The gate reads the stored Quality score rows with Claude's saved deductions applied; a company Claude has not checked yet
counts at its raw score and is labelled so."""
import pandas as pd

from . import breaking, closest, gate, picks, store, swing


def gate_for(conn, date: str) -> dict[str, dict]:
    """symbol -> adjusted score entry, from the newest stored Quality score run on or before `date`."""
    rows = store.sentinel(conn, date)[1]
    return gate.table(breaking.apply(rows, store.breaking(conn)))


def choose_all(body: dict, scored: pd.DataFrame, entries: dict, excluded, earnings: dict | None = None) -> dict:
    """{"picks", "swing", "swing_storm"} for a report body, both lists through the same gate table.
    `earnings` is earnings.cached(): His way skips names reporting within 7 days, Steady picks get a note."""
    flow = {s["name"]: s["flow_bps"] for s in body["sectors"]}
    chosen = picks.as_dicts(picks.choose(scored, flow, excluded, entries, earnings, body["date"]))
    trades = swing.as_dicts(swing.choose(scored, flow, body["indexes"], body["date"], excluded, entries, earnings))
    return {"picks": chosen, "swing": trades, "swing_storm": swing.is_stormy(body["indexes"]),
            # display only, never money or paper records: filled only while the real list is empty
            "picks_near": [] if chosen else closest.steady(scored, entries, excluded),
            "swing_near": [] if trades else closest.his_way(scored, entries, excluded, earnings, body["date"])}
