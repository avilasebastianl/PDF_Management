"""
Anotaciones (fase 3): crear, mover, recolorear, editar y eliminar, siempre en
coordenadas de la pagina tal como se ve (tambien en paginas giradas), con
deshacer/rehacer y Guardar como.
"""

import pymupdf
import pytest
from conftest import make_pdf

from pdfmanagement import core
from pdfmanagement.core.editing import AnnotationStyle, DocumentSession
from pdfmanagement.core.editing import annotations as annots
from pdfmanagement.core.editing.text import page_search

RED = (0.9, 0.1, 0.1)
BLUE = (0.2, 0.4, 1.0)


@pytest.fixture(params=[0, 90], ids=["normal", "girada"])
def session(request, tmp_path):
    opened = DocumentSession.open(make_pdf(tmp_path / "doc.pdf", 2, rotation=request.param))
    yield opened
    opened.close()


def close_to(rect, expected, tolerance=6):
    return all(abs(a - b) <= tolerance for a, b in zip(tuple(rect), tuple(expected), strict=True))


def only(session, page=0):
    [info] = session.annotations(page)
    return info


def test_shapes_are_placed_where_they_are_seen(session):
    style = AnnotationStyle(color=BLUE, width=3)
    session.add_shape(0, "rect", (100, 120, 250, 200), style)
    info = only(session)
    assert info.kind == "Square" and info.label == "Rectangulo"
    assert close_to(info.rect, (100, 120, 250, 200)), info.rect
    assert info.color == pytest.approx(BLUE)
    assert session.history.undo_label == "Agregar rectangulo (pagina 1)"
    session.undo()
    assert session.annotations(0) == []
    session.redo()
    assert len(session.annotations(0)) == 1


def test_markup_from_selected_words(session):
    words = session.words(0)
    rects = [pymupdf.Rect(word[:4]) for word in words]
    session.add_markup(0, "highlight", rects, AnnotationStyle())
    info = only(session)
    assert info.kind == "Highlight" and info.label == "Resaltado"
    page = session.document[0]
    quads = annots.find(page, info.xref).vertices  # 4 puntos por palabra, en coordenadas del PDF
    for index, rect in enumerate(rects):
        corners = [pymupdf.Point(point) * page.rotation_matrix for point in quads[index * 4 : index * 4 + 4]]
        assert close_to(pymupdf.Rect(corners[0], corners[0]) | corners[1] | corners[2] | corners[3], rect, tolerance=1)
    assert session.history.undo_label == "Resaltar texto (pagina 1)"
    session.add_markup(0, "strikeout", rects[:1], AnnotationStyle(color=RED))
    assert [a.kind for a in session.annotations(0)] == ["Highlight", "StrikeOut"]
    with pytest.raises(core.InvalidInputError):
        session.add_markup(0, "underline", [], AnnotationStyle())


def test_note_and_free_text(session):
    session.add_note(0, (300, 300), "Revisar esta clausula", AnnotationStyle())
    session.add_free_text(0, (80, 400, 330, 440), "Aprobado - año 2026", AnnotationStyle(color=RED))
    note, text = session.annotations(0)
    assert note.kind == "Text" and note.content == "Revisar esta clausula" and note.has_text
    # El cuadro conserva la esquina y el ancho dibujados y toma el alto de una linea.
    assert close_to(text.rect, (80, 400, 330, 400 + text.rect.height)) and 14 < text.rect.height < 24
    assert text.font_size == 12 and text.color == pytest.approx(RED, abs=0.01)
    page = session.document[0]
    [found] = page_search(page, "Aprobado - año 2026")
    assert text.rect.intersects(found) and abs(found.x0 - text.rect.x0) < 5, "texto derecho en su lugar"
    with pytest.raises(core.InvalidInputError):
        session.add_free_text(0, (80, 500, 300, 540), "   ", AnnotationStyle())


def test_lines_arrows_and_ink(session):
    session.add_line(0, (100, 100), (300, 200), AnnotationStyle(color=RED, width=2), arrow=True)
    session.add_ink(0, [[(100, 300), (120, 320), (160, 310), (200, 340)]], AnnotationStyle(width=4))
    line, ink = session.annotations(0)
    assert (line.kind, ink.kind) == ("Line", "Ink")
    assert close_to(line.rect, (100, 100, 300, 200), tolerance=12)
    assert session.history.undo_label == "Dibujar a mano (pagina 1)"
    with pytest.raises(core.InvalidInputError):
        session.add_ink(0, [[(10, 10)]], AnnotationStyle())


@pytest.mark.parametrize("kind", ["rect", "note", "free_text", "line", "ink"])
def test_move_annotations(session, kind):
    style = AnnotationStyle(color=RED, width=3, opacity=0.6)
    create = {
        "rect": lambda: session.add_shape(0, "rect", (100, 100, 200, 160), style),
        "note": lambda: session.add_note(0, (100, 100), "nota", style),
        "free_text": lambda: session.add_free_text(0, (100, 100, 260, 140), "texto", style),
        "line": lambda: session.add_line(0, (100, 100), (200, 160), style, arrow=True),
        "ink": lambda: session.add_ink(0, [[(100, 100), (150, 130), (200, 160)]], style),
    }
    xref = create[kind]()
    before = only(session)
    session.move_annotation(0, xref, 40, 25)
    new_xref = session.move_annotation(0, only(session).xref, -40, -25)  # ida y vuelta: sin deriva
    assert close_to(only(session).rect, before.rect, tolerance=0.5)
    new_xref = session.move_annotation(0, new_xref, 40, 25)
    after = only(session)
    assert after.xref == new_xref
    assert close_to(after.rect, before.rect + (40, 25, 40, 25), tolerance=2), (before.rect, after.rect)
    assert after.color == pytest.approx(before.color, abs=0.01), "las propiedades se conservan al mover"
    assert session.history.undo_label.startswith("Mover ")
    if kind == "line":
        page = session.document[0]  # la pagina debe seguir viva mientras se usa la anotacion
        annot = annots.find(page, new_xref)
        assert annot.line_ends[1] == pymupdf.PDF_ANNOT_LE_OPEN_ARROW
        assert annot.border["width"] == 3
    session.undo()
    assert close_to(only(session).rect, before.rect, tolerance=1)


