from __future__ import annotations

import os
from datetime import UTC, date, datetime
from functools import lru_cache
from math import isfinite

import pandas as pd
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    create_engine,
    func,
    select,
    text,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    categoria = Column(String(100), nullable=True)
    costo = Column(Numeric(10, 2), nullable=False, default=0)
    precio_divisa = Column(Numeric(10, 2), nullable=False, default=0)
    precio_bcv = Column(Numeric(10, 2), nullable=False, default=0)
    stock = Column(Integer, nullable=False, default=0)
    precio_unitario = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, default=date.today)
    cliente = Column(String(200), nullable=False)
    vendedor = Column(String(50), nullable=True)
    producto = Column(String(200), nullable=True)
    cantidad = Column(Integer, nullable=False, default=1)
    precio_venta = Column(Numeric(10, 2), nullable=False, default=0)
    costo = Column(Numeric(10, 2), nullable=False, default=0)
    ganancia = Column(Numeric(10, 2), nullable=False, default=0)
    moneda = Column(String(10), nullable=False, default="BCV")
    deuda = Column(Numeric(10, 2), nullable=False, default=0)
    estatus = Column(String(20), nullable=False, default="PENDIENTE")
    total = Column(Numeric(10, 2), nullable=False, default=0)
    items = relationship("ItemVenta", back_populates="venta", cascade="all, delete-orphan")
    cuotas = relationship("Cuota", back_populates="venta", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="venta", cascade="all, delete-orphan")


class ItemVenta(Base):
    __tablename__ = "items_venta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    venta = relationship("Venta", back_populates="items")
    producto = relationship("Producto")


class Cuota(Base):
    __tablename__ = "cuotas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    numero = Column(Integer, nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    estado = Column(String(20), nullable=False, default="pendiente")

    venta = relationship("Venta", back_populates="cuotas")


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    fecha = Column(Date, default=date.today)
    cliente = Column(String(200), nullable=False)
    producto = Column(String(200), nullable=True)
    monto_bs = Column(Numeric(10, 2), nullable=False, default=0)
    monto_usd = Column(Numeric(10, 2), nullable=False, default=0)
    referencia = Column(String(100), nullable=False)
    tasa_bcv = Column(Numeric(10, 2), nullable=False, default=0)
    nro_cuota = Column(Integer, nullable=False, default=1)

    venta = relationship("Venta", back_populates="pagos")


def get_database_url() -> str:
    try:
        import streamlit as st

        if "DATABASE_URL" in st.secrets:
            value = str(st.secrets["DATABASE_URL"]).strip()
            if value and "<" not in value and ">" not in value:
                return value
    except Exception:
        pass

    env_url = os.getenv("DATABASE_URL")
    if env_url:
        value = str(env_url).strip()
        if value and "<" not in value and ">" not in value:
            return value

    return ""


@lru_cache(maxsize=4)
def _create_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def get_engine():
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError(
            "No hay una URL de conexión válida para PostgreSQL. Edita .streamlit/secrets.toml o define DATABASE_URL."
        )
    return _create_engine(database_url)


def _validate_finite_numbers(**values: float | int) -> None:
    invalid = [name for name, value in values.items() if not isfinite(float(value))]
    if invalid:
        raise ValueError(f"Valores numéricos inválidos: {', '.join(invalid)}.")


