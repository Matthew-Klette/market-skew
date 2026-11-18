"""TimesFM 2.5 worker. Started only by forecast.py, inside the predictor's own Python environment.

stdin JSON: {"contexts": [[floats]...], "horizon": int}
stdout JSON: {"paths": [[[q10, q50, q90] per step] per context]}
"""
import json
import os
import sys

# TimesFM output columns: mean, then the 10th..90th percentiles.
POSITIONS = (1, 5, 9)
BATCH = 16


def main() -> int:
    answer_to = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)  # library prints cannot corrupt the answer
    import numpy
    import timesfm

    payload = json.load(sys.stdin)
    horizon = int(payload["horizon"])
    contexts = [numpy.asarray(c, dtype=float) for c in payload["contexts"]]
    longest = max(len(c) for c in contexts)
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(sys.argv[1], local_files_only=True)
    model.compile(timesfm.ForecastConfig(max_context=max(longest, 32), max_horizon=max(horizon, 32), normalize_inputs=True,
                                         use_continuous_quantile_head=True, force_flip_invariance=True, infer_is_positive=bool(payload.get("positive", False)),
                                         fix_quantile_crossing=True, per_core_batch_size=BATCH))
    paths = []
    for start in range(0, len(contexts), BATCH):
        _, quantiles = model.forecast(horizon=horizon, inputs=contexts[start:start + BATCH])
        for row in range(quantiles.shape[0]):
            paths.append([[float(quantiles[row, step, p]) for p in POSITIONS] for step in range(horizon)])
    json.dump({"paths": paths}, answer_to)
    answer_to.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
