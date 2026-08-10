from __future__ import annotations

import argparse
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import select

import database as db


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _column(reference: str) -> str:
    return re.match(r"[A-Z]+", reference).group()


def read_xlsx(path: Path) -> dict[str, list[tuple[int, dict[str, object]]]]:
    with ZipFile(path) as archive:
        shared_path = "xl/sharedStrings.xml"
        shared = []
        if shared_path in archive.namelist():
            root = ET.fromstring(archive.read(shared_path))
            shared = [
                "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
                for item in root
            ]

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        result = {}

        for sheet in workbook.find(f"{{{MAIN_NS}}}sheets"):
            name = sheet.attrib["name"].strip()
            target = targets[sheet.attrib[f"{{{REL_NS}}}id"]]
            target = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
            worksheet = ET.fromstring(archive.read(target))
            rows = []
            for row in worksheet.findall(
                f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"
            ):
                values = {}
                for cell in row.findall(f"{{{MAIN_NS}}}c"):
                    value_node = cell.find(f"{{{MAIN_NS}}}v")
                    raw = value_node.text if value_node is not None else None
                    cell_type = cell.attrib.get("t")
                    if cell_type == "s" and raw is not None:
                        value = shared[int(raw)]
                    elif cell_type == "inlineStr":
                        value = "".join(
                            node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t")
                        )
                    else:
                        value = raw
                    if value not in (None, ""):
                        values[_column(cell.attrib["r"])] = value

                meaningful = [
                    value for value in values.values() if str(value).strip() not in {"", "0", "0.0"}
                ]
                if meaningful:
                    rows.append((int(row.attrib["r"]), values))
            result[name] = rows
        return result