def ensure_schema() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        producto_columns = {
            row[0]
            for row in connection.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'productos'")
            ).fetchall()
        }
        venta_columns = {
            row[0]
            for row in connection.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'ventas'")
            ).fetchall()
        }
        pago_columns = {
            row[0]
            for row in connection.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'pagos'")
            ).fetchall()
        }

        if "costo" not in producto_columns:
            connection.execute(text("ALTER TABLE productos ADD COLUMN costo NUMERIC(10, 2) DEFAULT 0"))
        if "precio_divisa" not in producto_columns:
            connection.execute(text("ALTER TABLE productos ADD COLUMN precio_divisa NUMERIC(10, 2) DEFAULT 0"))
        if "precio_bcv" not in producto_columns:
            connection.execute(text("ALTER TABLE productos ADD COLUMN precio_bcv NUMERIC(10, 2) DEFAULT 0"))
        for column_name, definition in {
            "categoria": "VARCHAR(100)",
            "precio_unitario": "NUMERIC(10, 2) DEFAULT 0",
            "created_at": "TIMESTAMP WITH TIME ZONE",
        }.items():
            if column_name not in producto_columns:
                connection.execute(text(f"ALTER TABLE productos ADD COLUMN {column_name} {definition}"))

        for column_name, definition in {
            "fecha": "DATE",
            "cliente": "VARCHAR(200)",
            "vendedor": "VARCHAR(50)",
            "producto": "VARCHAR(200)",
            "cantidad": "INTEGER DEFAULT 1",
            "precio_venta": "NUMERIC(10, 2) DEFAULT 0",
            "costo": "NUMERIC(10, 2) DEFAULT 0",
            "ganancia": "NUMERIC(10, 2) DEFAULT 0",
            "moneda": "VARCHAR(10) DEFAULT 'BCV'",
            "deuda": "NUMERIC(10, 2) DEFAULT 0",
            "estatus": "VARCHAR(20) DEFAULT 'PENDIENTE'",
            "total": "NUMERIC(10, 2) DEFAULT 0",
        }.items():
            if column_name not in venta_columns:
                connection.execute(text(f"ALTER TABLE ventas ADD COLUMN {column_name} {definition}"))

        for column_name, definition in {
            "venta_id": "INTEGER",
            "fecha": "DATE",
            "cliente": "VARCHAR(200)",
            "producto": "VARCHAR(200)",
            "monto_bs": "NUMERIC(10, 2)",
            "monto_usd": "NUMERIC(10, 2)",
            "referencia": "VARCHAR(100)",
            "tasa_bcv": "NUMERIC(10, 2)",
            "nro_cuota": "INTEGER",
        }.items():
            if column_name not in pago_columns:
                connection.execute(text(f"ALTER TABLE pagos ADD COLUMN {column_name} {definition} DEFAULT NULL"))


def init_db():
    try:
        engine = get_engine()
        Base.metadata.create_all(engine)
        ensure_schema()
        return engine
    except Exception as exc:
        raise RuntimeError(f"No se pudo inicializar la base de datos: {exc}") from exc


def get_session():
    try:
        SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
        return SessionLocal()
    except Exception as exc:
        raise RuntimeError(f"No se pudo abrir la sesión de base de datos: {exc}") from exc


def test_connection() -> bool:
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(select(1))
    return True


def load_inventory_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        productos = session.execute(select(Producto).order_by(Producto.nombre.asc())).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": producto.id,
                    "nombre": producto.nombre,
                    "costo": float(producto.costo or 0),
                    "precio_divisa": float(producto.precio_divisa or 0),
                    "precio_bcv": float(producto.precio_bcv or 0),
                    "stock": int(producto.stock or 0),
                }
                for producto in productos
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar el inventario: {exc}") from exc
    finally:
        session.close()


def save_inventory_changes(edited_df: pd.DataFrame) -> int:
    if edited_df.empty:
        return 0

    session = get_session()
    try:
        updated_rows = 0
        for record in edited_df.to_dict(orient="records"):
            producto = session.get(Producto, int(record["id"]))
            if producto is None:
                continue

            _validate_finite_numbers(
                costo=record["costo"],
                precio_divisa=record["precio_divisa"],
                precio_bcv=record["precio_bcv"],
                stock=record["stock"],
            )
            if any(float(record[column]) < 0 for column in ["costo", "precio_divisa", "precio_bcv", "stock"]):
                raise ValueError("Los costos, precios y existencias no pueden ser negativos.")

            changed = False
            for column in ["costo", "precio_divisa", "precio_bcv", "stock"]:
                new_value = record[column]
                current_value = getattr(producto, column)
                if current_value != new_value:
                    setattr(producto, column, new_value)
                    changed = True

            if changed:
                updated_rows += 1

        session.commit()
        return updated_rows
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudieron guardar los cambios: {exc}") from exc
    finally:
        session.close()


