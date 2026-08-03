"""The analysis-modality vocabulary and the DataTypes -> modality seam.

The defect these pin: `DataTypes` is an ASSAY vocabulary ("snRNA-seq, Visium,
H&E") and a record's `modality` is the ANALYSIS axis chapters are organized
by. Copying one into the other put "H&E" in a status row and produced a
`### H&E` chapter section reading "This modality is **not audited**" -- the
design's information carrier (spec 3.4.4) firing for a stain, in append-only
records that only the owner can delete.
"""

import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.modality import (
    ANALYSIS_MODALITIES,
    ModalityError,
    check_analysis_modalities,
    map_data_types,
)


def test_h_and_e_only_paper_yields_no_modality():
    """The reproduced defect. An imaging assay has no analysis modality, so
    the honest answer is an empty list -- never a guess, because a wrong
    modality is indistinguishable from a right one once it is on disk."""
    assert map_data_types("H&E") == []


def test_visium_maps_to_spatial_rna():
    assert map_data_types("Visium") == ["spatial_rna"]
    assert map_data_types("10x Visium") == ["spatial_rna"]


def test_mixed_data_types_keep_only_what_maps():
    """A real paper's DataTypes mixes assays that do and do not map. The
    mappable ones must survive and the rest must vanish silently -- dropping
    H&E is not a loss, it is the point."""
    assert map_data_types("snRNA-seq, Visium, H&E") == ["scRNA", "spatial_rna"]


def test_bulk_atac_does_not_become_single_cell_atac():
    """The taxonomy spells the single-cell forms 'scATAC-seq'/'snATAC-seq'
    and lists bare 'ATAC-seq' as bulk. Mapping bare ATAC-seq to scATAC would
    claim single-cell evidence a bulk paper never produced."""
    assert map_data_types("ATAC-seq") == []
    assert map_data_types("scATAC-seq") == ["scATAC"]


def test_spatial_atac_maps_to_its_own_modality():
    assert map_data_types("Spatial ATAC") == ["spatial_atac"]
    assert map_data_types("spatial-ATAC-seq") == ["spatial_atac"]


def test_result_is_sorted_and_deduplicated():
    """The result is written into an append-only record, so it must not
    depend on the order the model happened to list the assays in."""
    assert map_data_types("Visium, snRNA-seq, MERFISH, scRNA-seq") == [
        "scRNA", "spatial_rna",
    ]


def test_ambiguous_platform_contributes_nothing():
    """GeoMx is 'spatial proteomics/transcriptomics' in the taxonomy itself;
    which one a given paper used is not knowable here."""
    assert map_data_types("NanoString GeoMx") == []


def test_empty_data_types_is_not_an_error():
    assert map_data_types("") == []
    assert map_data_types("  ,  ") == []


def test_check_accepts_every_vocabulary_value():
    check_analysis_modalities("test", sorted(ANALYSIS_MODALITIES))


def test_check_accepts_an_empty_list():
    """No modality recorded is a real state, not a defect."""
    check_analysis_modalities("test", [])


def test_check_rejects_an_assay_name_and_names_it():
    with pytest.raises(ModalityError) as excinfo:
        check_analysis_modalities("record 2026-08-02-x", ["scRNA", "H&E"])

    assert "H&E" in str(excinfo.value)
    assert "2026-08-02-x" in str(excinfo.value)
