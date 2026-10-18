"""Obsidian & Cobalt Slate Studio panels and dialogs for File Studio.

Every tool is built as a modular `QWidget` studio view (`CropStudio`, `BackdropStudio`,
`EditStudio`, `AnnotateStudio`, `RedactStudio`, `MetadataStudio`) that can be embedded
directly inside the main rectangular File Studio window (for seamless zero-popup UX)
or opened standalone via its `Dialog` wrapper (`CropDialog`, `AddBgDialog`, etc.).

All raster loading, EXIF orientation, and PDF page rendering use native in-memory
libraries (`Pillow` + `pillow-heif`, `PyMuPDF` / `fitz`, and `libvips`) — zero ImageMagick!
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QIntValidator,
    QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QButtonGroup, QColorDialog, QDialog, QFileDialog, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSlider, QVBoxLayout, QWidget,
)

from . import converters as cv
from . import icons

# --------------------------------------------------------------------------- Slate Studio Palette
BG_MAIN = "#14161B"
BG_CARD = "#1C1F26"
BG_ELEV = "#242832"
BG_HOVER = "#2C313E"
BORDER = "#2B303C"
BORDER_HI = "#3B82F6"

ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"
EMERALD = "#10B981"
DANGER = "#EF4444"

TEXT_PRI = "#F3F4F6"
TEXT_SEC = "#9CA3AF"
TEXT_MUTED = "#6B7280"

# --------------------------------------------------------------------------- Typography System
FONT_SANS = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans", sans-serif'
FONT_DISPLAY = '"Inter Display", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
FONT_MONO = '"JetBrainsMono Nerd Font", "JetBrains Mono", "Hack", "Cascadia Code", "Consolas", monospace'


def ui_font(
    size: int = 12,
    weight: QFont.Weight = QFont.Weight.Normal,
    display: bool = False,
    mono: bool = False,
) -> QFont:
    """Create a high-fidelity QFont configured with subpixel antialiasing and optimal hinting."""
    f = QFont()
    if mono:
        f.setFamilies(["JetBrainsMono Nerd Font", "JetBrains Mono", "Hack", "Cascadia Code", "Consolas", "monospace"])
        f.setStyleHint(QFont.StyleHint.Monospace, QFont.StyleStrategy.PreferAntialias)
    elif display:
        f.setFamilies(["Inter Display", "Inter", "-apple-system", "Segoe UI", "sans-serif"])
        f.setStyleHint(QFont.StyleHint.SansSerif, QFont.StyleStrategy.PreferAntialias)
    else:
        f.setFamilies(["Inter", "Segoe UI", "Noto Sans", "sans-serif"])
        f.setStyleHint(QFont.StyleHint.SansSerif, QFont.StyleStrategy.PreferAntialias)

    f.setPixelSize(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return f


STUDIO_QSS = f"""
QWidget {{
    color: {TEXT_PRI};
    font-family: {FONT_SANS};
    font-size: 12px;
}}
QLabel {{
    color: {TEXT_SEC};
    font-family: {FONT_SANS};
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}}
QLabel#valueLabel {{
    color: {TEXT_PRI};
    font-family: {FONT_MONO};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#sectionTitle {{
    color: {TEXT_MUTED};
    font-family: {FONT_DISPLAY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}
