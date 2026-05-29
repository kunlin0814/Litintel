import os
import time
import json
import re
from typing import Any, Dict, List, Tuple
from google.api_core.exceptions import ResourceExhausted

import google.generativeai as genai
from prefect import task, get_run_logger

# Module-level API client initialization (reused across all calls)
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

from modules.prompts import get_system_instruction

# Global model cache
_GEMINI_MODEL = None


def _extract_last_author(authors_str: str) -> str:
    """Extract last author from author list for Group fallback."""
    if not authors_str or authors_str == "No authors listed":
        return ""
    # Split by common delimiters
    parts = authors_str.replace(" and ", ", ").split(", ")
    if parts:
        # Get last author, clean up common suffixes
        last = parts[-1].strip()
        # Remove common patterns like "et al."
        if "et al" in last.lower():
            # If there's "et al.", use the previous author if available
            # Otherwise extract the part before "et al."
            if len(parts) > 1:
                last = parts[-2].strip()
            else:
                # Single element like "Smith J et al."
                last = last.split("et al")[0].strip()
        return last
    return ""


def _extract_json_text(resp: Any) -> str:
    """Pull best-effort JSON text out of a Gemini response."""
    raw = (getattr(resp, "text", None) or "").strip()
    if not raw and getattr(resp, "candidates", None):
        # Fall back to concatenating candidate part texts.
        for cand in resp.candidates:
            parts = getattr(cand, "content", None)
            if not parts or not getattr(parts, "parts", None):
                continue
            texts = [p.text for p in parts.parts if getattr(p, "text", None)]
            if texts:
                raw = "".join(texts).strip()
                break
    # Strip Markdown fences if present
    if raw.startswith("```json"):
        raw = raw[len("```json"):].strip()
    elif raw.startswith("```"):
        raw = raw[len("```"):].strip()
    if raw.endswith("```"):
        raw = raw[:-len("```")].strip()
    return raw


def _load_response_json(raw: str) -> Dict[str, Any]:
    """Attempt to parse JSON even if Gemini wraps it in prose/code fences.

    If we have to repair obviously truncated JSON (unterminated string / braces),
    we add a special marker key ``"__TRUNCATED__"`` so callers can downgrade
    confidence or tag the record.
    """
    if not raw:
        return {}
    
    # Try direct parsing first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # DANGEROUS REGEX REMOVED per valid feedback.
    # It was capturing inner objects ({...}) instead of the full JSON.
    # We rely on the brace-balancer below.

    # Improved: try to find and extract just the JSON structure
    # Look for balanced braces
    # Prefer starting at a proper JSON object (not arbitrary text with braces)
    brace_count = 0
    start_idx = raw.find('{"RelevanceScore"')
    if start_idx == -1:
        start_idx = raw.find('{')
    if start_idx != -1:
        for i in range(start_idx, len(raw)):
            if raw[i] == '{':
                brace_count += 1
            elif raw[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    try:
                        return json.loads(raw[start_idx:i+1])
                    except json.JSONDecodeError:
                        pass
                    break
    
    # Attempt to repair truncated JSON
    # This is a best-effort heuristic for common truncation patterns
    try:
        # If it looks like a truncated string inside a JSON
        # e.g. {"key": "valu
        # We can try to close it.
        repaired = raw.strip()
        # If it doesn't end with '}', try to close the last open string and object
        if not repaired.endswith('}'):
            # Count quotes to see if we are inside a string
            # This is a naive check, doesn't handle escaped quotes perfectly but might suffice
            quote_count = repaired.count('"')
            if quote_count % 2 == 1:
                repaired += '"'
            
            # Count braces to see how many to close
            open_braces = repaired.count('{')
            close_braces = repaired.count('}')
            repaired += '}' * (open_braces - close_braces)

            obj = json.loads(repaired)
            # Mark that we had to repair a truncation so callers can react.
            if isinstance(obj, dict):
                obj["__TRUNCATED__"] = True
            return obj
    except (json.JSONDecodeError, Exception):
        pass

    # Last resort: return empty dict and log the error
    # We re-raise to let the caller handle logging/fallback if they want, 
    # or we can just raise ValueError as before.
    # The original code raised ValueError with the original error.
    # We will try to provide a helpful message.
    raise ValueError(f"Could not parse JSON from response. Raw (first 500 chars): {raw[:500]}")


def _call_gemini_api(user_prompt: str, logger, system_instruction: str) -> Tuple[Dict[str, Any], int]:
    """Call Gemini API and return parsed JSON response."""
    global _GEMINI_MODEL
    
    # Note: re-initializing model if instruction changes is needed for Gemini
    # but for now we assume one instruction per run or acceptable overhead
    if _GEMINI_MODEL is None or _GEMINI_MODEL._system_instruction != system_instruction:
        response_schema = {
            "type": "OBJECT",
            "properties": {
                "RelevanceScore": {"type": "INTEGER"},
                "ReuseScore": {"type": "INTEGER"},
                "WhyRelevant": {"type": "STRING"},
                "StudySummary": {"type": "STRING"},
                "PaperRole": {"type": "STRING"},
                "Theme": {"type": "STRING"},
                "Methods": {"type": "STRING"},
                "KeyFindings": {"type": "STRING"},
                "DataTypes": {"type": "STRING"},
                "Group": {"type": "STRING"},
                "CellIdentitySignatures": {"type": "STRING"},
                "PerturbationsUsed": {"type": "STRING"},
            },
            "required": [
                "RelevanceScore",
                "ReuseScore",
                "WhyRelevant",
                "StudySummary",
                "PaperRole",
                "Theme",
                "Methods",
                "KeyFindings",
                "DataTypes",
                "Group",
                "CellIdentitySignatures",
                "PerturbationsUsed",
            ],
        }
        
        _GEMINI_MODEL = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction,
            generation_config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            },
        )
    
    resp = _GEMINI_MODEL.generate_content(user_prompt)
    raw_json = _extract_json_text(resp)
    
    # Estimate output tokens
    estimated_output_tokens = len(raw_json) // 4
    
    return _load_response_json(raw_json), estimated_output_tokens