def create_product(nombre: str, costo: float, precio_divisa: float, precio_bcv: float, stock: int) -> Producto:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del producto es obligatorio.")
    _validate_finite_numbers(costo=costo, precio_divisa=precio_divisa, precio_bcv=precio_bcv, stock=stock)
    if min(costo, precio_divisa, precio_bcv, stock) < 0:
        raise ValueError("Los costos, precios y existencias no pueden ser negativos.")

    session = get_session()
    try:
        producto = Producto(
            nombre=nombre,
            costo=costo,
            precio_divisa=precio_divisa,
            precio_bcv=precio_bcv,
            stock=stock,
        )
        session.add(producto)
        session.commit()
        return producto
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo crear el producto: {exc}") from exc
    finally:
        session.close()


def load_available_products_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        productos = (
            session.execute(
                select(Producto)
                .where(Producto.stock > 0)
                .order_by(Producto.nombre.asc())
            )
            .scalars()
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "id": producto.id,
                    "nombre": producto.nombre,
                    "costo": float(producto.costo or 0),
                    "precio_divisa": float(producto.precio_divisa or 0),
                    "precio_bcv": float(producto.precio_bcv or 0),
                    "stock": int(producto.stock or 0),
                }
                for producto in productos
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar los productos disponibles: {exc}") from exc
    finally:
        session.close()


def register_sale(
    *,
    fecha: date,
    cliente: str,
    vendedor: str,
    producto_nombre: str,
    producto_id: int,
    cantidad: int,
    precio_venta: float,
    costo_total: float,
    ganancia: float,
    deuda: float,
    estatus: str,
) -> Venta:
    cliente = cliente.strip()
    vendedor = vendedor.strip()
    producto_nombre = producto_nombre.strip()
    if not cliente or not producto_nombre:
        raise ValueError("El cliente y el producto son obligatorios.")
    _validate_finite_numbers(
        cantidad=cantidad,
        precio_venta=precio_venta,
        costo_total=costo_total,
        ganancia=ganancia,
        deuda=deuda,
    )
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    if precio_venta < 0 or costo_total < 0 or deuda < 0:
        raise ValueError("Los importes de la venta no pueden ser negativos.")
    if deuda > precio_venta:
        raise ValueError("La deuda no puede superar el precio de venta.")

    session = get_session()
    try:
        with session.begin():
            stock_update = session.execute(
                update(Producto)
                .where(Producto.id == producto_id, Producto.stock >= cantidad)
                .values(stock=Producto.stock - cantidad)
            )
            if stock_update.rowcount != 1:
                producto_existe = session.execute(
                    select(Producto.id).where(Producto.id == producto_id)
                ).scalar_one_or_none()
                if producto_existe is None:
                    raise ValueError("Producto no encontrado.")
                raise ValueError("No hay suficiente stock para completar la venta.")

            venta = Venta(
                fecha=fecha,
                cliente=cliente,
                vendedor=vendedor,
                producto=producto_nombre,
                cantidad=cantidad,
                precio_venta=precio_venta,
                costo=costo_total,
                ganancia=ganancia,
                moneda="BCV",
                deuda=deuda,
                estatus=estatus,
                total=precio_venta,
            )
            session.add(venta)
            session.flush()
            return venta
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo registrar la venta: {exc}") from exc
    finally:
        session.close()