QPushButton {{
    font-family: {FONT_SANS};
}}
QPushButton#resetBtn {{
    background: {BG_ELEV};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 14px;
    color: {TEXT_SEC};
    font-family: {FONT_SANS};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#resetBtn:hover {{
    background: {BG_HOVER};
    color: {TEXT_PRI};
    border-color: #3E4556;
}}
QPushButton#primaryBtn {{
    background: {ACCENT};
    border: 1px solid #60A5FA;
    border-radius: 7px;
    padding: 6px 18px;
    color: #FFFFFF;
    font-family: {FONT_SANS};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#primaryBtn:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#toolBtn {{
    background: {BG_ELEV};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 12px;
    color: {TEXT_PRI};
    font-family: {FONT_SANS};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#toolBtn:hover {{
    background: {BG_HOVER};
    border-color: #4B5563;
}}
QLineEdit#pxInput {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    color: {TEXT_PRI};
    selection-background-color: {ACCENT};
    selection-color: white;
    font-family: {FONT_MONO};
    font-size: 12px;
    font-weight: 600;
}}
QLineEdit#pxInput:focus {{
    border-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 5px;
    background: {BG_ELEV};
    border-radius: 2.5px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2.5px;
}}
QSlider::add-page:horizontal {{
    background: {BG_ELEV};
    border-radius: 2.5px;
}}
QSlider::handle:horizontal {{
    background: #F9FAFB;
    border: 2px solid {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: #FFFFFF;
    border-color: #60A5FA;
}}
"""


# --------------------------------------------------------------------------- Fast Native Image Loader
def pil_to_qimage(im: Image.Image) -> QImage:
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888)
    return qimg.copy()


def qimage_to_pil(qimg: QImage) -> Image.Image:
    q = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = q.bits()
    ptr.setsize(q.height() * q.bytesPerLine())
    return Image.frombuffer("RGBA", (q.width(), q.height()), bytes(ptr), "raw", "RGBA", q.bytesPerLine(), 1).copy()


def load_image(path: Path) -> QImage:
    """Load any image or PDF cover page into a QImage using PyMuPDF / Pillow / libvips."""
    kind = cv.kind_of(path)
    if kind == "pdf":
        try:
            import pymupdf
            with pymupdf.open(str(path)) as doc:
                page = doc[0]
                pix = page.get_pixmap(dpi=200, alpha=False)
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            return qimg.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        except Exception:
            pass

    # Try Pillow + pillow-heif first (fast & native)
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return pil_to_qimage(im).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except Exception:
        pass

    # Fallback to pyvips / libvips for SVG, JXL, HDR, etc.
    try:
        import os
        os.environ.setdefault("VIPS_WARNING", "0")
        import pyvips
        vimg = pyvips.Image.new_from_file(str(path), access="sequential")
        if vimg.bands < 3:
            vimg = vimg.colourspace("srgb")
        if vimg.bands == 3:
            vimg = vimg.bandjoin(255)
        mem = vimg.write_to_memory()
        qimg = QImage(mem, vimg.width, vimg.height, vimg.width * 4, QImage.Format.Format_RGBA8888).copy()
        return qimg.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except Exception:
        pass

    img = QImage(str(path))
    if not img.isNull():
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    fallback = QImage(640, 420, QImage.Format.Format_ARGB32_Premultiplied)
    fallback.fill(QColor(BG_CARD))
    return fallback


# --------------------------------------------------------------------------- Reusable Dark Controls
class _Divider(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(1)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BORDER))


class SegmentedBar(QWidget):
    """Sleek dark segmented pill bar with Cobalt Blue active capsule."""
    changed = pyqtSignal(object)

    def __init__(self, items: list[tuple[str, object]], current: int = 0):
        super().__init__()
        self.items = items
        self.idx = current
        self.hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        total_chars = sum(len(lbl) for lbl, _ in items)
        self.setMinimumWidth(max(170, total_chars * 8 + len(items) * 22))

    def set_index(self, idx: int, emit: bool = False):
        self.idx = max(0, min(idx, len(self.items) - 1))
        self.update()
        if emit:
            self.changed.emit(self.items[self.idx][1])

    def set_value(self, val: object, emit: bool = False):
        for i, (_, v) in enumerate(self.items):
            if v == val:
                self.set_index(i, emit=emit)
                break

    def _cell_rect(self, i: int) -> QRectF:
        n = max(1, len(self.items))
        m = 3.0
        w = (self.width() - 2 * m) / n
        return QRectF(m + i * w, m, w, self.height() - 2 * m)

    def mouseMoveEvent(self, e):
        pos = e.position()
        h = -1
        for i in range(len(self.items)):
            if self._cell_rect(i).contains(pos):
                h = i
                break
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.hover >= 0:
            self.set_index(self.hover, emit=True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        outer = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setBrush(QColor(BG_CARD))
        p.setPen(QPen(QColor(BORDER), 1.0))
        p.drawRoundedRect(outer, 7.0, 7.0)

        f = ui_font(11, QFont.Weight.DemiBold)
        p.setFont(f)

        for i, (label, _) in enumerate(self.items):
            r = self._cell_rect(i)
            if i == self.idx:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(ACCENT))
                p.drawRoundedRect(r, 5.0, 5.0)
                p.setPen(QColor("#FFFFFF"))
            else:
                if i == self.hover:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(BG_HOVER))
                    p.drawRoundedRect(r, 5.0, 5.0)
                p.setPen(QColor(TEXT_PRI if i == self.hover else TEXT_SEC))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)


# --------------------------------------------------------------------------- Base Studio Panel & Dialog Wrapper
class StudioPanel(QWidget):
    """Base embeddable panel used inside File Studio or wrapped in a standalone QDialog."""
    saved = pyqtSignal(Path, str)
    cancelled = pyqtSignal()

    def __init__(self, title: str, path: Path):
        super().__init__()
        self.title = title
        self.path = path
        self.result_path: Path | None = None
        self.action_label: str = title
        self.setStyleSheet(STUDIO_QSS)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 12, 16, 14)
        self.root.setSpacing(11)

    def build_footer(self, primary_label: str) -> tuple[QPushButton, QPushButton]:
        self.root.addWidget(_Divider())
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 0)
        reset = QPushButton("Reset")
        reset.setObjectName("resetBtn")
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        primary = QPushButton(primary_label)
        primary.setObjectName("primaryBtn")
        primary.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(reset)
        row.addStretch(1)
        row.addWidget(primary)
        self.root.addLayout(row)
        return reset, primary

    def finish_save(self, dest: Path, label: str):
        self.result_path = dest
        self.action_label = label
        self.saved.emit(dest, label)


class _SlateDialog(QDialog):
    """Frameless dark obsidian dialog wrapper around any StudioPanel."""
    MARGIN = 12

    def __init__(self, panel: StudioPanel, w: int = 560, h: int = 620):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.panel = panel
        self.path = panel.path
        self.result_path: Path | None = None
        self._drag_offset: QPoint | None = None
        self.setWindowTitle(panel.title)
        self.setStyleSheet(STUDIO_QSS)

        outer = QVBoxLayout(self)
        m = self.MARGIN
        outer.setContentsMargins(m, m, m, m)
        outer.setSpacing(0)

        # Header bar
        hdr = QWidget()
        hdr.setFixedHeight(44)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(10)

        title_lbl = QLabel(f"{panel.title}  ·  {panel.path.name}")
        title_lbl.setStyleSheet(f"color: {TEXT_PRI}; font-size: 13px; font-weight: 700; font-family: {FONT_DISPLAY};")
        hl.addWidget(title_lbl)
        hl.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_ELEV}; border: 1px solid {BORDER}; border-radius: 6px; color: {TEXT_SEC}; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {DANGER}; border-color: {DANGER}; color: white; }}"
        )
        close_btn.clicked.connect(self.reject)
        hl.addWidget(close_btn)

        outer.addWidget(hdr)
        outer.addWidget(_Divider())
        outer.addWidget(panel, 1)

        panel.saved.connect(self._on_panel_saved)
        panel.cancelled.connect(self.reject)
        self.resize(w, h)

    def _on_panel_saved(self, dest: Path, _label: str):
        self.result_path = dest
        self.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

        for i in range(5):
            pad = (5 - i) * 2.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 26))
            p.drawRoundedRect(card.adjusted(-pad, -pad + 2, pad, pad + 2), 12 + pad * 0.4, 12 + pad * 0.4)

        p.setBrush(QColor(BG_MAIN))
        p.setPen(QPen(QColor(BORDER), 1.2))
        p.drawRoundedRect(card, 12, 12)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < self.MARGIN + 46:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _):
        self._drag_offset = None


# ============================================================================== 1. Crop Studio
class CropCanvas(QWidget):
    changed = pyqtSignal()
    HANDLE = 8

    def __init__(self, img: QImage):
        super().__init__()
        self.img = img
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.ratio: float | None = None
        self.rect_img = QRectF(0, 0, img.width(), img.height())
        self._drag: str | None = None
        self._start_pt = QPointF()
        self._start_rect = QRectF()

    def crop_box(self) -> tuple[int, int, int, int]:
        r = self.rect_img.normalized()
        x = max(0, min(round(r.x()), self.img.width() - 1))
        y = max(0, min(round(r.y()), self.img.height() - 1))
        w = max(1, min(round(r.width()), self.img.width() - x))
        h = max(1, min(round(r.height()), self.img.height() - y))
        return x, y, w, h

    def set_ratio(self, ratio: float | None):
        self.ratio = ratio
        iw, ih = self.img.width(), self.img.height()
        if ratio is None:
            self.rect_img = QRectF(0, 0, iw, ih)
        else:
            if iw / ih > ratio:
                h = ih
                w = h * ratio
            else:
                w = iw
                h = w / ratio
            self.rect_img = QRectF((iw - w) / 2, (ih - h) / 2, w, h)
        self.changed.emit()
        self.update()

    def set_size(self, w: int, h: int):
        iw, ih = self.img.width(), self.img.height()
        w = max(8, min(w, iw))
        h = max(8, min(h, ih))
        c = self.rect_img.center()
        x = max(0.0, min(c.x() - w / 2, iw - w))
        y = max(0.0, min(c.y() - h / 2, ih - h))
        self.rect_img = QRectF(x, y, w, h)
        self.changed.emit()
        self.update()

    def _view(self) -> tuple[QRectF, float]:
        m = 16
        avail = QRectF(self.rect()).adjusted(m, m, -m, -m)
        s = min(avail.width() / max(1, self.img.width()), avail.height() / max(1, self.img.height()))
        w, h = self.img.width() * s, self.img.height() * s
        return QRectF(avail.center().x() - w / 2, avail.center().y() - h / 2, w, h), s

    def _to_screen(self, r: QRectF) -> QRectF:
        v, s = self._view()
        return QRectF(v.x() + r.x() * s, v.y() + r.y() * s, r.width() * s, r.height() * s)

    def _handles(self, sr: QRectF) -> dict[str, QPointF]:
        return {
            "tl": sr.topLeft(), "tr": sr.topRight(),
            "bl": sr.bottomLeft(), "br": sr.bottomRight(),
            "t": QPointF(sr.center().x(), sr.top()),
            "b": QPointF(sr.center().x(), sr.bottom()),
            "l": QPointF(sr.left(), sr.center().y()),
            "r": QPointF(sr.right(), sr.center().y()),
        }

    def _hit(self, pos: QPointF) -> str | None:
        sr = self._to_screen(self.rect_img)
        for name, pt in self._handles(sr).items():
            if math.hypot(pos.x() - pt.x(), pos.y() - pt.y()) <= self.HANDLE + 5:
                return name
        return "move" if sr.contains(pos) else None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Dark studio canvas card
        p.setPen(QPen(QColor(BORDER), 1.0))
        p.setBrush(QColor(BG_CARD))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        v, _ = self._view()
        p.drawImage(v, self.img)

        sr = self._to_screen(self.rect_img)
        dim = QPainterPath()
        dim.addRect(v)
        hole = QPainterPath()
        hole.addRect(sr)
        p.fillPath(dim.subtracted(hole), QColor(8, 10, 14, 175))

        # Rule of thirds grid
        p.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DashLine))
        for i in (1, 2):
            x = sr.left() + sr.width() * i / 3
            y = sr.top() + sr.height() * i / 3
            p.drawLine(QPointF(x, sr.top()), QPointF(x, sr.bottom()))
            p.drawLine(QPointF(sr.left(), y), QPointF(sr.right(), y))

        # Cobalt selection frame
        p.setPen(QPen(QColor(ACCENT), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sr)

        p.setBrush(QColor("#FFFFFF"))
        p.setPen(QPen(QColor(ACCENT), 2.0))
        for name, pt in self._handles(sr).items():
            if len(name) == 2:
                hr = QRectF(pt.x() - 5.5, pt.y() - 5.5, 11, 11)
                p.drawRoundedRect(hr, 3, 3)
            elif name in ("t", "b"):
                hr = QRectF(pt.x() - 11, pt.y() - 3.5, 22, 7)
                p.drawRoundedRect(hr, 3.5, 3.5)
            else:
                hr = QRectF(pt.x() - 3.5, pt.y() - 11, 7, 22)
                p.drawRoundedRect(hr, 3.5, 3.5)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = self._hit(e.position())
            self._start_pt = e.position()
            self._start_rect = QRectF(self.rect_img)

    def mouseMoveEvent(self, e):
        if not self._drag:
            h = self._hit(e.position())
            cursors = {
                "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                "move": Qt.CursorShape.SizeAllCursor,
            }
            self.setCursor(cursors.get(h, Qt.CursorShape.ArrowCursor))
            return

        _, s = self._view()
        dx = (e.position().x() - self._start_pt.x()) / s
        dy = (e.position().y() - self._start_pt.y()) / s
        iw, ih = float(self.img.width()), float(self.img.height())
        r = QRectF(self._start_rect)
        MIN = 16.0

        if self._drag == "move":
            nx = max(0.0, min(r.x() + dx, iw - r.width()))
            ny = max(0.0, min(r.y() + dy, ih - r.height()))
            r.moveTo(nx, ny)
        else:
            if "l" in self._drag:
                r.setLeft(max(0.0, min(r.left() + dx, r.right() - MIN)))
            if "r" in self._drag:
                r.setRight(min(iw, max(r.right() + dx, r.left() + MIN)))
            if "t" in self._drag:
                r.setTop(max(0.0, min(r.top() + dy, r.bottom() - MIN)))
            if "b" in self._drag:
                r.setBottom(min(ih, max(r.bottom() + dy, r.top() + MIN)))

            if self.ratio:
                w = r.width()
                h = w / self.ratio
                if r.top() + h > ih:
                    h = ih - r.top()
                    w = h * self.ratio
                r.setWidth(w)
                r.setHeight(h)

        self.rect_img = r
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, _):
        self._drag = None


class CropStudio(StudioPanel):
    RATIOS = [("Free", None), ("1:1", 1.0), ("16:9", 16 / 9), ("9:16", 9 / 16), ("4:3", 4 / 3), ("3:4", 3 / 4)]

    def __init__(self, path: Path):
        super().__init__("Crop & Aspect", path)
        self.canvas = CropCanvas(load_image(path))
        self.root.addWidget(self.canvas, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Aspect Ratio"))
        row.addStretch(1)
        self.seg = SegmentedBar(self.RATIOS)
        self.seg.changed.connect(self.canvas.set_ratio)
        row.addWidget(self.seg)
        self.root.addLayout(row)

        size = QHBoxLayout()
        size.setSpacing(8)
        self.w = QLineEdit()
        self.h = QLineEdit()
        for le, lab in ((self.w, "Width"), (self.h, "Height")):
            le.setObjectName("pxInput")
            le.setValidator(QIntValidator(8, 100000, self))
            le.setFixedWidth(78)
            size.addWidget(QLabel(lab))
            size.addWidget(le)
            le.editingFinished.connect(self._typed)
        size.addWidget(QLabel("px"))
        size.addStretch(1)
        self.root.addLayout(size)

        reset, apply_ = self.build_footer("Save Cropped Image")
        reset.clicked.connect(self._reset)
        apply_.clicked.connect(self._save)
        self.canvas.changed.connect(self._sync)
        self._sync()

    def _reset(self):
        self.seg.set_index(0, emit=True)

    def _sync(self):
        _, _, w, h = self.canvas.crop_box()
        for le, v in ((self.w, w), (self.h, h)):
            le.blockSignals(True)
            le.setText(str(v))
            le.blockSignals(False)

    def _typed(self):
        try:
            w = int(self.w.text() or "8")
            h = int(self.h.text() or "8")
        except ValueError:
            self._sync()
            return
        if self.canvas.ratio:
            if self.sender() is self.w:
                h = round(w / self.canvas.ratio)
            else:
                w = round(h * self.canvas.ratio)
        self.canvas.set_size(w, h)
        self._sync()

    def _save(self):
        x, y, w, h = self.canvas.crop_box()
        dest = cv.crop_image(self.path, x, y, w, h)
        self.finish_save(dest, "Cropping image")


class CropDialog(_SlateDialog):
    def __init__(self, path: Path):
        self.studio = CropStudio(path)
        super().__init__(self.studio, 540, 620)
        self.canvas = self.studio.canvas
        self.seg = self.studio.seg
        self.w = self.studio.w
        self.h = self.studio.h

    def _sync(self):
        self.studio._sync()

    def _save(self):
        self.studio._save()


# ============================================================================== 2. Studio Backdrop (Add BG)
GRADIENTS = [
    ("#0F172A", "#1E3A8A", "#0EA5E9", "#312E81"),  # 1: Deep Cobalt Aurora (Default dark-native!)
    ("#18181B", "#27272A", "#3F3F46", "#09090B"),  # 2: Carbon Matte Studio
    ("#311042", "#6366F1", "#EC4899", "#1E1B4B"),  # 3: Cyber Nebula
    ("#064E3B", "#10B981", "#0EA5E9", "#022C22"),  # 4: Northern Emerald
    ("#FF4E50", "#FFD200", "#F7971E", "#7F53AC"),  # 5: Sunset Mesh
    ("#4FACFE", "#00F2FE", "#66A6FF", "#89F7FE"),  # 6: Arctic Cyan
    ("#E0C3FC", "#8EC5FC", "#FBC2EB", "#A6C1EE"),  # 7: Soft Lavender
    ("#11998E", "#38EF7D", "#0F2027", "#203A43"),  # 8: Forest Mint
    ("#F8FAFC", "#E2E8F0", "#CBD5E1", "#94A3B8"),  # 9: Clean Alabaster Light
]

SOLIDS = [
    "#0F172A", "#18181B", "#1E293B", "#3B82F6", "#6366F1",
    "#10B981", "#F59E0B", "#EC4899", "#F8FAFC",
]


def make_mesh_gradient_image(colors: tuple[str, str, str, str], w: int, h: int) -> QImage:
    gw, gh = 64, 64
    small = QImage(gw, gh, QImage.Format.Format_ARGB32_Premultiplied)
    c00, c10, c01, c11 = [QColor(c) for c in colors]
    p = QPainter(small)
    for y in range(gh):
        v = y / max(1, gh - 1)
        r_left = c00.red() * (1 - v) + c01.red() * v
        g_left = c00.green() * (1 - v) + c01.green() * v
        b_left = c00.blue() * (1 - v) + c01.blue() * v

        r_right = c10.red() * (1 - v) + c11.red() * v
        g_right = c10.green() * (1 - v) + c11.green() * v
        b_right = c10.blue() * (1 - v) + c11.blue() * v

        lg = QLinearGradient(0, y, gw, y)
        lg.setColorAt(0.0, QColor(int(r_left), int(g_left), int(b_left)))
        lg.setColorAt(1.0, QColor(int(r_right), int(g_right), int(b_right)))
        p.fillRect(0, y, gw, 1, lg)
    p.end()
    return small.scaled(max(1, w), max(1, h), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)


def render_with_bg(img: QImage, bg, pad: int, radius: int, shadow: int, ratio: float | None) -> QImage:
    iw, ih = img.width(), img.height()
    W, H = iw + 2 * pad, ih + 2 * pad
    if ratio:
        if W / max(1, H) < ratio:
            W = round(H * ratio)
        else:
            H = round(W / ratio)

    out = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    if isinstance(bg, QImage):
        s = bg.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                      Qt.TransformationMode.SmoothTransformation)
        p.drawImage(0, 0, s, (s.width() - W) // 2, (s.height() - H) // 2, W, H)
    elif isinstance(bg, tuple):
        mesh = make_mesh_gradient_image(bg, W, H)
        p.drawImage(0, 0, mesh)
    else:
        p.fillRect(0, 0, W, H, QColor(bg))

    x0, y0 = (W - iw) / 2, (H - ih) / 2

    if shadow > 0:
        k = 8
        sw, sh = max(1, W // k), max(1, H // k)
        m = QImage(sw, sh, QImage.Format.Format_ARGB32_Premultiplied)
        m.fill(Qt.GlobalColor.transparent)
        mp = QPainter(m)
        mp.setRenderHint(QPainter.RenderHint.Antialiasing)
        mp.setBrush(QColor(0, 0, 0, 155))
        mp.setPen(Qt.PenStyle.NoPen)
        mp.drawRoundedRect(QRectF(x0 / k, (y0 + shadow * 0.35) / k, iw / k, ih / k),
                           radius / k, radius / k)
        mp.end()
        p.drawImage(QRectF(0, 0, W, H), m.scaled(W, H, transformMode=Qt.TransformationMode.SmoothTransformation))

    clip = QPainterPath()
    clip.addRoundedRect(QRectF(x0, y0, iw, ih), radius, radius)
    p.setClipPath(clip)
    p.drawImage(QPointF(x0, y0), img)
    p.end()
    return out


class _SwatchButton(QPushButton):
    def __init__(self, value, kind: str = "solid", checked: bool = False):
        super().__init__()
        self.value = value
        self.kind = kind
        self.setCheckable(kind in ("mesh", "solid", "picker"))
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34 if kind == "picker" else 28, 22 if kind == "picker" else 28)
        self._mesh_img = make_mesh_gradient_image(value, 56, 56) if kind == "mesh" else None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(2, 2, self.width() - 4, self.height() - 4)
        rad = 6.0

        if self.kind == "mesh" and self._mesh_img is not None:
            clip = QPainterPath()
            clip.addRoundedRect(r, rad, rad)
            p.save()
            p.setClipPath(clip)
            p.drawImage(r, self._mesh_img)
            p.restore()
        elif self.kind in ("solid", "picker"):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self.value))
            p.drawRoundedRect(r, rad, rad)
        elif self.kind == "image":
            p.setPen(QPen(QColor(BORDER), 1))
            p.setBrush(QColor(BG_ELEV))
            p.drawRoundedRect(r, rad, rad)
            icons.draw_icon(p, "add_image", r.center(), 16, QColor(TEXT_PRI))
            return

        if self.isChecked():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(ACCENT), 2.2))
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), rad + 1, rad + 1)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
            p.drawRoundedRect(r, rad, rad)


class BackdropStudio(StudioPanel):
    RATIOS = [("Auto", None), ("1:1", 1.0), ("16:9", 16 / 9), ("4:5", 4 / 5)]

    def __init__(self, path: Path):
        super().__init__("Studio Backdrop", path)
        self.img = load_image(path)
        m = max(self.img.width(), self.img.height())
        self.preview_scale = min(1.0, 500 / max(1, m))
        self.small = self.img.scaled(
            max(1, round(self.img.width() * self.preview_scale)),
            max(1, round(self.img.height() * self.preview_scale)),
            transformMode=Qt.TransformationMode.SmoothTransformation,
        )
        self.bg: object = GRADIENTS[0]
        self.ratio: float | None = None

        preview_card = QWidget()
        preview_card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 10px;")
        pv_lay = QVBoxLayout(preview_card)
        pv_lay.setContentsMargins(14, 14, 14, 14)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(400, 240)
        self.preview.setStyleSheet("border: none; background: transparent;")
        pv_lay.addWidget(self.preview, 1)
        self.root.addWidget(preview_card, 1)

        self.swatches = QButtonGroup(self)
        self.swatches.setExclusive(True)

        bg_row1 = QHBoxLayout()
        bg_row1.setSpacing(6)
        bg_row1.addWidget(QLabel("Backdrop"))
        bg_row1.addStretch(1)
        for idx, g in enumerate(GRADIENTS):
            b = _SwatchButton(g, "mesh", checked=(idx == 0))
            b.clicked.connect(lambda _=False, gg=g: self._set_bg(gg))
            self.swatches.addButton(b)
            bg_row1.addWidget(b)
        img_btn = _SwatchButton(None, "image")
        img_btn.setToolTip("Choose custom background image...")
        img_btn.clicked.connect(self._pick_img)
        bg_row1.addWidget(img_btn)
        self.root.addLayout(bg_row1)

        bg_row2 = QHBoxLayout()
        bg_row2.setSpacing(6)
        bg_row2.addWidget(QLabel(""))
        bg_row2.addStretch(1)
        for c in SOLIDS:
            b = _SwatchButton(c, "solid")
            b.clicked.connect(lambda _=False, cc=c: self._set_bg(cc))
            self.swatches.addButton(b)
            bg_row2.addWidget(b)
        self.picker_btn = _SwatchButton("#3B82F6", "picker")
        self.picker_btn.setToolTip("Custom colour...")
        self.picker_btn.clicked.connect(self._pick_color)
        self.swatches.addButton(self.picker_btn)
        bg_row2.addWidget(self.picker_btn)
        self.root.addLayout(bg_row2)

        self.sliders: dict[str, tuple[QSlider, int]] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for row_i, (key, title, lo, hi, val) in enumerate((
            ("pad", "Padding", 0, 240, 56),
            ("corner", "Corners", 0, 80, 16),
            ("shadow", "Shadow", 0, 80, 32),
        )):
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setValue(val)
            v_lbl = QLabel(f"{val} px")
            v_lbl.setObjectName("valueLabel")
            v_lbl.setFixedWidth(48)
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            s.valueChanged.connect(lambda v, lb=v_lbl: (lb.setText(f"{v} px"), self._update()))
            grid.addWidget(QLabel(title), row_i, 0)
            grid.addWidget(s, row_i, 1)
            grid.addWidget(v_lbl, row_i, 2)
            self.sliders[key] = (s, val)
        self.root.addLayout(grid)

        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Canvas Ratio"))
        rrow.addStretch(1)
        self.rseg = SegmentedBar(self.RATIOS)
        self.rseg.changed.connect(self._set_ratio)
        rrow.addWidget(self.rseg)
        self.root.addLayout(rrow)

        reset, save = self.build_footer("Save Framed Image")
        reset.clicked.connect(self._reset)
        save.clicked.connect(self._save)
        self._update()

    def _set_bg(self, bg):
        self.bg = bg
        self._update()

    def _set_ratio(self, r):
        self.ratio = r
        self._update()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.picker_btn.value), self, "Backdrop Colour")
        if c.isValid():
            self.picker_btn.value = c.name()
            self.picker_btn.setChecked(True)
            self._set_bg(c.name())

    def _pick_img(self):
        f, _ = QFileDialog.getOpenFileName(self, "Backdrop Image", str(self.path.parent),
                                           "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.avif *.heic)")
        if f:
            im = load_image(Path(f))
            if not im.isNull():
                self._set_bg(im)

    def _vals(self, scale: float = 1.0) -> dict[str, int]:
        return {k: round(s.value() * scale) for k, (s, _) in self.sliders.items()}

    def _update(self):
        v = self._vals(self.preview_scale)
        out = render_with_bg(self.small, self.bg, v["pad"], v["corner"], v["shadow"], self.ratio)
        pm = QPixmap.fromImage(out).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "sliders"):
            self._update()

    def _reset(self):
        for s, default in self.sliders.values():
            s.setValue(default)
        self.rseg.set_index(0, emit=False)
        self.swatches.buttons()[0].setChecked(True)
        self.ratio = None
        self._set_bg(GRADIENTS[0])

    def _save(self):
        v = self._vals(1.0)
        out = render_with_bg(self.img, self.bg, v["pad"], v["corner"], v["shadow"], self.ratio)
        dest = cv.unique_path(self.path.parent, f"{self.path.stem} With Background", "png")
        out.save(str(dest), "PNG")
        self.finish_save(dest, "Adding studio backdrop")


class AddBgDialog(_SlateDialog):
    def __init__(self, path: Path):
        self.studio = BackdropStudio(path)
        super().__init__(self.studio, 560, 680)
        self.sliders = self.studio.sliders
        self.rseg = self.studio.rseg
        self.swatches = self.studio.swatches

    def _set_bg(self, bg):
        self.studio._set_bg(bg)

    def _update(self):
        self.studio._update()

    def _save(self):
        self.studio._save()


# ============================================================================== 3. Adjust & Transform Studio
class EditStudio(StudioPanel):
    def __init__(self, path: Path):
        super().__init__("Adjust & Transform", path)
        self.orig = load_image(path)
        self.rot = 0
        self.flip_h = False
        self.flip_v = False

        preview_card = QWidget()
        preview_card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 10px;")
        pv_lay = QVBoxLayout(preview_card)
        pv_lay.setContentsMargins(14, 14, 14, 14)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(400, 240)
        self.preview.setStyleSheet("border: none; background: transparent;")
        pv_lay.addWidget(self.preview, 1)
        self.root.addWidget(preview_card, 1)

        trow = QHBoxLayout()
        trow.setSpacing(8)
        trow.addWidget(QLabel("Transform"))
        trow.addStretch(1)
        for lbl, fn in (
            ("↺ 90°", lambda: self._rotate(-90)),
            ("↻ 90°", lambda: self._rotate(90)),
            ("⇆ Flip H", self._toggle_h),
            ("⇅ Flip V", self._toggle_v),
        ):
            b = QPushButton(lbl)
            b.setObjectName("toolBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            trow.addWidget(b)
        self.root.addLayout(trow)

        self.sliders: dict[str, tuple[QSlider, int, QLabel]] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for row_i, (key, title, lo, hi, val, unit) in enumerate((
            ("bright", "Brightness", -100, 100, 0, "%"),
            ("contrast", "Contrast", -100, 100, 0, "%"),
            ("sat", "Saturation", -100, 100, 0, "%"),
            ("scale", "Scale", 10, 200, 100, "%"),
        )):
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setValue(val)
            v_lbl = QLabel(f"{val}{unit}")
            v_lbl.setObjectName("valueLabel")
            v_lbl.setFixedWidth(48)
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            s.valueChanged.connect(lambda v, lb=v_lbl, u=unit: (lb.setText(f"{v}{u}"), self._update_preview()))
            grid.addWidget(QLabel(title), row_i, 0)
            grid.addWidget(s, row_i, 1)
            grid.addWidget(v_lbl, row_i, 2)
            self.sliders[key] = (s, val, v_lbl)
        self.root.addLayout(grid)

        reset, save = self.build_footer("Save Adjusted Image")
        reset.clicked.connect(self._reset)
        save.clicked.connect(self._save)
        self._update_preview()

    def _rotate(self, deg: int):
        self.rot = (self.rot + deg) % 360
        self._update_preview()

    def _toggle_h(self):
        self.flip_h = not self.flip_h
        self._update_preview()

    def _toggle_v(self):
        self.flip_v = not self.flip_v
        self._update_preview()

    def _reset(self):
        self.rot = 0
        self.flip_h = False
        self.flip_v = False
        for s, default, _ in self.sliders.values():
            s.setValue(default)
        self._update_preview()

    def _render_pil(self, full_res: bool = False):
        src = self.orig
        if not full_res:
            m = max(src.width(), src.height())
            if m > 520:
                src = src.scaled(520, 520, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        im = qimage_to_pil(src)
        if self.rot:
            im = im.rotate(-self.rot, expand=True)
        if self.flip_h:
            im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if self.flip_v:
            im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        b = self.sliders["bright"][0].value()
        c = self.sliders["contrast"][0].value()
        s = self.sliders["sat"][0].value()
        sc = self.sliders["scale"][0].value()

        if b != 0:
            im = ImageEnhance.Brightness(im).enhance(max(0.05, 1.0 + b / 100.0))
        if c != 0:
            im = ImageEnhance.Contrast(im).enhance(max(0.05, 1.0 + c / 100.0))
        if s != 0:
            im = ImageEnhance.Color(im).enhance(max(0.0, 1.0 + s / 100.0))
        if full_res and sc != 100:
            nw = max(8, round(im.width * sc / 100.0))
            nh = max(8, round(im.height * sc / 100.0))
            im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        return im

    def _update_preview(self):
        im = self._render_pil(full_res=False)
        qimg = pil_to_qimage(im)
        pm = QPixmap.fromImage(qimg).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "sliders"):
            self._update_preview()

    def _save(self):
        out = self._render_pil(full_res=True)
        ext = self.path.suffix.lstrip(".").lower()
        if ext not in ("png", "jpg", "jpeg", "webp", "bmp", "avif"):
            ext = "png"
        dest = cv.unique_path(self.path.parent, f"{self.path.stem} Edited", ext)
        if ext in ("jpg", "jpeg"):
            out = out.convert("RGB")
        out.save(str(dest))
        self.finish_save(dest, "Editing image")


class EditDialog(_SlateDialog):
    def __init__(self, path: Path):
        self.studio = EditStudio(path)
        super().__init__(self.studio, 540, 620)
        self.sliders = self.studio.sliders

    @property
    def rot(self):
        return self.studio.rot

    @rot.setter
    def rot(self, val):
        self.studio.rot = val

    def _update_preview(self):
        self.studio._update_preview()

    def _save(self):
        self.studio._save()


# ============================================================================== 4. Annotate & Redact Studios
@dataclass
class CanvasItem:
    """Vector markup item supporting Canva-like hit testing, move, and handle resize."""
    kind: str  # "box", "arrow", "pen", "highlight", "pixelate", "blur", "blackout"
    color: QColor
    stroke_width: float
    rect: QRectF = field(default_factory=QRectF)
    p0: QPointF = field(default_factory=QPointF)
    p1: QPointF = field(default_factory=QPointF)
    points: list[QPointF] = field(default_factory=list)

    def clone(self) -> CanvasItem:
        return CanvasItem(
            self.kind,
            QColor(self.color),
            self.stroke_width,
            QRectF(self.rect),
            QPointF(self.p0),
            QPointF(self.p1),
            [QPointF(p) for p in self.points],
        )

    def bounds(self) -> QRectF:
        if self.kind in ("box", "pixelate", "blur", "blackout"):
            return self.rect.normalized()
        elif self.kind == "arrow":
            return QRectF(self.p0, self.p1).normalized()
        elif self.points:
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            return QRectF(min(xs), min(ys), max(1.0, max(xs) - min(xs)), max(1.0, max(ys) - min(ys)))
        return QRectF()

    def translate(self, dx: float, dy: float, max_w: float, max_h: float):
        if self.kind in ("box", "pixelate", "blur", "blackout"):
            r = self.rect.normalized()
            nx = max(0.0, min(r.x() + dx, max_w - r.width()))
            ny = max(0.0, min(r.y() + dy, max_h - r.height()))
            self.rect = QRectF(nx, ny, r.width(), r.height())
        elif self.kind == "arrow":
            self.p0 = QPointF(
                max(0.0, min(self.p0.x() + dx, max_w)),
                max(0.0, min(self.p0.y() + dy, max_h)),
            )
            self.p1 = QPointF(
                max(0.0, min(self.p1.x() + dx, max_w)),
                max(0.0, min(self.p1.y() + dy, max_h)),
            )
        elif self.points:
            self.points = [
                QPointF(max(0.0, min(p.x() + dx, max_w)), max(0.0, min(p.y() + dy, max_h)))
                for p in self.points
            ]


def _dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    l2 = dx * dx + dy * dy
    if l2 <= 0.0001:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / l2))
    proj_x = a.x() + t * dx
    proj_y = a.y() + t * dy
    return math.hypot(p.x() - proj_x, p.y() - proj_y)


class _MarkupCanvas(QWidget):
    item_selected = pyqtSignal(object)

    def __init__(self, img: QImage, mode: str = "annotate"):
        super().__init__()
        self.orig = img
        self.mode = mode
        self.tool = "box" if mode == "annotate" else "pixelate"
        self.color = QColor("#3B82F6")
        self.stroke_width = 5.0
        self.items: list[CanvasItem] = []
        self.selected_item: CanvasItem | None = None
        self._drawing_item: CanvasItem | None = None
        self._drag_mode: str | None = None
        self._drag_start_screen: QPointF | None = None
        self._drag_start_item: CanvasItem | None = None
        self._pill_del_rect: QRectF | None = None
        self._pill_dup_rect: QRectF | None = None

        self.setMinimumSize(400, 300)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _view(self) -> tuple[QRectF, float]:
        m = 12
        avail = QRectF(self.rect()).adjusted(m, m, -m, -m)
        s = min(avail.width() / max(1, self.orig.width()),
                avail.height() / max(1, self.orig.height()))
        w, h = self.orig.width() * s, self.orig.height() * s
        return QRectF(avail.center().x() - w / 2, avail.center().y() - h / 2, w, h), s

    def _to_img(self, pt: QPointF) -> QPointF:
        v, s = self._view()
        x = max(0.0, min((pt.x() - v.x()) / s, float(self.orig.width())))
        y = max(0.0, min((pt.y() - v.y()) / s, float(self.orig.height())))
        return QPointF(x, y)

    def _to_screen(self, pt: QPointF) -> QPointF:
        v, s = self._view()
        return QPointF(v.x() + pt.x() * s, v.y() + pt.y() * s)

    def _to_screen_rect(self, r: QRectF) -> QRectF:
        v, s = self._view()
        return QRectF(v.x() + r.x() * s, v.y() + r.y() * s, r.width() * s, r.height() * s)

    def undo(self):
        if self.items:
            popped = self.items.pop()
            if self.selected_item is popped:
                self.selected_item = self.items[-1] if self.items else None
                self.item_selected.emit(self.selected_item)
            self.update()

    def clear_all(self):
        self.items.clear()
        self.selected_item = None
        self.item_selected.emit(None)
        self.update()

    def delete_selected(self):
        if self.selected_item is not None and self.selected_item in self.items:
            self.items.remove(self.selected_item)
            self.selected_item = self.items[-1] if self.items else None
            self.item_selected.emit(self.selected_item)
            self.update()

    def duplicate_selected(self):
        if self.selected_item is not None:
            clone = self.selected_item.clone()
            clone.translate(16.0, 16.0, float(self.orig.width()), float(self.orig.height()))
            self.items.append(clone)
            self.selected_item = clone
            self.item_selected.emit(clone)
            self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            e.accept()
            return
        if e.key() == Qt.Key.Key_D and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.duplicate_selected()
            e.accept()
            return
        if e.key() == Qt.Key.Key_Z and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
            e.accept()
            return
        if e.key() == Qt.Key.Key_Escape:
            self.selected_item = None
            self.item_selected.emit(None)
            self.update()
            e.accept()
            return
        # Nudge selected item with arrow keys
        if self.selected_item is not None:
            step = 10.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
            dx, dy = 0.0, 0.0
            if e.key() == Qt.Key.Key_Left:
                dx = -step
            elif e.key() == Qt.Key.Key_Right:
                dx = step
            elif e.key() == Qt.Key.Key_Up:
                dy = -step
            elif e.key() == Qt.Key.Key_Down:
                dy = step
            if dx != 0.0 or dy != 0.0:
                self.selected_item.translate(dx, dy, float(self.orig.width()), float(self.orig.height()))
                self.update()
                e.accept()
                return
        super().keyPressEvent(e)

    def _handles_for(self, item: CanvasItem) -> dict[str, QPointF]:
        if item.kind in ("box", "pixelate", "blur", "blackout"):
            sr = self._to_screen_rect(item.rect.normalized())
            return {
                "tl": sr.topLeft(),
                "tr": sr.topRight(),
                "bl": sr.bottomLeft(),
                "br": sr.bottomRight(),
                "t": QPointF(sr.center().x(), sr.top()),
                "b": QPointF(sr.center().x(), sr.bottom()),
                "l": QPointF(sr.left(), sr.center().y()),
                "r": QPointF(sr.right(), sr.center().y()),
            }
        elif item.kind == "arrow":
            return {
                "p0": self._to_screen(item.p0),
                "p1": self._to_screen(item.p1),
            }
        return {}

    def _hit_test(self, pos: QPointF) -> tuple[CanvasItem | None, str | None]:
        # 1. Handles of selected item
        if self.selected_item is not None:
            handles = self._handles_for(self.selected_item)
            for h_name, h_pt in handles.items():
                if math.hypot(pos.x() - h_pt.x(), pos.y() - h_pt.y()) <= 9.0:
                    return self.selected_item, h_name

        # 2. Check all items in reverse order (topmost first)
        for item in reversed(self.items):
            if item.kind in ("box", "pixelate", "blur", "blackout"):
                sr = self._to_screen_rect(item.rect.normalized())
                if item.kind == "box":
                    if sr.adjusted(-6, -6, 6, 6).contains(pos):
                        return item, "move"
                else: # Redaction
                    if sr.contains(pos):
                        return item, "move"
            elif item.kind == "arrow":
                s0 = self._to_screen(item.p0)
                s1 = self._to_screen(item.p1)
                if _dist_to_segment(pos, s0, s1) <= 9.0:
                    return item, "move"
            elif item.points:
                for i in range(len(item.points) - 1):
                    s0 = self._to_screen(item.points[i])
                    s1 = self._to_screen(item.points[i + 1])
                    if _dist_to_segment(pos, s0, s1) <= 9.0:
                        return item, "move"
        return None, None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position()

            # 1. Floating pill button clicks
            if self.selected_item is not None:
                if self._pill_del_rect and self._pill_del_rect.contains(pos):
                    self.delete_selected()
                    return
                if self._pill_dup_rect and self._pill_dup_rect.contains(pos):
                    self.duplicate_selected()
                    return

            # 2. Hit test existing item or handle
            item, handle = self._hit_test(pos)
            if item is not None:
                self.selected_item = item
                self._drag_mode = handle
                self._drag_start_screen = pos
                self._drag_start_item = item.clone()
                self.item_selected.emit(item)
                self.update()
                return

            # 3. Empty canvas clicked
            pt = self._to_img(pos)
            if self.tool == "select":
                self.selected_item = None
                self.item_selected.emit(None)
                self.update()
                return

            # Start drawing new item
            self.selected_item = None
            self.item_selected.emit(None)
            if self.tool in ("pen", "highlight"):
                self._drawing_item = CanvasItem(self.tool, self.color, self.stroke_width, points=[pt])
            elif self.tool == "arrow":
                self._drawing_item = CanvasItem(self.tool, self.color, self.stroke_width, p0=pt, p1=pt)
            else: # box, pixelate, blur, blackout
                self._drawing_item = CanvasItem(self.tool, self.color, self.stroke_width, rect=QRectF(pt, pt))
            self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        v, s = self._view()
        img_w, img_h = float(self.orig.width()), float(self.orig.height())

        # A. Dragging / Resizing selected item
        if self._drag_mode is not None and self.selected_item is not None and self._drag_start_item is not None:
            dx = (pos.x() - self._drag_start_screen.x()) / s
            dy = (pos.y() - self._drag_start_screen.y()) / s

            if self._drag_mode == "move":
                self.selected_item.rect = QRectF(self._drag_start_item.rect)
                self.selected_item.p0 = QPointF(self._drag_start_item.p0)
                self.selected_item.p1 = QPointF(self._drag_start_item.p1)
                self.selected_item.points = [QPointF(p) for p in self._drag_start_item.points]
                self.selected_item.translate(dx, dy, img_w, img_h)

            elif self.selected_item.kind in ("box", "pixelate", "blur", "blackout"):
                orig_r = self._drag_start_item.rect.normalized()
                r = QRectF(orig_r)
                MIN_S = 8.0
                if "l" in self._drag_mode:
                    r.setLeft(max(0.0, min(orig_r.left() + dx, orig_r.right() - MIN_S)))
                if "r" in self._drag_mode:
                    r.setRight(min(img_w, max(orig_r.right() + dx, orig_r.left() + MIN_S)))
                if "t" in self._drag_mode:
                    r.setTop(max(0.0, min(orig_r.top() + dy, orig_r.bottom() - MIN_S)))
                if "b" in self._drag_mode:
                    r.setBottom(min(img_h, max(orig_r.bottom() + dy, orig_r.top() + MIN_S)))
                self.selected_item.rect = r.normalized()

            elif self.selected_item.kind == "arrow":
                if self._drag_mode == "p0":
                    self.selected_item.p0 = QPointF(
                        max(0.0, min(self._drag_start_item.p0.x() + dx, img_w)),
                        max(0.0, min(self._drag_start_item.p0.y() + dy, img_h)),
                    )
                elif self._drag_mode == "p1":
                    self.selected_item.p1 = QPointF(
                        max(0.0, min(self._drag_start_item.p1.x() + dx, img_w)),
                        max(0.0, min(self._drag_start_item.p1.y() + dy, img_h)),
                    )
            self.update()
            return

        # B. Drawing new item
        if self._drawing_item is not None:
            pt = self._to_img(pos)
            if self._drawing_item.kind in ("pen", "highlight"):
                self._drawing_item.points.append(pt)
            elif self._drawing_item.kind == "arrow":
                self._drawing_item.p1 = pt
            else: # box, pixelate, blur, blackout
                start_p = self._drawing_item.rect.topLeft()
                self._drawing_item.rect = QRectF(start_p, pt)
            self.update()
            return

        # C. Cursor feedback on hover
        if self.selected_item is not None:
            if (self._pill_del_rect and self._pill_del_rect.contains(pos)) or \
               (self._pill_dup_rect and self._pill_dup_rect.contains(pos)):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                return

        item, handle = self._hit_test(pos)
        if handle:
            cursors = {
                "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                "p0": Qt.CursorShape.PointingHandCursor, "p1": Qt.CursorShape.PointingHandCursor,
                "move": Qt.CursorShape.SizeAllCursor,
            }
            self.setCursor(cursors.get(handle, Qt.CursorShape.ArrowCursor))
        else:
            if self.tool == "select":
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._drawing_item is not None:
                item = self._drawing_item
                self._drawing_item = None
                valid = False
                if item.kind in ("pen", "highlight") and len(item.points) >= 2:
                    valid = True
                elif item.kind == "arrow" and math.hypot(item.p1.x() - item.p0.x(), item.p1.y() - item.p0.y()) >= 5.0:
                    valid = True
                elif item.kind in ("box", "pixelate", "blur", "blackout"):
                    item.rect = item.rect.normalized()
                    if item.rect.width() >= 4.0 and item.rect.height() >= 4.0:
                        valid = True

                if valid:
                    self.items.append(item)
                    self.selected_item = item
                    self.item_selected.emit(item)
                self.update()

            if self._drag_mode is not None:
                self._drag_mode = None
                self._drag_start_screen = None
                self._drag_start_item = None
                self.update()

    def render_final(self) -> QImage:
        out = self.orig.copy()
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale_factor = max(1.0, max(out.width(), out.height()) / 900.0)

        all_items = list(self.items) + ([self._drawing_item] if self._drawing_item else [])
        for item in all_items:
            kind = item.kind
            col = QColor(item.color)
            sw = item.stroke_width * scale_factor
            if kind in ("pen", "highlight"):
                pts = item.points
                if len(pts) < 2:
                    continue
                if kind == "highlight":
                    col.setAlpha(110)
                    sw *= 3.2
                p.setPen(QPen(col, sw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath(pts[0])
                for pt in pts[1:]:
                    path.lineTo(pt)
                p.drawPath(path)
            elif kind == "box":
                r = item.rect.normalized()
                p.setPen(QPen(col, sw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, 4 * scale_factor, 4 * scale_factor)
            elif kind == "arrow":
                p0, p1 = item.p0, item.p1
                p.setPen(QPen(col, sw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawLine(p0, p1)
                ang = math.atan2(p1.y() - p0.y(), p1.x() - p0.x())
                head = 14 * scale_factor + sw * 1.5
                for da in (-2.6, 2.6):
                    hp = QPointF(p1.x() + math.cos(ang + da) * head,
                                 p1.y() + math.sin(ang + da) * head)
                    p.drawLine(p1, hp)
            elif kind in ("pixelate", "blur", "blackout"):
                r = item.rect.normalized().intersected(QRectF(0, 0, out.width(), out.height()))
                ir = r.toRect()
                if ir.width() < 4 or ir.height() < 4:
                    continue
                if kind == "blackout":
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#090A0F"))
                    p.drawRoundedRect(r, 4 * scale_factor, 4 * scale_factor)
                elif kind == "pixelate":
                    sub = out.copy(ir)
                    block = max(8, int(18 * scale_factor))
                    tiny = sub.scaled(max(1, ir.width() // block), max(1, ir.height() // block),
                                      Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.FastTransformation)
                    pix = tiny.scaled(ir.width(), ir.height(),
                                      Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.FastTransformation)
                    p.drawImage(ir.topLeft(), pix)
                elif kind == "blur":
                    sub = out.copy(ir)
                    k = max(6, int(14 * scale_factor))
                    tiny = sub.scaled(max(1, ir.width() // k), max(1, ir.height() // k),
                                      Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                    blurred = tiny.scaled(ir.width(), ir.height(),
                                          Qt.AspectRatioMode.IgnoreAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
                    p.drawImage(ir.topLeft(), blurred)
        p.end()
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setPen(QPen(QColor(BORDER), 1.0))
        p.setBrush(QColor(BG_CARD))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        v, _ = self._view()
        rendered = self.render_final()
        p.drawImage(v, rendered)

        # Canva-style Selection Frame & Handles
        self._pill_del_rect = None
        self._pill_dup_rect = None

        if self.selected_item is not None:
            sr = self._to_screen_rect(self.selected_item.bounds())

            # 1. Selection Bounding Box Outline
            p.setPen(QPen(QColor(ACCENT), 1.6, Qt.PenStyle.SolidLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            sel_box = sr.adjusted(-2.0, -2.0, 2.0, 2.0)
            p.drawRect(sel_box)

            # 2. Handles
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor(ACCENT), 1.8))
            handles = self._handles_for(self.selected_item)
            for h_name, pt in handles.items():
                if len(h_name) == 2 and h_name not in ("p0", "p1"):
                    hr = QRectF(pt.x() - 4.5, pt.y() - 4.5, 9.0, 9.0)
                    p.drawRoundedRect(hr, 2.5, 2.5)
                elif h_name in ("t", "b"):
                    hr = QRectF(pt.x() - 8.0, pt.y() - 3.0, 16.0, 6.0)
                    p.drawRoundedRect(hr, 3.0, 3.0)
                elif h_name in ("l", "r"):
                    hr = QRectF(pt.x() - 3.0, pt.y() - 8.0, 6.0, 16.0)
                    p.drawRoundedRect(hr, 3.0, 3.0)
                elif h_name in ("p0", "p1"):
                    p.drawEllipse(pt, 5.0, 5.0)

            # 3. Canva Floating Action Pill Capsule
            kind_title = self.selected_item.kind.capitalize()
            b = self.selected_item.bounds()
            if self.selected_item.kind in ("box", "pixelate", "blur", "blackout"):
                dim_str = f"{kind_title} {int(b.width())}×{int(b.height())}"
            else:
                dim_str = kind_title

            pill_w = 154.0
            pill_h = 26.0
            cx = sel_box.center().x()
            cy = sel_box.top() - 18.0
            if cy - pill_h / 2.0 < v.top() + 6.0:
                cy = sel_box.bottom() + 18.0

            pill_r = QRectF(cx - pill_w / 2.0, cy - pill_h / 2.0, pill_w, pill_h)

            if pill_r.left() < v.left():
                pill_r.moveLeft(v.left())
            if pill_r.right() > v.right():
                pill_r.moveRight(v.right())

            # Draw capsule
            p.setPen(QPen(QColor(BORDER), 1.0))
            p.setBrush(QColor("#1A1D24"))
            p.drawRoundedRect(pill_r, 6.0, 6.0)

            # Label text
            f_pill = ui_font(10, QFont.Weight.Bold)
            p.setFont(f_pill)
            p.setPen(QColor(TEXT_SEC))
            p.drawText(
                QRectF(pill_r.left() + 8.0, pill_r.top(), pill_w - 56.0, pill_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                dim_str,
            )

            # Divider
            p.setPen(QPen(QColor(BORDER), 1.0))
            p.drawLine(QPointF(pill_r.right() - 44.0, pill_r.top() + 5.0),
                       QPointF(pill_r.right() - 44.0, pill_r.bottom() - 5.0))

            # Duplicate button ⧉
            self._pill_dup_rect = QRectF(pill_r.right() - 42.0, pill_r.top() + 3.0, 18.0, 20.0)
            p.setPen(QColor(TEXT_MUTED))
            f_sym = ui_font(11, QFont.Weight.Normal)
            p.setFont(f_sym)
            p.drawText(self._pill_dup_rect, Qt.AlignmentFlag.AlignCenter, "⧉")

            # Delete button ✕
            self._pill_del_rect = QRectF(pill_r.right() - 22.0, pill_r.top() + 3.0, 18.0, 20.0)
            p.setPen(QColor("#F87171"))
            p.drawText(self._pill_del_rect, Qt.AlignmentFlag.AlignCenter, "✕")


class AnnotateStudio(StudioPanel):
    TOOLS = [("Select", "select"), ("Box", "box"), ("Arrow", "arrow"), ("Pen", "pen"), ("Highlight", "highlight")]
    COLORS = ["#3B82F6", "#EF4444", "#F59E0B", "#10B981", "#A855F7", "#FFFFFF", "#0F172A"]

    def __init__(self, path: Path):
        super().__init__("Annotate & Markup", path)
        self.canvas = _MarkupCanvas(load_image(path), mode="annotate")
        self.canvas.item_selected.connect(self._on_item_selected)
        self.root.addWidget(self.canvas, 1)

        trow = QHBoxLayout()
        trow.addWidget(QLabel("Markup Tool"))
        trow.addStretch(1)
        self.tseg = SegmentedBar(self.TOOLS, current=1)  # Default to Box
        self.tseg.changed.connect(self._on_tool_changed)
        trow.addWidget(self.tseg)

        del_btn = QPushButton("🗑 Delete")
        del_btn.setObjectName("toolBtn")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(self.canvas.delete_selected)
        trow.addWidget(del_btn)

        undo_btn = QPushButton("↶ Undo")
        undo_btn.setObjectName("toolBtn")
        undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        undo_btn.clicked.connect(self.canvas.undo)
        trow.addWidget(undo_btn)
        self.root.addLayout(trow)

        crow = QHBoxLayout()
        crow.addWidget(QLabel("Colour & Stroke"))
        crow.addStretch(1)
        self.cgroup = QButtonGroup(self)
        self.color_buttons: list[_SwatchButton] = []
        for i, c in enumerate(self.COLORS):
            b = _SwatchButton(c, "solid", checked=(i == 0))
            b.setFixedSize(26, 26)
            b.clicked.connect(lambda _=False, col=c: self._set_color(col))
            self.cgroup.addButton(b)
            self.color_buttons.append(b)
            crow.addWidget(b)

        self.stroke_slider = QSlider(Qt.Orientation.Horizontal)
        self.stroke_slider.setRange(2, 16)
        self.stroke_slider.setValue(5)
        self.stroke_slider.setFixedWidth(110)
        self.stroke_slider.valueChanged.connect(self._set_stroke)
        crow.addSpacing(8)
        crow.addWidget(self.stroke_slider)
        self.root.addLayout(crow)

        reset, save = self.build_footer("Save Annotated Image")
        reset.clicked.connect(self.canvas.clear_all)
        save.clicked.connect(self._save)

    def _on_tool_changed(self, t: str):
        self.canvas.tool = t
        if self.canvas.selected_item is not None and t in ("box", "arrow", "pen", "highlight"):
            self.canvas.selected_item.kind = t
            self.canvas.update()

    def _set_color(self, c: str):
        col = QColor(c)
        self.canvas.color = col
        if self.canvas.selected_item is not None:
            self.canvas.selected_item.color = col
            self.canvas.update()

    def _set_stroke(self, v: int):
        self.canvas.stroke_width = float(v)
        if self.canvas.selected_item is not None:
            self.canvas.selected_item.stroke_width = float(v)
            self.canvas.update()

    def _on_item_selected(self, item: CanvasItem | None):
        if item is not None:
            if item.kind in ("box", "arrow", "pen", "highlight"):
                self.tseg.set_value(item.kind)
            self.stroke_slider.blockSignals(True)
            self.stroke_slider.setValue(int(item.stroke_width))
            self.stroke_slider.blockSignals(False)

            hex_c = item.color.name().upper()
            for b in self.color_buttons:
                if str(b.value).upper() == hex_c:
                    b.setChecked(True)
                    break

    def _save(self):
        out = self.canvas.render_final()
        ext = self.path.suffix.lstrip(".").lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            ext = "png"
        dest = cv.unique_path(self.path.parent, f"{self.path.stem} Annotated", ext)
        out.save(str(dest))
        self.finish_save(dest, "Annotating image")


class AnnotateDialog(_SlateDialog):
    def __init__(self, path: Path):
        self.studio = AnnotateStudio(path)
        super().__init__(self.studio, 540, 620)
        self.canvas = self.studio.canvas
        self.tseg = self.studio.tseg

    def _save(self):
        self.studio._save()


class RedactStudio(StudioPanel):
    MODES = [("Select", "select"), ("Pixelate", "pixelate"), ("Gaussian Blur", "blur"), ("Blackout", "blackout")]

    def __init__(self, path: Path):
        super().__init__("Redact Sensitive", path)
        self.canvas = _MarkupCanvas(load_image(path), mode="redact")
        self.canvas.item_selected.connect(self._on_item_selected)
        self.root.addWidget(self.canvas, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Redaction Style"))
        row.addStretch(1)
        self.seg = SegmentedBar(self.MODES, current=1)  # Default to Pixelate
        self.seg.changed.connect(self._on_mode_changed)
        row.addWidget(self.seg)

        del_btn = QPushButton("🗑 Delete")
        del_btn.setObjectName("toolBtn")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(self.canvas.delete_selected)
        row.addWidget(del_btn)

        undo_btn = QPushButton("↶ Undo")
        undo_btn.setObjectName("toolBtn")
        undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        undo_btn.clicked.connect(self.canvas.undo)
        row.addWidget(undo_btn)
        self.root.addLayout(row)

        hint = QLabel("Drag to redact. Click any redaction to move, resize, or switch style like Canva.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.root.addWidget(hint)

        reset, save = self.build_footer("Save Redacted Copy")
        reset.clicked.connect(self.canvas.clear_all)
        save.clicked.connect(self._save)

    def _on_mode_changed(self, m: str):
        self.canvas.tool = m
        if self.canvas.selected_item is not None and m in ("pixelate", "blur", "blackout"):
            self.canvas.selected_item.kind = m
            self.canvas.update()

    def _on_item_selected(self, item: CanvasItem | None):
        if item is not None and item.kind in ("pixelate", "blur", "blackout"):
            self.seg.set_value(item.kind)

    def _save(self):
        out = self.canvas.render_final()
        ext = self.path.suffix.lstrip(".").lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            ext = "png"
        dest = cv.unique_path(self.path.parent, f"{self.path.stem} Redacted", ext)
        out.save(str(dest))
        self.finish_save(dest, "Redacting image")


class RedactDialog(_SlateDialog):
    def __init__(self, path: Path):
        self.studio = RedactStudio(path)
        super().__init__(self.studio, 540, 600)
        self.canvas = self.studio.canvas
        self.seg = self.studio.seg

    def _save(self):
        self.studio._save()


# ============================================================================== 5. Metadata Inspector Studio
class MetadataStudio(StudioPanel):
    def __init__(self, path: Path):
        super().__init__("Metadata & Properties", path)
        rows = cv.inspect_metadata(path)

        card = QWidget()
        card.setStyleSheet(f"background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 10px;")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(7)
        for i, (k, v) in enumerate(rows):
            kl = QLabel(k)
            kl.setStyleSheet(f"color: {TEXT_SEC}; font-weight: 600; border: none; font-family: {FONT_SANS};")
            vl = QLabel(v)
            vl.setObjectName("valueLabel")
            vl.setStyleSheet(f"color: {TEXT_PRI}; font-weight: 600; border: none; font-family: {FONT_MONO};")
            grid.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(vl, i, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(1, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                border: none;
                background: {BG_MAIN};
                width: 6px;
                border-radius: 3px;
                margin: 4px 2px 4px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #374151;
                border-radius: 3px;
                min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        scroll.setWidget(card)
        self.root.addWidget(scroll, 1)

        can_strip = cv.kind_of(path) in ("image", "video", "audio", "pdf")
        close_btn, strip_btn = self.build_footer("Strip Metadata && Save Clean" if can_strip else "Done")
        close_btn.setText("Back")
        close_btn.clicked.connect(self.cancelled.emit)
        if can_strip:
            strip_btn.clicked.connect(self._strip)
        else:
            strip_btn.clicked.connect(self.cancelled.emit)

    def _strip(self):
        dest = cv.strip_metadata(self.path)
        self.finish_save(dest, "Stripping metadata")


class MetadataDialog(_SlateDialog):
    def __init__(self, path: Path):
        self.studio = MetadataStudio(path)
        super().__init__(self.studio, 500, 520)
