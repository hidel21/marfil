from datetime import date
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

import database as db
from database import (
    Producto,
    Venta,
    Pago,
    create_product,
    init_db,
    load_available_products_dataframe,
    load_financial_metrics,
    load_inventory_dataframe,
    load_low_stock_products_dataframe,
    load_payment_metrics,
    load_payment_summary_dataframe,
    load_pending_accounts_dataframe,
    load_pending_collections_dataframe,
    load_pending_sales_dataframe,
    load_recent_sales_dataframe,
    load_all_sales_dataframe,
    load_all_payments_dataframe,
    load_commission_dataframe,
    register_payment,
    register_sale,
    save_inventory_changes,
    seed_sample_data,
    test_connection,
)
from services.pdf_generator import generar_recibo_pdf
from services.rates import format_currency, obtener_todas_las_tasas

def render_metric_card(title: str, value: str, icon: str, accent: str = "#7c3aed") -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-card-title">{icon} {title}</div>
            <div class="metric-card-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_whatsapp_message(cliente: str, producto: str, deuda_usd: float, tasa_bcv: float) -> str:
    monto_bs = deuda_usd * tasa_bcv
    message = (
        f"Hola *{cliente}*, te saludamos de *SISTEMA MARFIL* 🍾.\n"
        f"Te recordamos que mantienes un saldo pendiente de *${deuda_usd:,.2f} USD* correspondiente a tu compra de *{producto}*.\n\n"
        f"📌 *Tasa BCV del día:* Bs. {tasa_bcv:,.2f}\n"
        f"📌 *Total en Bolívares:* Bs. {monto_bs:,.2f}\n\n"
        f"💳 *Datos de Pago Móvil BNC:*\n"
        f"- Banco: BNC (0191)\n"
        f"- C.I.: V-XX.XXX.XXX\n"
        f"- Teléfono: 04XX-XXX-XXXX\n\n"
        "¡Agradecemos tu confirmación!"
    )
    return quote_plus(message)


def build_whatsapp_url(cliente: str, producto: str, deuda_usd: float, tasa_bcv: float) -> str:
    encoded = build_whatsapp_message(cliente, producto, deuda_usd, tasa_bcv)
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
                "Producto",
                "Cliente",
                "Vendedor",
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
                "Cliente",
                "Producto",
                "Monto Pagado ($)",
                "Moneda",
                "Fecha Compra (Si es BCV)",
                "Tasa Venta (Si es BCV)",
                "Total en Bs",
                "Referencia",
                "Nro Cuota",
                "Venta ID",
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
    "precio_venta_": "precio_venta",
    "precio_divisa_o_tasa_usdt": "precio_divisa",
    "precio_divisa": "precio_divisa",
    "precio_tasa_bcv": "precio_bcv",
    "costo": "costo",
    "costo_": "costo",
    "ganancia": "ganancia",
    "moneda": "moneda",
    "deuda": "deuda",
    "deuda_": "deuda",
    "fecha": "fecha",
    "fecha_de_pago": "fecha",
    "fecha_compra_si_es_bcv": "fecha",
    "venta_id": "venta_id",
    "estatus": "estatus",
    "monto_pagado": "monto_pagado",
    "monto_pagado_": "monto_pagado",
    "monto_bs": "monto_bs",
    "monto_usd": "monto_usd",
    "referencia": "referencia",
    "tasa_bcv": "tasa_bcv",
    "nro_cuota": "nro_cuota",
    "total_en_bs": "total_en_bs",
}


