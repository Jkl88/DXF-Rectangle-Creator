from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContourKind(Enum):
    RECT = "rect"
    CIRCLE = "circle"
    DXF = "dxf"


class CornerMode(Enum):
    RADIUS = "radius"
    CHAMFER = "chamfer"


class HoleKind(Enum):
    CIRCLE = "circle"
    RECT = "rect"
    OVAL = "oval"
    POLYGON = "polygon"


class ArrayKind(Enum):
    GRID = "grid"
    MIRROR = "mirror"
    CIRCULAR = "circular"


class MirrorAxis(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class SelectionKind(Enum):
    NONE = "none"
    CONTOUR = "contour"
    ORIGIN = "origin"
    HOLE = "hole"
    ARRAY = "array"
    DIMENSION = "dimension"
    TITLE_BLOCK = "title_block"
    MEASURE = "measure"
    SHUTTER = "shutter"
    INFINITE_LINE = "infinite_line"
    DRAWN_RECT = "drawn_rect"


@dataclass
class RectContour:
    width: float = 120.0
    height: float = 48.0
    corner_mode: CornerMode = CornerMode.RADIUS
    corner_size: float = 0.0

    def max_corner_size(self) -> float:
        return min(self.width, self.height) * 0.5

    def clamp_corner(self) -> None:
        self.corner_size = max(0.0, min(self.corner_size, self.max_corner_size()))


@dataclass
class CircleContour:
    diameter: float = 80.0


@dataclass
class DxfContour:
    """Imported DXF geometry; coordinates in editor space (Y down, origin at DXF 0,0)."""
    entities: list[dict] = field(default_factory=list)
    origin_x: float = 0.0
    origin_y: float = 0.0
    origin_set: bool = False
    source_file: str = ""


@dataclass
class Hole:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    kind: HoleKind = HoleKind.CIRCLE
    cx: float = 10.0
    cy: float = 10.0
    diameter: float = 6.0
    width: float = 6.0
    height: float = 6.0
    angle: float = 0.0
    sides: int = 6
    color: str = "#e03131"

    def display_name(self, index: int) -> str:
        return self.name or f"Отверстие {index}"


@dataclass
class HoleArray:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    source_hole_id: str = ""
    kind: ArrayKind = ArrayKind.GRID
    count_x: int = 2
    count_y: int = 2
    step_x: float = 20.0
    step_y: float = 20.0
    grid_angle: float = 0.0
    mirror_axis: MirrorAxis = MirrorAxis.HORIZONTAL
    center_x: float = 60.0
    center_y: float = 24.0
    center_fixed: bool = False
    radius: float = 30.0
    count: int = 4
    step_angle: float = 0.0

    def display_name(self, index: int) -> str:
        return self.name or f"Массив {index}"


@dataclass
class ObjectDisplayState:
    show_dims: bool = False


@dataclass
class DimensionState:
    dim_id: str
    offset: float = 7.0
    font_size: int = 9
    font_size_custom: bool = False
    always_show: bool = False
    locked: bool = False
    ref_anchor: float | None = None
    # Frozen dim-line endpoints for angled (grid step) dimensions: d1x, d1y, d2x, d2y
    line_anchor: tuple[float, float, float, float] | None = None
    # Override default placement side (top/bottom/left/right) when user flips a dimension.
    side: str | None = None


@dataclass
class LeaderState:
    note_id: str
    offset_x: float = -50.0
    offset_y: float = -20.0
    font_size: int = 9
    font_size_custom: bool = False
    always_show: bool = False
    locked: bool = False


@dataclass
class InstanceState:
    key: str
    always_show: bool = True


@dataclass
class Selection:
    kind: SelectionKind = SelectionKind.NONE
    object_id: str = ""
    instance_index: int = -1


@dataclass
class TitleBlock:
    developer: str = ""
    logo_path: str = ""
    logo_text: str = ""
    logo_mode: str = "image"  # "image" | "text"
    include_in_png: bool = True


@dataclass
class MeasureAnchor:
    kind: str = "free"
    object_id: str = ""
    instance_index: int = -1
    role: str = ""
    entity_index: int = -1
    x: float = 0.0
    y: float = 0.0


@dataclass
class MeasureAnnotation:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    kind: str = "linear"  # linear | diameter | radius
    size: float = 0.0
    p1x: float = 0.0
    p1y: float = 0.0
    p2x: float = 0.0
    p2y: float = 0.0
    anchor1: MeasureAnchor = field(default_factory=MeasureAnchor)
    anchor2: MeasureAnchor = field(default_factory=MeasureAnchor)

    def display_name(self, index: int) -> str:
        return self.name or f"Размер {index}"


@dataclass
class ShutterLayoutParams:
    gap_horizontal: float = 20.0
    gap_vertical: float = 6.5
    wide_width: float = 11.4
    thin_width: float = 0.6
    cell_height: float = 80.0

    @property
    def cell_width(self) -> float:
        return self.wide_width + self.thin_width

    @classmethod
    def defaults(cls) -> ShutterLayoutParams:
        from app.geometry.shutter import (
            GAP_HORIZONTAL, GAP_VERTICAL, SHUTTER_H, SHUTTER_THIN_W, SHUTTER_WIDE_W,
        )
        return cls(
            gap_horizontal=GAP_HORIZONTAL,
            gap_vertical=GAP_VERTICAL,
            wide_width=SHUTTER_WIDE_W,
            thin_width=SHUTTER_THIN_W,
            cell_height=SHUTTER_H,
        )


@dataclass
class ShutterRegion:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    cx: float = 60.0
    cy: float = 24.0
    width: float = 120.0
    height: float = 86.5
    angle: float = 0.0  # 0, 90, 180, 270
    color: str = "#495057"

    def display_name(self, index: int) -> str:
        return self.name or f"Шторки {index}"


@dataclass
class InfiniteLine:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    src_x1: float = 0.0
    src_y1: float = 0.0
    src_x2: float = 0.0
    src_y2: float = 0.0
    offset: float = 0.0
    inf_x1: float = 0.0
    inf_y1: float = 0.0
    inf_x2: float = 0.0
    inf_y2: float = 0.0
    color: str = "#868e96"
    locked: bool = False
    source_anchor: MeasureAnchor = field(default_factory=MeasureAnchor)

    def display_name(self, index: int) -> str:
        return self.name or f"Всп. линия {index}"


@dataclass
class DrawnRectangle:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    cx: float = 60.0
    cy: float = 24.0
    width: float = 120.0
    height: float = 48.0
    angle: float = 0.0
    color: str = "#495057"

    def display_name(self, index: int) -> str:
        return self.name or f"Прямоугольник {index}"


@dataclass
class ResolvedHole:
    kind: HoleKind
    cx: float
    cy: float
    diameter: float = 6.0
    width: float = 6.0
    height: float = 6.0
    angle: float = 0.0
    sides: int = 6
    source_id: str = ""


def _clone_hole(hole: Hole, cx: float, cy: float, angle_delta: float = 0.0) -> ResolvedHole:
    return ResolvedHole(
        kind=hole.kind,
        cx=cx,
        cy=cy,
        diameter=hole.diameter,
        width=hole.width,
        height=hole.height,
        angle=hole.angle + angle_delta,
        sides=hole.sides,
        source_id=hole.id,
    )


def _transform_point(x: float, y: float, ox: float, oy: float, angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    dx, dy = x - ox, y - oy
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return ox + dx * cos_a - dy * sin_a, oy + dx * sin_a + dy * cos_a
