"""Exports contain only real saved captures, user notes and available OCR."""
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .storage import Store


def export_session(store: Store, sid: str, kind: str, enhanced: bool | None = None) -> Path:
    with store.lock(sid):
        session = store.read(sid)
        directory = store.directory(sid) / "exports"
        directory.mkdir(exist_ok=True)
        if kind not in {"pdf", "zip", "json", "txt"}:
            raise ValueError("Supported export formats: pdf, zip, json, txt")
        target = directory / f"lecture.{kind}"
        temporary = directory / f"lecture.{kind}.tmp"
        variant = "enhanced" if (session["settings"]["enhanced_export"] if enhanced is None else enhanced) else "original"
        captures = sorted(session["captures"], key=lambda c: c["sequence"])
        if kind == "json":
            temporary.write_text(json.dumps(store.public(session), ensure_ascii=False, indent=2))
        elif kind == "txt":
            temporary.write_text("\n\n".join(f"{c['name']} — {c['timestamp']}\n{c['ocr']['text']}" for c in captures if c["ocr"]["text"]))
        elif kind == "zip":
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                for capture in captures:
                    archive.write(store.capture_path(sid, capture["id"], variant), f"capture_{capture['sequence']:04d}.jpg")
                archive.writestr("metadata.json", json.dumps(store.public(session), ensure_ascii=False, indent=2))
        else:
            _pdf(store, session, captures, variant, temporary)
        temporary.replace(target)
        return target


def _pdf(store: Store, session: dict, captures: list, variant: str, target: Path) -> None:
    if "WhiteboardSans" not in pdfmetrics.getRegisteredFontNames():
        font = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        pdfmetrics.registerFont(TTFont("WhiteboardSans", str(font)))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("BoardTitle", fontName="WhiteboardSans", fontSize=26, leading=34, textColor=colors.HexColor("#16302b"), spaceAfter=18))
    styles.add(ParagraphStyle("BoardText", fontName="WhiteboardSans", fontSize=10, leading=15, spaceAfter=9))
    styles.add(ParagraphStyle("BoardHeading", fontName="WhiteboardSans", fontSize=16, leading=22, spaceAfter=12))
    text = lambda value, style="BoardText": Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])
    story = [Spacer(1, 95), text("AI Whiteboard Smart Capture", "BoardHeading"),
             text(session["title"], "BoardTitle"), text(session["course"]),
             text(f"Session created: {session['created_at']} (UTC)"),
             text(f"{len(captures)} saved captures · {variant} images"), text(session["description"])]
    for capture in captures:
        path = store.capture_path(session["id"], capture["id"], variant)
        with PILImage.open(path) as pixels:
            width, height = pixels.size
        scale = min((A4[0] - 80) / width, 490 / height)
        source = f" · Video {capture['source_seconds']:.1f}s" if capture["source_seconds"] is not None else ""
        story += [PageBreak(), text(capture["name"], "BoardHeading"),
                  text(f"#{capture['sequence']:02d} · {capture['capture_type']} · {capture['timestamp']}{source}"),
                  Image(str(path), width=width * scale, height=height * scale), Spacer(1, 16)]
        if capture["note"]:
            story += [text("Notes", "BoardHeading"), text(capture["note"])]
        if capture["ocr"]["text"]:
            story += [text("Recognized text (may contain errors)", "BoardHeading"), text(capture["ocr"]["text"])]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("WhiteboardSans", 8)
        canvas.setFillColor(colors.HexColor("#64746e"))
        canvas.drawString(40, 25, "AI Whiteboard Smart Capture · Local lecture notes")
        canvas.drawRightString(A4[0] - 40, 25, str(document.page))
        canvas.restoreState()

    SimpleDocTemplate(str(target), pagesize=A4, rightMargin=40, leftMargin=40,
                      topMargin=40, bottomMargin=45, title=session["title"]).build(story, onFirstPage=footer, onLaterPages=footer)
