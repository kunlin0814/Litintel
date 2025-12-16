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

# Initialize OpenAI client if available (lazy import to avoid hard dependency)
try:
    from openai import OpenAI
    _OPENAI_CLIENT = OpenAI(api_key=os.environ.get("OPENAI_API_KEY")) if os.environ.get("OPENAI_API_KEY") else None
except ImportError:
    _OPENAI_CLIENT = None


# =============================================================================
# CACHE-OPTIMIZED SYSTEM INSTRUCTION
# =============================================================================
# This large, static system message (>1024 tokens) is automatically cached by
# OpenAI's API, providing a 50% discount on input tokens for all subsequent
# calls within a session. All static content (schema, rubric, taxonomy,
# constraints) is consolidated here to maximize cache efficiency.
# =============================================================================

SYSTEM_INSTRUCTION = """You are a PhD-level bioinformatics curator specializing in cancer biology, prostate cancer, spatial transcriptomics, single-cell genomics, and multi-omics methods.

================================================================================
TASK: Analyze the provided paper text and return a structured JSON object.
================================================================================

## OUTPUT JSON SCHEMA (strict)

You MUST return a JSON object with EXACTLY these fields:

{
  "RelevanceScore": <integer 0-100>,
  "WhyRelevant": <string, 1 sentence>,
  "StudySummary": <string, 2-3 sentences>,
  "PaperRole": <string, 1 sentence>,
  "Theme": <string, semicolon-separated tags>,
  "Methods": <string, platforms and tools>,
  "KeyFindings": <string, semicolon-separated points>,
  "DataTypes": <string, comma-separated assays>,
  "Group": <string, PI or Lab name>,
  "CellIdentitySignatures": <string, marker definitions>,
  "PerturbationsUsed": <string, semicolon-separated manipulations>
}

================================================================================
RELEVANCE SCORING RUBRIC
================================================================================

Score papers based on their relevance to PROSTATE CANCER + SPATIAL/SINGLE-CELL/MULTI-OMICS:

### Tier 0: Not Relevant (Score = 0)
- Paper has neither cancer focus NOR spatial/single-cell/multi-omics methods
- Pure clinical trials without molecular data
- Computational methods tested only on non-cancer data

### Tier 1: Weak Relevance (Score = 30-60)
- Generic cancer study without spatial/single-cell/multi-omics (score 30-45)
- Spatial/single-cell method paper but tested on non-cancer tissue (score 45-60)
- Review articles summarizing the field (score 40-50)

### Tier 2: Moderate Relevance (Score = 70-84)
- Cancer-focused study with LIMITED spatial/single-cell/multi-omics
- Non-prostate cancer with 1-2 relevant technologies
- Prostate cancer with only bulk RNA-seq or standard genomics
- Method development tested on cancer cell lines only

### Tier 3: High Relevance (Score = 85-94)
- Prostate cancer + at least ONE key technology:
  * Single-cell RNA-seq (scRNA-seq, snRNA-seq)
  * Single-cell ATAC-seq (scATAC-seq, snATAC-seq)
  * Multiome (10x Multiome, joint RNA+ATAC)
  * Spatial transcriptomics (Visium, Xenium, CosMx, GeoMx, MERFISH, Slide-seq)
- Non-prostate cancer with ≥3 relevant technologies

### Tier 4: Highest Relevance (Score = 95-100)
- Prostate cancer + BOTH:
  * Single-cell/multiome technology AND
  * Spatial technology
- Primary human tissue data (not just cell lines)
- Novel biological insights into prostate cancer heterogeneity

================================================================================
METHOD & PLATFORM TAXONOMY
================================================================================

Use these controlled terms when classifying Methods and DataTypes:

### Single-Cell Sequencing
- scRNA-seq, snRNA-seq (single-cell/nucleus RNA)
- scATAC-seq, snATAC-seq (single-cell/nucleus ATAC)
- Multiome, 10x Multiome (joint RNA+ATAC)
- CITE-seq (protein + RNA)
- scDNA-seq (single-cell DNA/CNV)

### Spatial Technologies
- 10x Visium, Visium HD (spot-based spatial transcriptomics)
- 10x Xenium (in-situ spatial transcriptomics)
- NanoString CosMx (in-situ spatial transcriptomics)
- NanoString GeoMx (spatial proteomics/transcriptomics)
- MERFISH, seqFISH (imaging-based spatial)
- Slide-seq, Slide-seqV2 (bead-based spatial)
- Spatial ATAC, spatial-ATAC-seq

### Bulk Sequencing
- Bulk RNA-seq
- WGS (whole genome sequencing)
- WES (whole exome sequencing)
- ChIP-seq, CUT&RUN, CUT&Tag
- ATAC-seq (bulk)
- Bisulfite-seq, WGBS (methylation)

### Imaging & Histology
- H&E staining
- Immunohistochemistry (IHC)
- Immunofluorescence (IF)
- Multiplexed imaging (CODEX, IMC, MIBI)

### Computational Methods
- Trajectory inference, pseudotime analysis
- RNA velocity
- Cell-cell communication (CellChat, CellPhoneDB, NicheNet)
- Deconvolution (RCTD, cell2location, Tangram)
- CNV inference (inferCNV, CopyKAT, epiAneufinder)
- Integration (Harmony, LIGER, Seurat CCA)

================================================================================
FIELD EXTRACTION GUIDELINES
================================================================================

### WhyRelevant
- 1 sentence explaining why you assigned the RelevanceScore
- Be specific about which technologies and cancer types were present

### StudySummary
- 2-3 sentences covering: (1) study aim, (2) system/cohort studied, (3) main finding
- Example: "This study profiled the tumor microenvironment in localized prostate cancer using snRNA-seq and Visium. The authors analyzed 15 treatment-naive samples and 10 post-treatment samples. They identified a novel CAF subtype associated with treatment resistance."

### PaperRole
- 1 sentence categorizing the paper's contribution
- Examples: "Core framework paper for spatial prostate cancer analysis", "Incremental method improvement for CNV calling", "First comprehensive atlas of prostate cancer cell states", "Benchmarking study comparing deconvolution methods"

### Theme
- Semicolon-separated controlled tags describing research themes
- Examples: "Spatial lineage tracing; Tumor heterogeneity; Treatment resistance"
- Common themes: Tumor microenvironment; Immune infiltration; Epithelial plasticity; AR signaling; Neuroendocrine differentiation; Metastasis; Drug resistance; Clonal evolution; CNV inference; Epigenetic regulation

### Methods
- List experimental platforms AND computational tools mentioned
- Format: "Experimental: [platforms]; Computational: [tools]"
- Example: "Experimental: 10x Visium, snRNA-seq; Computational: Seurat v5, CellChat, inferCNV"

### KeyFindings
- Concise bullet points separated by semicolons
- Each finding should be a complete thought
- Example: "Identified 3 novel CAF subtypes; SPINK1+ cells mark aggressive disease; Spatial niche analysis revealed immune exclusion zones"

### DataTypes
- Comma-separated list using controlled vocabulary from taxonomy above
- Example: "snRNA-seq, Visium, H&E"

### Group
- The Principal Investigator or Lab name
- PRIORITY ORDER:
  1. Look for "Corresponding Author" or "Correspondence to" in the text
  2. Extract the PI name or lab name
  3. If no correspondence info, use the LAST author from the provided author list
  4. If no authors available, return empty string
- Format: "LastName Lab" or just "LastName"

### CellIdentitySignatures
- Extract gene signatures explicitly used to define cell types/states
- Format: "CellType1: GENE1, GENE2; CellType2: GENE3, GENE4"
- Example: "Basal: KRT5, KRT14, TP63; Luminal: KRT8, KRT18, AR; Club: SCGB1A1, PIGR"
- Return empty string if not explicitly reported

### PerturbationsUsed
- Semicolon-separated list of genetic or chemical manipulations
- Include: knockouts, knockdowns, overexpression, drug treatments, CRISPR screens
- Example: "PTEN knockout; Enzalutamide treatment; ERG overexpression; CRISPR screen for AR regulators"
- Return empty string if no perturbations

================================================================================
STRICT OUTPUT CONSTRAINTS
================================================================================

1. Return ONLY the JSON object - no markdown, no explanation, no preamble
2. All string values must be properly escaped (no unescaped quotes or newlines)
3. RelevanceScore MUST be an integer between 0 and 100
4. Missing information → empty string (""), never null or "N/A"
5. Do NOT fabricate information - only extract what is explicitly stated
6. Keep output compact - no unnecessary whitespace in JSON
7. All 11 fields are REQUIRED in the output

================================================================================
"""

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