def test_markup_cannot_be_moved(session):
    xref = session.add_markup(0, "underline", [pymupdf.Rect(session.words(0)[0][:4])], AnnotationStyle())
    with pytest.raises(core.InvalidInputError):
        session.move_annotation(0, xref, 10, 10)
    assert session.history.undo_label == "Subrayar texto (pagina 1)", "el intento fallido no queda en el historial"


def test_recolor_edit_text_and_delete(session):
    note = session.add_note(0, (200, 200), "original", AnnotationStyle())
    text = session.add_free_text(0, (80, 400, 330, 440), "Borrador", AnnotationStyle(color=RED))
    session.set_annotation_color(0, note, BLUE)
    session.set_annotation_text(0, note, "corregida")
    session.set_annotation_text(0, text, "Final")
    session.set_annotation_color(0, text, BLUE)
    infos = {info.xref: info for info in session.annotations(0)}
    assert infos[note].content == "corregida" and infos[note].color == pytest.approx(BLUE, abs=0.01)
    assert infos[text].content == "Final"
    assert session.history.undo_label == "Cambiar color de texto"
    with pytest.raises(core.InvalidInputError):
        session.set_annotation_text(0, text, "")
    session.delete_annotation(0, note)
    assert [info.xref for info in session.annotations(0)] == [text]
    assert session.history.undo_label == "Eliminar nota"
    session.undo()
    assert len(session.annotations(0)) == 2
    with pytest.raises(core.InvalidInputError):
        session.delete_annotation(0, 999999)


def test_annotations_survive_save_as_and_page_moves(session, tmp_path):
    session.add_shape(1, "ellipse", (100, 100, 200, 200), AnnotationStyle(color=BLUE))
    session.add_note(0, (50, 50), "primera", AnnotationStyle())
    session.move([1], 0)  # la elipse viaja con su pagina
    assert [info.kind for info in session.annotations(0)] == ["Circle"]
    output = session.save_as(tmp_path / "anotado.pdf")
    reopened = DocumentSession.open(output)
    assert [(info.page, info.kind) for info in reopened.annotations()] == [(0, "Circle"), (1, "Text")]
    reopened.close()


def test_failed_operation_does_not_undo_the_previous_one(session):
    """MuPDF descarta las operaciones vacias: antes el rollback deshacia la anterior."""
    session.add_note(0, (50, 50), "previa", AnnotationStyle())
    with pytest.raises(core.InvalidInputError):
        session.add_shape(0, "rect", (100, 100, 101, 101), AnnotationStyle())  # falla antes de modificar
    assert [info.content for info in session.annotations(0)] == ["previa"]
    assert session.history.undo_depth == 1
    with session.history.operation("Nada"):
        pass
    assert session.history.undo_label == "Agregar nota (pagina 1)", "una operacion vacia no se registra"


def test_text_after_undo_has_a_valid_font(session):
    """Antes: texto, deshacer, texto -> "cannot find object in xref" (fuente en la cache de MuPDF)."""
    pymupdf.TOOLS.reset_mupdf_warnings()
    session.add_free_text(0, (60, 400, 300, 440), "Primero", AnnotationStyle())
    session.undo()
    session.add_free_text(0, (60, 500, 300, 540), "Segundo", AnnotationStyle())
    page = session.document[0]
    page.get_pixmap()
    assert "cannot find object" not in pymupdf.TOOLS.mupdf_warnings()
    assert session.history.undo_depth == 1


def test_free_text_font_size_and_fitting(session):
    """El tamano de letra se puede cambiar y el cuadro se ajusta al texto."""
    xref = session.add_free_text(0, (100, 100, 102, 102), "Clic simple", AnnotationStyle(), fontsize=14)
    info = only(session)
    assert info.font_size == 14
    assert 60 < info.rect.width < 120, "con un clic el cuadro toma el ancho del texto"
    session.set_annotation_font_size(0, xref, 28)
    bigger = only(session)
    assert bigger.font_size == 28 and bigger.rect.height > info.rect.height * 1.6
    assert close_to(bigger.rect.tl, info.rect.tl, tolerance=1), "crece desde la esquina superior izquierda"
    assert session.history.undo_label == "Cambiar tamano de texto"
    session.set_annotation_text(0, xref, "Un texto bastante mas largo que ya no cabe en una sola linea del cuadro")
    longer = only(session)
    assert longer.rect.height > bigger.rect.height * 1.8 and longer.rect.width == pytest.approx(
        bigger.rect.width, abs=1
    )
    session.undo()
    session.undo()
    assert only(session).font_size == 14
    with pytest.raises(core.InvalidInputError):
        session.set_annotation_font_size(0, xref, 1)
    note = session.add_note(0, (300, 300), "nota", AnnotationStyle())
    with pytest.raises(core.InvalidInputError):
        session.set_annotation_font_size(0, note, 20)
