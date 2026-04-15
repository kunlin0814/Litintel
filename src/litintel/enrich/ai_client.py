import os
import time
import json
import re
import logging
from typing import Dict, Any, Tuple, Optional, List
from pydantic import ValidationError

# Legacy generativeai imports removed - using unified google.genai sdk only
from google import genai
from google.genai import types

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from litintel.config import AIConfig, AIProvider
from litintel.enrich.schema import Tier1Record, Tier2Record

logger = logging.getLogger(__name__)

def _extract_json(raw: str) -> Dict[str, Any]:
    """Extract and parse JSON from AI response, handling markdown code blocks."""
    if not raw:
        return {}
    
    text = raw.strip()
    
    # Try to extract JSON from markdown code block
    # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
    code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    if code_block_match:
        text = code_block_match.group(1).strip()
    
    # Try to find JSON object directly
    # Look for first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode error: {e}. Raw (first 500): {raw[:500]}")
        return {}

# Global Clients (OpenAI client can be cached; Gemini client cached)
_OPENAI_CLIENT = None
_GEMINI_CLIENT = None

def _use_vertex_ai() -> bool:
    """Check if Vertex AI mode is enabled (default: True).

    Set USE_VERTEX_AI=false in env to fall back to API key mode.
    Vertex AI requires GCP_PROJECT_ID (and optionally GCP_LOCATION).
    API key mode requires GOOGLE_API_KEY.
    """
    return os.environ.get('USE_VERTEX_AI', 'true').lower() not in ('false', '0', 'no')

def _get_openai_client():
    global _OPENAI_CLIENT
    if not _OPENAI_CLIENT:
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not set")
        _OPENAI_CLIENT = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _OPENAI_CLIENT

def _get_gemini_client():
    """Return a cached google-genai Client.

    Default: Vertex AI mode (enterprise license, data not used for training).
      Requires: GCP_PROJECT_ID env var, ADC credentials (gcloud auth).
      Optional: GCP_LOCATION env var (default: us-central1).

    Fallback: API key mode (set USE_VERTEX_AI=false).
      Requires: GOOGLE_API_KEY env var.
    """
    global _GEMINI_CLIENT
    if not _GEMINI_CLIENT:
        if _use_vertex_ai():
            project = os.environ.get('GCP_PROJECT_ID')
            if not project:
                raise ValueError(
                    'GCP_PROJECT_ID not set. Required for Vertex AI mode. '
                    'Set USE_VERTEX_AI=false to use API key instead.'
                )
            location = os.environ.get('GCP_LOCATION', 'us-central1')
            _GEMINI_CLIENT = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
            logger.info('Gemini client initialized via Vertex AI (project=%s, location=%s)', project, location)
        else:
            api_key = os.environ.get('GOOGLE_API_KEY')
            if not api_key:
                raise ValueError('GOOGLE_API_KEY not set (API key mode)')
            _GEMINI_CLIENT = genai.Client(api_key=api_key)
            logger.info('Gemini client initialized via API key')
    return _GEMINI_CLIENT


def _call_gemini(
    client: genai.Client,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: Dict[str, Any],
    thinking_level: str = "MEDIUM"
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    
    # We pass the JSON schema to the Gemini API
    # Note: If pydantic schema is passed, genai supports it directly, but here we assume Dict
    # Thinking level is now explicitly passed per model via YAML config
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.1,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_level=thinking_level,
        ),
    )
    # We do not have structured outputs strict guarantee for complex dicts like OpenAI json_schema,
    # but application/json usually works well enough if the schema is printed in the prompt, or if we pass response_schema.
    # Note: google-genai supports response_schema
    if schema:
       config.response_schema = schema

    try:
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=config
        )
        raw_json = response.text
        
        usage = {
            "input": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
            "output": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
            "cached": response.usage_metadata.cached_content_token_count if getattr(response.usage_metadata, 'cached_content_token_count', None) else 0,
            "thinking": getattr(response.usage_metadata, 'thoughts_token_count', 0) or 0
        }
        
        logger.debug(f"Gemini raw response ({model}, thinking={thinking_level}): {raw_json[:500] if raw_json else ''}...")
        return _extract_json(raw_json), usage
        
    except Exception as e:
        # Simple Rate Limit Retry Logic
        if "429" in str(e) or "quota" in str(e).lower() or "rate limit" in str(e).lower():
            logger.warning(f"Gemini 429 Rate Limit. Retrying {model}...")
            time.sleep(2)
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=config
            )
            raw_json = response.text
            usage = {
                "input": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "output": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                "cached": 0 
            }
            logger.debug(f"Gemini raw response after retry ({model}): {raw_json[:500] if raw_json else ''}...")
            return _extract_json(raw_json), usage
        raise e

