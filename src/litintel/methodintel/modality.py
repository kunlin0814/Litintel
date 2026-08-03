"""The analysis-modality vocabulary, and the one seam that maps assays onto it.

Two different vocabularies were being used as if they were one, which is what
let a staining platform become a chapter section:

  ANALYSIS modality -- what a layer 1 record indexes on, and what a chapter is
      organized by: scRNA / scATAC / spatial_rna / spatial_atac / multiome.
      "Is this method audited for spatial ATAC?" is a question on this axis.
  ASSAY / platform  -- what the Pass 1 `DataTypes` field carries, drawn from
      the METHOD & PLATFORM TAXONOMY in enrich/prompt_templates.py:
      "snRNA-seq, Visium, H&E".

The two overlap but are not the same axis, and several assay terms have no
analysis modality at all. Writing an assay name into a record's `modality`
made chapters.py render `### H&E` with "This modality is **not audited**" --
the design's information carrier (spec 3.4.4) firing for a stain.

So the vocabulary lives here, once, and both the writer (writer.py, which
gates what enters append-only layer 1) and the renderer
(chapters.py::assemble_chapter) check against THIS module rather than each
carrying its own idea of what a modality is.

Mapping rule: map only where the mapping is real and unambiguous. An assay
with no analysis modality contributes NOTHING -- an empty modality list is
honest, a guessed one corrupts the chapter and cannot be withdrawn, because
layer 1 is append-only (spec D4).
"""

from __future__ import annotations

from typing import Iterable, List


# The analysis-modality axis. These five are the values every hand-curated
# record in the knowledge base uses, and the values chapters.py's per-modality
# sections are written for.
ANALYSIS_MODALITIES: frozenset[str] = frozenset({
    "scRNA",
    "scATAC",
    "spatial_rna",
    "spatial_atac",
    "multiome",
})


# Controlled DataTypes term (lowercased) -> analysis modality.
#
# Keys are taken from the METHOD & PLATFORM TAXONOMY the Pass 1 and Pass 2
# prompts actually publish (prompt_templates.py, "Use these controlled terms
# when classifying Methods and DataTypes"), plus the short forms that same
# prompt's own worked example emits -- its DataTypes example is
# "snRNA-seq, Visium, H&E", i.e. "Visium", not the taxonomy's "10x Visium".
# Both forms are listed explicitly rather than normalized by stripping
# vendor prefixes: an explicit table is auditable against the prompt line by
# line, and a normalizer is one more place to be subtly wrong.
#
# DELIBERATELY ABSENT, because no honest mapping exists:
#   H&E staining, IHC, IF, multiplexed imaging (CODEX/IMC/MIBI)
#       -- imaging, not an analysis modality at all. This is the term that
#          produced the "### H&E ... not audited" chapter section.
#   Bulk RNA-seq, WGS, WES, ChIP-seq, CUT&RUN, CUT&Tag, Bisulfite-seq, WGBS,
#   Hi-C, and bare "ATAC-seq" (the taxonomy lists it as "ATAC-seq (bulk)")
#       -- bulk assays. Note that bare "ATAC-seq" must NOT map to scATAC:
#          the taxonomy spells the single-cell forms "scATAC-seq"/"snATAC-seq".
#   NanoString GeoMx
#       -- the taxonomy itself calls it "spatial proteomics/transcriptomics",
#          so which it is in a given paper is unknown here.
#   CITE-seq, scDNA-seq
#       -- single-cell, but protein+RNA and DNA/CNV respectively; neither is
#          one of the five analysis modalities.
_ASSAY_TO_MODALITY: dict[str, str] = {
    # Single-cell sequencing
    "scrna-seq": "scRNA",
    "snrna-seq": "scRNA",
    "scatac-seq": "scATAC",
    "snatac-seq": "scATAC",
    "multiome": "multiome",
    "10x multiome": "multiome",
    # Spatial transcriptomics -- spot-based, in-situ and imaging-based alike
    "10x visium": "spatial_rna",
    "visium": "spatial_rna",
    "10x visium hd": "spatial_rna",
    "visium hd": "spatial_rna",
    "10x xenium": "spatial_rna",
    "xenium": "spatial_rna",
    "nanostring cosmx": "spatial_rna",
    "cosmx": "spatial_rna",
    "merfish": "spatial_rna",
    "seqfish": "spatial_rna",
    "slide-seq": "spatial_rna",
    "slide-seqv2": "spatial_rna",
    # Spatial ATAC
    "spatial atac": "spatial_atac",
    "spatial-atac": "spatial_atac",
    "spatial atac-seq": "spatial_atac",
    "spatial-atac-seq": "spatial_atac",
}


class ModalityError(ValueError):
    """A modality value is not on the analysis-modality axis."""


def map_data_types(raw: str) -> List[str]:
    """Pass 1 `DataTypes` -> analysis modalities. Unmappable assays drop out.

    `DataTypes` is a comma-separated controlled list (prompt_templates.py:
    "### DataTypes -- Comma-separated list"), so the split lives here with
    the vocabulary rather than at each call site.

    Returns a sorted, de-duplicated list. Sorted because the result is
    written into an append-only record and must not depend on the order the
    model happened to list the assays in. Returns [] when nothing maps --
    a paper whose only DataTypes entry is "H&E" contributes no analysis
    modality, and saying nothing is the correct answer.
    """
    mapped = set()
    for term in raw.split(","):
        key = " ".join(term.strip().lower().split())
        if not key:
            continue
        modality = _ASSAY_TO_MODALITY.get(key)
        if modality is not None:
            mapped.add(modality)

    return sorted(mapped)


def check_analysis_modalities(where: str, modality: Iterable[str]) -> None:
    """Raise unless every value is on the analysis-modality axis.

    `where` names the record or file under inspection so the error points at
    the offending record rather than at the renderer. An empty list is
    legal -- "no modality recorded" is a real state (see map_data_types) and
    chapters.py already renders it as "unspecified" without inventing a
    per-modality audit section for it.
    """
    unknown = sorted({m for m in modality if m not in ANALYSIS_MODALITIES})
    if unknown:
        raise ModalityError(
            "%s: modality %s is not on the analysis-modality axis; expected "
            "values from %s (an assay or platform name such as an H&E or a "
            "bulk protocol is not a modality -- leave the list empty instead)"
            % (where, unknown, sorted(ANALYSIS_MODALITIES))
        )
