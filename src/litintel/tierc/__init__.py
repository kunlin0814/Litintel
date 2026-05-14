"""Tier C: figure-grounded multimodal PDF enrichment.

Triggered when (a) a Tier 1 paper scores >= min_score and has a PMC OA PDF, or
(b) a PDF sits in the manual inbox and its PMID is not yet in Notion.

Produces an Evidence Map (figures, anchors, methods), a Synthesis anchored to
the map, and a Verification report. See plan: elegant-roaming-sutton.md.
"""
