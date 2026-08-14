# Tier C: Figure-Grounded Multimodal PDF Enrichment

## What it does and why

Tier 1 Pass 1 scores papers on text (abstract + PMC full-text). Pass 2 extracts
computational methods from the same text. Neither pass reads a figure, a table
layout, a methods schematic, or a supplementary panel. For spatial/single-cell PCa
papers, the most important evidence is often *in the figures*.

Tier C feeds the PDF directly to Gemini 3.x (multimodal), extracts a structured
Evidence Map anchored to figure IDs, synthesizes findings from that map, and
verifies each finding back against the map for internal consistency. This is
distinct work from Pass 1/2 -- it is figure-grounded, not text-only.

---

## Two paths that trigger Tier C

| Path | Trigger | What it does |
|---|---|---|
| **Auto (pipeline)** | Biweekly cron: `RelevanceScore >= 90` AND `PMCID` present | Fetches PMC OA PDF, runs 3-stage engine, writes JSON to Drive, appends `TierC_*` fields to the Notion Tier 1 row |
| **Manual inbox** | PDF dropped in a Drive "inbox" folder whose PMID is not yet in Notion | Downloads PDF, runs page-1 identity extraction (Flash), resolves PMID via eutils, deduplicates against Notion, runs 3-stage engine, writes JSON to Drive, creates new Notion row |

Both paths write the same artifact shape and Notion fields.

---

## Three-stage engine

All three stages use the `tier_c.model` from `configs/*.yaml` (currently `gemini-3.7-flash`)
with multimodal (Stage 1) or text-only input.

```
Stage 1: Evidence Map
  Input : PDF bytes (multimodal)
  Output: EvidenceMap -- figures (id, caption, panels), anchors (id, text, figure_id),
          methods.BioinfoMethods (method_name, tool_package, purpose)
  Note  : if PDF > 18 MB, split into ~25-page chunks, run per chunk, merge maps.

Stage 2: Synthesis
  Input : EvidenceMap JSON (text-only)
  Output: Synthesis -- TopFindings (with figure+anchor+method refs), StoryMap
          (figure-to-figure causal links), Panels, Weaknesses, MethodPrimers

Stage 3: Verification
  Input : EvidenceMap + Synthesis JSON (text-only)
  Output: VerificationReport -- per-finding status (supported / supported_with_issues
          / unsupported), panel field checks, method consistency
```

Derived fields written to Notion:
- `TierC_Status` (complete / skipped_no_pdf / skipped_dedup / failed)
- `TierC_Source` (PMC_OA / Manual_Inbox)
- `TierC_DriveLink` (URL to `<PMID>_tierC.json`)
- `TierC_FigureCount`, `TierC_AnchorCount`, `TierC_MethodCount`
- `TierC_TopFindings` (top-3 headlines joined by "; ")
- `TierC_VerificationStatus` (all_supported / some_issues / unsupported)
- `TierC_Error` (only on failure or warnings)

---

## Files

```
src/litintel/tierc/
  schema.py     Pydantic models: EvidenceMap, Synthesis, VerificationReport,
                TierCArtifact (combines all three), TierCRecord (Notion summary)
  prompts.py    System prompts for stages 0 (identity), 1 (evidence map),
                2 (synthesis), 3 (verification) -- ported from OmniScope
  pdf_io.py     load_pmc_pdf_bytes, build_multimodal_parts, split_pdf_by_pages,
                downsample_pdf_images, pdf_size_mb
  engine.py     run_evidence_map, run_synthesis, run_verification, run_all_stages,
                merge_evidence_maps (chunk-and-merge for oversized PDFs)
  identity.py   extract_identity_from_pdf (page-1 Flash call), resolve_pmid_from_doi
                (eutils), resolve_identity (combined flow)
  inbox.py      list_inbox_pdfs, download_drive_pdf, move_to_subfolder, process_inbox
  runner.py     run_tier_c_for_record -- auto-path entry point called by pipeline/tier1.py

src/litintel/enrich/ai_client.py
  _call_gemini_multimodal -- sibling of _call_gemini for multimodal content list

src/litintel/storage/drive.py
  upload_tierc_artifact -- upsert <PMID>_tierC.json to Drive

src/litintel/storage/notion.py
  _build_tier1_properties -- extended to emit TierC_* fields when set

src/litintel/config.py
  TierCConfig -- pydantic model; AppConfig.tier_c (optional, None by default)

configs/tier1_pca.yaml
  tier_c: block (enabled, model, min_score, folder env names, chunk settings)

src/litintel/cli.py
  litintel tier-c inbox [--dry-run] -- process Drive inbox manually
  litintel tier-c pmid <PMID>   -- ad-hoc run; writes /tmp/<PMID>_tierC.json
```

---

## PDF size handling

Gemini inline-bytes limit is ~20 MB. Spatial/sc papers routinely exceed this.

1. PDF <= 18 MB -- sent as a single inline call (no splitting).
2. PDF > 18 MB -- split into chunks of `chunk_pages=25` (configurable).
   Evidence Maps are run per chunk, then merged:
   - identity: from chunk 1
   - figures: dedup by id
   - anchors: renumbered sequentially (anc_001 ... anc_NNN) for global uniqueness
   - methods: dedup by (method_name, tool_package)
