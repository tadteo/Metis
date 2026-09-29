"""Method validation adapted from the concurrent paired sign-flip implementation.

Executed-value binding stays in integrity.py. This module validates a registered
method's arithmetic; independence, exchangeability and complete multiplicity remain
scientific assumptions requiring independent review.
"""

from __future__ import annotations

import hashlib
import math
import re
from decimal import Decimal, DecimalException
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .contracts import Model


class AnalysisPair(Model):
    left: str
    right: str


class StatisticalPlan(Model):
    schema_version: Literal[1] = 1
    test: Literal["paired_sign_flip"]
    metric: str
    pairs: list[AnalysisPair] = Field(min_length=2, max_length=20)
    alternative: Literal["two-sided", "greater", "less"] = "two-sided"
    alpha: float = Field(gt=0, lt=1)
    family_size: int = Field(ge=1)
    correction: Literal["bonferroni"]
    assumptions: str = Field(min_length=30)


def register_plan(root: Path) -> dict[str, Any] | None:
    """Capture plan bytes before generated execution; never infer preregistration."""
    from .runtime_support import read_text

    try:
        (root / "statistical_plan.json").lstat()
    except FileNotFoundError:
        return None
    content = read_text(root, "statistical_plan.json", 1_000_000)
    StatisticalPlan.model_validate_json(content)
    return {
        "path": "statistical_plan.json",
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "content": content,
        "registered_before_execution": True,
        "registered_before_observing_results": False,
        "assumptions_host_certified": False,
    }


