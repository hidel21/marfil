import re
from datetime import date
from math import isfinite
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

import database as db
from database import (
    Producto,
    Venta,
    Pago,
    create_gasto,
    create_product,
    create_proveedor,
    init_db,
    load_available_products_dataframe,
    load_compras_dataframe,
    load_financial_metrics,
    load_excel_import_summary_dataframe,
    load_excel_sheet_dataframe,
    load_gastos_dataframe,
    load_gastos_total,
    load_inventory_dataframe,
    load_low_stock_products_dataframe,
    load_out_of_stock_demand_dataframe,
    load_payables_total,
    load_payment_metrics,
    load_payment_summary_dataframe,
    load_pending_accounts_dataframe,
    load_pending_collections_dataframe,
    load_pending_payables_dataframe,
    load_pending_sales_dataframe,
    load_product_margin_dataframe,
    load_proveedores_dataframe,
    load_recent_sales_dataframe,
    load_all_sales_dataframe,
    load_all_payments_dataframe,
    load_commission_dataframe,
    load_socios_dataframe,
    load_socios_investment_dataframe,
    load_top_clients_dataframe,
    load_top_products_dataframe,
    load_weekly_profitability_dataframe,
    register_payable_payment,
    register_payment,
    register_purchase,
    register_sale,
    save_inventory_changes,
    save_proveedor_changes,
    save_socio_changes,
    seed_default_socios,
    seed_sample_data,
    test_connection,
)
from services.pdf_generator import generar_recibo_pdf
from services.rates import format_currency, obtener_tasas_con_estado, obtener_todas_las_tasas

def render_metric_card(title: str, value: str, icon: str, _accent: str = "#7c3aed") -> None:
    st.metric(title, value, icon=icon, border=True)


# Los datos de pago salen de configuración, nunca del código: antes se enviaban los
# marcadores literales "V-XX.XXX.XXX" y "04XX-XXX-XXXX" a clientes reales.
# Se configuran en .streamlit/secrets.toml:
#
#   [datos_pago]
#   banco = "BNC (0191)"
#   documento = "V-12.345.678"
#   telefono = "0412-1234567"
#   titular = "Nombre del titular"     # opcional
DATOS_PAGO_REQUERIDOS = ("banco", "documento", "telefono")
DATOS_PAGO_OPCIONALES = ("titular",)
_PLACEHOLDER_RE = re.compile(r"X{2,}")

DATOS_PAGO_ETIQUETAS = {
    "banco": "Banco",
    "documento": "C.I./RIF",
    "telefono": "Teléfono",
    "titular": "Titular",
}


def obtener_datos_pago() -> tuple[dict[str, str], list[str]]:
    """Devuelve (datos, faltantes). Un valor con 'XX' cuenta como faltante."""
    try:
        seccion = st.secrets.get("datos_pago", {})
    except Exception:
        seccion = {}

    datos: dict[str, str] = {}
    for clave in DATOS_PAGO_REQUERIDOS + DATOS_PAGO_OPCIONALES:
        try:
            valor = seccion.get(clave, "")
        except Exception:
            valor = ""
        datos[clave] = str(valor or "").strip()

    faltantes = [
        DATOS_PAGO_ETIQUETAS[clave]
        for clave in DATOS_PAGO_REQUERIDOS
        if not datos[clave] or _PLACEHOLDER_RE.search(datos[clave].upper())
    ]
    return datos, faltantes


def build_datos_pago_block(datos: dict[str, str]) -> str:
    lineas = [f"- {DATOS_PAGO_ETIQUETAS[c]}: {datos[c]}" for c in DATOS_PAGO_REQUERIDOS]
    if datos.get("titular"):
        lineas.insert(0, f"- {DATOS_PAGO_ETIQUETAS['titular']}: {datos['titular']}")
    return "\n".join(lineas)


def build_whatsapp_message(
    cliente: str,
    producto: str,
    deuda_usd: float,
    tasa_bcv: float,
    datos_pago: dict[str, str],
) -> str:
    monto_bs = deuda_usd * tasa_bcv
    message = (
        f"Hola *{cliente}*, te saludamos de *SISTEMA MARFIL* 🍾.\n"
        f"Te recordamos que mantienes un saldo pendiente de *${deuda_usd:,.2f} USD* correspondiente a tu compra de *{producto}*.\n\n"
        f"📌 *Tasa BCV del día:* Bs. {tasa_bcv:,.2f}\n"
        f"📌 *Total en Bolívares:* Bs. {monto_bs:,.2f}\n\n"
        f"💳 *Datos de Pago Móvil:*\n"
        f"{build_datos_pago_block(datos_pago)}\n\n"
        "¡Agradecemos tu confirmación!"
    )
    return quote_plus(message)


def build_whatsapp_url(
    cliente: str,
    producto: str,
    deuda_usd: float,
    tasa_bcv: float,
    datos_pago: dict[str, str],
) -> str | None:
    """None cuando los datos de pago están incompletos: sin datos no se envía nada."""
    _, faltantes = obtener_datos_pago()
    if faltantes:
        return None
    encoded = build_whatsapp_message(cliente, producto, deuda_usd, tasa_bcv, datos_pago)
    return f"https://wa.me/?text={encoded}"


def get_csv_templates() -> dict[str, pd.DataFrame]:
    return {
        "📦 Productos / Inventario": pd.DataFrame(
            columns=[
                "Producto",
                "Costo ($)",
                "Precio (Divisa o tasa USDT)",
                "Precio tasa BCV",
                "Stock",
            ]
        ),
        "🛍️ Ventas Históricas": pd.DataFrame(
            columns=[
                "Fecha",
                "Producto",
                "Cliente",
                "Vendedor",
                "Cantidad",
                "Precio Venta ($)",
                "Costo ($)",
                "Ganancia ($)",
                "Moneda",
                "Deuda ($)",
                "Estatus",
            ]
        ),
        "💰 Historial de Pagos / Cuotas": pd.DataFrame(
            columns=[
                "Fecha de Pago",
                "Venta ID",
                "Cliente",
                "Producto",
                "Monto Bs",
                "Monto USD",
                "Referencia",
                "Tasa BCV",
                "Nro Cuota",
            ]
        ),
    }


def normalize_column_name(column: str) -> str:
    normalized = str(column).strip().lower()
    replacements = {
        "(": "",
        ")": "",
        "$": "",
        ",": "",
        ".": "",
        ":": "",
        "%": "",
        "-": "_",
        "/": "_",
        " ": "_",
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


COLUMN_FIELD_MAP = {
    "producto": "producto",
    "cliente": "cliente",
    "vendedor": "vendedor",
    "precio_venta": "precio_venta",
    "precio_venta_": "precio_venta",
    "precio_venta_dolares": "precio_venta",
    "precio_venta_usd": "precio_venta",
    "precio_divisa_o_tasa_usdt": "precio_divisa",
    "precio_divisa": "precio_divisa",
    "precio_tasa_bcv": "precio_bcv",
    "costo": "costo",
    "costo_": "costo",
    "ganancia": "ganancia",
    "ganancia_": "ganancia",
    "moneda": "moneda",
    "deuda": "deuda",
    "deuda_": "deuda",
    "cantidad": "cantidad",
    "fecha": "fecha",
    "fecha_de_pago": "fecha",
    "fecha_compra_si_es_bcv": "fecha_compra",
    "venta_id": "venta_id",
    "estatus": "estatus",
    "monto_pagado": "monto_pagado",
    "monto_pagado_": "monto_pagado",
    "monto_bs": "monto_bs",
    "monto_usd": "monto_usd",
    "referencia": "referencia",
    "tasa_bcv": "tasa_bcv",
    "tasa_venta_si_es_bcv": "tasa_bcv",
    "nro_cuota": "nro_cuota",
    "total_en_bs": "total_en_bs",
}


def parse_numeric_value(value: object) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    text = (
        text.replace("$", "")
        .replace("Bs.", "")
        .replace("bs.", "")
        .replace("Bs", "")
        .replace("bs", "")
        .replace("\u00a0", "")
        .replace(" ", "")
    )

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        integer, decimal = text.rsplit(",", 1)
        text = f"{integer.replace(',', '')}.{decimal}" if len(decimal) <= 2 else text.replace(",", "")
    elif text.count(".") > 1:
        integer, decimal = text.rsplit(".", 1)
        text = f"{integer.replace('.', '')}.{decimal}"
    elif "." in text:
        integer, decimal = text.rsplit(".", 1)
        if len(decimal) == 3:
            text = integer + decimal

    try:
        number = float(text)
        return number if isfinite(number) else None
    except ValueError:
        return None


def convert_csv_value(value: object, target_type: type[float] | type[int]):
    number = parse_numeric_value(value)
    if number is None:
        if pd.isna(value) or str(value).strip() == "":
            return None
        raise ValueError(f"Valor numérico inválido: {value!r}")
    if target_type is int:
        if not number.is_integer():
            raise ValueError(f"Se esperaba un número entero y se recibió: {value!r}")
        return int(number)
    return float(number)


def parse_csv_date(value: object) -> date:
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"Fecha inválida: {value!r}")
    return parsed.date()


