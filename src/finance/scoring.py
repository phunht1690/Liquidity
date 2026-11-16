"""LQS là xếp hạng tương đối trong rổ tại cùng thời điểm."""
from __future__ import annotations

from math import isfinite
from typing import Any

DEFAULT_WEIGHTS = {"spread_bps": .25, "depth_min_vnd": .25, "execution_cost_bps": .25,
                   "amihud_5m": .15, "two_sided_ratio": .10}
HIGHER_IS_BETTER = {"depth_min_vnd", "two_sided_ratio"}


def _valid(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value)


def lqs_category(score: float | None) -> str:
    """Một bộ nhãn tương đối dùng chung cho API, giao diện và CSV."""
    if not _valid(score):
        return "Chưa đủ dữ liệu"
    return "Cao" if score >= 75 else "Trung bình" if score >= 50 else "Thấp" if score >= 25 else "Rất thấp"


def _percentiles(values: list[float], higher_better: bool) -> list[float]:
    if len(values) == 1:
        return [50.0]
    ranked = sorted(values)
    result = []
    for value in values:
        # Rank trung bình cho ties, chuẩn hóa 0–100. Chỉ dùng rổ hoàn chỉnh.
        first, last = ranked.index(value), len(ranked) - 1 - ranked[::-1].index(value)
        percentile = ((first + last) / 2) / (len(values) - 1) * 100
        result.append(percentile if higher_better else 100 - percentile)
    return result


def score_cross_section(rows: list[dict[str, Any]], weights: dict[str, float] | None = None,
                        incomplete_fill_penalty_bps: float = 100) -> list[dict[str, Any]]:
    weights = DEFAULT_WEIGHTS if weights is None else weights
    if set(weights) != set(DEFAULT_WEIGHTS) or any(not _valid(v) or v < 0 for v in weights.values()) or abs(sum(weights.values()) - 1) > 1e-8:
        raise ValueError("LQS phải có đủ 5 trọng số không âm, tổng bằng 1.")
    if incomplete_fill_penalty_bps < 0 or not isfinite(incomplete_fill_penalty_bps):
        raise ValueError("Phạt thiếu thanh khoản phải không âm và hữu hạn.")
    output = [dict(row) for row in rows]
    complete: list[dict[str, Any]] = []
    for row in output:
        row.update(lqs=None, category=lqs_category(None), component_percentiles=None)
        buy, sell = row.get("buy"), row.get("sell")
        if not buy or not sell or any(not _valid(side.get(key)) for side in (buy, sell) for key in ("slip_bps", "fill_ratio")):
            row["execution_cost_bps"] = None
            continue
        row["execution_cost_bps"] = (buy["slip_bps"] + sell["slip_bps"]) / 2 + incomplete_fill_penalty_bps * (1 - (buy["fill_ratio"] + sell["fill_ratio"]) / 2)
        if all(_valid(row.get(key)) for key in weights) and row.get("quality") == "valid":
            complete.append(row)
    for row in complete:
        row["component_percentiles"] = {}
    for key in weights:
        ranks = _percentiles([row[key] for row in complete], key in HIGHER_IS_BETTER) if complete else []
        for row, rank in zip(complete, ranks):
            row["component_percentiles"][key] = rank
    for row in complete:
        score = sum(weights[key] * row["component_percentiles"][key] for key in weights)
        row["lqs"] = score
        row["category"] = lqs_category(score)
    return output
