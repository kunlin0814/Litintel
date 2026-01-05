# Escalation Logic (Shadow Judge)

## Overview

The pipeline uses a two-tier validation system to ensure scoring accuracy:

1. **Heuristic Checks (H1-H4)**: Deterministic rules that flag potentially problematic assessments
2. **Shadow Judge**: AI-powered second opinion that validates flagged papers

---

## Heuristic Triggers

| ID | Name | Trigger Condition | Config Key |
|----|------|-------------------|------------|
| H1 | Short Rationale | `WhyRelevant` < 50 chars | `min_rationale_length` |
| H2 | Ambiguous Score | Score in [70, 79] range | `score_range` |
| H3 | Text/Score Mismatch | High language + low score OR vice versa | `h3_high_score_thresh`, `h3_low_score_thresh` |
| H4 | High Reuse, Low Score | `ReuseScore` >= 4 but low relevance | `escalate_on_high_reuse` |
| H5 | High Tier 3+ Direct | Score >= 87 (direct to mini) | `escalate_min_score` |

**Config Example (`tier1_pca.yaml`):**
```yaml
escalation_triggers:
  score_range: [70, 79]       # H2
  min_rationale_length: 50    # H1
  escalate_on_high_reuse: 4   # H4
  h3_high_score_thresh: 80    # H3
  h3_low_score_thresh: 70     # H3
  escalate_min_score: 87      # H5
  retry_on_error: true
```

---

## Shadow Judge

When heuristics flag a paper (and full-text is available), Shadow Judge (`gpt-5-mini`) reviews:

### Input
- Raw paper sections (Abstract, Methods, Results)
- Nano's assessment (Score, WhyRelevant, StudySummary, ReuseScore)

### Decision Types

| Decision | Meaning | Action |
|----------|---------|--------|
| **PASS** | Nano's assessment is acceptable | Keep Nano's output |
| **DISAGREE** | Concerns exist but no proof | Keep Nano's + log for review |
| **OVERTURN** | Factual error with evidence | Replace with corrected output |

### Overturn Criteria (STRICT)

Shadow Judge can only OVERTURN if Nano made a **material factual error**:
- Claims an effect not supported by Results
- Universalizes a conditional finding
- Misstates direction or significance
- Contradicts Methods or controls
- Assigns high relevance without evidence
- Self-contradiction (e.g., "highly relevant" but Score < 70)

**NOT valid reasons to overturn:**
- Missing details (Nano's job is to be concise)
- Conservative scoring (acceptable)
- Vague language (acceptable)
- "I would score differently" (not valid)

### Evidence Requirement

To overturn, Shadow Judge must provide:
1. `quoted_evidence`: Exact quote from paper OR Nano's contradictory statements
2. `contradiction`: Explanation of the factual error
3. `error_type`: "paper_contradiction" or "internal_inconsistency"

---

## Guardrails

### 25% Overturn Rate Limit

If Shadow Judge overturn rate exceeds 25% (after 10+ papers), pipeline halts.

**Why?** High overturn rate suggests:
- System prompt needs refinement
- Scoring rubric is unclear
- Model version changed behavior

### Emergency Actions

When guardrail triggers:
1. Pipeline stops immediately
2. `ESCALATION_COUNTERFACTUALS` dumped to `logs/escalation_counterfactuals_{timestamp}_CRASHed.jsonl`
3. Human review required before resuming

---

## Logging

### Counterfactuals Log

All Shadow Judge decisions are logged to `ESCALATION_COUNTERFACTUALS`:

```json
{
  "pmid": "12345678",
  "nano_score": 75,
  "heuristic_signals": ["H2: ambiguous_score"],
  "shadow_judge_decision": "PASS",
  "shadow_judge_details": {...},
  "timestamp": "2025-01-04 21:30:00"
}
```

### DISAGREE Log

Separate log for DISAGREE cases (useful for rubric tuning):

```json
{
  "pmid": "87654321",
  "nano_score": 72,
  "heuristic_signals": ["H2: ambiguous_score", "H1: short_rationale"],
  "shadow_judge_details": {
    "decision": "DISAGREE",
    "error_type": null,
    "quoted_evidence": null,
    "contradiction": "Score seems low for spatial multiome study"
  }
}
```

---

## Output Files

| File | Contents |
|------|----------|
| `papers_tier1_validated.md` | Only Shadow Judge validated papers (PASS or DISAGREE) |
| `logs/escalation_counterfactuals_*.jsonl` | All Shadow Judge decisions |

---

## Recommendations

1. **Review DISAGREE cases regularly** - They indicate rubric edge cases
2. **Monitor overturn rate** - Sustained >10% suggests prompt issues
3. **Abstract-only skips Shadow Judge** - No Methods/Results to validate against
4. **Tune heuristics conservatively** - Fewer false positives = less cost
