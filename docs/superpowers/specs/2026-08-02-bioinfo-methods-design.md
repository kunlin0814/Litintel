# bioinfo-methods: a compounding, agent-queryable method knowledge base

**Status:** Design (approved in conversation, pending written review)
**Date:** 2026-08-02
**Owner:** Kun-Lin Ho
**Supersedes nothing.** Extends `docs/methodintel_plan.md` (2026-05-11) and
`docs/integration_brainstorm.md` (2026-07-22).

---

## 1. Problem

LitIntel today answers "what is new in prostate cancer spatial/single-cell
literature." That is useful but it does not compound: the value of a curated
paper decays as the paper ages, and nothing in the system accumulates.

The durable asset is not the paper set. It is the **method knowledge**: which
computational method is currently correct for a given analysis stage, what
replaced what, and why. That knowledge is:

- universal (survives a change of disease area, tissue, or employer),
- slow-moving (a method's status changes on a scale of years),
- and currently scattered across paper rows, Notion text fields, and memory.

The concrete failure this design fixes: asking an AI agent "how do I do
neighborhood analysis" today triggers an opaque web search whose answer varies
run to run and whose citations are unverified. There is no local, auditable,
citable alternative to consult first.

### Why the current pipeline cannot produce this

`configs/tier1_pca.yaml:8-14` gates discovery on
`(prostate OR prostatic OR "prostate cancer") AND (spatial|single-cell|ATAC|...)`.
The disease term is an **AND at discovery time**, so method and benchmark papers
that do not mention prostate never enter the corpus. This is structural, not a
tuning problem.

---

## 2. Core decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | The taxonomy is **seeded from the field's own maps** -- reviews, tool docs, benchmarks -- not from keyword search and not from the analyst's memory | Both alternatives fail on unknown unknowns. A keyword sweep cannot return a method you cannot name; enumerating "top-down from the stage list" only moves the same blind spot from PubMed into the analyst's head. Reviews and tutorial indices are enumerations *already written by people who know the whole field*. See section 3.4. |
| D1a | Keyword retrieval is retained, scoped to **evidence for an already-named `(stage, method)` pair** | "scRNA clustering" is noise; "Leiden connectivity guarantee, benchmark" is precise. `source_plan.py` keeps its job, but stops deciding what exists. |
| D2 | Knowledge lives in **`dotfiles`**, code stays in **`Litintel`** | Clean split: knowledge is universal and must outlive the pipeline; code is PCa-scoped. `dotfiles` is already a separate repo, so this satisfies the repo-separation goal without a new repo. |
| D3 | **Git is the source of truth. Notion is a view.** | The requirement is a traceable history of what changed and why. `git log -p` is exactly that, for free, diffable and offline. Notion page history is time-limited, not diffable, and not agent-queryable. `storage/notion.py` also truncates every text property to 2000 chars, which method chapters will exceed immediately. |
| D4 | **Two layers**: curated evidence (append-only) -> synthesized chapters (derived) | Derived-and-committed chapters make the change log automatic and guarantee the synthesis cannot drift from its evidence. |
| D5 | Layer 2 is **regenerated, never hand-edited** | A `git diff` of a chapter between two dates *is* the "what changed and why" answer, with the commit pointing at the evidence that caused it. Hand-editing breaks that invariant. |
| D6 | Lifecycle status stays **user-confirmed, not LLM-inferred** | Carried forward unchanged from `docs/methodintel_plan.md:246`. Prevents training-era defaults from masquerading as authoritative. |
| D7 | The Tier 1 PCa pipeline is **demoted, not retired** | It keeps its own Notion record (still useful as a field-awareness feed) and additionally emits usage evidence. Nothing is deleted; it stops being the *source* of method knowledge and becomes *evidence* of adoption. |
| D8 | **Both layers are Markdown with YAML frontmatter.** HTML is a generated view only, never a storage format | One format for structured fields (frontmatter, as machine-strict as bare YAML) and prose (body). Already the house pattern -- agent-memory files and `SKILL.md` use exactly this shape, so bare YAML would be a third convention for no gain. Bare YAML has no rendering story at all. HTML is excluded as storage because HTML diffs are unreadable, which would break D5 outright; agents also read tag soup worse than Markdown. Rendering MD to HTML later is free; the reverse is not. |

---

## 3. Architecture

```
Litintel (code, PCa-scoped)                 dotfiles (knowledge, universal)
-----------------------------------         -----------------------------------
pubmed/ enrich/ tierc/ storage/             skills/bioinfo-methods/
methodintel/ {schema,router,                  SKILL.md
              source_plan,verify}             INDEX.md
        |                                     references/   <- layer 1
        |  writes plain files                 chapters/     <- layer 2
        +-------------------------------->
           one config key, one-way
```

**The dependency is one-way and file-based.** `dotfiles` never imports
`Litintel` and gains no Python dependency. If the pipeline is retired, the
knowledge base still loads into every agent and still works. That property is
the operational definition of "compounding."

### 3.1 Why `dotfiles/skills/` is the right home

`setup.sh::setup_wire_skills()` already walks every subdirectory of
`dotfiles/skills/` and deploys it to all three harnesses:

```
setup.sh:164   ln -sf "${src_file}" "${claude_dest}"    # Claude -> symlink
setup.sh:165   cp -f  "${src_file}" "${codex_dest}"     # Codex  -> copy (see below)
setup.sh:167   ln -sf "${src_file}" "${gemini_dest}"    # Gemini -> symlink
```

Consequences to rely on:

- Claude and Gemini get **file-level symlinks**, so editing an existing chapter
  is live in the next session with no `setup.sh` run.
- **Adding a new file** requires `setup.sh`, to mint the symlink.
- `setup.sh:112` refuses to prune when the source dir is empty, and pruning is
  driven by the `.dotfiles-skills` manifest, so an unrelated skill is never
  deleted.

**Pending one-line change to `setup.sh` (owner: Kun-Lin, not part of this
spec).** Codex now supports symlinked skill files, so the `cp -f` at `:165` is a
leftover from when it did not. Changing it to `ln -sf` also makes the `rm -rf`
staleness clearing at `:149-153` dead -- that block exists only to stop stale
*copies* accumulating. With all three harnesses symlinked, editing an existing
chapter is live everywhere and `setup.sh` is needed only when files are added.
Worth doing before the first large skill lands, since a knowledge base is edited
far more often than it is extended.

The pattern is already proven in the same repo:
`skills/bioinfo-code/references/ArchR/` holds `01_setup-and-installation.md`
through `10_trajectory-analysis.md`, and `AGENTS.md:199` already instructs
agents to "start with `INDEX.md`, then the topic file." `bioinfo-methods`
reuses that shape, adding the evidence layer and history the ArchR reference
lacks.

### 3.2 Layout

```
skills/bioinfo-methods/
  SKILL.md                       # trigger + how to query. Small.
  INDEX.md                       # chapter list + status-at-a-glance table. Small.
  references/                    # LAYER 1 -- curated evidence, append-only
    clustering/
      2026-08-02-traag2019-louvain-connectivity.md
      2026-08-02-pmid41234567-usage.md
    neighborhood_analysis/
    normalization/
  chapters/                      # LAYER 2 -- derived, regenerated, committed
    clustering.md
    neighborhood_analysis.md
    normalization.md
```

`references/` is sharded by stage so it mirrors `chapters/` one-to-one.

**Naming note.** In `bioinfo-code`, `references/` holds synthesized topic files
(the layer-2 equivalent here). In `bioinfo-methods`, `references/` holds the
curated evidence records and `chapters/` holds the synthesis. The word is kept
for structural symmetry with its sibling skill; the semantic difference is
deliberate, not accidental. The distinguishing property is curation: a
reference record is **selected and kept by a human**, not bulk-downloaded from
an API.

### 3.3 Progressive disclosure (required, not optional)

`setup.sh:120` notes that a deployed skill costs catalog budget, and this one
deploys to three harnesses. Therefore:

- `SKILL.md` and `INDEX.md` must stay small. They are the only files an agent
  loads by default.
- A chapter is read **on demand**, by name, from `INDEX.md`.
- `references/` is never bulk-loaded. It is read only on the audit path
  ("why did this status change?") or when regenerating a chapter.

### 3.4 Discovery: how the taxonomy gets populated

This is the load-bearing section. Two obvious approaches both fail, and they
fail the same way:

- **Keyword search over primary literature.** Noisy at useful breadth ("scRNA
  clustering" returns thousands of irrelevant hits), and structurally incapable
  of returning a method the searcher cannot name.
- **Waiting for the PCa pipeline to surface methods.** A method reaches the
  corpus only once someone applies it to prostate cancer and publishes. That is
  a lag of years, and for most methods it never happens at all.

Both are instances of the same defect: **you cannot query for what you do not
know exists.** Someone new to spatial transcriptomics does not know to ask about
neighborhood analysis, so no query formulation will surface it.

**The resolution: do not derive the field map. Read the maps the field already
publishes.** Enumeration is a reading problem, not a search problem.

| Source class | What it enumerates | Unknown it closes |
|---|---|---|
| Best-practice / review papers | the analysis pipeline, stage by stage | "I do not know that stage exists" -- the review has a section named after it |
| Tool docs and tutorial tables of contents | the tasks an ecosystem treats as standard | same, from the implementer's side. A mature package's tutorial index is a task map written by its authors |
| Benchmarking papers | competing methods inside one stage | "do I know all the options for this stage?" |
| Ecosystem release notes (scverse, Bioconductor, package changelogs) | what changed since the last check | "what appeared this year?" -- deterministic, no LLM required |

A review's **section headings are the stage taxonomy.** Candidate anchors for
single-cell: Luecken & Theis 2019 (Mol Syst Biol) and Heumos et al. 2023 (Nat
Rev Genet, best practices across modalities). Spatial has equivalents not yet
identified. `# VERIFY: confirm exact citations and current spatial equivalents
before any of them is written into a chapter.`

Precedent already in this repo family: `skills/bioinfo-code/references/ArchR/`
mirrors the ArchR manual's chapter structure. That is this move, applied one
level down -- taking a map someone else already drew.

#### 3.4.1 Coverage audit (the honest answer to unknown unknowns)

Completeness cannot be proven. It can be made **auditable**, which is the
strongest available claim:

- **Between stages.** Take the newest best-practice review's section list. Diff
  it against `chapters/`. The delta is the blind spot, named. Run on major
  review publication, roughly every 12-18 months.
- **Within a stage.** Diff a benchmark paper's method table against that
  chapter's status table. The delta is the missing option set.

This converts an open-ended worry into a scheduled, mechanical check with a
concrete output. It is the only part of this design that addresses unknown
unknowns, so it is not optional.

#### 3.4.2 Role of the PCa pipeline, restated

Tier 1 is the **lagging confirmation feed**: it reports which methods were
actually adopted in this specific field, which is real signal and available for
free. It is explicitly *not* a discovery channel. A method must already exist in
the taxonomy before Tier 1 can confirm adoption of it -- so the ordering is
seed-from-maps first, confirm-from-corpus second, never the reverse.

---

## 4. Layer 1: reference records

One Markdown file per record, structured fields in YAML frontmatter (D8).
**Append-only: never edited, never deleted.** A superseded claim is contradicted
by a newer record, not overwritten -- that is what makes the history real rather
than asserted.

```markdown
<!-- references/clustering/2026-08-02-traag2019-louvain-connectivity.md -->
---
id: 2026-08-02-traag2019-louvain-connectivity
stage: clustering
methods: ["Louvain", "Leiden"]
kind: benchmark          # benchmark | usage | deprecation | best_practice | personal
recorded: 2026-08-02
source_ref:
  kind: doi              # pmid | doi | url | docs_url | github_url | personal_obs
  value: "10.1038/s41598-019-41695-z"
  note: "Traag, Waltman, van Eck 2019"
citation:                # REQUIRED when source_ref.kind is pmid or doi
  first_author: "Traag"
  journal: "Sci Rep"
  year: 2019
confidence: high         # high | medium | low
---

Louvain can yield arbitrarily badly connected, and in some cases disconnected,
communities. Leiden guarantees well-connected communities.

Bears on the ArchR Louvain -> Leiden decision at Apollo Stage 5.
```

The claim itself lives in the **body**, as prose, not as a quoted YAML scalar.
That is the readability win: the record renders in VSCode preview and on GitHub,
and the part a human actually reads is plain text. Frontmatter carries only what
a machine needs to index on.

#### Citation is mandatory, not decorative

`citation` is **required** whenever `source_ref.kind` is `pmid` or `doi`. A
record citing a paper without first author, journal, and year is invalid and the
generator must reject it.

Rationale: the primary reader of a chapter is not only the author. A PI
evaluating a method recommendation will weigh venue and recency whether or not
the author does, and a recommendation that cannot show where its evidence was
published is not defensible in that conversation. The design does not take a
position on impact factor; it only guarantees the information is present.

All three fields are already retrievable for free -- `pubmed/client.py` returns
journal, year, and authors on every `efetch`, so the usage feed populates this
with no extra call. Manual and `docs_url` / `github_url` records fill what
applies and omit the block otherwise.

The `source_ref` block is deliberately **field-identical to
`methodintel/schema.py::SourceRef` (`:91`)**, and `kind` reuses
`SourceRefKind` (`:80`) verbatim, including `personal_obs`. A record maps to
one `EvidenceClaim` (`schema.py:99`) -- frontmatter to fields, body to
`statement` -- with no translation layer.

### 4.1 Four feeds

Ordered by when they run, not by volume. Feed 1 is the only one that can
introduce a *new stage*; the rest populate stages that already exist.

| Feed | Source | Kind | Cost |
|---|---|---|---|
| **1. Field maps** (3.4) | Review section headings, tool tutorial indices, benchmark tables | `best_practice`, `benchmark` | small, a few reads per refresh |
| 2. Targeted evidence | Agent retrieval for an **already-named** `(stage, method)`, via `source_plan.py::build_source_plan()` (`:4`) | `benchmark`, `deprecation` | small, on demand |
| 3. Personal observation | Hand-written from Apollo / pipeline work | `personal` | free |
| 4. Usage signal (lagging) | Pass 2 output on records scoring `>= pass2_min_score` (88), `enrich/ai_client.py::enrich_pass2_methods` | `usage` | free -- already computed today |

Feed 3 is the differentiator. Benchmark papers are public and any agent
can find them; "ArchR Louvain failed this way on our spatial ATAC data" exists
nowhere else. Over years this is what makes the base better than a search rather
than merely more stable than one.

### 4.2 Write protocol across the repo boundary

Litintel **writes** reference records into the configured path but **never
commits** them. The human reviews and commits in `dotfiles`.

This is not a limitation to work around. It is the review gate D6 requires,
enforced by the repo boundary instead of by convention.

**Worktree isolation applies, and it splits by write mechanism.** Both repos are
opted in -- `worktree-isolation` marker present in each `.git` -- so
`institution/hooks/trunk_write_guard.sh` is live. Confirmed behavior:

| Write path | Policed? | Rule |
|---|---|---|
| Agent `Edit`/`Write` tool into the `dotfiles` **trunk** | yes -- **blocked**, exit 2 | Must go through `dotfiles-claude`, land by `merge --ff-only`. |
| Agent `Edit`/`Write` into `dotfiles-claude` | passes | Normal agent home. |
| Pipeline write from Python/Bash | **no** | The hook is a Claude `PreToolUse(Edit\|Write)` guard; its header (`:12-13`) states Bash writes are deliberately out of scope, with the git pre-commit hook as the backstop. |

So a Litintel run would *not* be blocked writing into the trunk, but agent-driven
chapter generation would be. To keep one rule instead of two:

```yaml
methods_repo_path: "~/GitHub/dotfiles-claude/skills/bioinfo-methods"
```

**Assumption stated:** point at the agent worktree home, not the trunk, and land
everything by `git -C ~/GitHub/dotfiles merge --ff-only claude`. This obeys the
isolation rule with no exception carved for the pipeline, and the resulting lag
before `setup.sh` redeploys *is* the D6 review gate rather than a cost. The
alternative -- pipeline writes straight into the trunk, since append-only records
carry unique date+id filenames and essentially never conflict -- is rejected only
because it needs a standing exception to A3.

---

## 5. Layer 2: chapters

One Markdown chapter per pipeline stage -- the "encyclopedia chapter" unit.
Generated from the stage's `references/` shard, committed to git, never edited
by hand.

Required sections:

1. **Current recommendation** -- one method, one implementation, one sentence.
2. **Status table** -- per method: `lifecycle_status`, `last_reviewed`,
   `successor_methods`. Fields are exactly
   `schema.py::MethodOption` (`:119-135`), which **already carries all three**
   (`:132-134`) -- no schema change needed.
3. **Tradeoffs** -- when each option becomes the better choice and what it costs.
4. **What changed** -- most recent status transitions, each citing the reference
   record id that caused it.
5. **References** -- numbered bibliography, paper-style (see 5.2).
6. **Open questions** -- what is unresolved, tagged for a future pass.

Every claim in a chapter must carry a reference record id. A chapter sentence
with no backing record is a generation bug, not an editorial choice.

### 5.1 Citation rendering

Prose carries inline numeric markers; the chapter foot carries the numbered
list. It reads like a paper:

```markdown
Leiden is preferred over Louvain because Louvain can produce disconnected
communities, while Leiden guarantees connectivity [1]. Adoption in spatial
ATAC followed within two years [2,3].

## References

1. Traag et al. Sci Rep (2019). doi:10.1038/s41598-019-41695-z  [verified]
2. ...
```

**Numbers are cosmetic and assigned at render time.** The stable identifier is
always the reference record id. Two consequences that matter:

- Section 4 ("What changed") cites **record ids, never numbers**, so the
  semantic history stays stable when the bibliography renumbers.
- Inserting a claim renumbers everything after it. That diff is noise, but it is
  confined to the References block and the inline markers -- it cannot corrupt
  the changelog, which is what D5 protects.

The `verified` flag from `verify.py::verify_evidence_claims()` (`:26`) renders
as a badge on the bibliography entry rather than as its own table, which keeps
the chapter lighter than the earlier separate-evidence-table design.

### 5.2 Method vs implementation, kept separate

`schema.py::MethodOption` already splits `algorithm` from `implementation`
(`:127-128`) precisely because one algorithm is exposed by several packages with
different pipeline-fit consequences. Chapters must preserve that split.

Worked example -- neighborhood analysis:

- **Stage:** neighborhood analysis
- **Implementation:** Squidpy
- **Methods it exposes:** Moran's I, Ripley's K/L, neighborhood enrichment

`# VERIFY: confirm exact Squidpy function names and module paths against current
docs before writing any of them into a chapter.`

A chapter that says "use Squidpy" without naming the method has flattened the
axes this system exists to keep separate.

---

## 6. Integration contract

Litintel's entire integration surface is **one new key** in `configs/*.yaml`:

```yaml
methods_repo_path: "~/GitHub/dotfiles/skills/bioinfo-methods"
```

No Python is copied or shared. This matches the existing fan-out shape --
`storage/drive.py` and `storage/notion.py` already write into systems that have
no knowledge of Litintel. Writing into a directory is strictly simpler than
either.

### 6.1 Existing code that plugs in unchanged

| Component | Location | Role here |
|---|---|---|
| `RouterMode` (5 modes) | `schema.py:8-16` | Classifies the question. `STALENESS_CHECK` is the "what changed" path. |
| `ArtifactType` | `schema.py:18-26` | `LIFECYCLE_REPORT` and `STAGE_MAP` map onto chapters. |
| `SourceRef` / `SourceRefKind` | `schema.py:80-97` | Reference record schema (section 4). |
| `EvidenceClaim` | `schema.py:99-109` | Enforces "no claim without a source" at schema level. |
| `MethodOption` | `schema.py:119-135` | Chapter status table. Lifecycle fields already present. |
| `MethodGraphEdge` | `schema.py:154+` | `replaces_or_modernizes`, `deprecated_by`, `competes_with` already in `ALLOWED_EDGE_TYPES`. |
| `verify_evidence_claims()` | `verify.py:26` | Sets the `verified` flag in chapter evidence tables. |
| `build_source_plan()` | `source_plan.py:4` | Drives the targeted-evidence feed. |

`methodintel/` still lacks `prompts.py` and `build_dossier.py`
(`docs/methodintel_plan.md` Phase 3, `docs/todo_litintel.html` section 3). The
chapter generator is where that gap gets closed.

### 6.2 Views (all derived, none authoritative)

- **Claude / Codex / Gemini skill** -- via `setup.sh`. The "check my base before
  web searching" path. Primary consumer.
- **Notion** -- a *second* database, method-shaped, distinct from the PCa paper
  DB. For browsing only.
- **Vertex RAG corpus** -- chapters synced through the existing
  `storage/rag_corpus.py` for semantic query.

---

## 7. Out of scope (YAGNI)

Explicitly deferred until a real chapter proves the need:

- The six-tier lifecycle enum (`schema.py:111` keeps 3 tiers; Phase 4.5).
- A visual method graph. JSON edges only.
- Automated chapter regeneration on a schedule. Manual invocation first.
- Notion export for methods. Local artifact must be useful first.
- Splitting `references/` out of the skill directory. Revisit only if the
  symlink count becomes a real problem.
- Changing `configs/tier1_pca.yaml` discovery. The PCa corpus stays as-is (D7).
- A generated browsable `INDEX.html` over the chapters. This is the right home
  for HTML when it is wanted (D8), and it is purely additive -- a renderer over
  committed Markdown, addable at any time without touching storage.

---

## 8. Definition of done for v1

- [ ] `skills/bioinfo-methods/` exists in `dotfiles` with `SKILL.md` + `INDEX.md`.
- [ ] `setup.sh` deploys it to all three harnesses (verified by observing the
      deployed file in each of the three harness trees, not assumed).
- [ ] One stage fully populated end to end -- clustering, reusing the existing
      Stage 5 MVP question from `docs/methodintel_plan.md:76`.
- [ ] That chapter is generated from its `references/` shard, not hand-written,
      and every claim carries a record id.
- [ ] A Claude session answers a clustering method question from the chapter
      **without a web search**, with citations.
- [ ] Every cited `pmid`/`doi` record carries first author, journal, and year,
      and the chapter renders them as a numbered bibliography (5.1).
- [ ] Tier 1 emits at least one `usage` record into `references/` on a real run.
- [ ] A status change is demonstrable as a `git diff` on the chapter.
- [ ] The stage list in `INDEX.md` was seeded from a named review's section
      headings (D1 / 3.4), and that review is recorded as a reference record so
      the next coverage audit has a baseline to diff against.

---

## 9. Open questions

1. **Stage taxonomy -- the one blocking item.** *Method* is now settled (D1 /
   3.4: seed from a review's section headings, not from memory), but the
   *source* is not chosen. Needs: one named single-cell best-practice review
   and one spatial equivalent, current as of 2026.
   `# VERIFY: confirm Luecken & Theis 2019 (Mol Syst Biol) and Heumos et al.
   2023 (Nat Rev Genet) exist as cited, and identify the spatial counterpart --
   none is confirmed yet.` `docs/methodintel_plan.md:480` supplies five
   candidate stages, which is a starting overlap to diff against, not the list.
2. **Coverage-audit cadence.** 3.4.1 proposes running the between-stage diff on
   major review publication (~12-18 months). Whether that is manual, or a
   `staleness_check` invocation, is undecided.
3. **Chapter regeneration cost.** Not yet estimated.
   `docs/methodintel_plan.md:287` budgets <= 50k input / <= 10k output tokens
   per dossier; a chapter is a different unit and the number does not
   necessarily transfer.
4. **Notion methods DB schema.** Deferred (section 7), so its property mapping
   is undefined. Not blocking.
5. ~~Whether `trunk_write_guard.sh` blocks the cross-repo write.~~ **Resolved**
   -- see the table in 4.2. Both repos are opted in; the hook policies agent
   `Edit`/`Write` tool calls only, not Bash/Python writes. Design now routes
   through `dotfiles-claude` so one rule covers both paths.
6. ~~Codex symlink support in `setup.sh`.~~ **Closed by owner decision
   (2026-08-02): leave as is.** `cp -f` appears for Codex at `:165` (skills),
   `:317-318` (hooks), and `:478-479` (dispatch bin); changing one without the
   others is inconsistent, and the hook paths carry more risk than the benefit
   justifies. Consequence to accept: editing an existing chapter is live for
   Claude and Gemini but requires a `setup.sh` run for Codex.