def require_csv_text(value: object, field_name: str) -> str:
    if pd.isna(value):
        raise ValueError(f"El campo {field_name} es obligatorio.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"El campo {field_name} es obligatorio.")
    return text


def preprocess_uploaded_csv(uploaded_file) -> pd.DataFrame:
    for header_row in range(0, 6):
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, header=header_row, dtype=str)
        except Exception:
            continue

        normalized_columns = [normalize_column_name(col) for col in df.columns]
        if any(name in normalized_columns for name in ["producto", "cliente", "fecha", "monto_pagado", "venta_id"]):
            return df

    uploaded_file.seek(0)
    return pd.read_csv(uploaded_file, dtype=str)


def map_uploaded_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapped = {}
    for col in df.columns:
        normalized = normalize_column_name(col)
        mapped[col] = COLUMN_FIELD_MAP.get(normalized, normalized)

    mapped_names = list(mapped.values())
    duplicated = sorted({name for name in mapped_names if mapped_names.count(name) > 1})
    if duplicated:
        raise ValueError(f"Hay columnas duplicadas después de normalizar: {', '.join(duplicated)}.")

    df = df.rename(columns=mapped)

    drop_cols = [c for c in df.columns if c.startswith("unnamed") and df[c].isna().all()]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    if "" in df.columns:
        df = df.drop(columns=[""])

    return df


def prepare_import_dataframe(df: pd.DataFrame, entity: str) -> pd.DataFrame:
    df = map_uploaded_columns(df)

    if entity == "🛍️ Ventas Históricas":
        if "estatus" not in df.columns:
            df["estatus"] = "PENDIENTE"
        if "cantidad" not in df.columns:
            df["cantidad"] = 1
        if "deuda" not in df.columns:
            df["deuda"] = 0.0

    if entity == "💰 Historial de Pagos / Cuotas":
        if "nro_cuota" not in df.columns:
            df["nro_cuota"] = 1
        if "monto_bs" not in df.columns:
            df["monto_bs"] = None
        if "monto_usd" not in df.columns:
            df["monto_usd"] = None

        if "monto_pagado" in df.columns and "moneda" in df.columns:
            monto_bs = []
            monto_usd = []
            for idx, row in df.iterrows():
                monto_value = parse_numeric_value(row.get("monto_pagado"))
                total_en_bs_value = parse_numeric_value(row.get("total_en_bs"))
                tasa_value = parse_numeric_value(row.get("tasa_bcv"))
                moneda_value = str(row.get("moneda", "")).lower()
                if "usd" in moneda_value:
                    monto_usd.append(monto_value)
                    monto_bs.append(0.0)
                elif "bcv" in moneda_value or "bs" in moneda_value or "bolivar" in moneda_value:
                    bs_value = total_en_bs_value if total_en_bs_value is not None else monto_value
                    monto_bs.append(bs_value)
                    monto_usd.append(bs_value / tasa_value if bs_value is not None and tasa_value else None)
                else:
                    monto_bs.append(total_en_bs_value or 0.0)
                    monto_usd.append(monto_value)

            df["monto_bs"] = monto_bs
            df["monto_usd"] = monto_usd

        for idx, row in df.iterrows():
            monto_bs_value = parse_numeric_value(row.get("monto_bs"))
            monto_usd_value = parse_numeric_value(row.get("monto_usd"))
            tasa_value = parse_numeric_value(row.get("tasa_bcv"))
            if monto_usd_value is None and monto_bs_value is not None and tasa_value:
                df.at[idx, "monto_usd"] = monto_bs_value / tasa_value

    return df


def validate_csv_columns(df: pd.DataFrame, required_columns: list[str]) -> tuple[bool, list[str]]:
    missing = [col for col in required_columns if col not in df.columns]
    return len(missing) == 0, missing