def load_recent_sales_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        ventas = (
            session.execute(select(Venta).order_by(Venta.id.desc()).limit(10)).scalars().all()
        )
        return pd.DataFrame(
            [
                {
                    "id": venta.id,
                    "fecha": venta.fecha,
                    "cliente": venta.cliente,
                    "vendedor": venta.vendedor,
                    "producto": venta.producto,
                    "cantidad": int(venta.cantidad or 0),
                    "precio_venta": float(venta.precio_venta or 0),
                    "costo": float(venta.costo or 0),
                    "ganancia": float(venta.ganancia or 0),
                    "deuda": float(venta.deuda or 0),
                    "estatus": venta.estatus,
                }
                for venta in ventas
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar el historial de ventas: {exc}") from exc
    finally:
        session.close()


def load_all_sales_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        ventas = session.execute(select(Venta).order_by(Venta.id.asc())).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": venta.id,
                    "fecha": venta.fecha,
                    "cliente": venta.cliente,
                    "vendedor": venta.vendedor,
                    "producto": venta.producto,
                    "cantidad": int(venta.cantidad or 0),
                    "precio_venta": float(venta.precio_venta or 0),
                    "costo": float(venta.costo or 0),
                    "ganancia": float(venta.ganancia or 0),
                    "deuda": float(venta.deuda or 0),
                    "estatus": venta.estatus,
                }
                for venta in ventas
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar todas las ventas: {exc}") from exc
    finally:
        session.close()


def load_all_payments_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        resultados = (
            session.execute(
                select(
                    Pago,
                    Venta.vendedor.label("venta_vendedor"),
                    Venta.deuda.label("venta_deuda"),
                    Venta.estatus.label("venta_estatus"),
                )
                .join(Venta, Pago.venta_id == Venta.id)
                .order_by(Pago.id.desc())
            )
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "id": pago.id,
                    "fecha": pago.fecha,
                    "cliente": pago.cliente,
                    "vendedor": venta_vendedor or "",
                    "producto": pago.producto,
                    "monto_bs": float(pago.monto_bs or 0),
                    "monto_usd": float(pago.monto_usd or 0),
                    "referencia": pago.referencia,
                    "tasa_bcv": float(pago.tasa_bcv or 0),
                    "nro_cuota": pago.nro_cuota,
                    "saldo_usd": float(venta_deuda or 0),
                    "estatus": venta_estatus,
                }
                for pago, venta_vendedor, venta_deuda, venta_estatus in resultados
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar los pagos: {exc}") from exc
    finally:
        session.close()


def load_pending_sales_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        ventas = session.execute(
            select(Venta).where(Venta.deuda > 0).order_by(Venta.cliente.asc())
        ).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": venta.id,
                    "cliente": venta.cliente,
                    "producto": venta.producto,
                    "deuda": float(venta.deuda or 0),
                    "estatus": venta.estatus,
                }
                for venta in ventas
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar las ventas pendientes: {exc}") from exc
    finally:
        session.close()