def parse_numeric_value(value: object) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    text = text.replace("$", "").replace("Bs", "").replace("bs", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


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
    df = df.rename(columns=mapped)

    drop_cols = [c for c in df.columns if c.startswith("unnamed") and df[c].isna().all()]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    if "" in df.columns:
        df = df.drop(columns=[""])

    return df


def prepare_import_dataframe(df: pd.DataFrame, entity: str) -> pd.DataFrame:
    df = map_uploaded_columns(df)

    if entity == "📦 Productos / Inventario":
        if "stock" not in df.columns:
            df["stock"] = 0
        if "precio_divisa" not in df.columns:
            df["precio_divisa"] = 0.0
        if "precio_bcv" not in df.columns:
            df["precio_bcv"] = 0.0
        if "costo" not in df.columns:
            df["costo"] = 0.0

    if entity == "🛍️ Ventas Históricas":
        if "estatus" not in df.columns:
            df["estatus"] = "PENDIENTE"
        if "cantidad" not in df.columns:
            df["cantidad"] = 1
        if "deuda" not in df.columns:
            df["deuda"] = 0.0

    if entity == "💰 Historial de Pagos / Cuotas":
        if "venta_id" not in df.columns:
            df["venta_id"] = 0
        if "referencia" not in df.columns:
            df["referencia"] = ""
        if "tasa_bcv" not in df.columns:
            df["tasa_bcv"] = 0.0
        if "nro_cuota" not in df.columns:
            df["nro_cuota"] = 1
        if "monto_bs" not in df.columns:
            df["monto_bs"] = None
        if "monto_usd" not in df.columns:
            df["monto_usd"] = None

        if "monto_pagado" in df.columns and "moneda" in df.columns:
            monto_bs = []
            monto_usd = []
            moneda_values = df["moneda"].fillna("").astype(str).str.lower()
            for idx, row in df.iterrows():
                monto_value = parse_numeric_value(row.get("monto_pagado"))
                total_en_bs_value = parse_numeric_value(row.get("total_en_bs"))
                if "usd" in moneda_values.iloc[idx]:
                    monto_usd.append(monto_value)
                    monto_bs.append(None)
                elif "bcv" in moneda_values.iloc[idx] or "bs" in moneda_values.iloc[idx] or "bolivar" in moneda_values.iloc[idx]:
                    monto_bs.append(total_en_bs_value if total_en_bs_value is not None else monto_value)
                    monto_usd.append(None)
                else:
                    monto_bs.append(total_en_bs_value if total_en_bs_value is not None else monto_value)
                    monto_usd.append(monto_value)

            df["monto_bs"] = monto_bs
            df["monto_usd"] = monto_usd

    return df


def validate_csv_columns(df: pd.DataFrame, required_columns: list[str]) -> tuple[bool, list[str]]:
    missing = [col for col in required_columns if col not in df.columns]
    return len(missing) == 0, missing


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
            /* Forzar fondo oscuro y texto legible en las métricas del Sidebar */
            [data-testid="stMetric"] {
                background-color: #1E293B !important;
                border: 1px solid #334155 !important;
                border-radius: 8px !important;
                padding: 15px !important;
            }
            [data-testid="stMetricValue"] {
                color: #10B981 !important;
                font-size: 1.4rem !important;
                font-weight: bold !important;
            }
            [data-testid="stMetricLabel"] {
                color: #F8FAFC !important;
                font-weight: 600 !important;
            }
            .st-emotion-cache-1jicfl2 { padding: 2rem 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_metrics() -> tuple[float, float, float, float]:
    st.markdown("---")
    st.subheader("💱 Tasas de Cambio")
    tasa_usd_bcv, tasa_eur_bcv, tasa_binance, tasa_usdt_com_ve = obtener_todas_las_tasas()
    render_metric_card("💵 Dólar BCV", f"Bs. {tasa_usd_bcv:,.2f}", "💵", "#2563eb")
    render_metric_card("💶 Euro BCV", f"Bs. {tasa_eur_bcv:,.2f}", "💶", "#0e7490")
    render_metric_card("🟡 Binance USDT", f"Bs. {tasa_binance:,.2f}", "🟡", "#d97706")
    render_metric_card("🔵 USDT.com.ve mejor", f"Bs. {tasa_usdt_com_ve:,.2f}", "🔵", "#16a34a")

    if st.button("🔄 Actualizar Tasas", use_container_width=True):
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
    if st.button("Inicializar base de datos", use_container_width=True):
        try:
            init_db()
            st.success("Tablas creadas correctamente.")
        except Exception as exc:
            st.error(f"No se pudo inicializar la base de datos: {exc}")

    if st.button("Cargar datos de ejemplo", use_container_width=True):
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
            "📥 Carga Masiva (CSV)",
        ],
        index=0,
        key="sidebar_nav",
    )


