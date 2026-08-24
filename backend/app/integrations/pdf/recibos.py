"""Recibo PDF pequeño y determinista; no contiene lógica de negocio."""

from __future__ import annotations

from fpdf import FPDF


def _texto(valor: object) -> str:
    """Helvetica cubre español/latin-1; sustituye símbolos externos sin romper el recibo."""
    return str(valor).replace("—", "-").encode("latin-1", "replace").decode("latin-1")


def generar_recibo(datos: dict) -> bytes:
    pdf = FPDF(format=(148, 210))
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_fill_color(45, 52, 58)
    pdf.rect(0, 0, 148, 28, "F")
    pdf.set_text_color(255, 250, 232)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, "MARFIL")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(12, 17)
    pdf.cell(0, 5, "PARFUM DE L'AME · COMPROBANTE DE ABONO")
    pdf.set_text_color(48, 53, 58)
    pdf.set_y(38)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Recibo #{datos['id']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    filas = [
        ("Cliente", datos["cliente"]),
        ("Venta", datos["venta"]),
        ("Fecha", str(datos["fecha"])),
        ("Canal", str(datos["canal"] or "-")),
        ("Referencia", str(datos["referencia"] or "-")),
        ("Monto registrado", f"{datos['monto_moneda']} {datos['moneda']}"),
        ("Equivalente", f"${datos['monto_usd']} USD"),
        ("Saldo restante", f"${datos['saldo_usd']} USD"),
    ]
    for etiqueta, valor in filas:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(42, 8, etiqueta)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(
            0,
            8,
            _texto(valor),
            border="B",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.ln(8)
    pdf.set_text_color(100, 104, 102)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0,
        5,
        "Comprobante generado por Sistema Marfil. Los montos se conservan en "
        "el libro de pagos y no pueden editarse.",
    )
    return bytes(pdf.output())