def _call_gemini_api(user_prompt: str, logger) -> Tuple[Dict[str, Any], int]:
    """Call Gemini API and return parsed JSON response."""
    global _GEMINI_MODEL
    
    if _GEMINI_MODEL is None:
        response_schema = {
            "type": "OBJECT",
            "properties": {
                "RelevanceScore": {"type": "INTEGER"},
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
            system_instruction=SYSTEM_INSTRUCTION,
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


def _call_openai_api(user_prompt: str, logger, model_name: str = "gpt-5-nano") -> Tuple[Dict[str, Any], int]:
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
            {"role": "system", "content": SYSTEM_INSTRUCTION},
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
    total_cached_tokens = 0  # Track actual cache hits from OpenAI
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
        
        # Pre-call token estimate for logging
        user_tokens_estimate = len(user_prompt) // 4
        
        parsed = {} # Ensure parsed is defined
        try:
            # Route to the appropriate provider with Escalation Logic
            if provider == "gemini":
                parsed, output_tokens = _call_gemini_api(user_prompt, logger)
            else:  # openai
                # Try 1: Default Model (Nano)
                try:
                    parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, model_name=DEFAULT_MODEL)
                    
                    # Log actual cache metrics from OpenAI
                    cache_pct = (cached_tokens / input_tokens * 100) if input_tokens > 0 else 0
                    logger.info(
                        f"PMID {pmid}: {input_tokens:,} input tokens "
                        f"(cached: {cached_tokens:,} = {cache_pct:.0f}%) | "
                        f"Output: {output_tokens:,} tokens"
                    )
                    total_input_tokens += input_tokens
                    total_cached_tokens += cached_tokens
                    
                    # Escalation Check
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

                    # Trigger 1: Ambiguous Score (70-84) - matches "limited spatial/single-cell" tier
                    if 70 <= rel_score <= 84:
                        needs_escalation = True
                        logger.warning(f"PMID {pmid}: Ambiguous score ({rel_score}) with {DEFAULT_MODEL}. Escalating...")
                        
                    # Trigger 2: Parsing Failure or Empty (Handled by exception/defaults usually, but check parsed dict)
                    if not parsed or parsed.get("WhyRelevant") == "Analysis failed or returned empty.":
                        needs_escalation = True
                        
                    if needs_escalation:
                        # Try 2: Escalation Model (Mini)
                        logger.info(f"Escalating PMID {pmid} to {ESCALATION_MODEL} for better reasoning...")
                        parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, model_name=ESCALATION_MODEL)
                        total_input_tokens += input_tokens
                        total_cached_tokens += cached_tokens
                        
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
                                parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, model_name=DEFAULT_MODEL)
                                total_input_tokens += input_tokens
                                total_cached_tokens += cached_tokens
                                logger.info(f"PMID {pmid}: Retry {retry+1} succeeded.")
                                break
                            except Exception as e_retry:
                                if retry == 2:  # Last retry
                                    logger.warning(f"PMID {pmid}: All retries failed. Escalating to {ESCALATION_MODEL}...")
                                    parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, model_name=ESCALATION_MODEL)
                                    total_input_tokens += input_tokens
                                    total_cached_tokens += cached_tokens
                    else:
                        # Other errors: escalate to better model
                        logger.warning(f"PMID {pmid}: Failed with {DEFAULT_MODEL} ({e_nano}). Escalating to {ESCALATION_MODEL}...")
                        parsed, output_tokens, input_tokens, cached_tokens = _call_openai_api(user_prompt, logger, model_name=ESCALATION_MODEL)
                        total_input_tokens += input_tokens
                        total_cached_tokens += cached_tokens

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

    return enriched
