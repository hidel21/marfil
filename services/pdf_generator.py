from __future__ import annotations

import io
from datetime import datetime

from fpdf import FPDF


def generar_recibo_pdf(pago_info: dict[str, object]) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "SISTEMA MARFIL - COMPROBANTE DE PAGO", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Fecha: {pago_info.get('fecha', datetime.today().date())}", ln=True)
    pdf.cell(0, 6, f"Folio de Pago: {pago_info.get('id')}", ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Datos del Cliente", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Cliente: {pago_info.get('cliente', '')}", ln=True)
    pdf.cell(0, 6, f"Vendedor: {pago_info.get('vendedor', '')}", ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Detalle de la Transacción", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Producto: {pago_info.get('producto', '')}", ln=True)
    pdf.cell(0, 6, f"Monto abonado (Bs.): Bs. {float(pago_info.get('monto_bs', 0)):,.2f}", ln=True)
    pdf.cell(0, 6, f"Tasa BCV aplicada: Bs. {float(pago_info.get('tasa_bcv', 0)):,.2f}", ln=True)
    pdf.cell(0, 6, f"Equivalente en USD: ${float(pago_info.get('monto_usd', 0)):,.2f}", ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, "Saldo", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Saldo restante en USD: ${float(pago_info.get('saldo_usd', 0)):,.2f}", ln=True)
    pdf.cell(0, 6, f"Estatus: {pago_info.get('estatus', '')}", ln=True)
    pdf.ln(10)

    pdf.set_font("Helvetica", "I", 11)
    pdf.multi_cell(0, 6, "¡Gracias por tu compra en Sistema Marfil! 🍾")

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer.read()
