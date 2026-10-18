"""File intelligence, conversion, and studio tool back-end for File Studio.

Powered by mature native C-backed engines (zero ImageMagick dependency):
- Pillow 13 + pillow-heif + libimagequant + libvips (pyvips) for high-speed image processing,
  format conversion (PNG, JPG, WebP, AVIF, HEIC, TIFF, ICO, BMP, PDF), and lossy/lossless compression.
- PyMuPDF (MuPDF C engine) for instant PDF probing, high-DPI page rendering, text extraction,
  metadata scrubbing, and stream/image compression.
- python-docx & LibreOffice for document generation and office conversions.
- FFmpeg / FFprobe for video and audio transcoding and stream inspection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from xml.etree import ElementTree as ET
import zipfile

from PIL import ExifTags, Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pillow_heif = None

try:
    import pymupdf
except Exception:
    pymupdf = None

os.environ.setdefault("VIPS_WARNING", "0")
try:
    import pyvips
except Exception:
    pyvips = None

# --------------------------------------------------------------------------- kinds
KINDS: dict[str, set[str]] = {
    "image": {
        "png", "jpg", "jpeg", "webp", "heic", "heif", "avif", "bmp", "tif",
        "tiff", "gif", "ico", "svg", "jxl", "qoi", "tga",
    },
    "pdf": {"pdf"},
    "doc": {"docx", "doc", "odt", "rtf", "txt", "md", "html", "htm"},
    "sheet": {"xlsx", "xls", "ods", "csv"},
    "slide": {"pptx", "ppt", "odp"},
    "video": {"mp4", "mov", "mkv", "webm", "avi", "m4v", "flv", "wmv", "mpg", "mpeg", "3gp", "ts"},
    "audio": {"mp3", "wav", "flac", "ogg", "m4a", "aac", "opus", "wma", "aiff", "aif"},
    "archive": {"zip", "tar", "gz", "tgz", "bz2", "xz"},
}

TYPE_LABELS: dict[str, str] = {
    "image": "Image",
    "pdf": "Document",
    "doc": "Document",
    "sheet": "Spreadsheet",
    "slide": "Presentation",
    "video": "Video",
    "audio": "Audio",
    "archive": "Archive",
}

# Format targets with concise technical hints for the UI grid
FORMAT_META: dict[str, str] = {
    "PNG": "Lossless · Alpha",
    "JPG": "Universal · Compact",
    "WEBP": "Modern Web · Small",
    "AVIF": "Next-Gen · Tiny",
    "HEIC": "Apple HEIF",
    "TIFF": "Print · Lossless",
    "BMP": "Uncompressed",
    "ICO": "App Icon",
    "GIF": "Animated Loop",
    "PDF": "Document",
    "DOCX": "Word Document",
    "ODT": "OpenDocument",
    "TXT": "Plain Text",
    "RTF": "Rich Text",
    "HTML": "Web Page",
    "XLSX": "Excel Sheet",
    "ODS": "OpenSheet",
    "CSV": "Comma Values",
    "PPTX": "PowerPoint",
    "ODP": "OpenSlides",
    "MP4": "H.264 Universal",
    "MKV": "Matroska Container",
    "WEBM": "VP9 Web Video",
    "MOV": "QuickTime",
    "AVI": "Legacy Video",
    "MP3": "Universal Audio",
    "WAV": "Uncompressed PCM",
    "FLAC": "Lossless Audio",
    "OGG": "Vorbis Audio",
    "M4A": "AAC Audio",
    "OPUS": "High-Efficiency",
    "AAC": "Advanced Audio",
    "ZIP": "Compressed Archive",
}

@dataclass
class FormatSpec:
    fmt: str
    category: str        # "image", "document", "spreadsheet", "presentation", "video", "audio", "archive"
    category_label: str  # "Image", "Document", "Spreadsheet", "Presentation", "Video", "Audio", "Archive"
    type_badge: str      # "IMG", "PDF", "DOC", "VID", "AUD", "ZIP", "SHEET", "SLIDE"
    icon: str            # "kind_image", "kind_pdf", "kind_doc", "kind_sheet", "kind_slide", "kind_video", "kind_audio", "kind_archive"
    desc: str            # Concise technical subtitle
    accent: str          # Format-specific or category accent hex


FORMAT_SPECS: dict[str, FormatSpec] = {
    # Image formats
    "WEBP": FormatSpec("WEBP", "image", "Image", "IMG", "kind_image", "Modern Web · Small", "#10B981"),
    "PNG": FormatSpec("PNG", "image", "Image", "IMG", "kind_image", "Lossless · Alpha", "#38BDF8"),
    "JPG": FormatSpec("JPG", "image", "Image", "IMG", "kind_image", "Universal · Compact", "#F59E0B"),
    "AVIF": FormatSpec("AVIF", "image", "Image", "IMG", "kind_image", "Next-Gen · Tiny", "#8B5CF6"),
    "HEIC": FormatSpec("HEIC", "image", "Image", "IMG", "kind_image", "Apple HEIF", "#EC4899"),
    "TIFF": FormatSpec("TIFF", "image", "Image", "IMG", "kind_image", "Print · Lossless", "#6366F1"),
    "BMP": FormatSpec("BMP", "image", "Image", "IMG", "kind_image", "Uncompressed", "#64748B"),
    "ICO": FormatSpec("ICO", "image", "Image", "ICON", "kind_image", "App Multi-Res Icon", "#F97316"),
    "GIF": FormatSpec("GIF", "video", "Animation", "ANIM", "kind_video", "Animated Loop", "#EC4899"),

    # Document & Text formats
    "PDF": FormatSpec("PDF", "document", "Document", "PDF", "kind_pdf", "Portable Document", "#EF4444"),
    "DOCX": FormatSpec("DOCX", "document", "Document", "DOC", "kind_doc", "Word Document", "#2563EB"),
    "ODT": FormatSpec("ODT", "document", "Document", "DOC", "kind_doc", "OpenDocument", "#3B82F6"),
    "TXT": FormatSpec("TXT", "document", "Document", "TEXT", "kind_doc", "Plain Text", "#94A3B8"),
    "RTF": FormatSpec("RTF", "document", "Document", "DOC", "kind_doc", "Rich Text", "#64748B"),
    "HTML": FormatSpec("HTML", "document", "Document", "WEB", "kind_doc", "Web Page", "#F97316"),

    # Spreadsheets & Presentations
    "XLSX": FormatSpec("XLSX", "spreadsheet", "Spreadsheet", "SHEET", "kind_sheet", "Excel Spreadsheet", "#10B981"),
    "ODS": FormatSpec("ODS", "spreadsheet", "Spreadsheet", "SHEET", "kind_sheet", "OpenSpreadsheet", "#059669"),
    "CSV": FormatSpec("CSV", "spreadsheet", "Spreadsheet", "DATA", "kind_sheet", "Comma-Separated Values", "#14B8A6"),
    "PPTX": FormatSpec("PPTX", "presentation", "Presentation", "SLIDE", "kind_slide", "PowerPoint Presentation", "#EA580C"),
    "ODP": FormatSpec("ODP", "presentation", "Presentation", "SLIDE", "kind_slide", "OpenPresentation", "#D97706"),

    # Video formats
    "MP4": FormatSpec("MP4", "video", "Video", "VID", "kind_video", "H.264 Universal Video", "#8B5CF6"),
    "WEBM": FormatSpec("WEBM", "video", "Video", "VID", "kind_video", "VP9 Web Video", "#06B6D4"),
    "MKV": FormatSpec("MKV", "video", "Video", "VID", "kind_video", "Matroska Container", "#6366F1"),
    "MOV": FormatSpec("MOV", "video", "Video", "VID", "kind_video", "Apple QuickTime", "#A855F7"),
    "AVI": FormatSpec("AVI", "video", "Video", "VID", "kind_video", "Legacy Audio-Video", "#64748B"),

    # Audio formats
    "MP3": FormatSpec("MP3", "audio", "Audio", "AUD", "kind_audio", "Universal Audio 192k", "#06B6D4"),
    "WAV": FormatSpec("WAV", "audio", "Audio", "AUD", "kind_audio", "Uncompressed PCM Wave", "#0EA5E9"),
    "FLAC": FormatSpec("FLAC", "audio", "Audio", "AUD", "kind_audio", "Lossless Master Audio", "#10B981"),
    "M4A": FormatSpec("M4A", "audio", "Audio", "AUD", "kind_audio", "AAC High-Quality Audio", "#3B82F6"),
    "OPUS": FormatSpec("OPUS", "audio", "Audio", "AUD", "kind_audio", "High-Efficiency Voice", "#8B5CF6"),
    "OGG": FormatSpec("OGG", "audio", "Audio", "AUD", "kind_audio", "Ogg Vorbis Audio", "#F59E0B"),
    "AAC": FormatSpec("AAC", "audio", "Audio", "AUD", "kind_audio", "Advanced Audio Coding", "#F43F5E"),

    # Archive formats
    "ZIP": FormatSpec("ZIP", "archive", "Archive", "ZIP", "kind_archive", "Compressed Archive", "#EAB308"),
    "TAR": FormatSpec("TAR", "archive", "Archive", "TAR", "kind_archive", "POSIX Tar Archive", "#CA8A04"),
}


def format_spec(fmt: str) -> FormatSpec:
    """Return rich FormatSpec with format icon, category, badge, and technical hint."""
    u = fmt.upper()
    if u in FORMAT_SPECS:
        return FORMAT_SPECS[u]
    return FormatSpec(
        fmt=u,
        category="misc",
        category_label="Format",
        type_badge=u[:4],
        icon="bolt",
        desc=FORMAT_META.get(u, "Convert Format"),
        accent="#3B82F6",
    )


TARGETS: dict[str, list[str]] = {
    # Ordered logically: native format types first, followed by cross-category exports (e.g. PDF/DOCX or Audio extract)
    "image": ["WEBP", "PNG", "JPG", "AVIF", "HEIC", "TIFF", "BMP", "ICO", "PDF", "DOCX"],
    "pdf": ["DOCX", "TXT", "PNG", "JPG"],
    "doc": ["PDF", "DOCX", "ODT", "TXT", "HTML", "RTF"],
    "sheet": ["PDF", "XLSX", "CSV", "ODS"],
    "slide": ["PDF", "PPTX", "PNG", "JPG", "ODP"],
    "video": ["MP4", "WEBM", "MKV", "MOV", "GIF", "MP3", "WAV"],
    "audio": ["MP3", "WAV", "FLAC", "M4A", "OPUS", "OGG", "AAC"],
    "archive": ["ZIP"],
}

# Legacy compatibility mapping for existing callers
TOOLS: dict[str, tuple[str, str, set[str]]] = {
    "compress": ("COMPRESS", "compress", {"image", "video", "audio", "pdf"}),
    "metadata": ("METADATA", "metadata", {"image", "video", "audio", "pdf", "doc", "archive"}),
    "edit": ("ADJUST", "edit", {"image", "video"}),
    "annotate": ("ANNOTATE", "annotate", {"image", "pdf"}),
    "addbg": ("BACKDROP", "addbg", {"image", "pdf"}),
    "crop": ("CROP", "crop", {"image", "pdf"}),
    "redact": ("REDACT", "redact", {"image", "pdf"}),
    "extract": ("EXTRACT", "extract", {"archive", "pdf"}),
}

DIALOG_TOOLS = {"crop", "addbg", "edit", "annotate", "redact", "metadata"}

ALIASES = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "heif": "heic", "aif": "aiff"}


class ConvertError(RuntimeError):
    pass


@dataclass
class ToolSpec:
    id: str
    title: str
    subtitle: str
    icon: str
    is_dialog: bool = False
    accent: str = "#3B82F6"


@dataclass
class FileProfile:
    path: Path
    kind: str | None
    ext: str
    badge: str
    type_label: str
    size_bytes: int
    size_str: str
    specs_str: str
    details: dict[str, str] = field(default_factory=dict)
    tools: list[ToolSpec] = field(default_factory=list)
    targets: list[tuple[str, str]] = field(default_factory=list)


def ext_of(p: Path) -> str:
    name = p.name.lower()
    if name.endswith(".tar.gz"):
        return "tgz"
    if name.endswith(".tar.bz2"):
        return "bz2"
    if name.endswith(".tar.xz"):
        return "xz"
    e = p.suffix.lower().lstrip(".")
    return ALIASES.get(e, e)


def kind_of(p: Path) -> str | None:
    e = ext_of(p)
    for kind, exts in KINDS.items():
        if e in exts:
            return kind
    return None


def common_kind(paths: list[Path]) -> str | None:
    kinds = {kind_of(p) for p in paths}
    return kinds.pop() if len(kinds) == 1 else None


def targets_for(paths: list[Path]) -> list[str]:
    kind = common_kind(paths)
    if not kind:
        if len(paths) > 1:
            return ["ZIP"]
        return []
    src_exts = {ext_of(p) for p in paths}
    tgts = [t for t in TARGETS.get(kind, []) if not (len(src_exts) == 1 and t.lower() in src_exts)]
    if len(paths) > 1 and "ZIP" not in tgts:
        tgts.append("ZIP")
    return tgts


def tools_for(paths: list[Path]) -> list[str]:
    kind = common_kind(paths)
    if not kind:
        return ["zip"] if len(paths) > 1 else []
    t = [tid for tid, (_, _, kinds) in TOOLS.items() if kind in kinds]
    if len(paths) > 1 and "zip" not in t:
        t.insert(0, "zip")
    return t


def smart_tools_for(paths: list[Path]) -> list[ToolSpec]:
    """Return context-aware, verified tools tailored to the exact file kind."""
    kind = common_kind(paths)
    single = len(paths) == 1
    if not kind:
        if len(paths) > 1:
            return [
                ToolSpec("zip", "Combine into ZIP", f"Package {len(paths)} files into .zip", "kind_archive", False, "#14B8A6")
            ]
        return []

    out: list[ToolSpec] = []
    if not single:
        out.append(ToolSpec("zip", "Combine into ZIP", f"Package {len(paths)} files into .zip", "kind_archive", False, "#14B8A6"))

    if kind == "image":
        out.append(ToolSpec("compress", "Compress Image", "Smart lossy/lossless shrink", "compress", False, "#10B981"))
        if single:
            out.append(ToolSpec("crop", "Crop & Aspect", "Freeform, 16:9, 1:1, exact px", "crop", True, "#3B82F6"))
            out.append(ToolSpec("addbg", "Studio Backdrop", "Mesh/solid frame & shadow", "addbg", True, "#8B5CF6"))
            out.append(ToolSpec("annotate", "Annotate & Markup", "Arrow, highlight, box, pen", "annotate", True, "#F59E0B"))
            out.append(ToolSpec("redact", "Redact Sensitive", "Pixelate, blur, or blackout", "redact", True, "#EF4444"))
            out.append(ToolSpec("edit", "Adjust & Transform", "Rotate, flip, exposure, scale", "edit", True, "#06B6D4"))
            out.append(ToolSpec("metadata", "Metadata & EXIF", "Inspect tags & strip clean", "metadata", True, "#64748B"))
        else:
            out.append(ToolSpec("metadata", "Strip All EXIF", "Save clean copies without tags", "metadata", False, "#64748B"))
            out.append(ToolSpec("edit", "Rotate 90° CW", "Batch rotate images", "edit", False, "#06B6D4"))

    elif kind == "pdf":
        out.append(ToolSpec("compress", "Compress PDF", "MuPDF stream & image shrink", "compress", False, "#10B981"))
        out.append(ToolSpec("extract", "Render Pages to PNG", "Export 200 DPI page images", "extract", False, "#3B82F6"))
        if single:
            out.append(ToolSpec("metadata", "PDF Metadata", "Inspect properties & scrub XMP", "metadata", True, "#64748B"))
            out.append(ToolSpec("annotate", "Annotate Cover Page", "Markup page 1 in studio", "annotate", True, "#F59E0B"))
            out.append(ToolSpec("redact", "Redact Cover Page", "Blur or blackout page 1", "redact", True, "#EF4444"))
            out.append(ToolSpec("crop", "Crop Cover Page", "Trim page 1 margins", "crop", True, "#3B82F6"))
            out.append(ToolSpec("addbg", "Frame Cover Page", "Add backdrop to page 1", "addbg", True, "#8B5CF6"))

    elif kind == "video":
        out.append(ToolSpec("compress", "Compress Video", "H.264 CRF-28 optimization", "compress", False, "#10B981"))
        out.append(ToolSpec("edit", "Rotate 90° CW", "Transpose video stream", "edit", False, "#06B6D4"))
        if single:
            out.append(ToolSpec("metadata", "Media Metadata", "Inspect streams & strip tags", "metadata", True, "#64748B"))
        else:
            out.append(ToolSpec("metadata", "Strip Metadata", "Remove container tags", "metadata", False, "#64748B"))

    elif kind == "audio":
        out.append(ToolSpec("compress", "Compress Audio", "128 kbps MP3 optimization", "compress", False, "#10B981"))
        if single:
            out.append(ToolSpec("metadata", "Audio Tags", "Inspect & strip ID3 metadata", "metadata", True, "#64748B"))

    elif kind in ("doc", "sheet", "slide"):
        if single:
            out.append(ToolSpec("metadata", "Document Info", "View file stats & details", "metadata", True, "#64748B"))

    elif kind == "archive":
        out.append(ToolSpec("extract", "Extract Archive", "Unpack into clean subfolder", "extract", False, "#10B981"))
        if single:
            out.append(ToolSpec("metadata", "Inspect Archive", "View contained files & sizes", "metadata", True, "#64748B"))

    return out


def format_file_size(paths: list[Path]) -> str:
    """Return human-readable size string like '1.1 MB' or '296 KB'."""
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    if total <= 0:
        return "0 B"
    if total < 1024:
        return f"{total} B"
    if total < 1024 * 1024:
        kb = total / 1024
        return f"{kb:.1f} KB" if kb < 100 else f"{round(kb)} KB"
    mb = total / (1024 * 1024)
    if mb < 100:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB" if gb >= 1 else f"{round(mb)} MB"


# --------------------------------------------------------------------------- Native Image & PDF Engine Helpers
def _open_pil_image(src: Path, auto_orient: bool = True) -> Image.Image:
    """Open any supported raster or vector image into a Pillow Image using Pillow/pillow-heif/pyvips."""
    try:
        im = Image.open(src)
        im.load()
        if auto_orient:
            im = ImageOps.exif_transpose(im)
        return im
    except Exception:
        if pyvips is not None:
            try:
                vimg = pyvips.Image.new_from_file(str(src), access="sequential")
                if auto_orient and hasattr(vimg, "autorot"):
                    vimg = vimg.autorot()
                buf = vimg.write_to_buffer(".png")
                im = Image.open(io.BytesIO(buf))
                im.load()
                return im
            except Exception as e:
                raise ConvertError(f"Could not decode image {src.name}: {e}") from e
        raise ConvertError(f"Could not decode image {src.name}")


def _flatten_alpha(im: Image.Image, bg: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """Composite alpha transparency over a solid background colour (for JPEG/BMP/PDF)."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, bg)
        canvas.paste(rgba, mask=rgba.split()[3])
        return canvas
    if im.mode != "RGB":
        return im.convert("RGB")
    return im


