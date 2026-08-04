from __future__ import annotations

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos


def generar_recibo_pdf(pago_info: dict[str, object]) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "SISTEMA MARFIL - COMPROBANTE DE PAGO", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Fecha: {pago_info.get('fecha', datetime.today().date())}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Folio de Pago: {pago_info.get('id')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Datos del Cliente", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Cliente: {pago_info.get('cliente', '')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Vendedor: {pago_info.get('vendedor', '')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Detalle de la Transacción", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Producto: {pago_info.get('producto', '')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Monto abonado (Bs.): Bs. {float(pago_info.get('monto_bs', 0)):,.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Tasa BCV aplicada: Bs. {float(pago_info.get('tasa_bcv', 0)):,.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Equivalente en USD: ${float(pago_info.get('monto_usd', 0)):,.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Saldo", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Saldo restante en USD: ${float(pago_info.get('saldo_usd', 0)):,.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Estatus: {pago_info.get('estatus', '')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)

    pdf.set_font("Helvetica", "I", 11)
    pdf.multi_cell(0, 6, "¡Gracias por tu compra en Sistema Marfil!")

    return bytes(pdf.output())