def _call_openai_api(user_prompt: str, logger, system_instruction: str, model_name: str = "gpt-5-nano") -> Tuple[Dict[str, Any], int]:
    """Call OpenAI Chat Completions API with strict schema enforcement."""
    # Use module-level client (reused across all calls)
    if _OPENAI_CLIENT is None:
        raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY environment variable.")
    
    # Define strict JSON schema matching Gemini's response_schema
    json_schema = {
        "name": "paper_enrichment_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "RelevanceScore": {
                    "type": "integer",
                    "description": "Relevance score from 0-100"
                },
                "ReuseScore": {
                    "type": "integer",
                    "description": "Data/method reusability score from 1-5"
                },
                "WhyRelevant": {
                    "type": "string",
                    "description": "1 sentence explaining the score"
                },
                "StudySummary": {
                    "type": "string",
                    "description": "2-3 sentences about aim, system/cohort, main result"
                },
                "PaperRole": {
                    "type": "string",
                    "description": "1 sentence conceptual summary of role"
                },
                "Theme": {
                    "type": "string",
                    "description": "Semi-colon separated controlled topic tags"
                },
                "Methods": {
                    "type": "string",
                    "description": "Experimental platforms and computational tools"
                },
                "KeyFindings": {
                    "type": "string",
                    "description": "Concise bullet-like points separated by ;"
                },
                "DataTypes": {
                    "type": "string",
                    "description": "Comma-separated assays"
                },
                "Group": {
                    "type": "string",
                    "description": "Principal Investigator or Lab Name"
                },
                "CellIdentitySignatures": {
                    "type": "string",
                    "description": "Explicitly stated cell type markers"
                },
                "PerturbationsUsed": {
                    "type": "string",
                    "description": "Genetic or chemical manipulations"
                }
            },
            "required": [
                "RelevanceScore",
                "ReuseScore",
                "WhyRelevant",
                "StudySummary",
                "PaperRole",
                "Theme",
                "Methods",
                "KeyFindings",
                "DataTypes",
                "Group",
                "CellIdentitySignatures",
                "PerturbationsUsed"
            ],
            "additionalProperties": False
        }
    }
    
    # Build API parameters
    params: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": json_schema
        }
    }
    
    # Only non-GPT-5 models support custom temperature
    if not model_name.startswith("gpt-5"):
        params["temperature"] = 0.1
    
    response = _OPENAI_CLIENT.chat.completions.create(**params)
    
    raw_json = response.choices[0].message.content
    output_tokens = response.usage.completion_tokens
    input_tokens = response.usage.prompt_tokens
    
    # Extract cached tokens if available (OpenAI returns this for cache hits)
    cached_tokens = getattr(response.usage, 'prompt_tokens_details', None)
    if cached_tokens and hasattr(cached_tokens, 'cached_tokens'):
        cached_tokens = cached_tokens.cached_tokens
    else:
        cached_tokens = 0
    
    return json.loads(raw_json), output_tokens, input_tokens, cached_tokens