def load_pending_collections_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        pagos_subquery = (
            select(
                Pago.venta_id.label("venta_id"),
                func.count(Pago.id).label("pagos_count"),
                func.coalesce(func.sum(Pago.monto_usd), 0).label("pagado_usd"),
            )
            .group_by(Pago.venta_id)
            .subquery()
        )

        resultados = (
            session.execute(
                select(
                    Venta.id,
                    Venta.fecha,
                    Venta.cliente,
                    Venta.vendedor,
                    Venta.producto,
                    Venta.deuda,
                    Venta.estatus,
                    func.coalesce(pagos_subquery.c.pagos_count, 0).label("pagos_count"),
                    func.coalesce(pagos_subquery.c.pagado_usd, 0).label("pagado_usd"),
                )
                .select_from(Venta)
                .outerjoin(pagos_subquery, Venta.id == pagos_subquery.c.venta_id)
                .order_by(Venta.deuda.desc())
            )
            .all()
        )

        rows = []
        for venta in resultados:
            deuda = float(venta.deuda or 0)
            pagos_count = int(venta.pagos_count or 0)
            pagado_usd = float(venta.pagado_usd or 0)
            if deuda == 0:
                semaforo_icon = "🟢"
                semaforo_label = "Al día / Completado"
            elif pagos_count == 0:
                semaforo_icon = "🔴"
                semaforo_label = "Moroso / Sin abonos"
            else:
                semaforo_icon = "🟡"
                semaforo_label = "Cuota pendiente / Con abonos"

            rows.append(
                {
                    "id": venta.id,
                    "fecha": venta.fecha,
                    "cliente": venta.cliente,
                    "vendedor": venta.vendedor,
                    "producto": venta.producto,
                    "deuda": deuda,
                    "pagos_count": pagos_count,
                    "pagado_usd": pagado_usd,
                    "estatus": venta.estatus,
                    "semaforo": f"{semaforo_icon} {semaforo_label}",
                    "semaforo_icon": semaforo_icon,
                }
            )

        return pd.DataFrame(rows)
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar las métricas de cobranza avanzada: {exc}") from exc
    finally:
        session.close()


def register_payment(
    *,
    venta_id: int,
    fecha: date,
    cliente: str,
    producto: str,
    monto_bs: float,
    monto_usd: float,
    referencia: str,
    tasa_bcv: float,
    nro_cuota: int,
) -> tuple[float, str]:
    _validate_finite_numbers(monto_bs=monto_bs, monto_usd=monto_usd, tasa_bcv=tasa_bcv, nro_cuota=nro_cuota)
    if monto_bs <= 0 or monto_usd <= 0 or tasa_bcv <= 0:
        raise ValueError("El monto y la tasa del abono deben ser mayores a cero.")
    if venta_id <= 0 or nro_cuota <= 0:
        raise ValueError("La venta y el número de cuota deben ser positivos.")
    if not referencia.strip():
        raise ValueError("La referencia bancaria es obligatoria.")

    session = get_session()
    try:
        with session.begin():
            venta = session.execute(
                select(Venta).where(Venta.id == venta_id).with_for_update()
            ).scalar_one_or_none()
            if venta is None:
                raise ValueError("Venta no encontrada.")

            deuda_actual = float(venta.deuda or 0)
            if deuda_actual <= 0:
                raise ValueError("La venta ya está pagada.")
            if monto_usd > deuda_actual + 0.005:
                raise ValueError(
                    f"El abono (${monto_usd:,.2f}) supera la deuda pendiente (${deuda_actual:,.2f})."
                )

            pago = Pago(
                venta_id=venta_id,
                fecha=fecha,
                cliente=venta.cliente,
                producto=venta.producto,
                monto_bs=monto_bs,
                monto_usd=monto_usd,
                referencia=referencia,
                tasa_bcv=tasa_bcv,
                nro_cuota=nro_cuota,
            )
            session.add(pago)

            nueva_deuda = max(0.0, deuda_actual - monto_usd)
            if nueva_deuda < 0.005:
                nueva_deuda = 0.0
            venta.deuda = nueva_deuda
            venta.estatus = "YA PAGO" if nueva_deuda == 0 else "PENDIENTE"
            session.flush()
            return nueva_deuda, venta.estatus
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo registrar el abono: {exc}") from exc
    finally:
        session.close()