def _call_openai(
    client: OpenAI, 
    model: str, 
    system_prompt: str, 
    user_prompt: str,
    schema: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    
    # Construct JSON schema for OpenAI
    # Note: strict=True mode has limitations with complex pydantic schemas
    # Using json_object mode instead for compatibility
    params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {
            "type": "json_object"  # Use json_object instead of strict json_schema
        }
    }
    if not model.startswith("gpt-5"):
        params["temperature"] = 0.1

    try:
        response = client.chat.completions.create(**params)
        raw_json = response.choices[0].message.content
        
        # Usage extraction
        u = response.usage
        output_tokens = u.completion_tokens
        input_tokens = u.prompt_tokens
        cached_tokens = 0
        
        # Extract cached tokens (OpenAI specific field)
        if hasattr(u, 'prompt_tokens_details') and u.prompt_tokens_details:
            cached_tokens = getattr(u.prompt_tokens_details, 'cached_tokens', 0)

        usage = {
            "input": input_tokens, 
            "output": output_tokens, 
            "cached": cached_tokens
        }
        
        logger.debug(f"OpenAI raw response ({model}): {raw_json[:500]}...")
        return _extract_json(raw_json), usage
    except Exception as e:
        # Simple Rate Limit Retry Logic
        if "429" in str(e) or "rate limit" in str(e).lower():
            logger.warning(f"OpenAI 429 Rate Limit. Retrying {model}...")
            time.sleep(2)
            response = client.chat.completions.create(**params)
            raw_json = response.choices[0].message.content
            
            u = response.usage
            usage = {
                "input": u.prompt_tokens,
                "output": u.completion_tokens,
                "cached": 0 # simplified retry
            }
            logger.debug(f"OpenAI raw response after retry ({model}): {raw_json[:500]}...")
            return _extract_json(raw_json), usage
        raise e

def _should_escalate_upfront(text: str, config: AIConfig, pmid: str) -> bool:
    """Check if complexity triggers warrant upfront escalation to better model."""
    if not config.escalation_triggers:
        return False
        
    t = config.escalation_triggers
    
    # 1. Length Check - use getattr for Pydantic model
    min_chars = getattr(t, 'min_chars', None) or 100000
    if len(text) > min_chars:
        logger.info(f"PMID {pmid}: Escalating - Text length {len(text)} > {min_chars}")
        return True
        
    # 2. Modality Count
    min_mod = getattr(t, 'min_modalities', None) or 99
    mod_kw = getattr(t, 'modality_keywords', []) or []
    if mod_kw:
        # Simple string check (case-insensitive)
        text_lower = text.lower()
        found_count = sum(1 for kw in mod_kw if kw.lower() in text_lower)
        if found_count >= min_mod:
            logger.info(f"PMID {pmid}: Escalating - Found {found_count} modalities (threshold {min_mod})")
            return True
            
    # 3. Complexity Keywords (not in typed config, but support for backwards compat)
    comp_kw = getattr(t, 'complexity_keywords', []) or []
    if comp_kw:
        text_lower = text.lower()
        for kw in comp_kw:
            if kw.lower() in text_lower:
                logger.info(f"PMID {pmid}: Escalating - Found complexity keyword '{kw}'")
                return True
                
    return False


# Key normalization map: lowercase -> canonical CamelCase
_KEY_MAP = {
    "relevancescore": "RelevanceScore",
    "whyrelevant": "WhyRelevant",
    "whyyoumightcare": "WhyYouMightCare",
    "studysummary": "StudySummary",
    "paperrole": "PaperRole",
    "theme": "Theme",
    "methods": "Methods",
    "keyfindings": "KeyFindings",
    "datatypes": "DataTypes",
    "group": "Group",
    "group (pi / lab)": "Group",
    "cellidentitysignatures": "CellIdentitySignatures",
    "perturbationsused": "PerturbationsUsed",
    "geo_validated": "GEO_Validated",
    "sra_validated": "SRA_Validated",
    "geo/sra validation": "GEO_Validated",
    "geo sra validation": "GEO_Validated",
    "pipelineconfidence": "PipelineConfidence",
}