def _save_pil_image(im: Image.Image, dest: Path, target_ext: str, *, quality: int = 88, strip: bool = False) -> Path:
    """Save a Pillow image to any target format using native C codecs (Pillow 13 / pillow-heif)."""
    t = ALIASES.get(target_ext.lower().lstrip("."), target_ext.lower().lstrip("."))
    save_kwargs: dict = {}
    if not strip:
        exif = im.info.get("exif")
        icc = im.info.get("icc_profile")
        if exif and t in ("jpg", "webp", "png", "tiff", "avif", "heic"):
            save_kwargs["exif"] = exif
        if icc and t in ("jpg", "webp", "png", "tiff", "avif", "heic"):
            save_kwargs["icc_profile"] = icc

    if t == "jpg":
        out_im = _flatten_alpha(im)
        out_im.save(dest, format="JPEG", quality=quality, optimize=True, progressive=True, **save_kwargs)
    elif t == "png":
        out_im = im if im.mode in ("RGB", "RGBA", "L", "LA", "P") else im.convert("RGBA")
        out_im.save(dest, format="PNG", optimize=True, compress_level=9, **save_kwargs)
    elif t == "webp":
        out_im = im if im.mode in ("RGB", "RGBA") else im.convert("RGBA" if "A" in im.mode else "RGB")
        out_im.save(dest, format="WEBP", quality=quality, method=6, **save_kwargs)
    elif t == "avif":
        out_im = im if im.mode in ("RGB", "RGBA") else im.convert("RGBA" if "A" in im.mode else "RGB")
        out_im.save(dest, format="AVIF", quality=quality, **save_kwargs)
    elif t == "heic":
        out_im = im if im.mode in ("RGB", "RGBA") else im.convert("RGBA" if "A" in im.mode else "RGB")
        out_im.save(dest, format="HEIF", quality=quality, **save_kwargs)
    elif t == "bmp":
        out_im = _flatten_alpha(im)
        out_im.save(dest, format="BMP")
    elif t == "tiff":
        out_im = im if im.mode in ("RGB", "RGBA", "L", "CMYK") else im.convert("RGBA")
        out_im.save(dest, format="TIFF", compression="tiff_adobe_deflate", **save_kwargs)
    elif t == "ico":
        out_im = im.convert("RGBA")
        if out_im.width > 256 or out_im.height > 256:
            out_im.thumbnail((256, 256), Image.Resampling.LANCZOS)
        sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(out_im.width, out_im.height)] or [(64, 64)]
        out_im.save(dest, format="ICO", sizes=sizes)
    elif t == "gif":
        out_im = im.convert("RGBA")
        out_im.save(dest, format="GIF", optimize=True)
    elif t == "pdf":
        out_im = _flatten_alpha(im)
        out_im.save(dest, format="PDF", resolution=150.0)
    else:
        im.save(dest)
    return dest