def validate_analysis(
    analysis: dict[str, Any], registration: dict[str, Any] | None, inputs: list[dict[str, Any]]
) -> dict[str, Any]:
    if analysis["method"] != "paired_sign_flip":
        return {"validated": False, "reason": "No registered method-specific validator"}
    if not registration or registration.get("registered_before_execution") is not True:
        raise ValueError("paired sign-flip analysis requires a plan registered before execution")
    content = registration.get("content", "")
    if hashlib.sha256(content.encode()).hexdigest() != registration.get("sha256"):
        raise ValueError("registered statistical plan hash disagrees with its recorded content")
    plan = StatisticalPlan.model_validate_json(content)
    if analysis["metric"] != plan.metric:
        raise ValueError("analysis metric disagrees with the registered statistical plan")
    samples = {item["id"]: item for item in inputs}
    differences: list[float] = []
    used: set[str] = set()
    seeds: set[int] = set()
    common_protocol: str | None = None
    common_data: Any = None
    group_code: tuple[str, str] | None = None
    common_unit: str | None = None
    for pair in plan.pairs:
        if pair.left == pair.right or pair.left in used or pair.right in used:
            raise ValueError("statistical analysis reuses paired samples")
        used.update((pair.left, pair.right))
        left, right = samples.get(pair.left), samples.get(pair.right)
        if left is None or right is None:
            raise ValueError("statistical analysis uses missing registered metric samples")
        if plan.metric not in left["metrics"] or plan.metric not in right["metrics"]:
            raise ValueError("statistical analysis samples lack the declared metric")
        lp, rp = left.get("provenance", {}), right.get("provenance", {})
        seed = lp.get("seed")
        if (
            not isinstance(seed, int)
            or isinstance(seed, bool)
            or seed != rp.get("seed")
            or seed in seeds
        ):
            raise ValueError("statistical analysis requires unique matched seed pairs")
        seeds.add(seed)
        protocol = lp.get("specification_sha256")
        if (
            not isinstance(protocol, str)
            or not re.fullmatch(r"[a-f0-9]{64}", protocol)
            or protocol != rp.get("specification_sha256")
            or (common_protocol is not None and protocol != common_protocol)
        ):
            raise ValueError("statistical analysis pairs violate the immutable protocol")
        common_protocol = protocol
        code = (str(lp.get("code_sha256", "")), str(rp.get("code_sha256", "")))
        if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in code):
            raise ValueError("statistical samples lack recorded source identity")
        if group_code is not None and code != group_code:
            raise ValueError("statistical analysis mixes source variants within a treatment group")
        group_code = code
        data = lp.get("data_provenance")
        if not isinstance(data, dict) or not data:
            raise ValueError("statistical samples lack recorded dataset provenance")
        if data != rp.get("data_provenance") or (differences and data != common_data):
            raise ValueError("statistical analysis pairs use inconsistent dataset provenance")
        common_data = data
        unit = lp.get("metric_units", {}).get(plan.metric, "scalar")
        if unit != rp.get("metric_units", {}).get(plan.metric, "scalar") or (
            common_unit is not None and unit != common_unit
        ):
            raise ValueError("statistical analysis pairs use inconsistent metric units")
        common_unit = unit
        differences.append(left["metrics"][plan.metric] - right["metrics"][plan.metric])
    if used != set(analysis["input_experiment_ids"]):
        raise ValueError("analysis input experiments disagree with the registered pairs")
    if any(not math.isfinite(difference) for difference in differences):
        raise ValueError("statistical paired differences exceed finite arithmetic")
    # Every finite binary float is an integer over a power-of-two denominator.
    # Shared integer units make ties exact without a unit-dependent tolerance.
    ratios = [difference.as_integer_ratio() for difference in differences]
    denominator = max(denominator for _, denominator in ratios)
    scaled = [numerator * (denominator // divisor) for numerator, divisor in ratios]
    observed = sum(scaled)

    def count_tail(index: int, total: int) -> int:
        if index == len(scaled):
            if plan.alternative == "two-sided":
                return int(abs(total) >= abs(observed))
            if plan.alternative == "greater":
                return int(total >= observed)
            return int(total <= observed)
        difference = scaled[index]
        return count_tail(index + 1, total - difference) + count_tail(index + 1, total + difference)

    assignments = 1 << len(scaled)
    # Clamp in integer arithmetic before conversion, including very large families.
    p_value = min(count_tail(0, 0) * plan.family_size, assignments) / assignments
    mean = float(Fraction(observed, denominator * len(scaled)))
    if not math.isfinite(mean) or (observed and mean == 0):
        raise ValueError("statistical mean difference exceeds representable finite arithmetic")
    if analysis["statistic"] not in {"p_value", "effect_size"}:
        raise ValueError("paired sign-flip validator supports p_value or effect_size outputs")
    # Counts over 2**n are exactly representable; means permit relative roundoff
    # without allowing a small nonzero effect to be replaced by zero or its negation.
    matches = (
        analysis["value"] == p_value
        if analysis["statistic"] == "p_value"
        else math.isclose(analysis["value"], mean, rel_tol=1e-12, abs_tol=0)
    )
    if not matches:
        raise ValueError("statistical output disagrees with independent exact recomputation")
    return {
        "validated": True,
        "method": plan.test,
        "plan_sha256": registration["sha256"],
        "p_value": p_value,
        "mean_difference": mean,
        "alpha": plan.alpha,
        "family_size": plan.family_size,
        "alternative": plan.alternative,
        "assumptions_host_certified": False,
        "complete_test_family_host_certified": False,
        "registered_before_observing_results": False,
    }


def validate_conclusion(text: str, conclusion: str, validation: dict[str, Any]) -> None:
    """An estimate annotation cannot override explicit significance wording."""
    negative_spans = [
        match.span()
        for match in re.finditer(
            r"\b(?:(?:not|no)\s+(?:(?:a|any)\s+)?(?:statistically\s+)?significant"
            r"|non[-\s]?significant|(?:statistically\s+)?insignificant)\b",
            text,
            re.I,
        )
    ]
    positive = any(
        not any(start <= match.start() and match.end() <= end for start, end in negative_spans)
        for match in re.finditer(r"\b(?:statistically\s+)?significant\b", text, re.I)
    )
    if (positive and conclusion != "significant") or (
        negative_spans and conclusion != "not_significant"
    ):
        raise ValueError("printed significance conclusion disagrees with the claim ledger")
    if conclusion == "estimate":
        return
    if not validation.get("validated"):
        raise ValueError("significance conclusions require a registered method-specific validator")
    significant = validation["p_value"] < validation["alpha"]
    if significant != (conclusion == "significant"):
        raise ValueError("executed analysis contradicts the claimed significance conclusion")


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def parse_reported_number(text: str) -> tuple[float, float]:
    """Bound arithmetic for untrusted manuscript lexemes; return value and rounding unit."""
    try:
        raw = Decimal(text)
        exponent = raw.as_tuple().exponent
        if (
            not isinstance(exponent, int)
            or not -324 <= exponent <= 308
            or len(raw.as_tuple().digits) > 400
        ):
            raise ValueError("reported number exceeds supported finite precision")
        value = float(raw)
        if not math.isfinite(value) or (value == 0 and raw != 0):
            raise ValueError(
                "reported number is not representable as a finite non-underflowing value"
            )
        return value, float(Decimal("0.5") * Decimal(10) ** exponent)
    except (DecimalException, OverflowError) as error:
        raise ValueError("reported number exceeds supported finite precision") from error


def validate_text_statistics(text: str, validation: dict[str, Any]) -> None:
    """Bind every labeled planned statistic; other quantitative claims need separate spans."""
    relation = r"(?P<relation><=|>=|<|>|=|≤|≥|\\leq?|\\geq?)"
    patterns = [
        (rf"\bp(?:[- ]?value)?\s*{relation}\s*(?P<number>{_NUMBER})", validation["p_value"]),
        (
            rf"\b(?:mean(?: paired)? difference|effect(?: size)?)\s*(?:is|of|:|=)?\s*(?P<number>{_NUMBER})",
            validation["mean_difference"],
        ),
    ]
    covered: set[tuple[int, int]] = set()
    for pattern, actual in patterns:
        for match in re.finditer(pattern, text, re.I):
            printed, tolerance = parse_reported_number(match.group("number"))
            comparison = match.groupdict().get("relation", "=")
            valid = {
                "=": abs(Decimal(str(actual)) - Decimal(str(printed))) <= Decimal(str(tolerance)),
                "<": actual < printed,
                ">": actual > printed,
                "<=": actual <= printed,
                ">=": actual >= printed,
                "≤": actual <= printed,
                "≥": actual >= printed,
                r"\le": actual <= printed,
                r"\leq": actual <= printed,
                r"\ge": actual >= printed,
                r"\geq": actual >= printed,
            }[comparison]
            if not valid:
                raise ValueError("printed statistical value disagrees with the executed analysis")
            covered.add(match.span("number"))
    numbers = {m.span() for m in re.finditer(rf"(?<![\w.]){_NUMBER}", text)}
    if numbers - covered:
        raise ValueError(
            "unbound number in statistical claim; use explicit p-value or mean difference labels and separate other quantitative spans"
        )
