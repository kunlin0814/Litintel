import os
import time
import json
import logging
from typing import Dict, Any, Tuple, Optional
from pydantic import ValidationError

import google.generativeai as genai
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from litintel.config import AIConfig, AIProvider
from litintel.enrich.schema import Tier1Record, Tier2Record

logger = logging.getLogger(__name__)

# Global Clients (OpenAI client can be cached; Gemini model cannot due to varying config)
_OPENAI_CLIENT = None
_GEMINI_CONFIGURED = False

def _get_openai_client():
    global _OPENAI_CLIENT
    if not _OPENAI_CLIENT:
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not set")
        _OPENAI_CLIENT = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _OPENAI_CLIENT

def _configure_gemini():
    """Configure Gemini API once. Raises if API key is missing."""
    global _GEMINI_CONFIGURED
    if not _GEMINI_CONFIGURED:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        _GEMINI_CONFIGURED = True

def _get_gemini_model(system_instruction: str, response_schema: Dict[str, Any]):
    """Create a fresh Gemini model per call (system_instruction & schema vary by tier)."""
    _configure_gemini()
    return genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction,
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        },
    )

def _call_openai(
    client: OpenAI, 
    model: str, 
    system_prompt: str, 
    user_prompt: str,
    schema: Dict[str, Any]
) -> Tuple[Dict[str, Any], int]:
    
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
        output_tokens = response.usage.completion_tokens
        return json.loads(raw_json), output_tokens
    except Exception as e:
        # Simple Rate Limit Retry Logic
        if "429" in str(e) or "rate limit" in str(e).lower():
            logger.warning(f"OpenAI 429 Rate Limit. Retrying {model}...")
            time.sleep(2)
            response = client.chat.completions.create(**params)
            raw_json = response.choices[0].message.content
            output_tokens = response.usage.completion_tokens
            return json.loads(raw_json), output_tokens
        raise e

def enrich_record(
    text: str,
    authors: str,
    pmid: str,
    config: AIConfig,
    system_prompt: str,
    json_schema: Dict[str, Any],
    pydantic_model: Any, # Tier1Record or Tier2Record class
    group_fallback: str = "",
    geo_candidates: str = "",
    sra_candidates: str = ""
) -> Dict[str, Any]:
    
    # Inject fallback into prompt
    final_system_prompt = system_prompt.format(group_fallback=group_fallback) # Expects {group_fallback} placeholder
    
    # Build user prompt with optional candidate validation
    user_prompt = f"""PMID: {pmid}
Authors: {authors}
GroupFallbackCandidate: {group_fallback}
"""
    
    # Add GEO/SRA candidates if present (for AI validation)
    if geo_candidates or sra_candidates:
        user_prompt += "\n--- ACCESSION VALIDATION ---\n"
        if geo_candidates:
            user_prompt += f"GEO_Candidates (found via regex): {geo_candidates}\n"
        if sra_candidates:
            user_prompt += f"SRA_Candidates (found via regex): {sra_candidates}\n"
        user_prompt += "Validate which are THIS study's data (see schema instructions).\n"
    
    user_prompt += f"""
TEXT_START
{text}
TEXT_END
"""
    
    provider = config.provider
    result_json = {}
    
    try:
        if provider == AIProvider.OPENAI:
            client = _get_openai_client()
            already_escalated = False
            
            # Try Default Model
            try:
                result_json, _ = _call_openai(client, config.model_default, final_system_prompt, user_prompt, json_schema)
            except Exception as e:
                logger.warning(f"PMID {pmid}: Failed with {config.model_default} ({e}). Escalating...")
                result_json, _ = _call_openai(client, config.model_escalate, final_system_prompt, user_prompt, json_schema)
                already_escalated = True
                
            # Score-based escalation (only if we haven't already escalated)
            if not already_escalated:
                score = result_json.get("RelevanceScore", 0)
                if 70 <= score <= 84:
                    logger.info(f"PMID {pmid}: Ambiguous score ({score}). Escalating to {config.model_escalate}...")
                    result_json, _ = _call_openai(client, config.model_escalate, final_system_prompt, user_prompt, json_schema)

        elif provider == AIProvider.GEMINI:
             # Gemini implementation (simplified for brevity, matching previous module)
             model = _get_gemini_model(final_system_prompt, json_schema)
             resp = model.generate_content(user_prompt)
             result_json = json.loads(resp.text) # Robust extraction needed in real impl
             
        # Normalize keys: OpenAI sometimes returns RELEVANCESCORE instead of RelevanceScore
        result_json = _normalize_keys(result_json)
        
        # Ensure AI-specific fields have defaults (don't validate full schema yet - that needs PubMed fields)
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
            "PipelineConfidence": "Low"
        }
        
        # Add missing fields with defaults
        for field, default in ai_field_defaults.items():
            if field not in result_json:
                result_json[field] = default
        
        return result_json

    except Exception as e:
        logger.error(f"Enrichment failed for {pmid}: {e}")
        return {"RelevanceScore": -1, "WhyRelevant": f"Error: {str(e)}", "PipelineConfidence": "Error"}

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

