from __future__ import annotations

import math

import ezdxf

from app.geometry.dxf_entities import _editor_to_dxf_xy, export_entities_to_msp
from app.geometry.shutter import thin_slats_for_export
from app.models.base import ContourKind, CornerMode, HoleKind
from app.models.document import Document


def _chamfered_rect_points(width, height, chamfer):
    if chamfer <= 0:
        return [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
    return [
        (chamfer, 0), (width - chamfer, 0), (width, chamfer),
        (width, height - chamfer), (width - chamfer, height),
        (chamfer, height), (0, height - chamfer), (0, chamfer), (chamfer, 0),
    ]


def _add_rect_contour(msp, rect):
    w, h, cs = rect.width, rect.height, rect.corner_size
    if cs <= 0:
        msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h), (0, 0)], close=True)
        return
    if rect.corner_mode == CornerMode.CHAMFER:
        msp.add_lwpolyline(_chamfered_rect_points(w, h, cs), close=True)
        return
    r = cs
    msp.add_line((r, 0), (w - r, 0))
    msp.add_arc(center=(w - r, r), radius=r, start_angle=270, end_angle=360)
    msp.add_line((w, r), (w, h - r))
    msp.add_arc(center=(w - r, h - r), radius=r, start_angle=0, end_angle=90)
    msp.add_line((w - r, h), (r, h))
    msp.add_arc(center=(r, h - r), radius=r, start_angle=90, end_angle=180)
    msp.add_line((0, h - r), (0, r))
    msp.add_arc(center=(r, r), radius=r, start_angle=180, end_angle=270)


def _add_slot(msp, rh, *, height: float, y_negate: bool):
    from app.geometry.slot import iter_slot_dxf_primitives, slot_is_round, to_world
    xy = lambda x, y: _editor_to_dxf_xy(x, y, height=height, y_negate=y_negate)
    if slot_is_round(rh.width, rh.height):
        msp.add_circle(xy(rh.cx, rh.cy), rh.height / 2)
        return
    for kind, data in iter_slot_dxf_primitives(rh.width, rh.height):
        if kind == "line":
            x1, y1, x2, y2 = data
            w1 = to_world(rh.cx, rh.cy, rh.angle, x1, y1)
            w2 = to_world(rh.cx, rh.cy, rh.angle, x2, y2)
            msp.add_line(xy(w1[0], w1[1]), xy(w2[0], w2[1]))
        elif kind == "arc":
            acx, acy, r, start, end = data
            wx, wy = to_world(rh.cx, rh.cy, rh.angle, acx, acy)
            cx, cy = xy(wx, wy)
            msp.add_arc(
                center=(cx, cy), radius=r,
                start_angle=start + rh.angle, end_angle=end + rh.angle,
            )
        elif kind == "circle":
            msp.add_circle(xy(rh.cx, rh.cy), data[2])


def _add_hole(msp, rh, *, height: float, y_negate: bool):
    xy = lambda x, y: _editor_to_dxf_xy(x, y, height=height, y_negate=y_negate)
    if rh.kind == HoleKind.CIRCLE:
        msp.add_circle(xy(rh.cx, rh.cy), rh.diameter / 2)
    elif rh.kind == HoleKind.OVAL:
        _add_slot(msp, rh, height=height, y_negate=y_negate)
    elif rh.kind == HoleKind.RECT:
        hw, hh = rh.width / 2, rh.height / 2
        pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
        rad = math.radians(rh.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        world = []
        for x, y in pts:
            wx = rh.cx + x * cos_a - y * sin_a
            wy = rh.cy + x * sin_a + y * cos_a
            world.append(xy(wx, wy))
        msp.add_lwpolyline(world, close=True)
    else:
        sides = max(3, rh.sides)
        r = rh.diameter / 2
        pts = []
        for i in range(sides):
            a = math.radians(360 * i / sides - 90 + rh.angle)
            pts.append(xy(rh.cx + r * math.cos(a), rh.cy + r * math.sin(a)))
        pts.append(pts[0])
        msp.add_lwpolyline(pts, close=True)


def _add_shutter_slats(
    msp, shutter, *, height: float, y_negate: bool, layout,
) -> None:
    xy = lambda x, y: _editor_to_dxf_xy(x, y, height=height, y_negate=y_negate)
    for corners in thin_slats_for_export(
        shutter.cx, shutter.cy, shutter.width, shutter.height,
        shutter.angle, layout,
    ):
        pts = [xy(x, y) for x, y in corners]
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        msp.add_lwpolyline(pts, close=True)


def _add_drawn_rectangle(msp, rect, *, height: float, y_negate: bool) -> None:
    xy = lambda x, y: _editor_to_dxf_xy(x, y, height=height, y_negate=y_negate)
    left = rect.cx - rect.width / 2
    right = rect.cx + rect.width / 2
    top = rect.cy - rect.height / 2
    bottom = rect.cy + rect.height / 2
    pts = [
        xy(left, top), xy(right, top), xy(right, bottom), xy(left, bottom), xy(left, top),
    ]
    msp.add_lwpolyline(pts, close=True)


def export_dxf(document: Document, file_path: str) -> None:
    doc = ezdxf.new(dxfversion="R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()

    dxf_contour = document.contour_kind == ContourKind.DXF
    if dxf_contour:
        _, _, _, height = document.contour_bounds()
        export_entities_to_msp(
            msp, document.dxf_contour.entities,
            height=height, y_negate=True,
        )
    elif document.contour_kind == ContourKind.CIRCLE:
        d = document.circle.diameter
        msp.add_circle((d / 2, d / 2), d / 2)
        height = d
    else:
        _add_rect_contour(msp, document.rect)
        height = document.rect.height

    y_negate = dxf_contour
    for rh in document.resolve_holes():
        _add_hole(msp, rh, height=height, y_negate=y_negate)

    for shutter in document.shutters:
        _add_shutter_slats(
            msp, shutter, height=height, y_negate=y_negate,
            layout=document.shutter_layout,
        )

    for rect in document.drawn_rects:
        _add_drawn_rectangle(msp, rect, height=height, y_negate=y_negate)

    doc.saveas(file_path)