def _normalize_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize AI output keys to canonical schema names."""
    out = {}
    for k, v in d.items():
        canonical = _KEY_MAP.get(k.lower().strip(), k)
        out[canonical] = v
    return out

def _coerce_relevance_score(score_value: Any) -> Tuple[int, bool]:
    """Return an int score (default 0) and flag if coercion failed."""
    if score_value is None:
        return 0, True
    try:
        coerced = int(score_value)
        return coerced, False
    except (TypeError, ValueError):
        return 0, True

SHADOW_JUDGE_PROMPT = """PMID: {pmid}

=== RAW PAPER DATA ===
ABSTRACT:
{abstract}

METHODS:
{methods}

RESULTS:
{results}

=== NANO'S ASSESSMENT (model-generated) ===
RelevanceScore: {nano_score}
WhyRelevant: {nano_why}
StudySummary: {nano_summary}
ReuseScore: {nano_reuse}

=== YOUR TASK ===
You are auditing Nano's assessment. You have STRICT rules:

OVERTURN ONLY IF Nano made a MATERIAL FACTUAL ERROR:
- Claims an effect not supported by Results
- Universalizes a conditional finding
- Misstates direction or significance
- Contradicts Methods or controls
- Assigns high relevance without evidence
- Contradicts itself (e.g., WhyRelevant uses strong positive language like "highly relevant" but RelevanceScore < 70, OR uses dismissive language but RelevanceScore > 85)

