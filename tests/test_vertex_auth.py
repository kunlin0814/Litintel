"""Test script: Verify Gemini API access.

Two modes:
  A) Personal API key  -> fill in API_KEY below
  B) Vertex AI (GCP)   -> fill in PROJECT_ID and LOCATION below,
                           then run:  gcloud auth application-default login

Fill in ONE of the two sections below, then run:
  python scripts/test_vertex_auth.py
"""

import sys

# =====================================================================
# CONFIGURATION -- fill in ONE of these two options
# =====================================================================

# Option A: Personal Gemini API key (from https://aistudio.google.com/apikey)
API_KEY = ''

# Option B: Vertex AI via company GCP project
#   1. Fill in PROJECT_ID and LOCATION
#   2. Run in terminal first:  gcloud auth application-default login
PROJECT_ID = ''
LOCATION = 'us-east5'

# =====================================================================


def main():
    # ---- Step 1: Check package ----
    try:
        from google import genai
        from google.genai import types
        print('[OK] google-genai package found.')
    except ImportError:
        print('[FAIL] google-genai not installed.')
        print('  Fix: pip install google-genai')
        sys.exit(1)

    # ---- Step 2: Determine mode and create client ----
    if API_KEY:
        print('[INFO] Mode: Personal API key')
        try:
            client = genai.Client(api_key=API_KEY)
            print('[OK] Client created with API key.')
        except Exception as e:
            print(f'[FAIL] Could not create client: {e}')
            sys.exit(1)

    elif PROJECT_ID:
        print(f'[INFO] Mode: Vertex AI (project={PROJECT_ID}, location={LOCATION})')
        try:
            client = genai.Client(
                vertexai=True,
                project=PROJECT_ID,
                location=LOCATION,
            )
            print('[OK] Vertex AI client created.')
        except Exception as e:
            print(f'[FAIL] Could not create Vertex AI client: {e}')
            print('  Did you run:  gcloud auth application-default login')
            sys.exit(1)

    else:
        print('[FAIL] No credentials configured.')
        print('  Edit this script and fill in either API_KEY or PROJECT_ID at the top.')
        sys.exit(1)

    # ---- Step 3: Test Gemini call ----
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Say hello in exactly 5 words.',
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=50,
            ),
        )
        print(f'[OK] Gemini response: {response.text}')
        if response.usage_metadata:
            print(f'     Tokens -> input={response.usage_metadata.prompt_token_count}, '
                  f'output={response.usage_metadata.candidates_token_count}')
        print('\n=== SUCCESS: Gemini API is working. ===')
    except Exception as e:
        print(f'[FAIL] Gemini API call failed: {e}')
        if PROJECT_ID:
            print('  Possible causes:')
            print('    - Vertex AI API not enabled on the project')
            print('    - Missing permissions (need Vertex AI User role)')
            print('    - Run:  gcloud auth application-default login')
        else:
            print('  Check that the API key is valid.')
        sys.exit(1)


if __name__ == '__main__':
    main()
