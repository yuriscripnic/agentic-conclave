"""Harness-level errors (spec §5): misuse of the evaluation harness itself."""

from __future__ import annotations


class EvaluationError(RuntimeError):
    """Unknown scenario, bad provider, bad repeat count, or unwritable output dir."""