def render_sidebar_metrics() -> tuple[float, float, float, float]:
    st.markdown("---")
    st.subheader("💱 Tasas de Cambio")
    rates, fallback_rates = obtener_tasas_con_estado()
    tasa_usd_bcv, tasa_eur_bcv, tasa_binance, tasa_usdt_com_ve = rates
    render_metric_card("💵 Dólar BCV", f"Bs. {tasa_usd_bcv:,.2f}", "💵", "#2563eb")
    render_metric_card("💶 Euro BCV", f"Bs. {tasa_eur_bcv:,.2f}", "💶", "#0e7490")
    render_metric_card("🟡 Binance USDT", f"Bs. {tasa_binance:,.2f}", "🟡", "#d97706")
    render_metric_card("🔵 USDT.com.ve mejor", f"Bs. {tasa_usdt_com_ve:,.2f}", "🔵", "#16a34a")

    if fallback_rates:
        st.warning(f"Sin actualización en vivo: {', '.join(fallback_rates)}. Se muestran valores de respaldo.")

    if st.button("🔄 Actualizar Tasas", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    return tasa_usd_bcv, tasa_eur_bcv, tasa_binance, tasa_usdt_com_ve


def render_sidebar_controls(rates: tuple[float, float, float, float]) -> None:
    st.markdown("---")
    tasa_usd_bcv, tasa_eur_bcv, tasa_binance, _ = rates
    with st.expander("🧮 Calculadora de Cobro Multimoneda"):
        monto_calc = st.number_input("Monto a cobrar", min_value=0.0, step=1.0, value=100.0)
        tipo_tasa = st.radio("Aplicar tasa", ["Dólar BCV", "Euro BCV", "Binance USDT"])
        tasa_aplicada = {
            "Dólar BCV": tasa_usd_bcv,
            "Euro BCV": tasa_eur_bcv,
            "Binance USDT": tasa_binance,
        }[tipo_tasa]
        monto_bs_cobrar = monto_calc * tasa_aplicada
        st.markdown(f"**Monto a transferir: {format_currency(monto_bs_cobrar)}**")

    st.markdown("---")
    if st.button("Inicializar base de datos", width="stretch"):
        try:
            init_db()
            st.success("Tablas creadas correctamente.")
        except Exception as exc:
            st.error(f"No se pudo inicializar la base de datos: {exc}")

    if st.button("Cargar datos de ejemplo", width="stretch"):
        try:
            seed_sample_data()
            st.success("Datos de ejemplo cargados.")
        except Exception as exc:
            st.error(f"No se pudo cargar datos de ejemplo: {exc}")


def render_sidebar_navigation() -> str:
    st.markdown("---")
    st.subheader("Navegación rápida")
    return st.radio(
        "Ir a",
        [
            "Sistema Marfil",
            "📲 Cobranza & WhatsApp",
            "📄 Recibos & Reportes",
            "📚 Datos migrados de Excel",
            "📥 Carga Masiva (CSV)",
        ],
        index=0,
        key="sidebar_nav",
    )


st.set_page_config(page_title="Sistema Marfil", page_icon="🌸", layout="wide")
st.title("🌸 Sistema Marfil MVP")
st.caption("Gestión de inventario, ventas y cobranza en cuotas")

with st.sidebar:
    sidebar_rates = render_sidebar_metrics()
    render_sidebar_controls(sidebar_rates)
    selected_section = render_sidebar_navigation()

if st.button("Probar conexión"):
    try:
        test_connection()
        st.success("Conexión a PostgreSQL OK")
    except Exception as exc:
        st.error(f"Error de conexión: {exc}")

st.divider()

if selected_section == "📲 Cobranza & WhatsApp":
    st.subheader("📲 Cobranza & WhatsApp")
    st.markdown(
        "Revisa el estado de cobro de clientes y genera recordatorios automáticos por WhatsApp con un solo click."
    )

    datos_pago, datos_pago_faltantes = obtener_datos_pago()
    if datos_pago_faltantes:
        st.warning(
            "No se pueden enviar recordatorios: faltan los datos de pago "
            f"({', '.join(datos_pago_faltantes)}). Cargalos en la sección "
            "`[datos_pago]` de `.streamlit/secrets.toml`.",
            icon="⚠️",
        )
    try:
        tasa_usd_bcv, _, _, _ = obtener_todas_las_tasas()
        cobranza_df = load_pending_collections_dataframe()
        if cobranza_df.empty:
            st.info("No hay ventas registradas para cobranza.")
        else:
            cobranza_df = cobranza_df.copy()
            cobranza_df["producto"] = cobranza_df["producto"].fillna("-")
            cobranza_df["deuda"] = cobranza_df["deuda"].astype(float)

            cobranza_df = cobranza_df[cobranza_df["deuda"] > 0]
            morosos_df = cobranza_df[cobranza_df["pagos_count"] == 0]
            abonos_df = cobranza_df[cobranza_df["pagos_count"] > 0]

            filter_option = st.radio(
                "Filtrar cobranza",
                ["Todos los Pendientes", "Sólo Morosos (Rojo)", "Con Abonos (Amarillo)"],
                horizontal=True,
            )

            if filter_option == "Sólo Morosos (Rojo)":
                display_df = morosos_df
            elif filter_option == "Con Abonos (Amarillo)":
                display_df = abonos_df
            else:
                display_df = cobranza_df

            col1, col2, col3 = st.columns(3)
            with col1:
                render_metric_card("Ventas Pendientes", f"{len(display_df)}", "⏳", "#fb7185")
            with col2:
                render_metric_card("Morosos (Rojo)", f"{len(morosos_df)}", "🔴", "#dc2626")
            with col3:
                render_metric_card("Con Abonos (Amarillo)", f"{len(abonos_df)}", "🟡", "#f59e0b")

            for _, row in display_df.iterrows():
                cliente = str(row["cliente"])
                producto = str(row["producto"])
                deuda = float(row["deuda"])
                pagos_count = int(row["pagos_count"])
                semaforo = row["semaforo"]
                total_bs = deuda * tasa_usd_bcv
                whatsapp_url = build_whatsapp_url(
                    cliente, producto, deuda, tasa_usd_bcv, datos_pago
                )

                with st.expander(f"{semaforo} — {cliente} • ${deuda:,.2f}", expanded=False):
                    st.markdown(
                        f"**Producto:** {producto}  \\"
                        f"**Deuda:** ${deuda:,.2f}  \\"
                        f"**Pagos Registrados:** {pagos_count}  \\"
                        f"**Total en Bolívares:** Bs. {total_bs:,.2f}"
                    )
                    if whatsapp_url:
                        st.link_button(
                            "📲 Enviar Recordatorio", whatsapp_url, width="stretch"
                        )
                    else:
                        st.button(
                            "📲 Enviar Recordatorio",
                            disabled=True,
                            width="stretch",
                            key=f"wa_bloqueado_{row.name}",
                            help="Cargá los datos de pago para poder enviar recordatorios.",
                        )
    except Exception as exc:
        st.error(f"No se pudo cargar el módulo de cobranza: {exc}")
elif selected_section == "📄 Recibos & Reportes":
    st.subheader("📄 Recibos & Reportes")
    st.markdown(
        "Genera comprobantes PDF por abono y exporta tus datos de inventario, ventas y pagos en CSV."
    )

    try:
        payments_df = load_all_payments_dataframe()
        if payments_df.empty:
            st.info("Aún no hay pagos registrados para generar recibos.")
        else:
            tab_recibos, tab_export = st.tabs(["Generador de Recibos", "Exportar Datos"])

            with tab_recibos:
                st.subheader("Historial de Abonos")
                st.dataframe(
                    payments_df[
                        ["id", "fecha", "cliente", "vendedor", "producto", "monto_bs", "monto_usd", "referencia", "nro_cuota", "saldo_usd", "estatus"]
                    ],
                    width="stretch",
                )

                for _, row in payments_df.iterrows():
                    with st.expander(
                        f"Pago {int(row['id'])} - {row['cliente']} - ${row['monto_usd']:,.2f}",
                        expanded=False,
                    ):
                        st.markdown(
                            f"**Cliente:** {row['cliente']}  \\"
                            f"**Vendedor:** {row['vendedor']}  \\"
                            f"**Producto:** {row['producto']}  \\"
                            f"**Monto abonado (Bs):** Bs. {row['monto_bs']:,.2f}  \\"
                            f"**Equivalente USD:** ${row['monto_usd']:,.2f}  \\"
                            f"**Saldo pendiente:** ${row['saldo_usd']:,.2f}  \\"
                            f"**Estatus:** {row['estatus']}"
                        )
                        pdf_bytes = generar_recibo_pdf(
                            {
                                "id": int(row["id"]),
                                "fecha": row["fecha"],
                                "cliente": row["cliente"],
                                "vendedor": row["vendedor"],
                                "producto": row["producto"],
                                "monto_bs": float(row["monto_bs"]),
                                "monto_usd": float(row["monto_usd"]),
                                "tasa_bcv": float(row["tasa_bcv"]),
                                "saldo_usd": float(row["saldo_usd"]),
                                "estatus": row["estatus"],
                            }
                        )
                        st.download_button(
                            "📄 Descargar Recibo PDF",
                            pdf_bytes,
                            file_name=f"Recibo_Pago_{int(row['id'])}.pdf",
                            mime="application/pdf",
                            width="stretch",
                        )

            with tab_export:
                st.subheader("Exportar Datos a CSV")

                inventario_df = load_inventory_dataframe()
                ventas_df = load_all_sales_dataframe()
                pagos_df = payments_df.copy()

                inventario_csv = inventario_df.to_csv(index=False).encode("utf-8")
                ventas_csv = ventas_df.to_csv(index=False).encode("utf-8")
                pagos_csv = pagos_df.to_csv(index=False).encode("utf-8")

                st.download_button(
                    "📥 Exportar Inventario",
                    inventario_csv,
                    file_name="inventario_marfil.csv",
                    mime="text/csv",
                    width="stretch",
                )
                st.download_button(
                    "📥 Exportar Historial de Ventas",
                    ventas_csv,
                    file_name="ventas_marfil.csv",
                    mime="text/csv",
                    width="stretch",
                )
                st.download_button(
                    "📥 Exportar Historial de Pagos",
                    pagos_csv,
                    file_name="pagos_marfil.csv",
                    mime="text/csv",
                    width="stretch",
                )
    except Exception as exc:
        st.error(f"No se pudo cargar el módulo de recibos y reportes: {exc}")
elif selected_section == "📚 Datos migrados de Excel":
    st.subheader("Datos migrados de Excel")
    st.caption("Consulta las pestañas originales preservadas durante cada migración.")
    try:
        import_summary = load_excel_import_summary_dataframe()
        if import_summary.empty:
            st.info("Aún no se ha migrado ningún libro de Excel.")
        else:
            latest_import_id = int(import_summary["importacion_id"].max())
            latest = import_summary[import_summary["importacion_id"] == latest_import_id]
            with st.container(horizontal=True):
                st.metric("Pestañas preservadas", int(latest["pestaña"].nunique()), border=True)
                st.metric("Filas con datos", int(latest["filas"].sum()), border=True)
                st.metric("Archivo", str(latest["archivo"].iloc[0]), border=True)

            selected_sheet = st.selectbox(
                "Pestaña del libro",
                latest["pestaña"].tolist(),
            )
            sheet_df = load_excel_sheet_dataframe(latest_import_id, selected_sheet)
            st.dataframe(sheet_df, hide_index=True, width="stretch")
    except Exception as exc:
        st.error(f"No se pudieron cargar los datos migrados: {exc}")
elif selected_section == "📥 Carga Masiva (CSV)":
    st.subheader("📥 Carga Masiva (CSV)")
    st.markdown(
        "Importa registros por lote desde archivos CSV para productos, ventas históricas y pagos/cuotas."
    )

    entity = st.selectbox(
        "Seleccionar entidad a importar",
        ["📦 Productos / Inventario", "🛍️ Ventas Históricas", "💰 Historial de Pagos / Cuotas"],
    )

    templates = get_csv_templates()
    template_df = templates.get(entity)
    if template_df is None:
        st.error("No se encontró la plantilla para la entidad seleccionada. Reinicia la app o selecciona otra opción.")
        templates = get_csv_templates()
        template_df = next(iter(templates.values()))

    st.markdown("**Descarga una plantilla de ejemplo**")
    template_cols = st.columns(3)
    for idx, (name, df_template) in enumerate(templates.items()):
        with template_cols[idx]:
            st.download_button(
                f"📄 {name}",
                df_template.to_csv(index=False).encode("utf-8"),
                file_name=f"plantilla_{name.replace(' ', '_').replace('/', '').lower()}.csv",
                mime="text/csv",
                width="stretch",
            )

    uploaded_file = st.file_uploader("Sube tu archivo CSV", type=["csv"])
    if uploaded_file is not None:
        try:
            csv_df = preprocess_uploaded_csv(uploaded_file)
            csv_df = prepare_import_dataframe(csv_df, entity)
            col1, col2 = st.columns(2)
            with col1:
                render_metric_card("Total de Filas", str(len(csv_df)), "📊", "#7c3aed")
            with col2:
                render_metric_card(
                    "Columnas Detectadas",
                    ", ".join(csv_df.columns.tolist()),
                    "🧾",
                    "#0f766e",
                )

            required_map = {
                "📦 Productos / Inventario": [
                    "producto",
                    "costo",
                    "precio_divisa",
                    "precio_bcv",
                    "stock",
                ],
                "🛍️ Ventas Históricas": [
                    "fecha",
                    "cliente",
                    "vendedor",
                    "producto",
                    "precio_venta",
                    "costo",
                    "ganancia",
                    "moneda",
                    "deuda",
                    "estatus",
                ],
                "💰 Historial de Pagos / Cuotas": [
                    "venta_id",
                    "fecha",
                    "cliente",
                    "producto",
                    "monto_bs",
                    "monto_usd",
                    "referencia",
                    "tasa_bcv",
                    "nro_cuota",
                ],
            }

            required_columns = required_map.get(entity, [])
            valid_columns, missing_columns = validate_csv_columns(csv_df, required_columns)
            if not valid_columns:
                st.error(
                    f"Faltan columnas obligatorias: {', '.join(missing_columns)}. Usa la plantilla de ejemplo para corregir el formato."
                )
            elif csv_df.empty:
                st.warning("El archivo no contiene filas para importar.")
            else:
                if st.button("🚀 Cargar Datos a la Base de Datos", width="stretch"):
                    session = db.get_session()
                    current_row = 1
                    try:
                        total_rows = len(csv_df)
                        progress = st.progress(0)
                        inserted = 0
                        for position, (_, row) in enumerate(csv_df.iterrows(), start=1):
                            current_row = position + 1
                            if entity == "📦 Productos / Inventario":
                                nombre = require_csv_text(row["producto"], "producto")
                                costo = convert_csv_value(row["costo"], float) or 0.0
                                precio_divisa = convert_csv_value(row["precio_divisa"], float) or 0.0
                                precio_bcv = convert_csv_value(row["precio_bcv"], float) or 0.0
                                stock = convert_csv_value(row["stock"], int) or 0
                                if min(costo, precio_divisa, precio_bcv, stock) < 0:
                                    raise ValueError("Los costos, precios y existencias no pueden ser negativos.")
                                producto = Producto(
                                    nombre=nombre,
                                    costo=costo,
                                    precio_divisa=precio_divisa,
                                    precio_bcv=precio_bcv,
                                    stock=stock,
                                )
                                session.add(producto)
                            elif entity == "🛍️ Ventas Históricas":
                                precio_venta = convert_csv_value(row["precio_venta"], float) or 0.0
                                costo = convert_csv_value(row["costo"], float) or 0.0
                                deuda = convert_csv_value(row["deuda"], float) or 0.0
                                cantidad = convert_csv_value(row.get("cantidad", 1), int) or 1
                                if min(precio_venta, costo, deuda) < 0 or cantidad <= 0:
                                    raise ValueError("Los importes no pueden ser negativos y la cantidad debe ser positiva.")
                                if deuda > precio_venta:
                                    raise ValueError("La deuda no puede superar el precio de venta.")
                                venta = Venta(
                                    fecha=parse_csv_date(row["fecha"]),
                                    cliente=require_csv_text(row["cliente"], "cliente"),
                                    vendedor=require_csv_text(row["vendedor"], "vendedor"),
                                    producto=require_csv_text(row["producto"], "producto"),
                                    cantidad=cantidad,
                                    precio_venta=precio_venta,
                                    costo=costo,
                                    ganancia=convert_csv_value(row["ganancia"], float) or 0.0,
                                    moneda=require_csv_text(row["moneda"], "moneda"),
                                    deuda=deuda,
                                    estatus=require_csv_text(row["estatus"], "estatus"),
                                    total=precio_venta,
                                )
                                session.add(venta)
                            else:
                                venta_id = convert_csv_value(row["venta_id"], int) or 0
                                monto_bs = convert_csv_value(row["monto_bs"], float) or 0.0
                                monto_usd = convert_csv_value(row["monto_usd"], float) or 0.0
                                tasa_bcv = convert_csv_value(row["tasa_bcv"], float) or 0.0
                                nro_cuota = convert_csv_value(row["nro_cuota"], int) or 1
                                if venta_id <= 0 or min(monto_bs, monto_usd) < 0 or monto_usd <= 0 or tasa_bcv <= 0:
                                    raise ValueError("Venta ID, monto USD y tasa BCV deben ser positivos; los montos no pueden ser negativos.")
                                if session.get(Venta, venta_id) is None:
                                    raise ValueError(f"No existe una venta con ID {venta_id}.")
                                pago = Pago(
                                    venta_id=venta_id,
                                    fecha=parse_csv_date(row["fecha"]),
                                    cliente=require_csv_text(row["cliente"], "cliente"),
                                    producto=require_csv_text(row["producto"], "producto"),
                                    monto_bs=monto_bs,
                                    monto_usd=monto_usd,
                                    referencia=require_csv_text(row["referencia"], "referencia"),
                                    tasa_bcv=tasa_bcv,
                                    nro_cuota=nro_cuota,
                                )
                                session.add(pago)

                            inserted += 1
                            if inserted % 25 == 0:
                                session.flush()
                            progress.progress(min(int((position / total_rows) * 100), 100))

                        session.commit()
                        st.success(f"✅ ¡Se cargaron {inserted} registros exitosamente en NeonDB!")
                        st.rerun()
                    except Exception as exc:
                        session.rollback()
                        st.error(f"Error al insertar datos en la fila {current_row}: {exc}")
                    finally:
                        session.close()
        except Exception as exc:
            st.error(f"No se pudo leer el archivo CSV: {exc}")
else:
    (
        productos_tab,
        ventas_tab,
        cuotas_tab,
        compras_tab,
        socios_tab,
        finanzas_tab,
        dashboard_tab,
    ) = st.tabs(
        [
            "📦 Productos & Stock",
            "🛍️ Registrar Venta",
            "💰 Registro de Cuotas (Hoja 6)",
            "🏭 Compras & Proveedores",
            "🤝 Socios & Inversión",
            "📈 Finanzas & Comisiones",
            "📊 Dashboard",
        ]
    )

if selected_section != "Sistema Marfil":
    st.stop()

with productos_tab:
    catalogo_tab, nuevo_producto_tab = st.tabs(["Catálogo e Inventario", "Agregar Nuevo Perfume"])

    with catalogo_tab:
        st.subheader("Catálogo e Inventario Interactivo")
        try:
            df = load_inventory_dataframe()
            if df.empty:
                st.info("Aún no hay productos registrados.")
            else:
                total_productos = int(df["id"].nunique())
                total_unidades = int(df["stock"].sum())
                valor_inventario = float((df["costo"] * df["stock"]).sum())

                col1, col2, col3 = st.columns(3)
                with col1:
                    render_metric_card("Total Productos Distintos", str(total_productos), "📦", "#7c3aed")
                with col2:
                    render_metric_card("Total Unidades en Stock", f"{total_unidades}", "📊", "#0f766e")
                with col3:
                    render_metric_card("Valor del Inventario a Costo ($)", f"{valor_inventario:,.2f}", "💵", "#ea580c")

                editor_df = st.data_editor(
                    df[
                        [
                            "id",
                            "nombre",
                            "categoria",
                            "costo",
                            "precio_divisa",
                            "precio_bcv",
                            "precio_original",
                            "precio_team",
                            "precio_revendedor",
                            "stock",
                        ]
                    ],
                    disabled=[
                        "id",
                        "nombre",
                        "categoria",
                        "precio_original",
                        "precio_team",
                        "precio_revendedor",
                    ],
                    width="stretch",
                    key="inventory_editor",
                )

                if st.button("Guardar Cambios de Inventario"):
                    try:
                        updated_rows = save_inventory_changes(editor_df)
                        if updated_rows:
                            st.success(f"Se actualizaron {updated_rows} producto(s) correctamente.")
                            st.rerun()
                        else:
                            st.info("No se detectaron cambios para guardar.")
                    except Exception as exc:
                        st.error(f"No se pudieron guardar los cambios: {exc}")
        except Exception as exc:
            st.error(f"No se pudo cargar el inventario: {exc}")

    with nuevo_producto_tab:
        st.subheader("Formulario para agregar nuevo perfume")
        with st.form("form_nuevo_producto", clear_on_submit=True):
            nombre = st.text_input("Nombre del producto")
            costo = st.number_input("Costo USDT", min_value=0.0, step=0.5)
            precio_divisa = st.number_input("Precio Divisa USD", min_value=0.0, step=0.5)
            precio_bcv = st.number_input("Precio BCV USD", min_value=0.0, step=0.5)
            stock_inicial = st.number_input("Stock Inicial", min_value=0, step=1)

            submitted = st.form_submit_button("Guardar Producto")
            if submitted:
                if not nombre.strip():
                    st.error("El nombre del producto es obligatorio.")
                else:
                    try:
                        create_product(
                            nombre=nombre.strip(),
                            costo=float(costo),
                            precio_divisa=float(precio_divisa),
                            precio_bcv=float(precio_bcv),
                            stock=int(stock_inicial),
                        )
                        st.success("Producto agregado correctamente.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo agregar el producto: {exc}")

with ventas_tab:
    st.subheader("Registrar Venta")

    try:
        productos_disponibles = load_available_products_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        productos_disponibles = None

    if productos_disponibles is None or productos_disponibles.empty:
        st.warning("No hay productos disponibles en inventario.")
    else:
        productos_disponibles["label"] = (
            productos_disponibles["nombre"] + " | stock: " + productos_disponibles["stock"].astype(str)
        )
        producto_options = productos_disponibles["label"].tolist()
        producto_map = dict(zip(productos_disponibles["label"], productos_disponibles.to_dict(orient="records")))

        with st.form("form_registro_venta", clear_on_submit=True):
            fecha = st.date_input("Fecha", value=date.today())
            cliente = st.text_input("Cliente", placeholder="Ingrese el nombre del cliente")
            vendedor = st.selectbox("Vendedor", options=["Gregory", "Hidelberg", "Otro"])
            producto_label = st.selectbox("Producto", options=producto_options)
            producto_info = producto_map[producto_label]

            cantidad = st.number_input(
                "Cantidad",
                min_value=1,
                max_value=int(producto_info["stock"]),
                step=1,
            )
            precio_bcv = float(producto_info["precio_bcv"] or 0)
            precio_divisa = float(producto_info["precio_divisa"] or 0)
            precio_sugerido = max(precio_bcv, precio_divisa) * cantidad
            precio_venta = st.number_input(
                "Precio de Venta (USD)",
                min_value=0.0,
                step=1.0,
                value=float(precio_sugerido),
            )
            deuda_inicial = st.number_input(
                "Deuda Inicial / Saldo Pendiente (USD)",
                min_value=0.0,
                step=1.0,
                value=float(precio_venta),
            )

            submitted = st.form_submit_button("Registrar Venta")
            if submitted:
                if not cliente.strip():
                    st.error("El nombre del cliente es obligatorio.")
                else:
                    try:
                        costo_unitario = float(producto_info["costo"] or 0)
                        costo_total = costo_unitario * cantidad
                        ganancia_neta = float(precio_venta) - costo_total
                        estatus = "YA PAGO" if deuda_inicial == 0 else "PENDIENTE"

                        register_sale(
                            fecha=fecha,
                            cliente=cliente.strip(),
                            vendedor=vendedor,
                            producto_nombre=producto_info["nombre"],
                            producto_id=int(producto_info["id"]),
                            cantidad=int(cantidad),
                            precio_venta=float(precio_venta),
                            costo_total=float(costo_total),
                            ganancia=float(ganancia_neta),
                            deuda=float(deuda_inicial),
                            estatus=estatus,
                        )
                        st.success("✅ Venta registrada y stock actualizado con éxito.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo registrar la venta: {exc}")

    st.divider()
    st.subheader("Historial Reciente de Ventas")
    try:
        historial = load_recent_sales_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        historial = None

    if historial is None or historial.empty:
        st.info("Aún no hay ventas registradas.")
    else:
        st.dataframe(historial, width="stretch")

with cuotas_tab:
    st.subheader("Registro de Cuotas y Abonos")

    try:
        ventas_pendientes = load_pending_sales_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        ventas_pendientes = None

    if ventas_pendientes is None or ventas_pendientes.empty:
        st.info("No hay ventas con deuda pendiente para registrar abonos.")
    else:
        ventas_pendientes["label"] = (
            "Cliente: "
            + ventas_pendientes["cliente"]
            + " | Producto: "
            + ventas_pendientes["producto"].fillna("-")
            + " | Deuda: $"
            + ventas_pendientes["deuda"].astype(str)
        )
        venta_options = ventas_pendientes["label"].tolist()
        venta_map = dict(zip(ventas_pendientes["label"], ventas_pendientes.to_dict(orient="records")))

        with st.form("form_registro_abono", clear_on_submit=True):
            fecha_pago = st.date_input("Fecha de Pago", value=date.today())
            venta_label = st.selectbox("Venta Activa", options=venta_options)
            venta_info = venta_map[venta_label]
            monto_bs = st.number_input("Monto en Bolívares (Bs)", min_value=0.0, step=10.0)
            referencia = st.text_input("Referencia Bancaria", placeholder="Ingrese el número o código")
            tasa_usd_bcv, _, _, _ = obtener_todas_las_tasas()
            tasa_bcv = st.number_input("Tasa BCV", min_value=0.0, step=0.1, value=float(tasa_usd_bcv))
            nro_cuota = st.selectbox("Bloque de Pago", options=[1, 2, 3], format_func=lambda value: f"Pago {value}")

            submitted = st.form_submit_button("Registrar Abono")
            if submitted:
                if monto_bs <= 0:
                    st.error("El monto en bolívares debe ser mayor a cero.")
                elif tasa_bcv <= 0:
                    st.error("La tasa BCV debe ser mayor a cero.")
                elif not referencia.strip():
                    st.error("La referencia bancaria es obligatoria.")
                else:
                    try:
                        monto_usd = float(monto_bs) / float(tasa_bcv)
                        nueva_deuda, estatus = register_payment(
                            venta_id=int(venta_info["id"]),
                            fecha=fecha_pago,
                            cliente=str(venta_info["cliente"]),
                            producto=str(venta_info["producto"]),
                            monto_bs=float(monto_bs),
                            monto_usd=float(monto_usd),
                            referencia=referencia.strip(),
                            tasa_bcv=float(tasa_bcv),
                            nro_cuota=int(nro_cuota),
                        )
                        st.success(
                            f"✅ Abono de Bs. {monto_bs:,.2f} (${monto_usd:,.2f}) registrado a {venta_info['cliente']}. Nueva deuda: ${nueva_deuda:,.2f}"
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo registrar el abono: {exc}")

    st.divider()
    st.subheader("Visualizador de Cobranza (Hoja 6)")

    try:
        total_bs, total_usd, completed_clients = load_payment_metrics()
        col1, col2, col3 = st.columns(3)
        with col1:
            render_metric_card("Total Recaudado en Bolívares (Bs)", f"{total_bs:,.2f}", "💳", "#2563eb")
        with col2:
            render_metric_card("Total Recaudado en Dólares ($)", f"{total_usd:,.2f}", "🌐", "#059669")
        with col3:
            render_metric_card("Clientes con Pago Completado", str(completed_clients), "✅", "#dc2626")
    except Exception as exc:
        st.warning(str(exc))

    try:
        payment_summary = load_payment_summary_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        payment_summary = None

    if payment_summary is None or payment_summary.empty:
        st.info("Aún no hay pagos registrados.")
    else:
        st.dataframe(payment_summary, width="stretch")

with compras_tab:
    st.subheader("🏭 Compras & Proveedores")

    proveedores_tab, registrar_compra_tab, cuentas_pagar_tab = st.tabs(
        ["Proveedores", "Registrar Compra", "Cuentas por Pagar"]
    )

    with proveedores_tab:
        st.markdown("Base de datos completa de proveedores.")
        with st.form("form_nuevo_proveedor", clear_on_submit=True):
            nombre_prov = st.text_input("Nombre del proveedor")
            contacto_prov = st.text_input("Persona de contacto")
            telefono_prov = st.text_input("Teléfono")
            email_prov = st.text_input("Email")
            notas_prov = st.text_area("Notas")
            submitted_prov = st.form_submit_button("Agregar Proveedor")
            if submitted_prov:
                if not nombre_prov.strip():
                    st.error("El nombre del proveedor es obligatorio.")
                else:
                    try:
                        create_proveedor(
                            nombre=nombre_prov,
                            contacto=contacto_prov,
                            telefono=telefono_prov,
                            email=email_prov,
                            notas=notas_prov,
                        )
                        st.success("Proveedor agregado correctamente.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo agregar el proveedor: {exc}")

        st.divider()
        try:
            proveedores_df = load_proveedores_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            proveedores_df = None

        if proveedores_df is None or proveedores_df.empty:
            st.info("Aún no hay proveedores registrados.")
        else:
            proveedores_editor_df = st.data_editor(
                proveedores_df,
                disabled=["id", "nombre"],
                column_order=["nombre", "contacto", "telefono", "email", "notas"],
                column_config={
                    "nombre": st.column_config.TextColumn("Proveedor"),
                    "contacto": st.column_config.TextColumn("Contacto"),
                    "telefono": st.column_config.TextColumn("Teléfono"),
                    "email": st.column_config.TextColumn("Email"),
                    "notas": st.column_config.TextColumn("Notas"),
                },
                width="stretch",
                key="proveedores_editor",
            )
            if st.button("Guardar Cambios de Proveedores"):
                try:
                    updated_rows = save_proveedor_changes(proveedores_editor_df)
                    if updated_rows:
                        st.success(f"Se actualizaron {updated_rows} proveedor(es) correctamente.")
                        st.rerun()
                    else:
                        st.info("No se detectaron cambios para guardar.")
                except Exception as exc:
                    st.error(f"No se pudieron guardar los cambios: {exc}")

    with registrar_compra_tab:
        st.markdown(
            "Registra una compra vinculada al catálogo de proveedores; el stock e inventario se actualizan automáticamente."
        )
        try:
            proveedores_df = load_proveedores_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            proveedores_df = None

        try:
            productos_df = load_inventory_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            productos_df = None

        if proveedores_df is None or proveedores_df.empty:
            st.warning("Registra al menos un proveedor antes de crear una compra.")
        elif productos_df is None or productos_df.empty:
            st.warning("Registra al menos un producto en el inventario antes de crear una compra.")
        else:
            proveedor_options = proveedores_df["nombre"].tolist()
            proveedor_map = dict(zip(proveedores_df["nombre"], proveedores_df.to_dict(orient="records")))
            producto_options = productos_df["nombre"].tolist()
            producto_map = dict(zip(productos_df["nombre"], productos_df.to_dict(orient="records")))

            with st.form("form_registro_compra", clear_on_submit=True):
                fecha_compra = st.date_input("Fecha", value=date.today())
                proveedor_nombre_sel = st.selectbox("Proveedor", options=proveedor_options)
                producto_nombre_sel = st.selectbox("Producto", options=producto_options)
                cantidad_compra = st.number_input("Cantidad", min_value=1, step=1, value=1)
                costo_unitario_compra = st.number_input(
                    "Costo Unitario ($)", min_value=0.0, step=0.5, value=0.0
                )
                monto_total_compra = float(costo_unitario_compra) * int(cantidad_compra)
                st.markdown(f"**Monto Total de la Compra: ${monto_total_compra:,.2f}**")
                monto_pagado_compra = st.number_input(
                    "Monto Pagado Ahora ($)",
                    min_value=0.0,
                    step=0.5,
                    value=float(monto_total_compra),
                )
                referencia_compra = st.text_input("Referencia / Nro. Factura")

                submitted_compra = st.form_submit_button("Registrar Compra")
                if submitted_compra:
                    try:
                        proveedor_info = proveedor_map[proveedor_nombre_sel]
                        producto_info = producto_map[producto_nombre_sel]
                        register_purchase(
                            fecha=fecha_compra,
                            proveedor_id=int(proveedor_info["id"]),
                            proveedor_nombre=str(proveedor_info["nombre"]),
                            producto_id=int(producto_info["id"]),
                            producto_nombre=str(producto_info["nombre"]),
                            cantidad=int(cantidad_compra),
                            costo_unitario=float(costo_unitario_compra),
                            monto_pagado=float(monto_pagado_compra),
                            referencia=referencia_compra,
                        )
                        st.success("✅ Compra registrada y stock actualizado con éxito.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo registrar la compra: {exc}")

        st.divider()
        st.subheader("Historial de Compras")
        try:
            compras_df = load_compras_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            compras_df = None

        if compras_df is None or compras_df.empty:
            st.info("Aún no hay compras registradas.")
        else:
            st.dataframe(
                compras_df,
                width="stretch",
                hide_index=True,
                column_order=[
                    "id",
                    "fecha",
                    "proveedor",
                    "producto",
                    "cantidad",
                    "costo_unitario",
                    "monto_total",
                    "monto_pagado",
                    "saldo",
                    "estatus",
                    "referencia",
                ],
                column_config={
                    "id": st.column_config.NumberColumn("N° Compra"),
                    "fecha": st.column_config.DateColumn("Fecha"),
                    "proveedor": st.column_config.TextColumn("Proveedor"),
                    "producto": st.column_config.TextColumn("Producto"),
                    "cantidad": st.column_config.NumberColumn("Cantidad"),
                    "costo_unitario": st.column_config.NumberColumn("Costo Unitario ($)", format="$%.2f"),
                    "monto_total": st.column_config.NumberColumn("Monto Total ($)", format="$%.2f"),
                    "monto_pagado": st.column_config.NumberColumn("Monto Pagado ($)", format="$%.2f"),
                    "saldo": st.column_config.NumberColumn("Saldo Pendiente ($)", format="$%.2f"),
                    "estatus": st.column_config.TextColumn("Estatus"),
                    "referencia": st.column_config.TextColumn("Referencia"),
                },
            )

    with cuentas_pagar_tab:
        st.markdown("Control global de cuentas por pagar a proveedores.")
        try:
            payables_df = load_pending_payables_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            payables_df = None

        if payables_df is None or payables_df.empty:
            st.success("🎉 No hay cuentas por pagar pendientes.")
        else:
            st.dataframe(
                payables_df,
                width="stretch",
                hide_index=True,
                column_order=["id", "fecha", "proveedor", "producto", "monto_total", "saldo", "estatus"],
                column_config={
                    "id": st.column_config.NumberColumn("N° Compra"),
                    "fecha": st.column_config.DateColumn("Fecha"),
                    "proveedor": st.column_config.TextColumn("Proveedor"),
                    "producto": st.column_config.TextColumn("Producto"),
                    "monto_total": st.column_config.NumberColumn("Monto Total ($)", format="$%.2f"),
                    "saldo": st.column_config.NumberColumn("Saldo Pendiente ($)", format="$%.2f"),
                    "estatus": st.column_config.TextColumn("Estatus"),
                },
            )

            payables_df["label"] = (
                "Compra #"
                + payables_df["id"].astype(str)
                + " | "
                + payables_df["proveedor"]
                + " | "
                + payables_df["producto"]
                + " | Saldo: $"
                + payables_df["saldo"].astype(str)
            )
            compra_options = payables_df["label"].tolist()
            compra_map = dict(zip(payables_df["label"], payables_df.to_dict(orient="records")))

            with st.form("form_abono_proveedor", clear_on_submit=True):
                fecha_abono = st.date_input("Fecha del Abono", value=date.today())
                compra_label = st.selectbox("Compra Pendiente", options=compra_options)
                compra_info = compra_map[compra_label]
                monto_abono = st.number_input("Monto a Abonar ($)", min_value=0.0, step=1.0)
                referencia_abono = st.text_input("Referencia")

                submitted_abono = st.form_submit_button("Registrar Abono a Proveedor")
                if submitted_abono:
                    try:
                        nuevo_saldo, estatus = register_payable_payment(
                            compra_id=int(compra_info["id"]),
                            fecha=fecha_abono,
                            monto=float(monto_abono),
                            referencia=referencia_abono,
                        )
                        st.success(
                            f"✅ Abono de ${monto_abono:,.2f} registrado a {compra_info['proveedor']}. Nuevo saldo: ${nuevo_saldo:,.2f}"
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo registrar el abono: {exc}")

with socios_tab:
    st.subheader("🤝 Socios & Inversión")
    st.markdown(
        "Indicadores de inversión individual por socio: capital aportado, % de participación y retorno (ROI) sobre la utilidad neta real."
    )

    try:
        socios_df = load_socios_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        socios_df = None

    if socios_df is None or socios_df.empty:
        st.info("Aún no hay socios registrados. Usa 'Inicializar base de datos' en la barra lateral para cargarlos.")
    else:
        st.markdown("**Capital aportado por socio**")
        socios_editor_df = st.data_editor(
            socios_df,
            disabled=["id", "nombre"],
            column_order=["nombre", "capital_invertido"],
            column_config={
                "nombre": st.column_config.TextColumn("Socio"),
                "capital_invertido": st.column_config.NumberColumn(
                    "Capital Invertido ($)", format="$%.2f", min_value=0.0, step=1.0
                ),
            },
            width="stretch",
            key="socios_editor",
        )
        if st.button("Guardar Capital de Socios"):
            try:
                updated_rows = save_socio_changes(socios_editor_df)
                if updated_rows:
                    st.success(f"Se actualizó el capital de {updated_rows} socio(s) correctamente.")
                    st.rerun()
                else:
                    st.info("No se detectaron cambios para guardar.")
            except Exception as exc:
                st.error(f"No se pudieron guardar los cambios: {exc}")

        st.divider()
        try:
            inversion_df = load_socios_investment_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            inversion_df = None

        if inversion_df is None or inversion_df.empty:
            st.info("Registra el capital invertido de al menos un socio para ver los indicadores.")
        else:
            st.dataframe(
                inversion_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "socio": st.column_config.TextColumn("Socio"),
                    "capital_invertido": st.column_config.NumberColumn("Capital Invertido ($)", format="$%.2f"),
                    "participacion_pct": st.column_config.NumberColumn("Participación (%)", format="%.1f%%"),
                    "ganancia_atribuida": st.column_config.NumberColumn("Ganancia Atribuida ($)", format="$%.2f"),
                    "roi_pct": st.column_config.NumberColumn("ROI (%)", format="%.1f%%"),
                },
            )

with finanzas_tab:
    st.subheader("📈 Finanzas & Comisiones")
    try:
        (
            total_revenue,
            total_cost,
            total_profit,
            total_debt,
            total_collected_usd,
            total_collected_bs,
            total_gastos,
            utilidad_neta_real,
        ) = load_financial_metrics()

        margin = (total_profit / total_revenue * 100) if total_revenue else 0.0
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            render_metric_card("Ingresos Totales ($)", f"${total_revenue:,.2f}", "💰", "#2563eb")
        with col2:
            render_metric_card("Costo Total ($)", f"${total_cost:,.2f}", "📉", "#dc2626")
        with col3:
            render_metric_card("Ganancia Bruta ($)", f"${total_profit:,.2f}", "📈", "#16a34a")
        with col4:
            render_metric_card("Margen Bruto", f"{margin:.1f}%", "🧾", "#7c3aed")

        col5, col6 = st.columns(2)
        with col5:
            render_metric_card("Cobrado en USD", f"${total_collected_usd:,.2f}", "🌐", "#059669")
        with col6:
            render_metric_card("Cobrado en Bs", f"Bs. {total_collected_bs:,.2f}", "💵", "#f59e0b")

        st.divider()
        st.subheader("🔎 Estado de deudas y comisiones")
        st.markdown(
            "Las métricas siguientes reflejan el flujo de ventas, costos, ganancia y comisión estimada al 10% sobre ganancia neta."
        )

        commission_df = load_commission_dataframe(commission_rate=0.1)
        if commission_df.empty:
            st.info("Aún no hay datos de ventas para calcular comisiones.")
        else:
            st.dataframe(commission_df, width="stretch")

        st.divider()
        st.subheader("Ventas Totales y Deuda")
        try:
            ventas_df = load_all_sales_dataframe()
            if ventas_df.empty:
                st.info("No hay ventas registradas aún.")
            else:
                st.dataframe(ventas_df, width="stretch")
        except Exception as exc:
            st.warning(str(exc))

        st.divider()
        st.subheader("📅 Rentabilidad Semanal")
        st.markdown("Semanas con mayor ganancia neta generada por las ventas.")
        try:
            semanal_df = load_weekly_profitability_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            semanal_df = None

        if semanal_df is None or semanal_df.empty:
            st.info("Aún no hay ventas suficientes para calcular la rentabilidad semanal.")
        else:
            top_semana = semanal_df.iloc[0]
            render_metric_card(
                "Semana más rentable",
                f"{top_semana['semana']} · ${top_semana['ganancia_total']:,.2f}",
                "🏆",
                "#16a34a",
            )
            st.dataframe(
                semanal_df,
                width="stretch",
                hide_index=True,
                column_order=["semana", "inicio_semana", "ganancia_total"],
                column_config={
                    "semana": st.column_config.TextColumn("Semana"),
                    "inicio_semana": st.column_config.DateColumn("Inicio de Semana"),
                    "ganancia_total": st.column_config.NumberColumn("Ganancia Total ($)", format="$%.2f"),
                },
            )
            chart_semanal = semanal_df.sort_values("inicio_semana")
            st.bar_chart(chart_semanal.set_index("semana")["ganancia_total"])

        st.divider()
        st.subheader("🧾 Margen de Ganancia por Producto")
        st.markdown("Costo vs. Precio de Venta vs. Ganancia neta, agregado por producto.")
        try:
            margen_df = load_product_margin_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            margen_df = None

        if margen_df is None or margen_df.empty:
            st.info("Aún no hay ventas registradas para calcular márgenes por producto.")
        else:
            st.dataframe(
                margen_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "producto": st.column_config.TextColumn("Producto"),
                    "unidades_vendidas": st.column_config.NumberColumn("Unidades Vendidas"),
                    "costo_total": st.column_config.NumberColumn("Costo Total ($)", format="$%.2f"),
                    "ingresos_total": st.column_config.NumberColumn("Precio de Venta Total ($)", format="$%.2f"),
                    "ganancia_total": st.column_config.NumberColumn("Ganancia Neta ($)", format="$%.2f"),
                    "margen_pct": st.column_config.NumberColumn("Margen (%)", format="%.1f%%"),
                },
            )

        st.divider()
        st.subheader("💼 Control Financiero Global")
        st.markdown("Cuentas por cobrar, cuentas por pagar, gastos generales y utilidad neta real del negocio.")
        try:
            total_por_pagar = load_payables_total()
        except Exception as exc:
            st.warning(str(exc))
            total_por_pagar = 0.0

        col7, col8, col9, col10 = st.columns(4)
        with col7:
            render_metric_card("Cuentas por Cobrar ($)", f"${total_debt:,.2f}", "⏳", "#dc2626")
        with col8:
            render_metric_card("Cuentas por Pagar ($)", f"${total_por_pagar:,.2f}", "🏭", "#ea580c")
        with col9:
            render_metric_card("Gastos Generales ($)", f"${total_gastos:,.2f}", "🧾", "#7c3aed")
        with col10:
            render_metric_card("Utilidad Neta Real ($)", f"${utilidad_neta_real:,.2f}", "✅", "#059669")

        with st.expander("➕ Registrar Gasto General"):
            with st.form("form_nuevo_gasto", clear_on_submit=True):
                fecha_gasto = st.date_input("Fecha", value=date.today(), key="fecha_gasto")
                categoria_gasto = st.text_input("Categoría", placeholder="Alquiler, servicios, transporte...")
                descripcion_gasto = st.text_input("Descripción")
                monto_gasto = st.number_input("Monto ($)", min_value=0.0, step=1.0)
                submitted_gasto = st.form_submit_button("Registrar Gasto")
                if submitted_gasto:
                    try:
                        create_gasto(
                            fecha=fecha_gasto,
                            categoria=categoria_gasto,
                            descripcion=descripcion_gasto,
                            monto=float(monto_gasto),
                        )
                        st.success("✅ Gasto registrado correctamente.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo registrar el gasto: {exc}")

        try:
            gastos_df = load_gastos_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            gastos_df = None

        if gastos_df is None or gastos_df.empty:
            st.info("Aún no hay gastos generales registrados.")
        else:
            st.dataframe(
                gastos_df,
                width="stretch",
                hide_index=True,
                column_order=["fecha", "categoria", "descripcion", "monto"],
                column_config={
                    "fecha": st.column_config.DateColumn("Fecha"),
                    "categoria": st.column_config.TextColumn("Categoría"),
                    "descripcion": st.column_config.TextColumn("Descripción"),
                    "monto": st.column_config.NumberColumn("Monto ($)", format="$%.2f"),
                },
            )
    except Exception as exc:
        st.error(f"No se pudo cargar el módulo financiero: {exc}")

with dashboard_tab:
    st.subheader("Resumen General del Negocio")

    try:
        total_bs, total_usd, total_ventas, total_por_cobrar = db.load_dashboard_metrics()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            render_metric_card("Total Recaudado en Bs", f"Bs. {total_bs:,.2f}", "💵", "#2563eb")
        with col2:
            render_metric_card("Total Recaudado en $", f"${total_usd:,.2f}", "🌐", "#059669")
        with col3:
            render_metric_card("Total Ventas en $", f"${total_ventas:,.2f}", "🛍️", "#7c3aed")
        with col4:
            render_metric_card("Total Por Cobrar en $", f"${total_por_cobrar:,.2f}", "⏳", "#dc2626")
    except Exception as exc:
        st.warning(str(exc))

    st.divider()
    st.subheader("🏆 Producto Más Vendido y Clientes Top")
    col_top1, col_top2 = st.columns(2)
    with col_top1:
        st.caption("Ranking de productos por unidades vendidas")
        try:
            top_productos_df = load_top_products_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            top_productos_df = None
        if top_productos_df is None or top_productos_df.empty:
            st.info("Aún no hay ventas registradas.")
        else:
            st.dataframe(
                top_productos_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "producto": st.column_config.TextColumn("Producto"),
                    "unidades_vendidas": st.column_config.NumberColumn("Unidades Vendidas"),
                    "ingresos_total": st.column_config.NumberColumn("Ingresos Totales ($)", format="$%.2f"),
                },
            )
    with col_top2:
        st.caption("Ranking de clientes por total comprado")
        try:
            top_clientes_df = load_top_clients_dataframe()
        except Exception as exc:
            st.warning(str(exc))
            top_clientes_df = None
        if top_clientes_df is None or top_clientes_df.empty:
            st.info("Aún no hay ventas registradas.")
        else:
            st.dataframe(
                top_clientes_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "cliente": st.column_config.TextColumn("Cliente"),
                    "compras_realizadas": st.column_config.NumberColumn("Compras Realizadas"),
                    "total_comprado": st.column_config.NumberColumn("Total Comprado ($)", format="$%.2f"),
                },
            )

    st.divider()
    st.subheader("🚨 Cuentas por Cobrar / Clientes Pendientes")
    try:
        cuentas_pendientes = db.load_pending_accounts_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        cuentas_pendientes = None

    if cuentas_pendientes is None or cuentas_pendientes.empty:
        st.success("🎉 ¡Excelente! No hay cuentas pendientes por cobrar.")
    else:
        ranking_deuda = cuentas_pendientes.sort_values("deuda", ascending=False).reset_index(drop=True)
        ranking_deuda.insert(0, "ranking", ranking_deuda.index + 1)
        st.caption("Ranking completo de clientes con saldo pendiente de pago")
        st.dataframe(
            ranking_deuda[["ranking", "fecha", "cliente", "vendedor", "producto", "precio_venta", "deuda", "estatus"]],
            width="stretch",
            hide_index=True,
            column_config={
                "ranking": st.column_config.NumberColumn("#"),
                "fecha": st.column_config.DateColumn("Fecha"),
                "cliente": st.column_config.TextColumn("Cliente"),
                "vendedor": st.column_config.TextColumn("Vendedor"),
                "producto": st.column_config.TextColumn("Producto"),
                "precio_venta": st.column_config.NumberColumn("Precio de Venta ($)", format="$%.2f"),
                "deuda": st.column_config.NumberColumn("Saldo Pendiente ($)", format="$%.2f"),
                "estatus": st.column_config.TextColumn("Estatus"),
            },
        )

        chart_pending = cuentas_pendientes[["cliente", "deuda"]].copy()
        chart_pending = chart_pending.sort_values("deuda", ascending=False).head(8)
        st.caption("Top de clientes con mayor saldo pendiente")
        st.bar_chart(chart_pending.set_index("cliente")["deuda"])

    st.divider()
    st.subheader("⚠️ Perfumes con Stock Bajo (≤ 2 unidades)")
    try:
        stock_critico = db.load_low_stock_products_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        stock_critico = None

    if stock_critico is None or stock_critico.empty:
        st.info("No hay perfumes con stock crítico en este momento.")
    else:
        st.dataframe(stock_critico, width="stretch")

        chart_stock = stock_critico[["nombre", "stock"]].copy()
        chart_stock = chart_stock.sort_values("stock", ascending=True)
        st.caption("Stock actual de perfumes bajo control")
        st.bar_chart(chart_stock.set_index("nombre")["stock"])

    st.divider()
    st.subheader("🔔 Productos Agotados con Mayor Demanda")
    st.markdown("Productos sin stock (0 unidades), ordenados por demanda histórica — prioriza el reabastecimiento.")
    try:
        agotados_df = load_out_of_stock_demand_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        agotados_df = None

    if agotados_df is None or agotados_df.empty:
        st.success("🎉 No hay productos agotados en este momento.")
    else:
        st.dataframe(
            agotados_df,
            width="stretch",
            hide_index=True,
            column_config={
                "nombre": st.column_config.TextColumn("Producto"),
                "demanda_historica": st.column_config.NumberColumn("Demanda Histórica (unidades)"),
            },
        )

    st.divider()
    st.subheader("⚡ Accesos rápidos")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Registrar una venta nueva", width="stretch"):
            st.info("Dirígete a la pestaña 🛍️ Registrar Venta para crear una venta nueva.")
    with col2:
        if st.button("Cargar un pago rápido", width="stretch"):
            st.info("Dirígete a la pestaña 💰 Registro de Cuotas para registrar un abono o pago.")