st.set_page_config(page_title="Sistema Marfil", page_icon="🌸", layout="wide")
inject_global_styles()
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
                whatsapp_url = build_whatsapp_url(cliente, producto, deuda, tasa_usd_bcv)

                with st.expander(f"{semaforo} — {cliente} • ${deuda:,.2f}", expanded=False):
                    st.markdown(
                        f"**Producto:** {producto}  \\"
                        f"**Deuda:** ${deuda:,.2f}  \\"
                        f"**Pagos Registrados:** {pagos_count}  \\"
                        f"**Total en Bolívares:** Bs. {total_bs:,.2f}"
                    )
                    st.link_button("📲 Enviar Recordatorio", whatsapp_url, use_container_width=True)
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
                    use_container_width=True,
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
                            use_container_width=True,
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
                    use_container_width=True,
                )
                st.download_button(
                    "📥 Exportar Historial de Ventas",
                    ventas_csv,
                    file_name="ventas_marfil.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                st.download_button(
                    "📥 Exportar Historial de Pagos",
                    pagos_csv,
                    file_name="pagos_marfil.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
    except Exception as exc:
        st.error(f"No se pudo cargar el módulo de recibos y reportes: {exc}")
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
    template_df = templates[entity]

    st.markdown("**Descarga una plantilla de ejemplo**")
    template_cols = st.columns(3)
    for idx, (name, df_template) in enumerate(templates.items()):
        with template_cols[idx]:
            st.download_button(
                f"📄 {name}",
                df_template.to_csv(index=False).encode("utf-8"),
                file_name=f"plantilla_{name.replace(' ', '_').replace('/', '').lower()}.csv",
                mime="text/csv",
                use_container_width=True,
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
                    "nombre",
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

            required_columns = required_map[entity]
            valid_columns, missing_columns = validate_csv_columns(csv_df, required_columns)
            if not valid_columns:
                st.error(
                    f"Faltan columnas obligatorias: {', '.join(missing_columns)}. Usa la plantilla de ejemplo para corregir el formato."
                )
            else:
                if st.button("🚀 Cargar Datos a la Base de Datos", use_container_width=True):
                    session = db.get_session()
                    try:
                        total_rows = len(csv_df)
                        progress = st.progress(0)
                        inserted = 0
                        for idx, row in csv_df.iterrows():
                            if entity == "📦 Productos / Inventario":
                                producto = Producto(
                                    nombre=str(row["nombre"]).strip(),
                                    costo=convert_csv_value(row["costo"], float) or 0.0,
                                    precio_divisa=convert_csv_value(row["precio_divisa"], float) or 0.0,
                                    precio_bcv=convert_csv_value(row["precio_bcv"], float) or 0.0,
                                    stock=convert_csv_value(row["stock"], int) or 0,
                                )
                                session.add(producto)
                            elif entity == "🛍️ Ventas Históricas":
                                fecha = pd.to_datetime(row["fecha"], errors="coerce")
                                venta = Venta(
                                    fecha=fecha.date() if not pd.isna(fecha) else date.today(),
                                    cliente=str(row["cliente"]).strip(),
                                    vendedor=str(row["vendedor"]).strip(),
                                    producto=str(row["producto"]).strip(),
                                    cantidad=convert_csv_value(row.get("cantidad", 1), int) or 1,
                                    precio_venta=convert_csv_value(row["precio_venta"], float) or 0.0,
                                    costo=convert_csv_value(row["costo"], float) or 0.0,
                                    ganancia=convert_csv_value(row["ganancia"], float) or 0.0,
                                    moneda=str(row["moneda"]).strip(),
                                    deuda=convert_csv_value(row["deuda"], float) or 0.0,
                                    estatus=str(row["estatus"]).strip(),
                                    total=convert_csv_value(row["precio_venta"], float) or 0.0,
                                )
                                session.add(venta)
                            else:
                                fecha = pd.to_datetime(row["fecha"], errors="coerce")
                                pago = Pago(
                                    venta_id=convert_csv_value(row["venta_id"], int) or 0,
                                    fecha=fecha.date() if not pd.isna(fecha) else date.today(),
                                    cliente=str(row["cliente"]).strip(),
                                    producto=str(row["producto"]).strip(),
                                    monto_bs=convert_csv_value(row["monto_bs"], float) or 0.0,
                                    monto_usd=convert_csv_value(row["monto_usd"], float) or 0.0,
                                    referencia=str(row["referencia"]).strip(),
                                    tasa_bcv=convert_csv_value(row["tasa_bcv"], float) or 0.0,
                                    nro_cuota=convert_csv_value(row["nro_cuota"], int) or 1,
                                )
                                session.add(pago)

                            inserted += 1
                            if inserted % 25 == 0:
                                session.flush()
                            progress.progress(min(int(((idx + 1) / total_rows) * 100), 100))

                        session.commit()
                        st.success(f"✅ ¡Se cargaron {inserted} registros exitosamente en NeonDB!")
                        st.rerun()
                    except Exception as exc:
                        session.rollback()
                        st.error(f"Error al insertar datos: {exc}")
                    finally:
                        session.close()
        except Exception as exc:
            st.error(f"No se pudo leer el archivo CSV: {exc}")
else:
    productos_tab, ventas_tab, cuotas_tab, finanzas_tab, dashboard_tab = st.tabs(["📦 Productos & Stock", "🛍️ Registrar Venta", "💰 Registro de Cuotas (Hoja 6)", "📈 Finanzas & Comisiones", "📊 Dashboard"])

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
                    df[["id", "nombre", "costo", "precio_divisa", "precio_bcv", "stock"]],
                    disabled=["id", "nombre"],
                    use_container_width=True,
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
        st.dataframe(historial, use_container_width=True)

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
        st.dataframe(payment_summary, use_container_width=True)

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
            st.dataframe(commission_df, use_container_width=True)

        st.divider()
        st.subheader("Ventas Totales y Deuda")
        try:
            ventas_df = load_all_sales_dataframe()
            if ventas_df.empty:
                st.info("No hay ventas registradas aún.")
            else:
                st.dataframe(ventas_df, use_container_width=True)
        except Exception as exc:
            st.warning(str(exc))
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
    st.subheader("🚨 Cuentas por Cobrar / Clientes Pendientes")
    try:
        cuentas_pendientes = db.load_pending_accounts_dataframe()
    except Exception as exc:
        st.warning(str(exc))
        cuentas_pendientes = None

    if cuentas_pendientes is None or cuentas_pendientes.empty:
        st.success("🎉 ¡Excelente! No hay cuentas pendientes por cobrar.")
    else:
        st.dataframe(
            cuentas_pendientes[["fecha", "cliente", "vendedor", "producto", "precio_venta", "deuda", "estatus"]],
            use_container_width=True,
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
        st.dataframe(stock_critico, use_container_width=True)

        chart_stock = stock_critico[["nombre", "stock"]].copy()
        chart_stock = chart_stock.sort_values("stock", ascending=True)
        st.caption("Stock actual de perfumes bajo control")
        st.bar_chart(chart_stock.set_index("nombre")["stock"])

    st.divider()
    st.subheader("⚡ Accesos rápidos")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Registrar una venta nueva", use_container_width=True):
            st.info("Dirígete a la pestaña 🛍️ Registrar Venta para crear una venta nueva.")
    with col2:
        if st.button("Cargar un pago rápido", use_container_width=True):
            st.info("Dirígete a la pestaña 💰 Registro de Cuotas para registrar un abono o pago.")