@task(retries=2, retry_delay_seconds=30)
def ai_enrich_records(
    records: List[Dict[str, Any]],
    efetch_data: Dict[str, Dict[str, Any]],
    pmc_fulltext_map: Dict[str, Dict[str, Any]],
    cfg: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    logger = get_run_logger()
    
    # Get provider from config (default to gemini for backward compatibility)
    if cfg is None:
        from modules.config import get_config
        cfg = get_config()
    
    provider = cfg.get("AI_PROVIDER", "gemini").lower()
    
    # Check API keys
    if provider == "gemini":
        if not os.environ.get("GOOGLE_API_KEY"):
            logger.warning("GOOGLE_API_KEY not set; skipping enrichment.")
            return records
        logger.info("Using Gemini API for enrichment")
    elif provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            logger.warning("OPENAI_API_KEY not set; skipping enrichment.")
            return records
        
        # Configuration for Nano-First Strategy
        DEFAULT_MODEL = "gpt-5-nano"
        ESCALATION_MODEL = "gpt-5-mini"
        logger.info(f"Using OpenAI API (Default: {DEFAULT_MODEL} -> Escalate: {ESCALATION_MODEL})")
    else:
        logger.error(f"Unknown AI_PROVIDER: {provider}. Use 'gemini' or 'openai'.")
        return records

    
    # -------------------------------------------------------------------------
    # PROMPT SELECTION
    # -------------------------------------------------------------------------
    template_name = cfg.get("ai", {}).get("prompt_template", "tier1_pca")
    system_instruction = get_system_instruction(template_name)
    logger.info(f"Loaded system instruction template: {template_name} ({len(system_instruction)} chars)")

    KNOWN_DATA_TYPES = {
        "scrna-seq",
        "scatac-seq",
        "scdna",
        "spatial transcriptomics",
        "10x visium",
        "xenium",
        "cosmx",
        "geomx",
        "slide-seq",
        "h&e",
        "wgs",
        "wes",
        "bulk rna-seq",
        "chip-seq",
        "atac-seq",
        "cite-seq",
        "multiome",
        "multi-omics",
        "cnv",
        "snrna-seq",
        "snatac-seq",
        "merfish",
        "seqfish",
    }

    enriched: List[Dict[str, Any]] = []
    
    # Token tracking for TPM monitoring
    total_input_tokens = 0
    total_output_tokens = 0
    total_cached_tokens = 0  
    
    # Per-model tracking: {model_name: {"input": 0, "output": 0, "cached": 0}}
    model_stats = {}
    
    start_time = time.time()
    
    for rec in records:
        pmid = str(rec.get("PMID", "")).strip()
        full_text_entry = pmc_fulltext_map.get(pmid)
        full_text_used = False
        if full_text_entry and full_text_entry.get("full_text"):
            # TEXT CAPPING: Prevent massive cost blowouts
            raw_full_text = full_text_entry["full_text"]
            MAX_CHARS = int(cfg.get("AI_MAX_CHARS", 80000))
            if len(raw_full_text) > MAX_CHARS:
                # Smart truncation: keep first half + last half
                # This captures intro AND methods/data availability
                half = MAX_CHARS // 2
                head = raw_full_text[:half]
                tail = raw_full_text[-half:]
                raw_full_text = head + "\n...[MIDDLE TRUNCATED]...\n" + tail
            
            text_to_analyze = (
                "Analysis based on Full Text (Abstract + Methods + Results + Data/Code Availability):\\n\\n"
                + raw_full_text
            )
            full_text_used = True
        else:
            abstract_text = efetch_data.get(pmid, {}).get("Abstract", "")
            if not abstract_text:
                text_to_analyze = "Title: " + str(rec.get("Title", "")) + "\\n\\n(No Abstract Available)"
            else:
                text_to_analyze = f"Analysis based on Abstract:\\n\\n{abstract_text}"

        # Add Authors to the prompt context
        authors_str = rec.get("Authors", "") or "No authors listed"
        last_author = _extract_last_author(authors_str)
        
        # Minimal user prompt - all instructions are in the cached system message
        user_prompt = (
            f"PMID: {pmid}\n"
            f"Authors: {authors_str}\n"
            f"GroupFallbackCandidate: {last_author if last_author else 'Not available'}\n\n"
            f"{text_to_analyze}"
        )
        
        # Token tracking with cache awareness
        # System message (~2000-3000 tokens) is cached after first call -> 50% discount
        # Dynamically estimate based on loaded instruction
        SYSTEM_TOKEN_ESTIMATE = len(system_instruction) // 4
        user_tokens = len(user_prompt) // 4
        
        # First call: full price. Subsequent: system tokens at 50% discount (approx for logging)
        if total_input_tokens == 0:
            effective_tokens = SYSTEM_TOKEN_ESTIMATE + user_tokens
        else:
            # Cached system tokens cost 50% less
            effective_tokens = (SYSTEM_TOKEN_ESTIMATE // 2) + user_tokens
        
        # We don't add to total_input_tokens here because we do it from actual API usage below
        # This is just for logging the "effective" cost view
        
        parsed = {} # Ensure parsed is defined
        try:
            # Route to the appropriate provider with Escalation Logic
            if provider == "gemini":
                parsed, output_tokens = _call_gemini_api(user_prompt, logger, system_instruction)
            else:  # openai
                # =====================================================================
                # PRE-EMPTIVE COMPLEXITY CHECK (BEFORE calling any model)
                # =====================================================================
                triggers = cfg.get("ai", {}).get("escalation_triggers", {})
                use_escalation_model = False  # Flag to skip Nano entirely
                
                # A. Length Check
                min_chars = triggers.get("min_chars")
                if min_chars and len(text_to_analyze) >= int(min_chars):
                    use_escalation_model = True
                    logger.info(f"PMID {pmid}: PRE-EMPTIVE ESCALATION (Length={len(text_to_analyze)} >= {min_chars}). Skipping {DEFAULT_MODEL}, using {ESCALATION_MODEL} directly.")
                
                # B. Modality Count Check
                if not use_escalation_model:
                    min_mods = triggers.get("min_modalities")
                    if min_mods:
                        keywords = triggers.get("modality_keywords", [])
                        text_lower = text_to_analyze.lower()
                        mod_count = 0
                        found_mods = []
                        for kw in keywords:
                            if kw.lower() in text_lower:
                                mod_count += 1
                                found_mods.append(kw)
                        
                        if mod_count >= int(min_mods):
                            use_escalation_model = True
                            logger.info(f"PMID {pmid}: PRE-EMPTIVE ESCALATION (Multi-modal: {mod_count} >= {min_mods} keywords: {found_mods}). Skipping {DEFAULT_MODEL}, using {ESCALATION_MODEL} directly.")
                
                # =====================================================================
                # MODEL CALL
                # =====================================================================
                if use_escalation_model:
                    # Skip Nano entirely, go straight to Mini
                    parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, system_instruction, model_name=ESCALATION_MODEL)
                    
                    # Update global stats
                    total_input_tokens += input_tokens
                    total_cached_tokens += cached_tokens
                    
                    # Update model stats
                    if ESCALATION_MODEL not in model_stats:
                        model_stats[ESCALATION_MODEL] = {"input": 0, "output": 0, "cached": 0}
                    model_stats[ESCALATION_MODEL]["input"] += input_tokens
                    model_stats[ESCALATION_MODEL]["output"] += output_tokens
                    model_stats[ESCALATION_MODEL]["cached"] += cached_tokens
                    
                    cache_pct = (cached_tokens / input_tokens * 100) if input_tokens > 0 else 0
                    logger.info(
                        f"PMID {pmid}: {input_tokens:,} input | {cached_tokens:,} cached ({cache_pct:.0f}%) | "
                        f"{output_tokens:,} output using {ESCALATION_MODEL} (direct)"
                    )
                else:
                    # Try Nano first
                    try:
                        parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, system_instruction, model_name=DEFAULT_MODEL)
                        
                        # Update global stats
                        total_input_tokens += input_tokens
                        total_cached_tokens += cached_tokens
                        
                        # Update model stats
                        if DEFAULT_MODEL not in model_stats:
                            model_stats[DEFAULT_MODEL] = {"input": 0, "output": 0, "cached": 0}
                        model_stats[DEFAULT_MODEL]["input"] += input_tokens
                        model_stats[DEFAULT_MODEL]["output"] += output_tokens
                        model_stats[DEFAULT_MODEL]["cached"] += cached_tokens

                        # Log actual cache metrics
                        cache_pct = (cached_tokens / input_tokens * 100) if input_tokens > 0 else 0
                        logger.info(
                            f"PMID {pmid}: {input_tokens:,} input | {cached_tokens:,} cached ({cache_pct:.0f}%) | "
                            f"{output_tokens:,} output using {DEFAULT_MODEL}"
                        )
                        
                        # =====================================================================
                        # POST-RESPONSE ESCALATION CHECK
                        # =====================================================================
                        rel_score = parsed.get("RelevanceScore")
                        needs_escalation = False
                        
                        # Treat None/Missing as reason to escalate
                        if rel_score is None:
                            needs_escalation = True
                            rel_score = 0
                        else:
                            try:
                                rel_score = int(rel_score)
                            except (ValueError, TypeError):
                                needs_escalation = True
                                rel_score = 0

                        # Trigger 1: Ambiguous Score (configurable range from YAML)
                        score_range = triggers.get("score_range", [70, 84])
                        score_low = score_range[0] if len(score_range) > 0 else 70
                        score_high = score_range[1] if len(score_range) > 1 else 84
                        if score_low <= rel_score <= score_high:
                            needs_escalation = True
                            logger.warning(f"PMID {pmid}: Ambiguous score ({rel_score}) in range [{score_low}-{score_high}] with {DEFAULT_MODEL}. Escalating...")
                            
                        # Trigger 2: Parsing Failure or Empty
                        if not parsed or parsed.get("WhyRelevant") == "Analysis failed or returned empty.":
                            needs_escalation = True
                            
                        # Trigger 3: High ReuseScore
                        reuse_threshold = triggers.get("escalate_on_high_reuse")
                        if reuse_threshold and not needs_escalation:
                            reuse_score = parsed.get("ReuseScore")
                            if reuse_score is not None:
                                try:
                                    reuse_score = int(reuse_score)
                                    if reuse_score >= int(reuse_threshold):
                                        needs_escalation = True
                                        logger.info(f"PMID {pmid}: High ReuseScore ({reuse_score} >= {reuse_threshold}). Escalating for better methods extraction...")
                                except (ValueError, TypeError):
                                    pass  # Ignore unparseable ReuseScore
                            
                        if needs_escalation:
                            # Try 2: Escalation Model (Mini)
                            logger.info(f"Escalating PMID {pmid} to {ESCALATION_MODEL} for better reasoning...")
                            parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, system_instruction, model_name=ESCALATION_MODEL)
                            
                            # Update global stats
                            total_input_tokens += input_tokens
                            total_cached_tokens += cached_tokens
                            
                            # Update model stats
                            if ESCALATION_MODEL not in model_stats:
                                model_stats[ESCALATION_MODEL] = {"input": 0, "output": 0, "cached": 0}
                            model_stats[ESCALATION_MODEL]["input"] += input_tokens
                            model_stats[ESCALATION_MODEL]["output"] += output_tokens
                            model_stats[ESCALATION_MODEL]["cached"] += cached_tokens
                            
                            cache_pct = (cached_tokens / input_tokens * 100) if input_tokens > 0 else 0
                            logger.info(
                                f"PMID {pmid} Escalation: {input_tokens:,} input | {cached_tokens:,} cached ({cache_pct:.0f}%) | "
                                f"{output_tokens:,} output using {ESCALATION_MODEL}"
                            )
                        
                    except Exception as e_nano:
                        # Check if it's an OpenAI rate limit (429)
                        error_str = str(e_nano).lower()
                        if "429" in error_str or "rate limit" in error_str:
                            logger.warning(f"PMID {pmid}: Rate limit with {DEFAULT_MODEL}. Retrying with backoff...")
                            # Simple retry with backoff
                            for retry in range(3):
                                wait_time = 2 ** retry  # 1s, 2s, 4s
                                time.sleep(wait_time)
                                try:
                                    parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, system_instruction, model_name=DEFAULT_MODEL)
                                    
                                    # Update global stats
                                    total_input_tokens += input_tokens
                                    total_cached_tokens += cached_tokens
                                    
                                    # Update model stats
                                    if DEFAULT_MODEL not in model_stats:
                                        model_stats[DEFAULT_MODEL] = {"input": 0, "output": 0, "cached": 0}
                                    model_stats[DEFAULT_MODEL]["input"] += input_tokens
                                    model_stats[DEFAULT_MODEL]["output"] += output_tokens
                                    model_stats[DEFAULT_MODEL]["cached"] += cached_tokens
                                    
                                    logger.info(f"PMID {pmid}: Retry {retry+1} succeeded.")
                                    break
                                except Exception as e_retry:
                                    if retry == 2:  # Last retry
                                        logger.warning(f"PMID {pmid}: All retries failed. Escalating to {ESCALATION_MODEL}...")
                                        parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, system_instruction, model_name=ESCALATION_MODEL)
                                        
                                        # Update global stats
                                        total_input_tokens += input_tokens
                                        total_cached_tokens += cached_tokens
                                        
                                        # Update model stats
                                        if ESCALATION_MODEL not in model_stats:
                                            model_stats[ESCALATION_MODEL] = {"input": 0, "output": 0, "cached": 0}
                                        model_stats[ESCALATION_MODEL]["input"] += input_tokens
                                        model_stats[ESCALATION_MODEL]["output"] += output_tokens
                                        model_stats[ESCALATION_MODEL]["cached"] += cached_tokens
                        else:
                            # Other errors: escalate to better model
                            logger.warning(f"PMID {pmid}: Failed with {DEFAULT_MODEL} ({e_nano}). Escalating to {ESCALATION_MODEL}...")
                            parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, system_instruction, model_name=ESCALATION_MODEL)
                            
                            # Update global stats
                            total_input_tokens += input_tokens
                            total_cached_tokens += cached_tokens
                            
                            # Update model stats
                            if ESCALATION_MODEL not in model_stats:
                                model_stats[ESCALATION_MODEL] = {"input": 0, "output": 0, "cached": 0}
                            model_stats[ESCALATION_MODEL]["input"] += input_tokens
                            model_stats[ESCALATION_MODEL]["output"] += output_tokens
                            model_stats[ESCALATION_MODEL]["cached"] += cached_tokens

            total_output_tokens += output_tokens
            
        except ResourceExhausted as e:
            # Gemini specific hard-stop
            error_details = str(e)
            logger.error(
                f"{provider.upper()} QUOTA EXCEEDED for PMID={pmid}\n"
                f"Error Details: {error_details}\n"
                f"STOPPING pipeline to prevent Notion database corruption."
            )
            raise e 
            
        except Exception as e:
            # RESILIENT ERROR HANDLING (OpenAI or Gemini misc errors)
            # Instead of crashing, mark this record as failed so Notion task can skip or flag it.
            logger.error(f"Enrichment FAILED for PMID {pmid}: {e}")
            parsed = {
                "RelevanceScore": -1,
                "WhyRelevant": f"AI enrichment failed: {str(e)}",
                "PipelineConfidence": "Error"
            }
            # We continue to the next record...
            
        # NOTE: Previous "crash on error" policy removed.
        
        # SHORT-CIRCUIT: If enrichment failed, skip all processing and append error record
        if parsed.get("RelevanceScore") == -1:
            rec.update({
                "RelevanceScore": -1,
                "WhyRelevant": parsed.get("WhyRelevant", "Enrichment failed"),
                "PipelineConfidence": "Error",
                "FullTextUsed": full_text_used,
            })
            enriched.append(rec)
            continue

        # If truncated-repair was needed, mark the title so it is easy to spot.
        if parsed.pop("__TRUNCATED__", False):
            title = str(rec.get("Title", ""))
            if not title.startswith("trct-title:"):
                rec["Title"] = f"trct-title: {title}" if title else "trct-title:"

        parsed.setdefault("RelevanceScore", 0)
        parsed.setdefault("WhyRelevant", "Analysis failed or returned empty.")
        parsed.setdefault("StudySummary", "")
        parsed.setdefault("PaperRole", "")
        parsed.setdefault("Theme", "")
        parsed.setdefault("Methods", "")
        parsed.setdefault("KeyFindings", "")
        parsed.setdefault("DataTypes", "")
        parsed.setdefault("Group", "")
        parsed.setdefault("CellIdentitySignatures", "")
        parsed.setdefault("PerturbationsUsed", "")

        raw_types = [
            t.strip().lower()
            for t in parsed.get("DataTypes", "").replace(";", ",").split(",")
            if t.strip()
        ]
        normalized_types: List[str] = []
        for dt in raw_types:
            matched = False
            for known in KNOWN_DATA_TYPES:
                if known in dt:
                    normalized_types.append(known)
                    matched = True
                    break
            if not matched:
                normalized_types.append(dt)
        parsed["DataTypes"] = ", ".join(dict.fromkeys(normalized_types))

        relevance_score = parsed.get("RelevanceScore")
        if relevance_score is None:
            relevance_score = 0
        try:
            relevance_score = int(relevance_score)
        except (ValueError, TypeError):
            relevance_score = 0
        
        why_relevant = parsed.get("WhyRelevant", "")
        wr = why_relevant.lower()
        if relevance_score == 0 and (
            "not relevant" not in wr and "irrelevant" not in wr and 
            "relevant" in wr and "no abstract" not in wr
        ):
            relevance_score = 50
            parsed["RelevanceScore"] = 50

        methods_str = parsed.get("Methods", "").lower()
        key_findings_str = parsed.get("KeyFindings", "").lower()
        confidence = "Low"
        if full_text_used:
            confidence = "High"
        else:
            if relevance_score >= 80:
                confidence = "Medium"
            else:
                strong_keywords = [
                    "spatial",
                    "visium",
                    "xenium",
                    "cosmx",
                    "scrna",
                    "snrna",
                    "multiome",
                    "multi-omics"
                ]
                if any(k in methods_str for k in strong_keywords) or any(
                    k in key_findings_str for k in strong_keywords
                ):
                    confidence = "Medium"
        
        # Check if escalaction improved things or if we still have low confidence
        if provider == "openai" and relevance_score <= 85 and relevance_score >= 70:
             confidence = "Medium-Ambiguous" # Mark as ambiguous but potentially handled by escalation

        rec.update(
            {
                "RelevanceScore": relevance_score,
                "WhyRelevant": parsed.get("WhyRelevant", ""),
                "StudySummary": parsed.get("StudySummary", ""),
                "PaperRole": parsed.get("PaperRole", ""),
                "Theme": parsed.get("Theme", ""),
                "Methods": parsed.get("Methods", ""),
                "KeyFindings": parsed.get("KeyFindings", ""),
                "DataTypes": parsed.get("DataTypes", ""),
                "Group": parsed.get("Group", ""),
                "CellIdentitySignatures": parsed.get("CellIdentitySignatures", ""),
                "PerturbationsUsed": parsed.get("PerturbationsUsed", ""),
                "PipelineConfidence": confidence,
                "FullTextUsed": full_text_used,
            }
        )
        enriched.append(rec)
        time.sleep(0.3)

    
    # -------------------------------------------------------------------------
    # FINAL CACHE SUMMARY
    # -------------------------------------------------------------------------
    if model_stats:
        logger.info("=" * 60)
        logger.info("AI ENRICHMENT TOKEN SUMMARY")
        logger.info("=" * 60)
        
        grand_total_input = 0
        grand_total_cached = 0
        
        for model_name, stats in model_stats.items():
            inp = stats["input"]
            cached = stats["cached"]
            out = stats["output"]
            pct = (cached / inp * 100) if inp > 0 else 0
            
            # OpenAI cache reads get 50% discount
            saved_tokens = int(cached * 0.5)
            
            logger.info(f"MODEL: {model_name}")
            logger.info(f"  - Input Tokens:  {inp:,}")
            logger.info(f"  - Cached Tokens: {cached:,} ({pct:.1f}%)")
            logger.info(f"  - Output Tokens: {out:,}")
            logger.info(f"  - Est. Savings:  ~{saved_tokens:,} tokens (50% discount)")
            logger.info("-" * 40)
            
            grand_total_input += inp
            grand_total_cached += cached
            
        total_pct = (grand_total_cached / grand_total_input * 100) if grand_total_input > 0 else 0
        logger.info(f"GRAND TOTAL INPUT:  {grand_total_input:,}")
        logger.info(f"GRAND TOTAL CACHED: {grand_total_cached:,} ({total_pct:.1f}%)")
        logger.info("=" * 60)

    return enriched
