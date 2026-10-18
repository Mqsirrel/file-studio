"""Crisp, resolution-independent vector icon renderer for File Studio.

Draws clean geometric icons for:
- Studio tools: compress, metadata, edit, annotate, addbg, crop, redact, extract
- File type badges: kind_image, kind_pdf, kind_video, kind_audio, kind_doc, kind_archive
- UI actions: back, close, folder, open_ext, copy, check, plus, bolt, add_image
"""
from __future__ import annotations

import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap


def _pen(color: QColor, width: float = 2.0) -> QPen:
    return QPen(
        QBrush(color),
        width,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )


def icon_pixmap(name: str, size: int, color: QColor | str) -> QPixmap:
    """Render a vector icon into a crisp transparent QPixmap."""
    col = QColor(color) if isinstance(color, str) else color
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    draw_icon(p, name, QPointF(size / 2.0, size / 2.0), float(size * 0.78), col)
    p.end()
    return pm


def draw_icon(p: QPainter, name: str, center: QPointF, size: float, color: QColor) -> None:
    """Draw named vector icon centered at `center` within a `size x size` box."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(center)
    s = size / 24.0
    p.scale(s, s)

    stroke = 2.1
    p.setPen(_pen(color, stroke))
    p.setBrush(Qt.BrushStyle.NoBrush)

    if name == "compress":
        p.drawLine(QPointF(-8.5, -8.5), QPointF(-2.2, -2.2))
        p.drawLine(QPointF(-7.2, -2.2), QPointF(-2.2, -2.2))
        p.drawLine(QPointF(-2.2, -7.2), QPointF(-2.2, -2.2))
        p.drawLine(QPointF(8.5, 8.5), QPointF(2.2, 2.2))
        p.drawLine(QPointF(7.2, 2.2), QPointF(2.2, 2.2))
        p.drawLine(QPointF(2.2, 7.2), QPointF(2.2, 2.2))

    elif name == "extract":
        # Box with upward arrow
        p.drawRoundedRect(QRectF(-8.5, -1.0, 17.0, 9.5), 2.2, 2.2)
        p.drawLine(QPointF(0.0, 4.0), QPointF(0.0, -8.5))
        p.drawLine(QPointF(-4.2, -4.5), QPointF(0.0, -8.5))
        p.drawLine(QPointF(4.2, -4.5), QPointF(0.0, -8.5))

    elif name == "metadata":
        path = QPainterPath()
        path.moveTo(1.0, -8.5)
        path.lineTo(7.5, -8.5)
        path.quadTo(8.5, -8.5, 8.5, -7.5)
        path.lineTo(8.5, -1.0)
        path.lineTo(-1.8, 9.2)
        path.quadTo(-3.0, 10.2, -4.2, 9.0)
        path.lineTo(-9.0, 4.2)
        path.quadTo(-10.2, 3.0, -9.2, 1.8)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(4.2, -4.2), 1.6, 1.6)

    elif name == "edit":
        rows = [(-6.0, 3.0), (0.0, -3.0), (6.0, 2.5)]
        r = 2.3
        for y, kx in rows:
            if kx - r > -8.5:
                p.drawLine(QPointF(-8.5, y), QPointF(kx - r, y))
            if kx + r < 8.5:
                p.drawLine(QPointF(kx + r, y), QPointF(8.5, y))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(kx, y), r, r)

    elif name == "annotate":
        rect = QRectF(-8.5, -8.5, 17.0, 17.0)
        p.drawArc(rect, 35 * 16, 285 * 16)
        p.drawLine(QPointF(5.5, -6.5), QPointF(-2.5, 1.5))
        p.drawLine(QPointF(7.8, -4.2), QPointF(-0.2, 3.8))
        p.drawLine(QPointF(5.5, -6.5), QPointF(7.8, -4.2))
        tip = QPainterPath()
        tip.moveTo(-2.5, 1.5)
        tip.lineTo(-4.2, 4.2)
        tip.lineTo(-0.2, 3.8)
        tip.closeSubpath()
        p.drawPath(tip)

    elif name == "addbg":
        frame = QRectF(-9.0, -7.2, 18.0, 14.4)
        p.drawRoundedRect(frame, 2.4, 2.4)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(-4.2, -2.5), 1.7, 1.7)
        mtn = QPainterPath()
        mtn.moveTo(-7.2, 5.2)
        mtn.lineTo(-2.2, 0.2)
        mtn.lineTo(1.0, 3.2)
        mtn.lineTo(4.0, -0.5)
        mtn.lineTo(7.4, 5.2)
        mtn.closeSubpath()
        p.drawPath(mtn)

    elif name == "crop":
        L1 = QPainterPath()
        L1.moveTo(-5.0, -9.0)
        L1.lineTo(-5.0, 5.0)
        L1.lineTo(9.0, 5.0)
        p.drawPath(L1)
        L2 = QPainterPath()
        L2.moveTo(-9.0, -5.0)
        L2.lineTo(5.0, -5.0)
        L2.lineTo(5.0, 9.0)
        p.drawPath(L2)

    elif name == "redact":
        eye = QPainterPath()
        eye.moveTo(-9.5, 0.0)
        eye.quadTo(0.0, -7.8, 9.5, 0.0)
        eye.quadTo(0.0, 7.8, -9.5, 0.0)
        p.drawPath(eye)
        p.drawEllipse(QPointF(0.0, 0.0), 2.8, 2.8)
        p.drawLine(QPointF(-7.5, -7.5), QPointF(7.5, 7.5))

    elif name == "resize":
        p.drawRoundedRect(QRectF(-8.0, -8.0, 16.0, 16.0), 2.5, 2.5)
        p.drawLine(QPointF(-4.5, 4.5), QPointF(4.5, -4.5))
        p.drawLine(QPointF(0.5, -4.5), QPointF(4.5, -4.5))
        p.drawLine(QPointF(4.5, -0.5), QPointF(4.5, -4.5))

    elif name == "add_image":
        p.setPen(_pen(color, 1.8))
        p.drawRoundedRect(QRectF(-8.5, -7.0, 14.5, 12.0), 2.2, 2.2)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(-4.2, -3.0), 1.4, 1.4)
        mtn = QPainterPath()
        mtn.moveTo(-6.8, 3.4)
        mtn.lineTo(-2.5, -0.5)
        mtn.lineTo(0.5, 2.0)
        mtn.lineTo(2.5, 0.0)
        mtn.lineTo(4.5, 3.4)
        mtn.closeSubpath()
        p.drawPath(mtn)
        p.setPen(_pen(color, 2.0))
        p.drawLine(QPointF(6.5, 3.0), QPointF(6.5, 8.6))
        p.drawLine(QPointF(3.7, 5.8), QPointF(9.3, 5.8))

    elif name == "bolt":
        bolt = QPainterPath()
        bolt.moveTo(1.2, -9.5)
        bolt.lineTo(-6.5, 1.0)
        bolt.lineTo(-0.5, 1.0)
        bolt.lineTo(-1.5, 9.5)
        bolt.lineTo(6.5, -1.0)
        bolt.lineTo(0.5, -1.0)
        bolt.closeSubpath()
        p.setBrush(color)
        p.setPen(_pen(color, 1.4))
        p.drawPath(bolt)

    elif name == "back":
        p.drawLine(QPointF(6.5, 0.0), QPointF(-6.5, 0.0))
        p.drawLine(QPointF(-1.5, -5.0), QPointF(-6.5, 0.0))
        p.drawLine(QPointF(-1.5, 5.0), QPointF(-6.5, 0.0))

    elif name == "close":
        p.drawLine(QPointF(-5.5, -5.5), QPointF(5.5, 5.5))
        p.drawLine(QPointF(5.5, -5.5), QPointF(-5.5, 5.5))

    elif name == "check":
        p.setPen(_pen(color, 2.4))
        p.drawLine(QPointF(-6.5, 0.5), QPointF(-1.8, 5.2))
        p.drawLine(QPointF(-1.8, 5.2), QPointF(7.0, -4.5))

    elif name == "folder":
        path = QPainterPath()
        path.moveTo(-9.0, -6.5)
        path.lineTo(-2.5, -6.5)
        path.lineTo(0.0, -4.0)
        path.lineTo(9.0, -4.0)
        path.lineTo(9.0, 6.8)
        path.lineTo(-9.0, 6.8)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "copy":
        p.drawRoundedRect(QRectF(-3.5, -3.5, 11.0, 11.5), 2.0, 2.0)
        p.drawLine(QPointF(-7.5, 4.0), QPointF(-7.5, -6.5))
        p.drawLine(QPointF(-7.5, -6.5), QPointF(3.0, -6.5))

    elif name == "plus":
        p.drawLine(QPointF(0.0, -6.5), QPointF(0.0, 6.5))
        p.drawLine(QPointF(-6.5, 0.0), QPointF(6.5, 0.0))

    elif name == "kind_image":
        p.drawRoundedRect(QRectF(-8.5, -7.0, 17.0, 14.0), 2.2, 2.2)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(-4.2, -2.5), 1.6, 1.6)
        mtn = QPainterPath()
        mtn.moveTo(-6.5, 4.5)
        mtn.lineTo(-2.2, -0.2)
        mtn.lineTo(1.2, 2.5)
        mtn.lineTo(4.2, -0.5)
        mtn.lineTo(6.5, 4.5)
        mtn.closeSubpath()
        p.drawPath(mtn)

    elif name == "kind_pdf":
        doc = QPainterPath()
        doc.moveTo(-7.0, -9.0)
        doc.lineTo(2.0, -9.0)
        doc.lineTo(7.0, -4.0)
        doc.lineTo(7.0, 9.0)
        doc.lineTo(-7.0, 9.0)
        doc.closeSubpath()
        p.drawPath(doc)
        p.drawLine(QPointF(2.0, -9.0), QPointF(2.0, -4.0))
        p.drawLine(QPointF(2.0, -4.0), QPointF(7.0, -4.0))
        p.drawLine(QPointF(-3.5, 1.5), QPointF(3.5, 1.5))
        p.drawLine(QPointF(-3.5, 5.0), QPointF(1.5, 5.0))

    elif name == "kind_doc":
        p.drawRoundedRect(QRectF(-7.0, -9.0, 14.0, 18.0), 2.2, 2.2)
        p.drawLine(QPointF(-3.5, -4.0), QPointF(3.5, -4.0))
        p.drawLine(QPointF(-3.5, -0.5), QPointF(3.5, -0.5))
        p.drawLine(QPointF(-3.5, 3.0), QPointF(3.5, 3.0))
        p.drawLine(QPointF(-3.5, 6.0), QPointF(1.0, 6.0))

    elif name == "kind_sheet":
        p.drawRoundedRect(QRectF(-8.0, -8.0, 16.0, 16.0), 2.2, 2.2)
        p.drawLine(QPointF(-2.0, -8.0), QPointF(-2.0, 8.0))
        p.drawLine(QPointF(-8.0, -2.5), QPointF(8.0, -2.5))
        p.drawLine(QPointF(-8.0, 3.0), QPointF(8.0, 3.0))

    elif name == "kind_slide":
        p.drawRoundedRect(QRectF(-9.0, -7.5, 18.0, 13.0), 2.0, 2.0)
        p.drawLine(QPointF(0.0, 5.5), QPointF(0.0, 8.5))
        p.drawLine(QPointF(-4.5, 8.5), QPointF(4.5, 8.5))

    elif name == "kind_video":
        p.drawRoundedRect(QRectF(-9.0, -7.0, 18.0, 14.0), 2.5, 2.5)
        tri = QPainterPath()
        tri.moveTo(-2.5, -3.8)
        tri.lineTo(4.2, 0.0)
        tri.lineTo(-2.5, 3.8)
        tri.closeSubpath()
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(tri)

    elif name == "kind_audio":
        p.drawLine(QPointF(-3.5, 4.5), QPointF(-3.5, -6.5))
        p.drawLine(QPointF(5.5, 2.5), QPointF(5.5, -8.5))
        p.drawLine(QPointF(-3.5, -6.5), QPointF(5.5, -8.5))
        p.setBrush(color)
        p.drawEllipse(QPointF(-5.5, 4.5), 2.5, 2.0)
        p.drawEllipse(QPointF(3.5, 2.5), 2.5, 2.0)

    elif name == "kind_archive":
        p.drawRoundedRect(QRectF(-8.0, -8.0, 16.0, 16.0), 2.5, 2.5)
        p.drawLine(QPointF(0.0, -8.0), QPointF(0.0, 2.0))
        p.drawRect(QRectF(-2.0, 2.0, 4.0, 3.5))

    p.restore()