def load_payment_summary_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        ventas = session.execute(select(Venta).order_by(Venta.id.asc())).scalars().all()
        pagos = session.execute(select(Pago).order_by(Pago.venta_id.asc(), Pago.nro_cuota.asc())).scalars().all()

        pagos_por_venta: dict[int, list[dict[str, object]]] = {}
        for pago in pagos:
            pagos_por_venta.setdefault(pago.venta_id, []).append(
                {
                    "fecha": pago.fecha,
                    "monto_bs": float(pago.monto_bs or 0),
                    "monto_usd": float(pago.monto_usd or 0),
                    "referencia": pago.referencia,
                    "nro_cuota": pago.nro_cuota,
                }
            )

        rows = []
        for venta in ventas:
            pago_blocks = pagos_por_venta.get(venta.id, [])
            block_values = ["-"] * 3
            for idx, pago in enumerate(pago_blocks[:3], start=1):
                block_values[idx - 1] = f"Bs. {pago['monto_bs']:.2f} / {pago['referencia']}"

            rows.append(
                {
                    "fecha_venta": venta.fecha,
                    "cliente": venta.cliente,
                    "vendedor": venta.vendedor,
                    "producto": venta.producto,
                    "precio_total": float(venta.precio_venta or 0),
                    "pago_1": block_values[0],
                    "pago_2": block_values[1],
                    "pago_3": block_values[2],
                    "deuda_usd": float(venta.deuda or 0),
                    "estatus": venta.estatus,
                }
            )

        return pd.DataFrame(rows)
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar la vista de cobranza: {exc}") from exc
    finally:
        session.close()


def load_dashboard_metrics() -> tuple[float, float, float, float]:
    session = get_session()
    try:
        total_bs = float(
            session.execute(text("SELECT COALESCE(SUM(monto_bs), 0) FROM pagos")).scalar_one()
        )
        total_usd = float(
            session.execute(text("SELECT COALESCE(SUM(monto_usd), 0) FROM pagos")).scalar_one()
        )
        total_ventas = float(
            session.execute(text("SELECT COALESCE(SUM(precio_venta), 0) FROM ventas")).scalar_one()
        )
        total_por_cobrar = float(
            session.execute(text("SELECT COALESCE(SUM(deuda), 0) FROM ventas WHERE deuda > 0")).scalar_one()
        )
        return total_bs, total_usd, total_ventas, total_por_cobrar
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar las métricas del dashboard: {exc}") from exc
    finally:
        session.close()


def load_pending_accounts_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        ventas = (
            session.execute(
                select(Venta)
                .where(Venta.deuda > 0)
                .order_by(Venta.deuda.desc())
            )
            .scalars()
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "fecha": venta.fecha,
                    "cliente": venta.cliente,
                    "vendedor": venta.vendedor,
                    "producto": venta.producto,
                    "precio_venta": float(venta.precio_venta or 0),
                    "deuda": float(venta.deuda or 0),
                    "estatus": venta.estatus,
                }
                for venta in ventas
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar las cuentas pendientes: {exc}") from exc
    finally:
        session.close()


def load_low_stock_products_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        productos = (
            session.execute(
                select(Producto)
                .where(Producto.stock <= 2)
                .order_by(Producto.stock.asc(), Producto.nombre.asc())
            )
            .scalars()
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "nombre": producto.nombre,
                    "costo": float(producto.costo or 0),
                    "precio_bcv": float(producto.precio_bcv or 0),
                    "stock": int(producto.stock or 0),
                }
                for producto in productos
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar el stock crítico: {exc}") from exc
    finally:
        session.close()


def load_payment_metrics() -> tuple[float, float, int]:
    session = get_session()
    try:
        total_bs = float(
            session.execute(select(text("COALESCE(SUM(monto_bs), 0)")).select_from(Pago)).scalar_one()
        )
        total_usd = float(
            session.execute(select(text("COALESCE(SUM(monto_usd), 0)")).select_from(Pago)).scalar_one()
        )
        completed_clients = int(
            session.execute(
                select(func.count(func.distinct(Venta.cliente))).where(Venta.estatus == "YA PAGO")
            ).scalar_one()
        )
        return total_bs, total_usd, completed_clients
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar las métricas de cobranza: {exc}") from exc
    finally:
        session.close()


