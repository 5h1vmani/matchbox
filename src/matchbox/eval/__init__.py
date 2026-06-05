"""Evaluation harness for Matchbox.

Scoring ranking quality and CV-selection coverage are measured here so
that tuning the rubric weights (``shared/rubric.json``) and the selection
constants (``matching/select.py``) is evidence-based, not guesswork. See
``docs/product-thesis.md`` ("Eval harness first") and section 9 of
``docs/v0.4-design.md``.

Two public surfaces:

* :mod:`matchbox.eval.metrics` — pure ranking/coverage metrics.
* :mod:`matchbox.eval.harness` — runs scoring + selection over a labeled
  golden corpus and returns a metrics dict; also a ``main()`` CLI.

The harness never mutates the database and never writes a document. It
imports the production scoring and matching functions unchanged.
"""

from __future__ import annotations

__all__ = ["harness", "metrics"]
