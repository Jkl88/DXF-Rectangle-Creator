from __future__ import annotations

import os

import ezdxf

from app.geometry.dxf_entities import import_modelspace_entities, normalize_imported_entities
from app.models.base import ContourKind, DxfContour
from app.models.document import Document


def apply_dxf_contour(document: Document, file_path: str) -> None:
    """Import all drawable geometry from DXF as fixed contour."""
    dxf = ezdxf.readfile(file_path)
    entities = normalize_imported_entities(import_modelspace_entities(dxf.modelspace()))
    if not entities:
        raise ValueError("В файле не найдено подходящей геометрии")

    document.contour_kind = ContourKind.DXF
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    document.dxf_contour = DxfContour(
        entities=entities,
        origin_x=0.0,
        origin_y=0.0,
        origin_set=False,
        source_file=os.path.basename(file_path),
    )
    document.name = base_name
    document.rect.corner_size = 0.0
