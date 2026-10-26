"""File Studio (Obsidian & Cobalt Slate Edition) – intelligent rectangular file studio & converter for Linux.

Features:
- Structured rectangular dark-mode File Studio window designed natively for KDE Plasma 6
- Live File Intelligence Header: thumbnail preview, format badge, dimensions/pages/codecs, file size
- Context-aware Smart Tools Grid: only displays verified, compatible tools for the exact file kind
- Inline Embedded Studio Panels (Crop, Studio Backdrop, Annotate, Redact, Adjust, Metadata) inside
  the main window via QStackedWidget — zero popup clutter, with instant '← Back to Actions' navigation
- Structured Convert Format Grid with technical format hints ('Modern Web · Small', 'Next-Gen · Tiny')
- Inline Status & Result Footer Bar with live progress, size-reduction percentage, 'Load Result',
  and 'Reveal in Folder' buttons
- Sleek dark SlateToast notification for quick right-click background conversions & compressions
- Minimal unobtrusive dark slate EdgeDockPill for drag-and-drop
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault("VIPS_WARNING", "0")

from PyQt6.QtCore import (
    QObject, QPoint, QPointF, QRect, QRectF, QRunnable,
    QSettings, QSize, Qt, QThreadPool, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QIcon,
    QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLayout, QMenu, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from . import converters as cv
from . import icons
from .dialogs import (
    ACCENT, ACCENT_HOVER, BG_CARD, BG_ELEV, BG_HOVER, BG_MAIN,
    BORDER, DANGER, EMERALD, STUDIO_QSS, TEXT_MUTED, TEXT_PRI, TEXT_SEC,
    FONT_SANS, FONT_DISPLAY, FONT_MONO, ui_font,
    AddBgDialog, AnnotateDialog, AnnotateStudio, BackdropStudio,
    CropDialog, CropStudio, EditDialog, EditStudio,
    MetadataDialog, MetadataStudio, RedactDialog, RedactStudio,
    StudioPanel, load_image,
)

APP_NAME = "File Studio"
SERVER_NAME = f"convertwheel-{os.getuid()}"

KIND_ACCENTS: dict[str, str] = {
    "image": "#3B82F6",
    "pdf": "#EF4444",
    "doc": "#2563EB",
    "sheet": "#10B981",
    "slide": "#F59E0B",
    "video": "#8B5CF6",
    "audio": "#06B6D4",
    "archive": "#14B8A6",
}

KIND_ICONS: dict[str, str] = {
    "image": "kind_image",
    "pdf": "kind_pdf",
    "doc": "kind_doc",
    "sheet": "kind_sheet",
    "slide": "kind_slide",
    "video": "kind_video",
    "audio": "kind_audio",
    "archive": "kind_archive",
}


# ============================================================ Background Worker
class _Signals(QObject):
    done = pyqtSignal(list, list)


class Job(QRunnable):
    def __init__(self, fn, paths: list[Path], batch: bool = False):
        super().__init__()
        self.fn, self.paths = fn, paths
        self.batch = batch
        self.signals = _Signals()

    def run(self):
        outs, errs = [], []
        if self.batch:
            try:
                res = self.fn(self.paths)
                if isinstance(res, list):
                    outs.extend(res)
                elif res:
                    outs.append(res)
            except cv.ConvertError as e:
                errs.append(str(e))
            except Exception as e:
                traceback.print_exc()
                errs.append(str(e))
        else:
            for p in self.paths:
                try:
                    outs.append(self.fn(p))
                except cv.ConvertError as e:
                    errs.append(f"{p.name}: {e}")
                except Exception as e:
                    traceback.print_exc()
                    errs.append(f"{p.name}: {e}")
        self.signals.done.emit(outs, errs)


# ============================================================ Dark Slate Toast (for CLI / Right-Click actions)
class SlateToast(QWidget):
    """Sleek dark Obsidian & Cobalt notification toast for right-click quick actions."""
    W, H = 360, 78
    MARGIN = 10

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.W + 2 * self.MARGIN, self.H + 2 * self.MARGIN)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.title = ""
        self.subtitle = ""
        self.progress = 0.0
        self.busy = False
        self.error = False
        self.target_path: Path | None = None
        self._pulse = 0.0

        self.pulse_timer = QTimer(self, interval=24)
        self.pulse_timer.timeout.connect(self._tick)
        self.hide_timer = QTimer(self, singleShot=True, interval=4500)
        self.hide_timer.timeout.connect(self.hide)

    def _place(self):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        x = scr.center().x() - self.width() // 2
        y = scr.bottom() - self.height() - 24
        self.move(x, y)

    def show_busy(self, title: str, count: int = 1):
        self.hide_timer.stop()
        self.title = title
        self.subtitle = f"Processing {count} files…" if count > 1 else "Processing with native engine…"
        self.progress = 0.35
        self.busy = True
        self.error = False
        self.target_path = None
        self._place()
        self.show()
        self.raise_()
        self.pulse_timer.start()
        self.update()

    def show_done(self, title: str, outs: list[Path], src_paths: list[Path] | None = None):
        self.pulse_timer.stop()
        self.busy = False
        self.error = False
        self.progress = 1.0
        self.title = title
        self.target_path = outs[0] if outs else None
        n = len(outs)
        if "ZIP" in title or "archive" in title.lower():
            cnt = len(src_paths or [])
            self.subtitle = f"{outs[0].name} ({cv.format_file_size(outs)}) · {cnt} files combined"
        elif n == 1 and src_paths and len(src_paths) == 1 and outs[0].is_file():
            try:
                s0 = src_paths[0].stat().st_size
                s1 = outs[0].stat().st_size
                pct = round((1 - s1 / max(1, s0)) * 100)
                if pct > 2:
                    self.subtitle = f"{outs[0].name} · {cv.format_file_size(outs)} (-{pct}%)"
                else:
                    self.subtitle = f"{outs[0].name} · {cv.format_file_size(outs)}"
            except OSError:
                self.subtitle = f"Saved {outs[0].name}"
        elif n == 1:
            self.subtitle = f"Saved {outs[0].name}"
        else:
            self.subtitle = f"Saved {n} files · Click to reveal"
        self._place()
        self.show()
        self.raise_()
        self.hide_timer.start()
        self.update()

    def show_error(self, title: str, msg: str):
        self.pulse_timer.stop()
        self.busy = False
        self.error = True
        self.progress = 1.0
        self.title = title
        self.subtitle = msg.splitlines()[0][:52]
        self.target_path = None
        self._place()
        self.show()
        self.raise_()
        self.hide_timer.start()
        self.update()

    def _tick(self):
        self._pulse = (self._pulse + 0.045) % 1.0
        self.progress = 0.25 + 0.65 * (0.5 + 0.5 * math.sin(self._pulse * math.tau))
        self.update()

    def mousePressEvent(self, e):
        m = self.MARGIN
        close_rect = QRectF(m + self.W - 30, m + 10, 22, 22)
        if close_rect.contains(e.position()):
            self.hide()
            return
        if self.target_path and self.target_path.exists():
            reveal_in_file_manager(self.target_path)
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        m = self.MARGIN
        card = QRectF(m, m, self.W, self.H)

        for i in range(4):
            pad = (4 - i) * 2.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 32))
            p.drawRoundedRect(card.adjusted(-pad, -pad + 2, pad, pad + 2), 11 + pad * 0.4, 11 + pad * 0.4)

        p.setBrush(QColor(BG_MAIN))
        accent_col = QColor(DANGER if self.error else (ACCENT if self.busy else EMERALD))
        p.setPen(QPen(QColor(BORDER), 1.2))
        p.drawRoundedRect(card, 11, 11)

        # Status badge on left
        badge_r = QRectF(m + 14, m + 14, 34, 34)
        bg_c = QColor(accent_col)
        bg_c.setAlpha(36)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg_c)
        p.drawRoundedRect(badge_r, 8, 8)
        icon_name = "close" if self.error else ("bolt" if self.busy else "check")
        icons.draw_icon(p, icon_name, badge_r.center(), 16.0, accent_col)

        # Title & Subtitle
        f_title = ui_font(12, QFont.Weight.Bold, display=True)
        p.setFont(f_title)
        p.setPen(QColor(TEXT_PRI))
        p.drawText(
            QRectF(m + 58, m + 13, self.W - 88, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.title,
        )

        f_sub = ui_font(11, QFont.Weight.Medium)
        p.setFont(f_sub)
        p.setPen(QColor(TEXT_SEC))
        p.drawText(
            QRectF(m + 58, m + 31, self.W - 72, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.subtitle,
        )

        # Close X at top-right
        icons.draw_icon(p, "close", QPointF(m + self.W - 18, m + 20), 11.0, QColor(TEXT_MUTED))

        # Progress bar at bottom
        track = QRectF(m + 14, m + self.H - 12, self.W - 28, 4.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BG_ELEV))
        p.drawRoundedRect(track, 2.0, 2.0)

        fill_w = max(8.0, track.width() * min(1.0, max(0.06, self.progress)))
        fill = QRectF(track.left(), track.top(), fill_w, track.height())
        p.setBrush(accent_col)
        p.drawRoundedRect(fill, 2.0, 2.0)


def reveal_in_file_manager(target: Path):
    if not target.exists():
        return
    if shutil.which("dolphin"):
        if target.is_dir():
            subprocess.Popen(["dolphin", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["dolphin", "--select", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(target if target.is_dir() else target.parent)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_file_default(target: Path):
    if target.exists() and shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ============================================================ Custom Rectangular Studio Cards
class ThumbnailPreview(QWidget):
    """60x60 rounded file preview widget rendering live image/PDF thumbnails or vector kind icons."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(60, 60)
        self.qimg: QImage | None = None
        self.kind: str | None = None
        self.badge: str = "FILE"

    def set_file(self, profile: cv.FileProfile):
        self.kind = profile.kind
        self.badge = profile.badge
        self.qimg = None
        if profile.kind in ("image", "pdf") and profile.path.exists():
            try:
                img = load_image(profile.path)
                if not img.isNull():
                    self.qimg = img.scaled(
                        120, 120,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
            except Exception:
                self.qimg = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)

        clip = QPainterPath()
        clip.addRoundedRect(r, 10.0, 10.0)
        p.save()
        p.setClipPath(clip)

        if self.qimg is not None and not self.qimg.isNull():
            # Subtle dark checkerboard for transparent thumbnails
            cell = 6
            for y in range(0, self.height(), cell):
                for x in range(0, self.width(), cell):
                    c = QColor("#1E222B") if ((x // cell + y // cell) % 2 == 0) else QColor("#161920")
                    p.fillRect(x, y, cell, cell, c)
            sx = max(0, (self.qimg.width() - self.width()) // 2)
            sy = max(0, (self.qimg.height() - self.height()) // 2)
            p.drawImage(
                r,
                self.qimg,
                QRectF(sx, sy, min(self.width(), self.qimg.width()), min(self.height(), self.qimg.height())),
            )
        else:
            accent = QColor(KIND_ACCENTS.get(self.kind or "", ACCENT))
            bg = QColor(accent)
            bg.setAlpha(30)
            p.fillRect(r, QColor(BG_ELEV))
            p.fillRect(r, bg)
            icon_name = KIND_ICONS.get(self.kind or "", "bolt")
            icons.draw_icon(p, icon_name, r.center(), 24.0, accent)

        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(BORDER), 1.0))
        p.drawRoundedRect(r, 10.0, 10.0)


class ToolCard(QWidget):
    """Structured rectangular card for a compatible Studio Tool."""
    clicked = pyqtSignal(cv.ToolSpec)

    def __init__(self, spec: cv.ToolSpec):
        super().__init__()
        self.spec = spec
        self.hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def enterEvent(self, e):
        self.hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.spec)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)

        accent = QColor(self.spec.accent)
        if self.hover:
            p.setBrush(QColor(BG_HOVER))
            border_c = QColor(accent)
            border_c.setAlpha(185)
            p.setPen(QPen(border_c, 1.2))
        else:
            p.setBrush(QColor(BG_CARD))
            p.setPen(QPen(QColor(BORDER), 1.0))
        p.drawRoundedRect(r, 9.0, 9.0)

        # Left icon badge
        ib = QRectF(11.0, 11.0, 36.0, 36.0)
        ibg = QColor(accent)
        ibg.setAlpha(38 if self.hover else 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ibg)
        p.drawRoundedRect(ib, 8.0, 8.0)
        icons.draw_icon(p, self.spec.icon, ib.center(), 17.0, accent)

        # Title
        f_title = ui_font(12, QFont.Weight.Bold, display=True)
        p.setFont(f_title)
        p.setPen(QColor(TEXT_PRI))
        p.drawText(
            QRectF(56.0, 10.0, self.width() - 66.0, 18.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.spec.title,
        )

        # Subtitle
        f_sub = ui_font(11, QFont.Weight.Normal)
        p.setFont(f_sub)
        p.setPen(QColor(TEXT_SEC))
        p.drawText(
            QRectF(56.0, 29.0, self.width() - 64.0, 17.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.spec.subtitle,
        )


class FormatChip(QWidget):
    """Structured rectangular format target card with format icon, category badge, and technical specs."""
    clicked = pyqtSignal(str)

    def __init__(self, spec: cv.FormatSpec | str, desc: str | None = None):
        super().__init__()
        if isinstance(spec, str):
            self.spec = cv.format_spec(spec)
            if desc:
                self.spec.desc = desc
        else:
            self.spec = spec
        self.fmt = self.spec.fmt
        self.hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(54)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def enterEvent(self, e):
        self.hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.fmt)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)

        accent = QColor(self.spec.accent)
        if self.hover:
            p.setBrush(QColor(BG_HOVER))
            border_c = QColor(accent)
            border_c.setAlpha(190)
            p.setPen(QPen(border_c, 1.3))
        else:
            p.setBrush(QColor(BG_CARD))
            p.setPen(QPen(QColor(BORDER), 1.0))
        p.drawRoundedRect(r, 8.0, 8.0)

        # 1. Left Icon Badge Box
        badge_size = 36.0
        ib = QRectF(9.0, (self.height() - badge_size) / 2.0, badge_size, badge_size)
        ibg = QColor(accent)
        ibg.setAlpha(36 if self.hover else 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ibg)
        p.drawRoundedRect(ib, 7.0, 7.0)

        # Crisp vector icon drawn in accent colour
        icons.draw_icon(p, self.spec.icon, ib.center(), 18.0, accent)

        # 2. Format Name + Category Tag Pill
        text_x = ib.right() + 10.0

        # Title font
        f_title = ui_font(12, QFont.Weight.Bold, display=True)
        p.setFont(f_title)
        fm_title = QFontMetrics(f_title)
        title_str = self.spec.fmt
        title_w = fm_title.horizontalAdvance(title_str)

        p.setPen(QColor("#FFFFFF" if self.hover else TEXT_PRI))
        p.drawText(
            QRectF(text_x, 8.0, title_w + 4.0, 18.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title_str,
        )

        # Category Tag Pill beside the format name
        tag_x = text_x + title_w + 6.0
        f_tag = ui_font(9, QFont.Weight.Bold, mono=True)
        p.setFont(f_tag)
        fm_tag = QFontMetrics(f_tag)
        tag_str = self.spec.type_badge
        tag_tw = fm_tag.horizontalAdvance(tag_str)
        pill_w = tag_tw + 8.0
        pill_h = 15.0
        pill_r = QRectF(tag_x, 9.5, pill_w, pill_h)

        if pill_r.right() < self.width() - 24.0:
            pill_bg = QColor(accent)
            pill_bg.setAlpha(34 if self.hover else 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pill_bg)
            p.drawRoundedRect(pill_r, 4.0, 4.0)

            p.setPen(accent)
            p.drawText(
                pill_r,
                Qt.AlignmentFlag.AlignCenter,
                tag_str,
            )

        # 3. Description / Technical spec line
        f_desc = ui_font(10, QFont.Weight.Medium)
        p.setFont(f_desc)
        p.setPen(QColor("#93C5FD" if self.hover else TEXT_MUTED))
        desc_text = self.spec.desc
        fm_desc = QFontMetrics(f_desc)
        avail_w = self.width() - text_x - 10.0
        elided = fm_desc.elidedText(desc_text, Qt.TextElideMode.ElideRight, int(avail_w))
        p.drawText(
            QRectF(text_x, 28.0, avail_w, 16.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        # 4. Subtle action arrow on hover on the far right
        if self.hover:
            f_arrow = ui_font(12, QFont.Weight.Bold)
            p.setFont(f_arrow)
            p.setPen(accent)
            p.drawText(
                QRectF(self.width() - 22.0, 8.0, 14.0, 18.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "→",
            )


# ============================================================ Main Rectangular File Studio Window
class FileStudioWindow(QWidget):
    """Structured Obsidian & Cobalt Slate rectangular File Studio."""
    MARGIN = 12
    DEFAULT_W = 640
    DEFAULT_H = 708

    def __init__(self, dock_pill: EdgeDockPill | None = None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(STUDIO_QSS)

        self.dock_pill = dock_pill
        self.settings = QSettings("convertwheel", "convertwheel")
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(2)
        self._jobs: list[Job] = []
        self.toast = SlateToast()

        self.paths: list[Path] = []
        self.profile: cv.FileProfile | None = None
        self.last_output: Path | None = None
        self.active_studio: StudioPanel | None = None
        self._drag_offset: QPoint | None = None
        self.busy = 0

        # Compatibility attributes
        self.expanded = False
        self.interactive = True
        self.mode = "convert"

        self._build_ui()
        self.resize(self.DEFAULT_W, self.DEFAULT_H)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        m = self.MARGIN
        outer.setContentsMargins(m, m, m, m)
        outer.setSpacing(0)

        # 1. Top Window Bar (App brand, Back button when in tool studio, Open File, Close)
        top_bar = QWidget()
        top_bar.setFixedHeight(42)
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(14, 0, 12, 0)
        tb.setSpacing(8)

        self.back_btn = QPushButton("← Back to Studio")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_ELEV}; border: 1px solid {BORDER}; border-radius: 6px; "
            f"padding: 4px 10px; color: {TEXT_PRI}; font-family: {FONT_SANS}; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}"
        )
        self.back_btn.clicked.connect(self.show_command_deck)
        self.back_btn.hide()
        tb.addWidget(self.back_btn)

        self.brand_lbl = QLabel("FILE STUDIO")
        self.brand_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: {FONT_DISPLAY}; font-size: 11px; font-weight: 800; letter-spacing: 1.2px;"
        )
        tb.addWidget(self.brand_lbl)

        self.studio_crumb_lbl = QLabel("")
        self.studio_crumb_lbl.setStyleSheet(f"color: {ACCENT}; font-family: {FONT_DISPLAY}; font-size: 12px; font-weight: 700;")
        self.studio_crumb_lbl.hide()
        tb.addWidget(self.studio_crumb_lbl)

        tb.addStretch(1)

        open_btn = QPushButton("+ Open File…")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_ELEV}; border: 1px solid {BORDER}; border-radius: 6px; "
            f"padding: 4px 10px; color: {TEXT_SEC}; font-family: {FONT_SANS}; font-size: 11px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT_PRI}; border-color: #3E4556; }}"
        )
        open_btn.clicked.connect(lambda: self.pick_files())
        tb.addWidget(open_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_ELEV}; border: 1px solid {BORDER}; border-radius: 6px; "
            f"color: {TEXT_SEC}; font-family: {FONT_SANS}; font-weight: 700; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {DANGER}; border-color: {DANGER}; color: white; }}"
        )
        close_btn.clicked.connect(self.collapse)
        tb.addWidget(close_btn)

        outer.addWidget(top_bar)

        # 2. File Intelligence Header Card
        self.header_wrap = QWidget()
        hw = QHBoxLayout(self.header_wrap)
        hw.setContentsMargins(16, 6, 16, 12)
        hw.setSpacing(14)

        self.thumb = ThumbnailPreview()
        hw.addWidget(self.thumb)

        meta_col = QVBoxLayout()
        meta_col.setContentsMargins(0, 2, 0, 2)
        meta_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self.filename_lbl = QLabel("Drop or select a file")
        self.filename_lbl.setStyleSheet(f"color: {TEXT_PRI}; font-family: {FONT_DISPLAY}; font-size: 14px; font-weight: 700;")
        title_row.addWidget(self.filename_lbl)

        self.badge_lbl = QLabel("READY")
        self.badge_lbl.setStyleSheet(
            f"background: {BG_ELEV}; color: {ACCENT}; border: 1px solid {BORDER}; "
            f"border-radius: 5px; padding: 2px 7px; font-family: {FONT_MONO}; font-size: 10px; font-weight: 700; letter-spacing: 0.6px;"
        )
        title_row.addWidget(self.badge_lbl)
        title_row.addStretch(1)
        meta_col.addLayout(title_row)

        self.specs_lbl = QLabel("Images · PDFs · Office Docs · Video · Audio · Archives")
        self.specs_lbl.setStyleSheet(f"color: {TEXT_SEC}; font-family: {FONT_SANS}; font-size: 12px; font-weight: 500;")
        meta_col.addWidget(self.specs_lbl)

        self.path_lbl = QLabel("")
        self.path_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-family: {FONT_MONO}; font-size: 11px;")
        meta_col.addWidget(self.path_lbl)

        hw.addLayout(meta_col, 1)
        outer.addWidget(self.header_wrap)

        div1 = QFrame()
        div1.setFixedHeight(1)
        div1.setStyleSheet(f"background: {BORDER}; border: none;")
        outer.addWidget(div1)

        # 3. Central Stacked Area: Page 0 = Command Deck (Tools + Formats), Page 1 = Embedded Studio Panel
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # --- Page 0: Command Deck inside a smooth scroll area ---
        self.deck_scroll = QScrollArea()
        self.deck_scroll.setWidgetResizable(True)
        self.deck_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.deck_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.deck_scroll.setStyleSheet(f"""
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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        """)

        self.deck_widget = QWidget()
        self.deck_widget.setStyleSheet("background: transparent;")
        self.deck_layout = QVBoxLayout(self.deck_widget)
        self.deck_layout.setContentsMargins(16, 12, 16, 12)
        self.deck_layout.setSpacing(10)

        # Tools Section
        self.tools_hdr = QLabel("SMART STUDIO TOOLS")
        self.tools_hdr.setObjectName("sectionTitle")
        self.deck_layout.addWidget(self.tools_hdr)

        self.tools_grid_wrap = QWidget()
        self.tools_grid = QGridLayout(self.tools_grid_wrap)
        self.tools_grid.setContentsMargins(0, 0, 0, 0)
        self.tools_grid.setHorizontalSpacing(10)
        self.tools_grid.setVerticalSpacing(8)
        self.deck_layout.addWidget(self.tools_grid_wrap)

        # Formats Section
        self.formats_hdr_row = QWidget()
        fhr = QHBoxLayout(self.formats_hdr_row)
        fhr.setContentsMargins(0, 0, 0, 0)
        fhr.setSpacing(8)

        self.formats_hdr = QLabel("QUICK CONVERT FORMAT")
        self.formats_hdr.setObjectName("sectionTitle")
        fhr.addWidget(self.formats_hdr)
        fhr.addStretch(1)

        self.format_filter_bar = QWidget()
        self.format_filter_layout = QHBoxLayout(self.format_filter_bar)
        self.format_filter_layout.setContentsMargins(0, 0, 0, 0)
        self.format_filter_layout.setSpacing(5)
        fhr.addWidget(self.format_filter_bar)

        self.deck_layout.addWidget(self.formats_hdr_row)

        self.formats_grid_wrap = QWidget()
        self.formats_grid = QGridLayout(self.formats_grid_wrap)
        self.formats_grid.setContentsMargins(0, 0, 0, 0)
        self.formats_grid.setHorizontalSpacing(10)
        self.formats_grid.setVerticalSpacing(8)
        self.deck_layout.addWidget(self.formats_grid_wrap)

        self.deck_layout.addStretch(1)
        self.deck_scroll.setWidget(self.deck_widget)
        self.stack.addWidget(self.deck_scroll)

        # --- Page 1: Embedded Studio Container ---
        self.studio_holder = QWidget()
        self.studio_holder_layout = QVBoxLayout(self.studio_holder)
        self.studio_holder_layout.setContentsMargins(0, 0, 0, 0)
        self.studio_holder_layout.setSpacing(0)
        self.stack.addWidget(self.studio_holder)

        # 4. Inline Result & Status Footer Bar
        div2 = QFrame()
        div2.setFixedHeight(1)
        div2.setStyleSheet(f"background: {BORDER}; border: none;")
        outer.addWidget(div2)

        self.footer_bar = QWidget()
        self.footer_bar.setFixedHeight(46)
        fb = QHBoxLayout(self.footer_bar)
        fb.setContentsMargins(16, 0, 14, 0)
        fb.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {ACCENT}; font-size: 11px;")
        fb.addWidget(self.status_dot)

        self.status_lbl = QLabel("Ready · Native Pillow 13 + PyMuPDF + libvips + FFmpeg engines")
        self.status_lbl.setStyleSheet(f"color: {TEXT_SEC}; font-family: {FONT_SANS}; font-size: 11px; font-weight: 600;")
        fb.addWidget(self.status_lbl, 1)

        self.use_result_btn = QPushButton("Load Result in Studio")
        self.use_result_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.use_result_btn.setStyleSheet(
            f"QPushButton {{ background: {BG_ELEV}; border: 1px solid {BORDER}; border-radius: 6px; "
            f"padding: 4px 10px; color: {TEXT_PRI}; font-family: {FONT_SANS}; font-size: 11px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}"
        )
        self.use_result_btn.clicked.connect(self._load_last_result)
        self.use_result_btn.hide()
        fb.addWidget(self.use_result_btn)

        self.reveal_btn = QPushButton("Reveal in Folder")
        self.reveal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reveal_btn.setStyleSheet(
            f"QPushButton {{ background: {EMERALD}; border: 1px solid #34D399; border-radius: 6px; "
            f"padding: 4px 11px; color: #FFFFFF; font-family: {FONT_SANS}; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #059669; }}"
        )
        self.reveal_btn.clicked.connect(self._reveal_last_result)
        self.reveal_btn.hide()
        fb.addWidget(self.reveal_btn)

        outer.addWidget(self.footer_bar)

    # ---------------------------------------------------------------- Window Positioning & Painting
    def _place_window(self, near: QPoint | None = None):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        w, h = self.width(), self.height()
        if near is not None and not near.isNull() and (near.x() > 20 or near.y() > 20):
            x = min(max(near.x() - w // 2, scr.left() + 12), scr.right() - w - 12)
            y = min(max(near.y() - h // 3, scr.top() + 12), scr.bottom() - h - 12)
        else:
            x = scr.center().x() - w // 2
            y = scr.center().y() - h // 2
        self.move(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = self.MARGIN
        card = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

        # Crisp multi-pass dark elevation shadow
        for i in range(5):
            pad = (5 - i) * 2.2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 28))
            p.drawRoundedRect(card.adjusted(-pad, -pad + 2, pad, pad + 2), 13 + pad * 0.4, 13 + pad * 0.4)

        p.setBrush(QColor(BG_MAIN))
        p.setPen(QPen(QColor(BORDER), 1.2))
        p.drawRoundedRect(card, 13.0, 13.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < self.MARGIN + 110:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _):
        self._drag_offset = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            if self.stack.currentIndex() == 1:
                self.show_command_deck()
            else:
                self.collapse()

    # ---------------------------------------------------------------- File Loading & Inspection
    def expand(self, paths: list[Path], interactive: bool = True, at: QPoint | None = None,
               prefer_mode: str | None = None):
        valid = [p for p in paths if p.exists() and p.is_file()]
        if not valid:
            self.toast.show_error("File not found", "Could not open the selected file.")
            return
        self.paths = valid
        self.expanded = True
        self.interactive = interactive
        if prefer_mode:
            self.mode = prefer_mode

        self.show_command_deck()
        self._populate_for_paths(valid)

        if not self.isVisible():
            self._place_window(at)
            self.show()
        self.raise_()
        self.activateWindow()

    def collapse(self):
        self.expanded = False
        self.hide()

    def _clear_grid(self, grid: QGridLayout):
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _clear_layout(self, layout: QLayout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _filter_formats(self, cat: str):
        self._selected_format_cat = cat
        self._update_filter_button_styles()
        self._render_format_chips()

    def _update_filter_button_styles(self):
        for cat_name, btn in getattr(self, "_filter_btns", {}).items():
            if cat_name == getattr(self, "_selected_format_cat", "ALL"):
                btn.setStyleSheet(
                    f"QPushButton {{ background: {ACCENT}; color: #FFFFFF; border: 1px solid {ACCENT}; "
                    f"border-radius: 10px; padding: 2px 9px; font-family: {FONT_SANS}; font-size: 10px; font-weight: 700; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {BG_ELEV}; color: {TEXT_MUTED}; border: 1px solid {BORDER}; "
                    f"border-radius: 10px; padding: 2px 9px; font-family: {FONT_SANS}; font-size: 10px; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: {BG_HOVER}; color: {TEXT_PRI}; border-color: #3E4556; }}"
                )

    def _render_format_chips(self):
        self._clear_grid(self.formats_grid)
        specs = getattr(self, "_all_format_specs", [])
        selected = getattr(self, "_selected_format_cat", "ALL")
        if selected != "ALL":
            specs = [s for s in specs if s.category_label == selected]

        cols = 2
        for idx, spec in enumerate(specs):
            chip = FormatChip(spec)
            chip.clicked.connect(self._on_format_clicked)
            self.formats_grid.addWidget(chip, idx // cols, idx % cols)

    def _populate_for_paths(self, paths: list[Path]):
        p0 = paths[0]
        prof = cv.inspect_file(p0)
        self.profile = prof
        self.thumb.set_file(prof)

        accent_hex = KIND_ACCENTS.get(prof.kind or "", ACCENT)
        if len(paths) == 1:
            name_text = p0.name if len(p0.name) <= 40 else p0.name[:37] + "…"
            self.filename_lbl.setText(name_text)
            self.badge_lbl.setText(prof.type_label.upper())
            self.specs_lbl.setText(prof.specs_str)
            self.path_lbl.setText(str(p0.parent))
        else:
            kind = cv.common_kind(paths)
            if kind:
                self.filename_lbl.setText(f"{len(paths)} {prof.type_label}s Selected")
                self.badge_lbl.setText(f"BATCH · {prof.badge}")
            else:
                self.filename_lbl.setText(f"{len(paths)} Files Selected")
                self.badge_lbl.setText("BATCH · MIXED")
            self.specs_lbl.setText(f"Total size: {cv.format_file_size(paths)} · Ready to combine or convert")
            self.path_lbl.setText(str(p0.parent))

        self.badge_lbl.setStyleSheet(
            f"background: {BG_ELEV}; color: {accent_hex}; border: 1px solid {BORDER}; "
            f"border-radius: 5px; padding: 2px 8px; font-family: {FONT_MONO}; font-size: 10px; font-weight: 800; letter-spacing: 0.6px;"
        )

        # Populate Smart Studio Tools Grid (2 columns)
        self._clear_grid(self.tools_grid)
        tools = cv.smart_tools_for(paths)
        if tools:
            self.tools_hdr.show()
            self.tools_grid_wrap.show()
            for idx, tspec in enumerate(tools):
                card = ToolCard(tspec)
                card.clicked.connect(self._on_tool_clicked)
                self.tools_grid.addWidget(card, idx // 2, idx % 2)
        else:
            self.tools_hdr.hide()
            self.tools_grid_wrap.hide()

        # Populate Convert Format Grid (2 columns with format icons, category pills, & filters)
        self._clear_grid(self.formats_grid)
        self._clear_layout(self.format_filter_layout)
        targets = cv.targets_for(paths)
        if targets:
            hdr = f"CONVERT {prof.badge} TO FORMAT" if cv.common_kind(paths) else "CONVERT TO FORMAT"
            self.formats_hdr.setText(hdr)
            self.formats_hdr_row.show()
            self.formats_grid_wrap.show()

            self._all_format_specs = [cv.format_spec(f) for f in targets]
            self._selected_format_cat = "ALL"

            cat_map: dict[str, list[cv.FormatSpec]] = {}
            for s in self._all_format_specs:
                cat_map.setdefault(s.category_label, []).append(s)

            if len(cat_map) > 1:
                self.format_filter_bar.show()
                self._filter_btns = {}

                btn_all = QPushButton(f"All ({len(targets)})")
                btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_all.clicked.connect(lambda: self._filter_formats("ALL"))
                self.format_filter_layout.addWidget(btn_all)
                self._filter_btns["ALL"] = btn_all

                for cat_name, cat_specs in cat_map.items():
                    btn_cat = QPushButton(f"{cat_name} ({len(cat_specs)})")
                    btn_cat.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn_cat.clicked.connect(lambda checked=False, c=cat_name: self._filter_formats(c))
                    self.format_filter_layout.addWidget(btn_cat)
                    self._filter_btns[cat_name] = btn_cat

                self._update_filter_button_styles()
            else:
                self.format_filter_bar.hide()

            self._render_format_chips()
        else:
            self.formats_hdr_row.hide()
            self.formats_grid_wrap.hide()

    # ---------------------------------------------------------------- Embedded Studio Navigation
    def show_command_deck(self):
        if self.active_studio is not None:
            self.studio_holder_layout.removeWidget(self.active_studio)
            self.active_studio.hide()
            self.active_studio.setParent(None)
            self.active_studio.deleteLater()
            self.active_studio = None
        self.stack.setCurrentIndex(0)
        self.back_btn.hide()
        self.studio_crumb_lbl.hide()
        self.header_wrap.show()

    def open_embedded_studio(self, tool_id: str, path: Path | None = None):
        target = path or (self.paths[0] if self.paths else None)
        if target is None or not target.exists():
            return
        if not self.paths or self.paths[0] != target:
            self.paths = [target]
            self._populate_for_paths([target])

        studio_map: dict[str, type[StudioPanel]] = {
            "crop": CropStudio,
            "addbg": BackdropStudio,
            "edit": EditStudio,
            "annotate": AnnotateStudio,
            "redact": RedactStudio,
            "metadata": MetadataStudio,
        }
        cls = studio_map.get(tool_id)
        if cls is None:
            return

        if self.active_studio is not None:
            self.studio_holder_layout.removeWidget(self.active_studio)
            self.active_studio.hide()
            self.active_studio.setParent(None)
            self.active_studio.deleteLater()
            self.active_studio = None

        panel = cls(target)
        panel.saved.connect(self._on_studio_saved)
        panel.cancelled.connect(self.show_command_deck)
        self.active_studio = panel
        self.studio_holder_layout.addWidget(panel, 1)

        # Compact header while inside an interactive canvas studio so canvas gets maximum room
        self.header_wrap.hide()
        self.back_btn.show()
        short_name = target.name if len(target.name) <= 22 else target.name[:19] + "…"
        self.studio_crumb_lbl.setText(f"·  {panel.title.upper()}  ({short_name})")
        self.studio_crumb_lbl.show()
        self.stack.setCurrentIndex(1)

        if not self.isVisible():
            self._place_window()
            self.show()
        self.raise_()
        self.activateWindow()

    def _on_studio_saved(self, dest: Path, label: str):
        src_paths = list(self.paths)
        self.last_output = dest
        self.show_command_deck()
        self._show_inline_done(label, [dest], src_paths)
        self.toast.show_done(label, [dest], src_paths)

    # ---------------------------------------------------------------- Actions & Conversions
    def _on_tool_clicked(self, spec: cv.ToolSpec):
        if not self.paths:
            return
        if spec.id == "zip":
            self._start(lambda ps: cv.create_zip(ps), list(self.paths), "Combining into ZIP", batch=True)
            return
        if spec.is_dialog and len(self.paths) == 1:
            self.open_embedded_studio(spec.id, self.paths[0])
        else:
            paths = list(self.paths)
            self._start(lambda p: cv.run_tool(p, spec.id), paths, spec.title)

    def _on_format_clicked(self, fmt: str):
        if not self.paths:
            return
        if fmt.upper() == "ZIP" and len(self.paths) > 1:
            self._start(lambda ps: cv.create_zip(ps), list(self.paths), "Combining into ZIP", batch=True)
            return
        paths = list(self.paths)
        self._start(lambda p: cv.convert(p, fmt), paths, f"Converting to {fmt}")

    def _start(self, fn, paths: list[Path], what: str, batch: bool = False):
        job = Job(fn, paths, batch=batch)
        job.signals.done.connect(lambda o, e, j=job, s=paths: self._finished(j, o, e, what, s))
        self._jobs.append(job)
        self.busy += 1
        self._show_inline_busy(what, len(paths))
        self.toast.show_busy(what, count=len(paths))
        if self.dock_pill:
            self.dock_pill.set_busy(True)
        self.pool.start(job)

    def _finished(self, job: Job, outs: list[Path], errs: list[str], what: str, src_paths: list[Path]):
        if job in self._jobs:
            self._jobs.remove(job)
        self.busy = max(0, self.busy - 1)
        if self.dock_pill and not self.busy:
            self.dock_pill.set_busy(False)
        if outs:
            self.last_output = outs[0]
            self._show_inline_done(what, outs, src_paths)
            self.toast.show_done(what, outs, src_paths=src_paths)
        if errs:
            self._show_inline_error(what, "\n".join(errs))
            self.toast.show_error(f"{what} failed", "\n".join(errs))

    def _show_inline_busy(self, what: str, count: int):
        self.status_dot.setStyleSheet(f"color: {ACCENT}; font-size: 11px;")
        self.status_lbl.setStyleSheet(f"color: {TEXT_PRI}; font-family: {FONT_SANS}; font-size: 11px; font-weight: 600;")
        self.status_lbl.setText(f"{what} ({count} file{'s' if count > 1 else ''})…")
        self.use_result_btn.hide()
        self.reveal_btn.hide()

    def _show_inline_done(self, what: str, outs: list[Path], src_paths: list[Path]):
        self.status_dot.setStyleSheet(f"color: {EMERALD}; font-size: 11px;")
        self.status_lbl.setStyleSheet(f"color: {EMERALD}; font-family: {FONT_SANS}; font-size: 11px; font-weight: 700;")
        out = outs[0]
        if "ZIP" in what or "archive" in what.lower():
            n = len(src_paths)
            self.status_lbl.setText(f"Saved {out.name} ({cv.format_file_size([out])}) · Packaged {n} files")
        elif len(outs) == 1 and src_paths and len(src_paths) == 1 and out.is_file():
            try:
                s0 = src_paths[0].stat().st_size
                s1 = out.stat().st_size
                pct = round((1 - s1 / max(1, s0)) * 100)
                if pct > 2:
                    msg = f"Saved {out.name} · {cv.format_file_size(outs)} (-{pct}% smaller)"
                else:
                    msg = f"Saved {out.name} ({cv.format_file_size(outs)})"
            except OSError:
                msg = f"Saved {out.name}"
            self.status_lbl.setText(msg)
        elif len(outs) == 1:
            self.status_lbl.setText(f"Saved {out.name}")
        else:
            self.status_lbl.setText(f"Saved {len(outs)} files")
        if out.is_file() and cv.kind_of(out) is not None:
            self.use_result_btn.show()
        else:
            self.use_result_btn.hide()
        self.reveal_btn.show()

    def _show_inline_error(self, what: str, err: str):
        self.status_dot.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
        self.status_lbl.setStyleSheet(f"color: {DANGER}; font-family: {FONT_SANS}; font-size: 11px; font-weight: 700;")
        self.status_lbl.setText(f"{what} failed: {err.splitlines()[0][:55]}")
        self.use_result_btn.hide()
        self.reveal_btn.hide()

    def _load_last_result(self):
        if self.last_output and self.last_output.exists() and self.last_output.is_file():
            self.expand([self.last_output], interactive=True)

    def _reveal_last_result(self):
        if self.last_output and self.last_output.exists():
            reveal_in_file_manager(self.last_output)

    # Legacy helper methods used by CLI / tests
    def _open_crop(self, path: Path):
        self.open_embedded_studio("crop", path)

    def _open_addbg(self, path: Path):
        self.open_embedded_studio("addbg", path)

    def _open_edit(self, path: Path):
        self.open_embedded_studio("edit", path)

    def _open_annotate(self, path: Path):
        self.open_embedded_studio("annotate", path)

    def _open_redact(self, path: Path):
        self.open_embedded_studio("redact", path)

    def _open_metadata(self, path: Path):
        self.open_embedded_studio("metadata", path)

    def pick_files(self, prefer_mode: str | None = None):
        start = self.settings.value("last_dir", str(Path.home() / "Desktop"))
        files, _ = QFileDialog.getOpenFileNames(None, "Open File in File Studio", start)
        if files:
            paths = [Path(f) for f in files]
            self.settings.setValue("last_dir", str(paths[0].parent))
            self.expand(paths, interactive=True, prefer_mode=prefer_mode)

    # ---------------------------------------------------------------- Drag & Drop on Studio Window
    @staticmethod
    def _extract_paths(mime) -> list[Path]:
        if not mime.hasUrls():
            return []
        out = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
        return [p for p in out if p.is_file()]

    def dragEnterEvent(self, e):
        paths = self._extract_paths(e.mimeData())
        if paths and cv.common_kind(paths):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        paths = self._extract_paths(e.mimeData())
        if paths:
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()
            self.expand(paths, interactive=True)


# ============================================================ Minimal Unobtrusive Edge Dock Pill
class EdgeDockPill(QWidget):
    """Sleek 38x38 dark slate edge dock badge for drag-and-drop or quick studio launch."""
    SIZE = 44

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.settings = QSettings("convertwheel", "convertwheel")
        self.studio: FileStudioWindow | None = None
        self.hover = False
        self.busy = False
        self._press: QPoint | None = None
        self._moved = False
        self._place()

    def set_studio(self, studio: FileStudioWindow):
        self.studio = studio

    def set_busy(self, b: bool):
        self.busy = b
        self.update()

    def _place(self):
        p = self.settings.value("dock_pos")
        scr = QGuiApplication.primaryScreen().availableGeometry()
        if isinstance(p, QPoint) and scr.contains(p):
            self.move(p)
        else:
            self.move(scr.right() - self.SIZE - 8, scr.center().y() - self.SIZE // 2)

    def enterEvent(self, e):
        self.hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._press is not None and e.buttons() & Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self._press
            if self._moved or delta.manhattanLength() > 5:
                self._moved = True
                self.move(self.pos() + delta)
                self._press = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._moved:
            self.settings.setValue("dock_pos", self.pos())
        elif self.studio is not None:
            if self.studio.isVisible():
                self.studio.collapse()
            elif self.studio.paths:
                self.studio.expand(self.studio.paths, interactive=True)
            else:
                self.studio.pick_files()
        self._press = None
        self._moved = False

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.setStyleSheet(f"""
            QMenu {{
                background: {BG_MAIN};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 5px;
                color: {TEXT_PRI};
                font-family: {FONT_SANS};
                font-size: 12px;
                font-weight: 500;
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 5px;
            }}
            QMenu::item:selected {{
                background: {ACCENT};
                color: white;
            }}
        """)
        if self.studio is not None:
            m.addAction("Open File Studio…", lambda: self.studio.pick_files())
            if self.studio.last_output and self.studio.last_output.exists():
                m.addAction(
                    f"Load Last Result ({self.studio.last_output.name})",
                    lambda: self.studio.expand([self.studio.last_output], interactive=True),
                )
        m.addSeparator()
        auto = QAction("Start on Login", m, checkable=True, checked=is_autostart_enabled())
        auto.toggled.connect(set_autostart)
        m.addAction(auto)
        m.addAction("Hide Dock Icon", self.hide)
        m.addSeparator()
        m.addAction("Quit File Studio", QApplication.quit)
        m.exec(e.globalPos())

    def dragEnterEvent(self, e):
        paths = FileStudioWindow._extract_paths(e.mimeData())
        if paths and cv.common_kind(paths):
            e.acceptProposedAction()
            self.hover = True
            self.update()
        else:
            e.ignore()

    def dragLeaveEvent(self, _):
        self.hover = False
        self.update()

    def dropEvent(self, e):
        self.hover = False
        self.update()
        paths = FileStudioWindow._extract_paths(e.mimeData())
        if paths and self.studio is not None:
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()
            self.studio.expand(paths, interactive=True, at=QCursor.pos())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(4.0, 4.0, self.width() - 8.0, self.height() - 8.0)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(r.adjusted(-1, 1, 1, 3), 10.0, 10.0)

        p.setBrush(QColor(BG_HOVER if self.hover else BG_CARD))
        border_c = QColor(ACCENT if (self.hover or self.busy) else BORDER)
        p.setPen(QPen(border_c, 1.3))
        p.drawRoundedRect(r, 10.0, 10.0)

        icon_c = QColor("#FFFFFF" if self.hover else ACCENT)
        icons.draw_icon(p, "bolt", r.center(), 17.0, icon_c)


# ========================================================================= Autostart & CLI
def launcher_cmd() -> str:
    exe = shutil.which("convertwheel")
    if exe:
        return exe
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    return f"{sys.executable} {run_py}"


def autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / "convertwheel.desktop"


def is_autostart_enabled() -> bool:
    if autostart_path().exists():
        return True
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-enabled", "convertwheel.service"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        return res.stdout.strip() == "enabled"
    except Exception:
        return False


def set_autostart(on: bool):
    f = autostart_path()
    if on:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            "[Desktop Entry]\nType=Application\nName=File Studio\n"
            f"Exec={launcher_cmd()}\nIcon=applications-graphics\nX-GNOME-Autostart-enabled=true\n"
        )
    else:
        f.unlink(missing_ok=True)

    # Sync systemd user service state if installed
    svc = Path.home() / ".config" / "systemd" / "user" / "convertwheel.service"
    if svc.exists():
        cmd = ["systemctl", "--user", "enable" if on else "disable", "convertwheel.service"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        except Exception:
            pass


def parse_cli_args(argv: list[str]) -> tuple[str | None, str | None, list[str]]:
    cmd: str | None = None
    target_fmt: str | None = None
    paths: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--to" and i + 1 < len(argv):
            cmd = "to"
            target_fmt = argv[i + 1].upper()
            i += 2
            continue
        if a.startswith("--to="):
            cmd = "to"
            target_fmt = a.split("=", 1)[1].upper()
            i += 1
            continue
        if a.startswith("--"):
            flag = a.lstrip("-").lower()
            if flag in (
                "studio", "tools", "convert", "crop", "addbg", "annotate",
                "redact", "edit", "compress", "metadata", "extract", "zip",
            ):
                cmd = flag
        elif not a.startswith("-"):
            p = Path(a).resolve()
            if p.exists():
                paths.append(str(p))
        i += 1
    return cmd, target_fmt, paths


def main():
    cmd, target_fmt, paths = parse_cli_args(sys.argv[1:])
    payload = json.dumps({"cmd": cmd, "target": target_fmt, "paths": paths})

    # Hand off to single running instance if available
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(payload.encode())
        sock.flush()
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        return 0

    if sys.argv:
        sys.argv[0] = "convertwheel"
    app = QApplication(sys.argv)
    app.setApplicationName("convertwheel")
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("convertwheel")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon.fromTheme("applications-graphics"))
    app.setFont(ui_font(12, QFont.Weight.Normal))

    dock = EdgeDockPill()
    studio = FileStudioWindow(dock_pill=dock)
    dock.set_studio(studio)
    dock.show()

    def dispatch(data_str: str):
        try:
            if data_str.strip().startswith("{"):
                obj = json.loads(data_str)
                c = obj.get("cmd")
                t_fmt = obj.get("target")
                ps = [Path(p) for p in obj.get("paths", []) if p and Path(p).is_file()]
            else:
                c = None
                t_fmt = None
                ps = [Path(p) for p in data_str.splitlines() if p and Path(p).is_file()]
        except Exception:
            return

        if not ps:
            studio.pick_files()
            return

        if c == "zip":
            studio._start(lambda p_list: cv.create_zip(p_list), ps, "Combining into ZIP", batch=True)
        elif c in ("crop", "addbg", "annotate", "redact", "edit", "metadata"):
            studio.open_embedded_studio(c, ps[0])
        elif c == "compress":
            studio._start(lambda p: cv.run_tool(p, "compress"), ps, "Compressing file")
        elif c == "extract":
            studio._start(lambda p: cv.run_tool(p, "extract"), ps, "Extracting pages / archive")
        elif c == "to" and t_fmt:
            studio._start(lambda p: cv.convert(p, t_fmt), ps, f"Converting to {t_fmt}")
        else:
            studio.expand(ps, interactive=True, at=QCursor.pos(), prefer_mode=c)

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    def on_conn():
        conn = server.nextPendingConnection()

        def read():
            data = bytes(conn.readAll()).decode(errors="ignore")
            dispatch(data)

        conn.readyRead.connect(read)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_conn)
    if paths:
        QTimer.singleShot(120, lambda: dispatch(payload))
    return app.exec()


# Backwards-compatible aliases
Wheel = FileStudioWindow
TangerineToast = SlateToast
