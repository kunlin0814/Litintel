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

# Global Clients
_GEMINI_MODEL_CLIENT = None
_OPENAI_CLIENT = None

def _get_openai_client():
    global _OPENAI_CLIENT
    if not _OPENAI_CLIENT:
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not set")
        _OPENAI_CLIENT = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _OPENAI_CLIENT

def _get_gemini_model(system_instruction: str, response_schema: Dict[str, Any]):
    global _GEMINI_MODEL_CLIENT
    if not _GEMINI_MODEL_CLIENT:
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        _GEMINI_MODEL_CLIENT = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction,
            generation_config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            },
        )
    return _GEMINI_MODEL_CLIENT

def _call_openai(
    client: OpenAI, 
    model: str, 
    system_prompt: str, 
    user_prompt: str,
    schema: Dict[str, Any]
) -> Tuple[Dict[str, Any], int]:
    
    # Construct JSON schema for OpenAI strict structure
    json_schema = {
        "name": "response_schema",
        "strict": True,
        "schema": schema 
    }
    
    params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": json_schema
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
    group_fallback: str = ""
) -> Dict[str, Any]:
    
    # Inject fallback into prompt
    final_system_prompt = system_prompt.format(group_fallback=group_fallback) # Expects {group_fallback} placeholder
    
    user_prompt = f"""PMID: {pmid}
Authors: {authors}
GroupFallbackCandidate: {group_fallback}

TEXT_START
{text}
TEXT_END
"""
    
    provider = config.provider
    result_json = {}
    
    try:
        if provider == AIProvider.OPENAI:
            client = _get_openai_client()
            # Try Default Model
            try:
                result_json, _ = _call_openai(client, config.model_default, final_system_prompt, user_prompt, json_schema)
            except Exception as e:
                logger.warning(f"PMID {pmid}: Failed with {config.model_default} ({e}). Escalating...")
                result_json, _ = _call_openai(client, config.model_escalate, final_system_prompt, user_prompt, json_schema)
                
            # Escalation Logic based on Score
            score = result_json.get("RelevanceScore", 0)
            if 70 <= score <= 84:
                 logger.info(f"PMID {pmid}: Ambiguous score ({score}). Escalating to {config.model_escalate}...")
                 result_json, _ = _call_openai(client, config.model_escalate, final_system_prompt, user_prompt, json_schema)

        elif provider == AIProvider.GEMINI:
             # Gemini implementation (simplified for brevity, matching previous module)
             model = _get_gemini_model(final_system_prompt, json_schema)
             resp = model.generate_content(user_prompt)
             result_json = json.loads(resp.text) # Robust extraction needed in real impl
             
        # Validation
        # validated_rec = pydantic_model(**result_json) # Strict check
        # return validated_rec.model_dump()
        return result_json

    except Exception as e:
        logger.error(f"Enrichment failed for {pmid}: {e}")
        return {"RelevanceScore": -1, "WhyRelevant": f"Error: {str(e)}", "PipelineConfidence": "Error"}