3. Max chunks is `max_chunks=4` (cap ~100 pages; configurable). Pages beyond cap
   are dropped with a log warning.
4. If a single chunk is still > 18 MB after splitting (image-dense supplement):
   `downsample_pdf_images` re-encodes images at JPEG quality=60.
5. If still over after downsampling: logged as `skipped_oversized`, no Tier C run.

---

## Cost

Stage 1 (multimodal PDF) is the expensive call. Gemini Pro charges on image tokens.
A 15-page sc/spatial paper is roughly $0.05-0.10 per paper for all three stages.
At the `min_score=90` gate with 25 papers/biweekly run, expect 0-3 Tier C papers
per run (< $0.30/run). Usage is captured in the `_call_gemini_multimodal` return
and logged at INFO level. Not yet written to `run_history.csv` (Step 5 scope).

---

## What you need to do before running Tier C

### 1. Add Notion database properties (do this once in the Notion UI)

Open your Tier 1 PCa Notion database and add the following properties:

| Property name | Type |
|---|---|
| `TierC_Status` | Select (options: complete, skipped_no_pdf, skipped_dedup, failed) |
| `TierC_Source` | Select (options: PMC_OA, Manual_Inbox) |
| `TierC_DriveLink` | URL |
| `TierC_FigureCount` | Number |
| `TierC_AnchorCount` | Number |
| `TierC_MethodCount` | Number |
| `TierC_TopFindings` | Text |
| `TierC_VerificationStatus` | Select (options: all_supported, some_issues, unsupported) |
| `TierC_Error` | Text |

The pipeline will silently skip writing these fields for records that did not run
Tier C, so existing rows are not affected.

### 2. Create Drive folders and set env vars

Create two folders in Google Drive (can be anywhere -- inbox and output are separate):

| Purpose | Env var | What to put there |
|---|---|---|
| Manual inbox | `GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID` | Drop PDFs here to trigger manual Tier C |
| Artifact output | `GOOGLE_DRIVE_TIERC_OUTPUT_FOLDER_ID` | Pipeline writes `<PMID>_tierC.json` here |

Add both to your `.env` file:

```
GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID=<folder_id_from_drive_url>
GOOGLE_DRIVE_TIERC_OUTPUT_FOLDER_ID=<folder_id_from_drive_url>
```

The folder ID is the string after `/folders/` in the Drive URL.

The inbox processor auto-creates `inbox/processed/` and `inbox/skipped/`
subfolders on first run -- you do not need to create those manually.

### 3. Install new dependencies (if not already present)

```bash
pip install "pypdf>=4.0" "Pillow>=10.0"
```

Both are already declared in `pyproject.toml`, so `pip install -e .` covers them.

### 4. Smoke-test the CLI before the next biweekly run

```bash
# Dry-run inbox: lists PDFs without downloading or processing
litintel tier-c inbox --dry-run

# Single-paper ad-hoc test (writes /tmp/<PMID>_tierC.json)
# Pick a PMID with score >= 90 and a known PMCID, e.g. from papers_tier1.csv
litintel tier-c pmid 38423450
```

If the pmid command succeeds, check `/tmp/<PMID>_tierC.json` for:
- `evidence_map.figures` non-empty
- `synthesis.TopFindings` has >= 3 entries
- `verification.TopFindings` all have a `status` field

### 5. Verify the auto-path wiring on a test run

```bash
# Runs full Tier 1 pipeline, only 3 papers, Tier C will fire if any hit >= 90
litintel tier1 --limit 3
```

Check that:
- Papers with `RelevanceScore >= 90` AND `PMCID` get `TierC_Status=complete`
- Drive output folder contains `<PMID>_tierC.json`
- Notion row has `TierC_*` columns populated

---

## Config knobs in `configs/tier1_pca.yaml`

```yaml
tier_c:
  enabled: true          # set false to disable globally
  model: "gemini-3.7-flash"
  thinking: "MEDIUM"
  min_score: 90          # only auto-path papers >= this get Tier C
  inbox_folder_id_env: "GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID"
  output_folder_id_env: "GOOGLE_DRIVE_TIERC_OUTPUT_FOLDER_ID"
  process_inbox_in_cron: true   # set false to make inbox CLI-only
  max_size_mb: 18.0      # PDFs above this are chunked
  chunk_pages: 25        # pages per chunk
  max_chunks: 4          # cap at 4 chunks (~100 pages total)
  identity_model: "gemini-3.7-flash"  # cheap model for page-1 identity
```

To disable Tier C entirely without editing the yaml: set `enabled: false` or remove
the `tier_c:` block.

---

## What is NOT included (out of scope, see plan)

- OmniScope Stage 3 (web-lookup Method Primer) -- Pass 2 already covers this from text.
- Markdown merge / human-readable summary (OmniScope Stage 5) -- not wanted.
- bioRxiv/medRxiv PDF fetcher -- preprints excluded from Tier 1 PubMed query.
- Usage cost written to `run_history.csv` -- planned for Step 5 verification.