def load_financial_metrics() -> tuple[float, float, float, float, float, float]:
    session = get_session()
    try:
        total_revenue = float(
            session.execute(text("SELECT COALESCE(SUM(precio_venta), 0) FROM ventas")).scalar_one()
        )
        total_cost = float(
            session.execute(text("SELECT COALESCE(SUM(costo), 0) FROM ventas")).scalar_one()
        )
        total_profit = float(
            session.execute(text("SELECT COALESCE(SUM(ganancia), 0) FROM ventas")).scalar_one()
        )
        total_debt = float(
            session.execute(text("SELECT COALESCE(SUM(deuda), 0) FROM ventas")).scalar_one()
        )
        total_collected_usd = float(
            session.execute(text("SELECT COALESCE(SUM(monto_usd), 0) FROM pagos")).scalar_one()
        )
        total_collected_bs = float(
            session.execute(text("SELECT COALESCE(SUM(monto_bs), 0) FROM pagos")).scalar_one()
        )
        return (
            total_revenue,
            total_cost,
            total_profit,
            total_debt,
            total_collected_usd,
            total_collected_bs,
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar las métricas financieras: {exc}") from exc
    finally:
        session.close()


def load_commission_dataframe(commission_rate: float = 0.1) -> pd.DataFrame:
    session = get_session()
    try:
        ventas = session.execute(select(Venta).order_by(Venta.vendedor.asc())).scalars().all()
        vendedor_map: dict[str, dict[str, object]] = {}

        for venta in ventas:
            vendedor = str(venta.vendedor or "Sin vendedor").strip() or "Sin vendedor"
            registro = vendedor_map.setdefault(
                vendedor,
                {
                    "vendedor": vendedor,
                    "cantidad_ventas": 0,
                    "ingresos_usd": 0.0,
                    "costo_usd": 0.0,
                    "ganancia_usd": 0.0,
                    "comision_usd": 0.0,
                },
            )
            registro["cantidad_ventas"] += 1
            registro["ingresos_usd"] += float(venta.precio_venta or 0)
            registro["costo_usd"] += float(venta.costo or 0)
            registro["ganancia_usd"] += float(venta.ganancia or 0)

        rows = []
        for registro in vendedor_map.values():
            comision = max(0.0, registro["ganancia_usd"] * commission_rate)
            rows.append(
                {
                    "vendedor": registro["vendedor"],
                    "ventas": int(registro["cantidad_ventas"]),
                    "ingresos_usd": round(registro["ingresos_usd"], 2),
                    "costo_usd": round(registro["costo_usd"], 2),
                    "ganancia_usd": round(registro["ganancia_usd"], 2),
                    "comision_usd": round(comision, 2),
                }
            )

        if not rows:
            return pd.DataFrame(
                columns=[
                    "vendedor",
                    "ventas",
                    "ingresos_usd",
                    "costo_usd",
                    "ganancia_usd",
                    "comision_usd",
                ]
            )
        return pd.DataFrame(rows).sort_values("comision_usd", ascending=False)
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar el resumen de comisiones: {exc}") from exc
    finally:
        session.close()


def seed_sample_data() -> bool:
    session = get_session()
    try:
        if session.execute(select(Producto)).scalars().first() is None:
            productos = [
                Producto(
                    nombre="Perfume 1",
                    categoria="Femenino",
                    costo=45.0,
                    precio_divisa=89.99,
                    precio_bcv=88.5,
                    stock=12,
                ),
                Producto(
                    nombre="Perfume 2",
                    categoria="Masculino",
                    costo=59.0,
                    precio_divisa=109.5,
                    precio_bcv=107.0,
                    stock=8,
                ),
                Producto(
                    nombre="Perfume 3",
                    categoria="Unisex",
                    costo=38.0,
                    precio_divisa=74.5,
                    precio_bcv=72.0,
                    stock=15,
                ),
            ]
            session.add_all(productos)
            session.commit()
        return True
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar los datos de ejemplo: {exc}") from exc
    finally:
        session.close()