# --------------------------------------------------------------------------- Probing & File Intelligence
def inspect_file(path: Path) -> FileProfile:
    """Fast, non-blocking probe of a file to populate the Studio header & smart actions."""
    ext = ext_of(path)
    kind = kind_of(path)
    badge = (ext or "FILE").upper()
    type_label = f"{badge} {TYPE_LABELS.get(kind, 'File')}" if kind else f"{badge} File"
    try:
        size_bytes = path.stat().st_size
    except OSError:
        size_bytes = 0
    size_str = format_file_size([path])
    specs_parts: list[str] = [size_str]
    details: dict[str, str] = {}

    if kind == "image":
        try:
            with Image.open(path) as im:
                w, h = im.size
                mode = im.mode
                specs_parts.insert(0, f"{w} × {h} px")
                specs_parts.append(mode)
                details["Dimensions"] = f"{w} × {h} px"
                details["Colour Mode"] = mode
        except Exception:
            if pyvips is not None:
                try:
                    vimg = pyvips.Image.new_from_file(str(path), access="sequential")
                    specs_parts.insert(0, f"{vimg.width} × {vimg.height} px")
                    details["Dimensions"] = f"{vimg.width} × {vimg.height} px"
                except Exception:
                    pass

    elif kind == "pdf" and pymupdf is not None:
        try:
            with pymupdf.open(path) as doc:
                n = doc.page_count
                lbl = "1 Page" if n == 1 else f"{n} Pages"
                specs_parts.insert(0, lbl)
                details["Pages"] = str(n)
                if n > 0:
                    rect = doc[0].rect
                    w_pt, h_pt = rect.width, rect.height
                    if abs(w_pt - 595) < 12 and abs(h_pt - 842) < 12:
                        ps = "A4"
                    elif abs(w_pt - 612) < 12 and abs(h_pt - 792) < 12:
                        ps = "Letter"
                    else:
                        ps = f"{round(w_pt)}×{round(h_pt)} pt"
                    specs_parts.append(ps)
                    details["Page Size"] = ps
        except Exception:
            pass

    elif kind in ("video", "audio"):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration:stream=codec_name,width,height,codec_type",
                 "-of", "default=noprint_wrappers=1", str(path)],
                capture_output=True, text=True, timeout=3,
            )
            kv: dict[str, str] = {}
            for line in r.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k not in kv and v != "N/A":
                        kv[k] = v
            if "width" in kv and "height" in kv:
                specs_parts.insert(0, f"{kv['width']}×{kv['height']}")
            if "codec_name" in kv:
                specs_parts.append(kv["codec_name"].upper())
            if "duration" in kv:
                try:
                    secs = float(kv["duration"])
                    mins = int(secs // 60)
                    rem = int(round(secs % 60))
                    specs_parts.append(f"{mins}:{rem:02d}")
                except ValueError:
                    pass
        except Exception:
            pass

    elif kind == "doc":
        if ext == "docx":
            try:
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                with zipfile.ZipFile(path) as z:
                    root = ET.fromstring(z.read("word/document.xml"))
                paras = [p for p in root.iter(f"{ns}p")]
                specs_parts.append(f"{len(paras)} paragraphs")
            except Exception:
                pass
        elif ext in ("txt", "md", "html"):
            try:
                txt = path.read_text(encoding="utf-8", errors="ignore")
                lines = len(txt.splitlines())
                words = len(txt.split())
                specs_parts.append(f"{lines} lines · {words} words")
            except Exception:
                pass

    elif kind == "archive":
        try:
            if ext == "zip" and zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as z:
                    n = len([i for i in z.infolist() if not i.is_dir()])
                specs_parts.insert(0, f"{n} files")
            elif tarfile.is_tarfile(path):
                with tarfile.open(path) as tf:
                    n = len([m for m in tf.getmembers() if m.isfile()])
                specs_parts.insert(0, f"{n} files")
        except Exception:
            pass

    t_list = [(t, FORMAT_META.get(t, "Convert")) for t in targets_for([path])]
    return FileProfile(
        path=path,
        kind=kind,
        ext=ext,
        badge=badge,
        type_label=type_label,
        size_bytes=size_bytes,
        size_str=size_str,
        specs_str=" · ".join(specs_parts),
        details=details,
        tools=smart_tools_for([path]),
        targets=t_list,
    )


# --------------------------------------------------------------------------- helpers
def unique_path(directory: Path, stem: str, ext: str) -> Path:
    cand = directory / f"{stem}.{ext}"
    n = 1
    while cand.exists():
        cand = directory / f"{stem} ({n}).{ext}"
        n += 1
    return cand


def unique_dir(directory: Path, name: str) -> Path:
    cand = directory / name
    n = 1
    while cand.exists():
        cand = directory / f"{name} ({n})"
        n += 1
    return cand


def run(cmd: list[str], timeout: int | None = None) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise ConvertError(f"Missing required tool: {cmd[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise ConvertError(f"{cmd[0]} timed out") from e
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-4:]
        raise ConvertError(f"{Path(cmd[0]).name} failed:\n" + "\n".join(tail))


def soffice(src: Path, convert_to: str, infilter: str | None = None) -> Path:
    """Run LibreOffice headless with a private profile (works even if LO is open)."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise ConvertError("LibreOffice is not installed")
    profile = Path(tempfile.gettempdir()) / f"convertwheel-lo-{os.getuid()}"
    with tempfile.TemporaryDirectory(prefix="cwheel-") as tmp:
        cmd = [exe, f"-env:UserInstallation=file://{profile}", "--headless", "--norestore"]
        if infilter:
            cmd.append(f"--infilter={infilter}")
        cmd += ["--convert-to", convert_to, "--outdir", tmp, str(src)]
        run(cmd, timeout=300)
        produced = list(Path(tmp).iterdir())
        if not produced:
            raise ConvertError("LibreOffice produced no output")
        f = produced[0]
        dest = unique_path(src.parent, src.stem, f.suffix.lstrip("."))
        shutil.move(str(f), dest)
        return dest


def ffmpeg(src: Path, dest: Path, args: list[str]) -> Path:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), *args, str(dest)])
    return dest


def ensure_raster_image(src: Path) -> tuple[Path, bool]:
    """If `src` is a PDF, render its first page to a temporary PNG via PyMuPDF."""
    if kind_of(src) == "pdf":
        if pymupdf is None:
            raise ConvertError("PyMuPDF is required for PDF studio rendering")
        tmp_dir = Path(tempfile.mkdtemp(prefix="cwheel-pdfimg-"))
        out = tmp_dir / f"{src.stem}.png"
        with pymupdf.open(src) as doc:
            if doc.page_count < 1:
                raise ConvertError("PDF has no pages")
            pix = doc[0].get_pixmap(dpi=200, alpha=False)
            pix.save(str(out))
        return out, True
    return src, False


# --------------------------------------------------------------------------- convert
def convert(src: Path, target: str) -> Path:
    kind = kind_of(src)
    t = target.lower()
    if kind == "image":
        return _convert_image(src, t)
    if kind == "pdf":
        return _convert_pdf(src, t)
    if kind in ("doc", "sheet", "slide"):
        return _convert_office(src, t)
    if kind in ("video", "audio"):
        return _convert_av(src, t)
    if kind == "archive" and t == "zip":
        return _repack_to_zip(src)
    raise ConvertError(f"Unsupported conversion: {src.name} → {target.upper()}")


def _repack_to_zip(src: Path) -> Path:
    dest = unique_path(src.parent, src.stem, "zip")
    with tempfile.TemporaryDirectory(prefix="cwheel-arc-") as tmp:
        shutil.unpack_archive(str(src), tmp)
        base = str(dest.with_suffix(""))
        out = shutil.make_archive(base, "zip", tmp)
        return Path(out)


def create_zip(paths: list[Path], dest: Path | None = None) -> Path:
    """Combine multiple files or folders into a single clean .zip archive."""
    if not paths:
        raise ConvertError("No files provided to archive")
    parent = paths[0].parent
    if dest is None:
        if len(paths) == 1:
            name = paths[0].stem
        else:
            name = f"Archive ({len(paths)} files)"
        dest = unique_path(parent, name, "zip")
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in paths:
            if p.is_file():
                zf.write(p, arcname=p.name)
            elif p.is_dir():
                for root, _, files in os.walk(p):
                    for f in files:
                        full = Path(root) / f
                        rel = full.relative_to(p.parent)
                        zf.write(full, arcname=str(rel))
    return dest


def _image_to_docx(src: Path) -> Path:
    """Create a clean .docx document embedding the image using python-docx and Pillow."""
    from docx import Document
    from docx.shared import Inches

    dest = unique_path(src.parent, src.stem, "docx")
    im = _open_pil_image(src, auto_orient=True)
    iw, ih = im.size
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    doc = Document()
    max_w_in = 6.0
    max_h_in = 8.5
    scale = min(max_w_in / max(1, iw / 96.0), max_h_in / max(1, ih / 96.0), 1.0)
    w_in = max(1.0, (iw / 96.0) * scale)
    doc.add_picture(buf, width=Inches(min(max_w_in, w_in)))
    doc.save(str(dest))
    return dest


def _convert_image(src: Path, t: str) -> Path:
    if t == "docx":
        return _image_to_docx(src)
    dest = unique_path(src.parent, src.stem, t)
    im = _open_pil_image(src, auto_orient=True)
    q = 92 if t == "jpg" else 85
    return _save_pil_image(im, dest, t, quality=q, strip=False)


def _convert_pdf(src: Path, t: str) -> Path:
    if t == "docx":
        return soffice(src, "docx:MS Word 2007 XML", infilter="writer_pdf_import")
    if pymupdf is None:
        raise ConvertError("PyMuPDF is not installed")
    if t == "txt":
        dest = unique_path(src.parent, src.stem, "txt")
        with pymupdf.open(src) as doc:
            pages_txt = [page.get_text("text").rstrip() for page in doc]
        dest.write_text("\n\n".join(pages_txt).strip() + "\n", encoding="utf-8")
        return dest
    if t in ("jpg", "png"):
        with pymupdf.open(src) as doc:
            n = doc.page_count
            if n == 0:
                raise ConvertError("PDF contains no pages")
            if n == 1:
                dest = unique_path(src.parent, src.stem, t)
                pix = doc[0].get_pixmap(dpi=200, alpha=False)
                if t == "jpg":
                    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    im.save(dest, format="JPEG", quality=92, optimize=True)
                else:
                    pix.save(str(dest))
                return dest
            folder = unique_dir(src.parent, f"{src.stem} ({t.upper()} pages)")
            folder.mkdir(parents=True, exist_ok=True)
            width = len(str(n))
            for i, page in enumerate(doc, 1):
                out_file = folder / f"{src.stem} {str(i).zfill(width)}.{t}"
                pix = page.get_pixmap(dpi=200, alpha=False)
                if t == "jpg":
                    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    im.save(out_file, format="JPEG", quality=92, optimize=True)
                else:
                    pix.save(str(out_file))
            return folder
    raise ConvertError(f"PDF → {t.upper()} not supported")


_OFFICE_FILTERS = {
    "txt": "txt:Text (encoded):UTF8",
    "csv": "csv:Text - txt - csv (StarCalc):44,34,76",
    "html": "html",
}


def _convert_office(src: Path, t: str) -> Path:
    if t in ("jpg", "png"):
        pdf = soffice(src, "pdf")
        try:
            return _convert_pdf(pdf, t)
        finally:
            pdf.unlink(missing_ok=True)
    if t == "txt":
        return _office_to_txt(src)
    infilter = "Text (encoded):UTF8" if ext_of(src) in ("txt", "md") else None
    return soffice(src, _OFFICE_FILTERS.get(t, t), infilter=infilter)


def _office_to_txt(src: Path) -> Path:
    dest = unique_path(src.parent, src.stem, "txt")
    if ext_of(src) == "docx":
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(src) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        lines = []
        for para in root.iter(f"{ns}p"):
            parts = []
            for node in para.iter():
                if node.tag == f"{ns}t" and node.text:
                    parts.append(node.text)
                elif node.tag == f"{ns}tab":
                    parts.append("\t")
                elif node.tag in (f"{ns}br", f"{ns}cr"):
                    parts.append("\n")
            lines.append("".join(parts))
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
        dest.write_text(text, encoding="utf-8")
        return dest
    if ext_of(src) in ("txt", "md"):
        shutil.copyfile(src, dest)
        return dest
    pdf = soffice(src, "pdf")
    try:
        if pymupdf is not None:
            with pymupdf.open(pdf) as doc:
                txt = "\n\n".join(p.get_text("text").rstrip() for p in doc).strip() + "\n"
            dest.write_text(txt, encoding="utf-8")
        else:
            raise ConvertError("PyMuPDF is required to extract text")
    finally:
        pdf.unlink(missing_ok=True)
    return dest


_AV_ARGS = {
    "mp4": ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"],
    "mov": ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k"],
    "mkv": ["-map", "0", "-c", "copy"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
             "-c:a", "libopus", "-b:a", "128k"],
    "avi": ["-c:v", "mpeg4", "-q:v", "3", "-c:a", "libmp3lame", "-q:a", "3"],
    "gif": ["-an", "-vf", "fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];"
            "[a]palettegen[p];[b][p]paletteuse", "-loop", "0"],
    "mp3": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-vn", "-c:a", "pcm_s16le"],
    "flac": ["-vn", "-c:a", "flac"],
    "ogg": ["-vn", "-c:a", "libvorbis", "-q:a", "5"],
    "m4a": ["-vn", "-c:a", "aac", "-b:a", "192k"],
    "opus": ["-vn", "-c:a", "libopus", "-b:a", "128k"],
    "aac": ["-vn", "-c:a", "aac", "-b:a", "192k"],
}


def _convert_av(src: Path, t: str) -> Path:
    if t not in _AV_ARGS:
        raise ConvertError(f"→ {t.upper()} not supported")
    dest = unique_path(src.parent, src.stem, t)
    try:
        return ffmpeg(src, dest, _AV_ARGS[t])
    except ConvertError:
        if t == "mkv":
            dest.unlink(missing_ok=True)
            return ffmpeg(src, dest, _AV_ARGS["mp4"][:-2])
        dest.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- tools
def inspect_metadata(src: Path) -> list[tuple[str, str]]:
    """Read key metadata fields from an image, video, audio, PDF, document, or archive."""
    rows: list[tuple[str, str]] = []
    try:
        st = src.stat()
        rows.append(("File name", src.name))
        rows.append(("Location", str(src.parent)))
        rows.append(("File size", f"{format_file_size([src])} ({st.st_size:,} bytes)"))
        rows.append(("Modified", datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")))
    except OSError:
        pass
    kind = kind_of(src)
    if kind == "image":
        try:
            with Image.open(src) as im:
                rows.append(("Format", str(im.format or ext_of(src).upper())))
                rows.append(("Dimensions", f"{im.width} × {im.height} px"))
                rows.append(("Colour mode", im.mode))
                if "dpi" in im.info:
                    dpi = im.info["dpi"]
                    rows.append(("DPI", f"{dpi[0]} × {dpi[1]}"))
                if "icc_profile" in im.info:
                    rows.append(("ICC profile", f"Embedded ({len(im.info['icc_profile']):,} B)"))
                exif = im.getexif()
                if exif:
                    for tag_id, val in exif.items():
                        tag_name = ExifTags.TAGS.get(tag_id, f"Tag {tag_id}")
                        if isinstance(val, bytes):
                            continue
                        s_val = str(val).strip()
                        if s_val and len(rows) < 28:
                            rows.append((f"EXIF {tag_name}", s_val[:120]))
                for k, v in im.info.items():
                    if k in ("exif", "icc_profile", "dpi") or isinstance(v, (bytes, tuple, list, dict)):
                        continue
                    s_val = str(v).strip()
                    if s_val and len(rows) < 28:
                        rows.append((str(k).title(), s_val[:120]))
        except Exception:
            pass
    elif kind in ("video", "audio"):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration,bit_rate:format_tags:stream=codec_name,width,height,sample_rate",
                 "-of", "default=noprint_wrappers=1", str(src)],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.replace("TAG:", "").strip().title()
                    v = v.strip()
                    if k and v and v != "N/A" and len(rows) < 26:
                        rows.append((k, v))
        except Exception:
            pass
    elif kind == "pdf" and pymupdf is not None:
        try:
            with pymupdf.open(src) as doc:
                rows.append(("Pages", str(doc.page_count)))
                if doc.page_count > 0:
                    rect = doc[0].rect
                    rows.append(("Page size", f"{round(rect.width)} × {round(rect.height)} pt"))
                rows.append(("Encrypted", "Yes" if doc.is_encrypted else "No"))
                meta = doc.metadata or {}
                for k, v in meta.items():
                    if v and str(v).strip():
                        rows.append((k.title(), str(v).strip()))
        except Exception:
            pass
    elif kind == "archive":
        try:
            if zipfile.is_zipfile(src):
                with zipfile.ZipFile(src) as z:
                    infos = [i for i in z.infolist() if not i.is_dir()]
                    rows.append(("Archive format", "ZIP"))
                    rows.append(("Total files", str(len(infos))))
                    for info in infos[:15]:
                        rows.append((info.filename, f"{info.file_size:,} B"))
        except Exception:
            pass
    return rows


def strip_metadata(src: Path) -> Path:
    kind = kind_of(src)
    ext = ext_of(src) or "out"
    dest = unique_path(src.parent, f"{src.stem} Clean", ext)
    if kind == "image":
        im = _open_pil_image(src, auto_orient=True)
        if im.mode not in ("RGB", "RGBA", "L", "LA"):
            im = im.convert("RGBA" if "A" in im.mode else "RGB")
        clean = Image.frombytes(im.mode, im.size, im.tobytes())
        return _save_pil_image(clean, dest, ext, quality=92, strip=True)
    if kind in ("video", "audio"):
        return ffmpeg(src, dest, ["-map", "0", "-map_metadata", "-1", "-map_chapters", "-1", "-c", "copy"])
    if kind == "pdf" and pymupdf is not None:
        with pymupdf.open(src) as doc:
            doc.set_metadata({})
            try:
                doc.del_xml_metadata()
            except Exception:
                pass
            try:
                doc.scrub(
                    attached_files=True,
                    clean_pages=True,
                    embedded_files=True,
                    hidden_text=False,
                    javascript=True,
                    metadata=True,
                    redactions=False,
                    remove_links=False,
                    reset_fields=False,
                     reset_responses=False,
                    thumbnails=True,
                    xml_metadata=True,
                )
            except Exception:
                pass
            doc.save(str(dest), garbage=4, deflate=True, clean=True)
        return dest
    raise ConvertError(f"Metadata stripping is not supported for {src.name}")


def extract_archive(src: Path) -> Path:
    dest_dir = unique_dir(src.parent, src.stem)
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.unpack_archive(str(src), str(dest_dir))
    except Exception as e:
        raise ConvertError(f"Could not extract {src.name}: {e}") from e
    return dest_dir


def _compress_image_native(src: Path) -> Path:
    """High-efficiency native image compression inspired by GNOME Curtail & Switcheroo."""
    ext = ext_of(src)
    out_ext = ext if ext in ("jpg", "webp", "png", "avif", "heic") else "jpg"
    dest = unique_path(src.parent, f"{src.stem} Compressed", out_ext)
    im = _open_pil_image(src, auto_orient=True)
    if im.width > 2560 or im.height > 2560:
        im.thumbnail((2560, 2560), Image.Resampling.LANCZOS)

    if out_ext == "png":
        # Quantize to 256-colour palette (like pngquant / Curtail) for 60-75% PNG reduction
        rgba = im.convert("RGBA")
        quantized = rgba.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
        quantized.save(dest, format="PNG", optimize=True, compress_level=9)
    else:
        _save_pil_image(im, dest, out_ext, quality=74, strip=True)
    return dest


def _compress_pdf_native(src: Path) -> Path:
    """Compress PDF streams, fonts, and embedded images using PyMuPDF's C engine."""
    if pymupdf is None:
        raise ConvertError("PyMuPDF is not installed")
    dest = unique_path(src.parent, f"{src.stem} Compressed", "pdf")
    with pymupdf.open(src) as doc:
        if hasattr(doc, "rewrite_images"):
            try:
                doc.rewrite_images(
                    dpi_threshold=150,
                    dpi_target=110,
                    quality=72,
                    lossy=True,
                    bitonal=False,
                )
            except Exception:
                pass
        doc.save(
            str(dest),
            garbage=4,
            clean=True,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
        )
    return dest


def run_tool(src: Path, tool: str) -> Path:
    kind = kind_of(src)
    ext = ext_of(src) or "out"

    if tool == "zip":
        return create_zip([src])

    if tool == "extract":
        if kind == "archive":
            return extract_archive(src)
        if kind == "pdf":
            return _convert_pdf(src, "png")

    if tool == "compress":
        if kind == "image":
            return _compress_image_native(src)
        if kind == "video":
            dest = unique_path(src.parent, f"{src.stem} Compressed", "mp4")
            return ffmpeg(src, dest, ["-vf", "scale='min(1920,iw)':-2", "-c:v", "libx264",
                                      "-crf", "28", "-preset", "medium", "-pix_fmt", "yuv420p",
                                      "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"])
        if kind == "audio":
            dest = unique_path(src.parent, f"{src.stem} Compressed", "mp3")
            return ffmpeg(src, dest, ["-vn", "-c:a", "libmp3lame", "-b:a", "128k"])
        if kind == "pdf":
            return _compress_pdf_native(src)

    if tool == "metadata":
        return strip_metadata(src)

    if tool == "edit":
        dest = unique_path(src.parent, f"{src.stem} Rotated", ext)
        if kind == "image":
            im = _open_pil_image(src, auto_orient=True)
            rotated = im.rotate(-90, expand=True)
            return _save_pil_image(rotated, dest, ext, quality=92, strip=False)
        if kind == "video":
            return ffmpeg(src, dest, ["-vf", "transpose=1", "-c:v", "libx264", "-crf", "20",
                                      "-pix_fmt", "yuv420p", "-c:a", "copy"])

    raise ConvertError(f"Tool '{tool}' is not compatible with {src.name}")


def crop_image(src: Path, x: int, y: int, w: int, h: int) -> Path:
    real_src, is_temp = ensure_raster_image(src)
    try:
        ext = "png" if is_temp else (ext_of(src) or "png")
        dest = unique_path(src.parent, f"{src.stem} Cropped", ext)
        im = _open_pil_image(real_src, auto_orient=True)
        x0 = max(0, min(im.width - 1, x))
        y0 = max(0, min(im.height - 1, y))
        x1 = max(x0 + 1, min(im.width, x0 + w))
        y1 = max(y0 + 1, min(im.height, y0 + h))
        cropped = im.crop((x0, y0, x1, y1))
        return _save_pil_image(cropped, dest, ext, quality=92)
    finally:
        if is_temp:
            shutil.rmtree(real_src.parent, ignore_errors=True)