DO NOT OVERTURN FOR:
- Missing details (Nano's job is to be concise)
- Conservative scoring (acceptable)
- Vague language (acceptable)
- "I would score differently" (not a valid reason)

If you cannot cite specific evidence (quote from paper OR Nano's self-contradiction), you MUST output PASS.

Answer with JSON:
{{
  "decision": "PASS" | "DISAGREE" | "OVERTURN",
  "error_type": "paper_contradiction" | "internal_inconsistency" | null,
  "quoted_evidence": "exact quote from paper OR Nano's contradictory statements",
  "contradiction": "explanation of factual error"
}}
"""

# Module-level tracking for rate guardrail
SHADOW_JUDGE_STATS = {"total": 0, "overturn": 0, "disagree": 0, "pass": 0}

def check_overturn_rate() -> Tuple[bool, float]:
    """Returns (is_too_high, rate). Threshold > 25%."""
    if SHADOW_JUDGE_STATS["total"] < 10:
        return False, 0.0
    rate = SHADOW_JUDGE_STATS["overturn"] / SHADOW_JUDGE_STATS["total"]
    return rate > 0.25, rate

def _shadow_judge(
    client: OpenAI,
    nano_output: Dict[str, Any],
    abstract: str,
    methods: str,
    results: str,
    pmid: str,
    model: str = "gpt-5-mini"
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Shadow Judge: validates Nano using raw paper sections.
    Returns (should_escalate, decision, details_dict).
    """
    nano_score = nano_output.get('RelevanceScore')
    nano_why = nano_output.get('WhyRelevant', '')[:400]
    nano_summary = nano_output.get('StudySummary', '')[:400]
    nano_reuse = "N/A"
    comp = nano_output.get('comp_methods')
    if isinstance(comp, dict):
        nano_reuse = comp.get('reuse_score_0to5', 'N/A')
        
    prompt = SHADOW_JUDGE_PROMPT.format(
        pmid=pmid,
        abstract=abstract[:20000],
        methods=methods[:20000],
        results=results[:20000],
        nano_score=nano_score,
        nano_why=nano_why,
        nano_summary=nano_summary,
        nano_reuse=nano_reuse
    )
    
    try:
        # Build params - gpt-5 models don't support custom temperature
        params = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        if not model.startswith("gpt-5"):
            params["temperature"] = 0  # Deterministic for non-gpt-5 models
            
        response = client.chat.completions.create(**params)
        result = json.loads(response.choices[0].message.content)
        
        decision = result.get("decision", "PASS").upper()
        
        # Update stats
        SHADOW_JUDGE_STATS["total"] += 1
        if decision == "OVERTURN":
            SHADOW_JUDGE_STATS["overturn"] += 1
        elif decision == "DISAGREE":
            SHADOW_JUDGE_STATS["disagree"] += 1
        else:
            SHADOW_JUDGE_STATS["pass"] += 1
            
        # Check guardrail
        too_high, rate = check_overturn_rate()
        if too_high:
            # EMERGENCY DUMP
            try:
                import pathlib
                logs_dir = pathlib.Path("logs")
                logs_dir.mkdir(exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                log_file = logs_dir / f"escalation_counterfactuals_{timestamp}_CRASHed.jsonl"
                with open(log_file, "w") as f:
                    for entry in ESCALATION_COUNTERFACTUALS:
                        f.write(json.dumps(entry) + "\n")
                logger.error(f"EMERGENCY DUMP: Saved logs to {log_file}")
            except Exception as dump_err:
                logger.error(f"Failed emergency dump: {dump_err}")
                
            logger.critical(f"Shadow Judge overturn rate {rate:.1%} exceeds 25% limit. Stopping.")
            raise RuntimeError(f"Shadow Judge overturn rate {rate:.1%} > 25%. Stopping for human review.")

        # Escalation criteria: OVERTURN + evidence
        has_evidence = bool(result.get("quoted_evidence"))
        should_escalate = (decision == "OVERTURN" and has_evidence)
        
        return should_escalate, decision, result
        
    except RuntimeError:
        raise  # Propagate the guardrail stop
    except Exception as e:
        logger.warning(f"Shadow Judge failed for {pmid}: {e}")
        return False, "ERROR", {"error": str(e)}

# Counterfactual logging
ESCALATION_COUNTERFACTUALS = []

def _log_counterfactual(pmid: str, nano_output: dict, signals: list, decision: str, judge_details: dict):
    """Log cases where heuristics flagged but Judge declined."""
    ESCALATION_COUNTERFACTUALS.append({
        "pmid": pmid,
        "nano_score": nano_output.get("RelevanceScore"),
        "heuristic_signals": signals,
        "shadow_judge_decision": decision,
        "shadow_judge_details": judge_details,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })

def get_escalation_counterfactuals() -> List[Dict[str, Any]]:
    """Return the list of counterfactual logs."""
    return ESCALATION_COUNTERFACTUALS

# DISAGREE cases - separate log for tuning rubric
ESCALATION_DISAGREE_LOG = []

def _log_disagree(pmid: str, nano_output: dict, signals: list, judge_details: dict):
    """Log cases where Shadow Judge disagreed but couldn't prove overturn."""
    ESCALATION_DISAGREE_LOG.append({
        "pmid": pmid,
        "nano_score": nano_output.get("RelevanceScore"),
        "heuristic_signals": signals,
        "shadow_judge_details": judge_details,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })

def get_disagree_log() -> List[Dict[str, Any]]:
    """Return the list of DISAGREE cases."""
    return ESCALATION_DISAGREE_LOG


def enrich_record(
    text: str,
    authors: str,
    pmid: str,
    config: AIConfig,
    system_prompt: str,
    json_schema: Dict[str, Any],
    pydantic_model: Any, 
    group_fallback: str = "",
    geo_candidates: str = "",
    sra_candidates: str = "",
    abstract: str = "",     # NEW
    methods_text: str = "", # NEW
    results_text: str = ""  # NEW
) -> Dict[str, Any]:
    
    # -------------------------------------------------------------------------
    # DECISION: SINGLE-PASS vs TWO-PASS
    # -------------------------------------------------------------------------
    use_two_pass = (
        getattr(config, 'pass1_model_fulltext', None) is not None 
        and getattr(config, 'pass1_model_abstract', None) is not None
    )
    
    has_full_text = bool(methods_text.strip() or results_text.strip())
    
    # -------------------------------------------------------------------------
    # PASS 1: SCORING & METADATA
    # -------------------------------------------------------------------------
    
    # Select Model for Pass 1
    model_to_use = config.model_default # Fallback
    
    if use_two_pass:
        if has_full_text:
            model_to_use = config.pass1_model_fulltext
        else:
            model_to_use = config.pass1_model_abstract
    else:
        # Legacy Logic (Single Pass escalation)
        if _should_escalate_upfront(text, config, pmid):
            model_to_use = config.model_escalate
            
    # Prepare Prompt for Pass 1
    # Note: system_prompt passed in is now _TIER1_PCA_SCORING_INSTRUCTION (if updated in main)
    # Inject fallback into prompt
    final_system_prompt = system_prompt.replace("{group_fallback}", group_fallback)
    
    user_prompt = f"PMID: {pmid}\nAuthors: {authors}\nGroupFallbackCandidate: {group_fallback}\n"
    if geo_candidates or sra_candidates:
        user_prompt += "\n--- ACCESSION VALIDATION ---\n"
        if geo_candidates: user_prompt += f"GEO_Candidates (found via regex): {geo_candidates}\n"
        if sra_candidates: user_prompt += f"SRA_Candidates (found via regex): {sra_candidates}\n"
        user_prompt += "Validate what matches.\n"
        
    user_prompt += f"\nTEXT_START\n{text}\nTEXT_END\n"

    # Execution Pass 1
    provider = config.provider
    result_json = {}
    
    # --- CALL API (Pass 1) ---
    try:
        if provider == AIProvider.OPENAI:
            client = _get_openai_client()
            logger.info(f"PMID {pmid} [Pass 1] Scoring with {model_to_use} (FullText={has_full_text})...")
            
            try:
                result_json, usage = _call_openai(client, model_to_use, final_system_prompt, user_prompt, json_schema)
                
                # Log usage
                cached_pct = 0.0
                if usage.get("input", 0) > 0:
                    cached_pct = (usage.get("cached", 0) / usage.get("input")) * 100
                logger.info(f"PMID {pmid} [Pass 1] Usage: In={usage.get('input')} (Cached {usage.get('cached')} / {cached_pct:.1f}%), Out={usage.get('output')}, Thinking={usage.get('thinking', 0)}")
                
            except Exception as e:
                # Simple retry with escalation model if in legacy single-pass mode
                logger.error(f"PMID {pmid} [Pass 1] Failed: {e}")
                if not use_two_pass and config.escalation_triggers and config.escalation_triggers.retry_on_error:
                    logger.warning(f"Retrying with {config.model_escalate}...")
                    result_json, _ = _call_openai(client, config.model_escalate, final_system_prompt, user_prompt, json_schema)
                else:
                    raise e
        elif provider == AIProvider.GEMINI:
            client = _get_gemini_client()
            # Resolve thinking level from config
            if use_two_pass:
                if has_full_text:
                    pass1_thinking = getattr(config, 'pass1_thinking_fulltext', None) or 'MEDIUM'
                else:
                    pass1_thinking = getattr(config, 'pass1_thinking_abstract', None) or 'MEDIUM'
            else:
                pass1_thinking = 'MEDIUM'
            logger.info(f"PMID {pmid} [Pass 1] Scoring with Gemini {model_to_use} (FullText={has_full_text}, Thinking={pass1_thinking})...")
            try:
                result_json, usage = _call_gemini(client, model_to_use, final_system_prompt, user_prompt, json_schema, thinking_level=pass1_thinking)
                
                # Log usage
                cached_pct = 0.0
                if usage.get("input", 0) > 0:
                    cached_pct = (usage.get("cached", 0) / usage.get("input")) * 100
                logger.info(f"PMID {pmid} [Pass 1] Usage: In={usage.get('input')} (Cached {usage.get('cached')} / {cached_pct:.1f}%), Out={usage.get('output')}, Thinking={usage.get('thinking', 0)}")
                
            except Exception as e:
                logger.error(f"PMID {pmid} [Pass 1] Failed with Gemini: {e}")
                if not use_two_pass and config.escalation_triggers and config.escalation_triggers.retry_on_error:
                    logger.warning(f"Retrying with escalation model {config.model_escalate}...")
                    result_json, _ = _call_gemini(client, config.model_escalate, final_system_prompt, user_prompt, json_schema, thinking_level=pass1_thinking)
                else:
                    raise e
        else:
            raise ValueError(f"Unknown provider: {provider}")

        # Normalize Keys & Coerce Score (Crucial for Pass 2 decision)
        result_json = _normalize_keys(result_json)
        score, _ = _coerce_relevance_score(result_json.get("RelevanceScore"))
        result_json["RelevanceScore"] = score
        
        # -------------------------------------------------------------------------
        # PASS 2: METHODS EXTRACTION (DEFERRED FOR BATCHING)
        # -------------------------------------------------------------------------
        # Pass 2 is now executed as a separate phase in tier1.py to maximize cache efficiency.
        # We just mark eligibility here.
        if use_two_pass and has_full_text:
            threshold = getattr(config, 'pass2_min_score', 88)
            if score >= threshold:
                result_json["_pass2_eligible"] = True
                logger.info(f"PMID {pmid}: Score {score} >= {threshold}. Marked for Pass 2 (batched).")
            else:
                result_json["_pass2_eligible"] = False
                logger.info(f"PMID {pmid}: Score {score} < {threshold}. Skipping Pass 2.")

        # Note: Shadow Judge / Heuristic escalation logic removed.
        # With Two-Pass Architecture, full-text papers already use gpt-5-mini directly,
        # making the Nano->Mini escalation validation unnecessary.
        result_json["EscalationTriggered"] = False

        # Calculate PipelineConfidence based on evidence and processing
        # High: Full-text + high score + no heuristic escalation triggered
        # Medium: Full-text OR (Abstract + high score)
        # Medium-Ambiguous: Abstract + escalation triggered (heuristic flagged)
        # Low: Abstract-only + low score
        score = result_json.get("RelevanceScore", 0)
        escalation_triggered = result_json.get("EscalationTriggered", False)
        
        if has_full_text:
            if score >= 80 and not escalation_triggered:
                calculated_confidence = "High"
            elif score >= 70:
                calculated_confidence = "Medium"
            else:
                calculated_confidence = "Low"
        else:
            # Abstract-only
            if escalation_triggered:
                calculated_confidence = "Medium-Ambiguous"
            elif score >= 85:
                calculated_confidence = "Medium"
            else:
                calculated_confidence = "Low"
        
        result_json["PipelineConfidence"] = calculated_confidence

        # Ensure AI-specific fields have defaults
        ai_field_defaults = {
            "RelevanceScore": 0,
            "WhyRelevant": "",
            "WhyYouMightCare": "",
            "StudySummary": "",
            "PaperRole": "",
            "Theme": "",
            "Methods": "",
            "KeyFindings": "",
            "DataTypes": "",
            "Group": "",
            "CellIdentitySignatures": "",
            "PerturbationsUsed": "",
            "GEO_Validated": "",
            "SRA_Validated": "",
            # Note: PipelineConfidence already set above, no default needed
        }
        
        for field, default in ai_field_defaults.items():
            if field not in result_json:
                result_json[field] = default

        return result_json


    except Exception as e:
        logger.error(f"Enrichment failed for {pmid}: {e}")
        return {"RelevanceScore": -1, "WhyRelevant": f"Error: {str(e)}", "PipelineConfidence": "Error"}


def enrich_pass2_methods(
    pmid: str,
    methods_text: str,
    results_text: str,
    config: AIConfig
) -> Dict[str, Any]:
    """
    Standalone Pass 2: Methods Extraction.
    
    Call this AFTER all Pass 1 scoring is complete to maximize prompt caching.
    Returns the comp_methods object to be merged into the main record.
    """
    if not methods_text.strip() and not results_text.strip():
        logger.warning(f"PMID {pmid} [Pass 2] No methods/results text provided.")
        return {}
    
    from litintel.enrich.prompt_templates import _TIER1_PCA_METHODS_INSTRUCTION
    methods_system_prompt = _TIER1_PCA_METHODS_INSTRUCTION
    methods_model = getattr(config, 'pass2_model', config.model_escalate)
    
    # Construct Methods-Specific User Prompt (Methods + Results sections)
    methods_user_prompt = f"PMID: {pmid}\nAnalyze these sections for computational methods:\n\n"
    methods_user_prompt += f"=== METHODS ===\n{methods_text}\n\n"
    methods_user_prompt += f"=== RESULTS ===\n{results_text}\n"
    
    try:
        provider = config.provider
        
        if provider == AIProvider.OPENAI:
            client = _get_openai_client()
            logger.info(f"PMID {pmid} [Pass 2] Methods extraction with {methods_model}...")
            methods_json, m_usage = _call_openai(client, methods_model, methods_system_prompt, methods_user_prompt, {})
        elif provider == AIProvider.GEMINI:
            client = _get_gemini_client()
            pass2_thinking = getattr(config, 'pass2_thinking', None) or 'LOW'
            logger.info(f"PMID {pmid} [Pass 2] Methods extraction with Gemini {methods_model} (Thinking={pass2_thinking})...")
            methods_json, m_usage = _call_gemini(client, methods_model, methods_system_prompt, methods_user_prompt, {}, thinking_level=pass2_thinking)
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        cached_pct = 0.0
        if m_usage.get("input", 0) > 0:
            cached_pct = (m_usage.get("cached", 0) / m_usage.get("input")) * 100
        logger.info(f"PMID {pmid} [Pass 2] Usage: In={m_usage.get('input')} (Cached {m_usage.get('cached')} / {cached_pct:.1f}%), Out={m_usage.get('output')}, Thinking={m_usage.get('thinking', 0)}")
        
        # Return just the comp_methods portion
        if "comp_methods" in methods_json:
            return {"comp_methods": methods_json["comp_methods"]}
        else:
            logger.warning(f"PMID {pmid} [Pass 2] returned no 'comp_methods' key.")
            return {}
            
    except Exception as e:
        logger.error(f"PMID {pmid} [Pass 2] Failed: {e}")
        return {"comp_methods_error": str(e)}