def number(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip().replace("$", "").replace(" ", "")
    match = re.search(r"-?\d[\d.,]*", text)
    if not match:
        return default
    text = match.group()
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        integer, decimal = text.rsplit(",", 1)
        text = f"{integer.replace(',', '')}.{decimal}"
    try:
        return float(text)
    except ValueError:
        return default


def excel_date(value: object) -> date | None:
    serial = number(value, -1)
    if serial < 1:
        return None
    return date(1899, 12, 30) + timedelta(days=int(serial))


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def similarity(left: dict[str, object], right: dict[str, object]) -> float:
    client = SequenceMatcher(None, normalized(left.get("B")), normalized(right.get("C"))).ratio()
    product = SequenceMatcher(None, normalized(left.get("D")), normalized(right.get("B"))).ratio()
    return client * 0.55 + product * 0.45


def migrate(path: Path) -> dict[str, int | str]:
    workbook = read_xlsx(path)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    db.init_db()
    session = db.get_session()
    try:
        if session.scalar(
            select(db.ImportacionExcel).where(db.ImportacionExcel.archivo_hash == source_hash)
        ):
            return {"estado": "ya_importado", "productos": 0, "ventas": 0, "pagos": 0}

        import_record = db.ImportacionExcel(archivo=path.name, archivo_hash=source_hash)
        session.add(import_record)
        session.flush()

        raw_count = 0
        for sheet_name, rows in workbook.items():
            if not rows:
                session.add(
                    db.FilaExcel(
                        importacion_id=import_record.id,
                        pestaña=sheet_name,
                        numero_fila=0,
                        datos={"estado": "Pestaña vacía en el archivo de origen"},
                    )
                )
                raw_count += 1
            for row_number, values in rows:
                session.add(
                    db.FilaExcel(
                        importacion_id=import_record.id,
                        pestaña=sheet_name,
                        numero_fila=row_number,
                        datos={key: value for key, value in values.items()},
                    )
                )
                raw_count += 1

        product_count = 0
        for row_number, row in workbook.get("PRECIOS PERF ORIGINALES", []):
            if row_number < 2 or not row.get("A"):
                continue
            session.add(
                db.Producto(
                    nombre=str(row["A"]).strip(),
                    categoria="Original",
                    precio_original=number(row.get("B")),
                    precio_team=number(row.get("C")),
                    precio_revendedor=number(row.get("D")),
                    precio_divisa=number(row.get("B")),
                    precio_bcv=number(row.get("B")),
                    stock=0,
                )
            )
            product_count += 1

        for row_number, row in workbook.get("PRECIOS PERF TOP QUALITY", []):
            if row_number < 4 or not row.get("A"):
                continue
            session.add(
                db.Producto(
                    nombre=str(row["A"]).strip(),
                    categoria="Top Quality",
                    costo=number(row.get("B")),
                    precio_divisa=number(row.get("C")),
                    precio_bcv=number(row.get("D")),
                    stock=0,
                )
            )
            product_count += 1

        control_rows = [
            row for row_number, row in workbook.get("CONTROL", [])
            if 4 <= row_number <= 33 and row.get("B") and row.get("D")
        ]
        sales_rows = [
            row for row_number, row in workbook.get("VENTAS", [])
            if row_number >= 5 and row.get("B") and row.get("C")
        ]
        unused_sales = sales_rows.copy()
        sales_with_source = []
        for control in control_rows:
            match = max(unused_sales, key=lambda candidate: similarity(control, candidate), default={})
            score = similarity(control, match) if match else 0
            if match and score >= 0.52:
                unused_sales.remove(match)
            else:
                match = {}
            sales_with_source.append((control, match))

        sale_count = 0
        payment_count = 0
        for control, sale_source in sales_with_source:
            price = number(control.get("E"))
            cost = number(sale_source.get("F"))
            status_raw = normalized(control.get("O"))
            payment_blocks = []
            for installment, (amount_col, date_col, reference_col) in enumerate(
                [("F", "G", "H"), ("I", "J", "K"), ("L", "M", "N")], start=1
            ):
                amount_bs = number(control.get(amount_col))
                paid_date = excel_date(control.get(date_col))
                if amount_bs > 0 and paid_date:
                    payment_blocks.append(
                        (installment, amount_bs, paid_date, str(control.get(reference_col) or "SIN REFERENCIA"))
                    )

            cash_payment = "efectivo" in normalized(control.get("F"))
            if "ya pago" in status_raw or cash_payment:
                debt = 0.0
                status = "YA PAGO"
            elif "sin abonos" in status_raw:
                debt = price
                status = "PENDIENTE"
            elif payment_blocks:
                debt = round(max(0.0, price * (3 - len(payment_blocks)) / 3), 2)
                status = "PENDIENTE" if debt else "YA PAGO"
            else:
                debt = price
                status = "PENDIENTE"

            sale = db.Venta(
                fecha=excel_date(control.get("A")) or date.today(),
                cliente=str(control.get("B")).strip(),
                vendedor=str(control.get("C") or "").strip(),
                producto=str(control.get("D")).strip(),
                cantidad=1,
                precio_venta=price,
                costo=cost,
                ganancia=number(sale_source.get("G"), price - cost),
                moneda=str(sale_source.get("H") or "BCV"),
                deuda=debt,
                estatus=status,
                total=price,
            )
            session.add(sale)
            session.flush()
            sale_count += 1

            paid_usd_total = max(0.0, price - debt)
            total_bs = sum(block[1] for block in payment_blocks)
            for installment, amount_bs, paid_date, reference in payment_blocks:
                amount_usd = paid_usd_total * amount_bs / total_bs if total_bs else 0
                if amount_usd <= 0:
                    continue
                session.add(
                    db.Pago(
                        venta_id=sale.id,
                        fecha=paid_date,
                        cliente=sale.cliente,
                        producto=sale.producto,
                        monto_bs=round(amount_bs, 2),
                        monto_usd=round(amount_usd, 2),
                        referencia=reference,
                        tasa_bcv=round(amount_bs / amount_usd, 2),
                        nro_cuota=installment,
                    )
                )
                payment_count += 1

        session.commit()
        return {
            "estado": "importado",
            "productos": product_count,
            "ventas": sale_count,
            "pagos": payment_count,
            "filas_excel": raw_count,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra el libro histórico de Sistema Marfil.")
    parser.add_argument("archivo", type=Path)
    args = parser.parse_args()
    if not args.archivo.is_file():
        parser.error(f"No existe el archivo: {args.archivo}")
    print(migrate(args.archivo.resolve()))


if __name__ == "__main__":
    main()
