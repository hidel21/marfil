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
    JSON,
    Numeric,
    String,
    create_engine,
    func,
    inspect,
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
    precio_original = Column(Numeric(10, 2), nullable=False, default=0)
    precio_team = Column(Numeric(10, 2), nullable=False, default=0)
    precio_revendedor = Column(Numeric(10, 2), nullable=False, default=0)
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


class Socio(Base):
    __tablename__ = "socios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False, unique=True)
    capital_invertido = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Proveedor(Base):
    __tablename__ = "proveedores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    contacto = Column(String(200), nullable=True)
    telefono = Column(String(50), nullable=True)
    email = Column(String(200), nullable=True)
    notas = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Compra(Base):
    __tablename__ = "compras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, default=date.today)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=False)
    proveedor_nombre = Column(String(200), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    producto_nombre = Column(String(200), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)
    costo_unitario = Column(Numeric(10, 2), nullable=False, default=0)
    monto_total = Column(Numeric(10, 2), nullable=False, default=0)
    monto_pagado = Column(Numeric(10, 2), nullable=False, default=0)
    saldo = Column(Numeric(10, 2), nullable=False, default=0)
    estatus = Column(String(20), nullable=False, default="PENDIENTE")
    referencia = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    pagos = relationship("PagoCompra", back_populates="compra", cascade="all, delete-orphan")


class PagoCompra(Base):
    __tablename__ = "pagos_compra"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compra_id = Column(Integer, ForeignKey("compras.id"), nullable=False)
    fecha = Column(Date, default=date.today)
    monto = Column(Numeric(10, 2), nullable=False, default=0)
    referencia = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    compra = relationship("Compra", back_populates="pagos")


class GastoGeneral(Base):
    __tablename__ = "gastos_generales"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, default=date.today)
    categoria = Column(String(100), nullable=False)
    descripcion = Column(String(500), nullable=True)
    monto = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ImportacionExcel(Base):
    __tablename__ = "importaciones_excel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    archivo = Column(String(255), nullable=False)
    archivo_hash = Column(String(64), nullable=False, unique=True)
    importado_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    filas = relationship("FilaExcel", back_populates="importacion", cascade="all, delete-orphan")


class FilaExcel(Base):
    __tablename__ = "filas_excel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    importacion_id = Column(Integer, ForeignKey("importaciones_excel.id"), nullable=False)
    pestaña = Column(String(200), nullable=False)
    numero_fila = Column(Integer, nullable=False)
    datos = Column(JSON, nullable=False)

    importacion = relationship("ImportacionExcel", back_populates="filas")


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
    inspector = inspect(engine)
    with engine.begin() as connection:
        producto_columns = {row["name"] for row in inspector.get_columns("productos")}
        venta_columns = {row["name"] for row in inspector.get_columns("ventas")}
        pago_columns = {row["name"] for row in inspector.get_columns("pagos")}

        if "costo" not in producto_columns:
            connection.execute(text("ALTER TABLE productos ADD COLUMN costo NUMERIC(10, 2) DEFAULT 0"))
        if "precio_divisa" not in producto_columns:
            connection.execute(text("ALTER TABLE productos ADD COLUMN precio_divisa NUMERIC(10, 2) DEFAULT 0"))
        if "precio_bcv" not in producto_columns:
            connection.execute(text("ALTER TABLE productos ADD COLUMN precio_bcv NUMERIC(10, 2) DEFAULT 0"))
        for column_name, definition in {
            "categoria": "VARCHAR(100)",
            "precio_unitario": "NUMERIC(10, 2) DEFAULT 0",
            "precio_original": "NUMERIC(10, 2) DEFAULT 0",
            "precio_team": "NUMERIC(10, 2) DEFAULT 0",
            "precio_revendedor": "NUMERIC(10, 2) DEFAULT 0",
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
        seed_default_socios()
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
                    "categoria": producto.categoria or "Sin categoría",
                    "costo": float(producto.costo or 0),
                    "precio_divisa": float(producto.precio_divisa or 0),
                    "precio_bcv": float(producto.precio_bcv or 0),
                    "precio_original": float(producto.precio_original or 0),
                    "precio_team": float(producto.precio_team or 0),
                    "precio_revendedor": float(producto.precio_revendedor or 0),
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


def load_financial_metrics() -> tuple[float, float, float, float, float, float, float, float]:
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
        total_gastos = float(
            session.execute(text("SELECT COALESCE(SUM(monto), 0) FROM gastos_generales")).scalar_one()
        )
        utilidad_neta_real = total_profit - total_gastos
        return (
            total_revenue,
            total_cost,
            total_profit,
            total_debt,
            total_collected_usd,
            total_collected_bs,
            total_gastos,
            utilidad_neta_real,
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


def load_excel_import_summary_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        rows = session.execute(
            select(
                ImportacionExcel.id,
                ImportacionExcel.archivo,
                ImportacionExcel.importado_at,
                FilaExcel.pestaña,
                func.count(FilaExcel.id).label("filas"),
            )
            .join(FilaExcel, FilaExcel.importacion_id == ImportacionExcel.id)
            .group_by(
                ImportacionExcel.id,
                ImportacionExcel.archivo,
                ImportacionExcel.importado_at,
                FilaExcel.pestaña,
            )
            .order_by(ImportacionExcel.id.desc(), FilaExcel.pestaña.asc())
        ).all()
        return pd.DataFrame(
            [
                {
                    "importacion_id": row.id,
                    "archivo": row.archivo,
                    "importado_at": row.importado_at,
                    "pestaña": row.pestaña,
                    "filas": int(row.filas),
                }
                for row in rows
            ]
        )
    finally:
        session.close()


def load_excel_sheet_dataframe(importacion_id: int, pestaña: str) -> pd.DataFrame:
    session = get_session()
    try:
        filas = session.execute(
            select(FilaExcel)
            .where(
                FilaExcel.importacion_id == importacion_id,
                FilaExcel.pestaña == pestaña,
            )
            .order_by(FilaExcel.numero_fila.asc())
        ).scalars().all()
        if not filas:
            return pd.DataFrame()
        records = [{"fila_excel": fila.numero_fila, **(fila.datos or {})} for fila in filas]
        return pd.DataFrame(records)
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


def seed_default_socios() -> bool:
    session = get_session()
    try:
        if session.execute(select(Socio)).scalars().first() is None:
            socios = [
                Socio(nombre="Gregory", capital_invertido=0),
                Socio(nombre="Hidelberg", capital_invertido=0),
                Socio(nombre="Gregor", capital_invertido=0),
            ]
            session.add_all(socios)
            session.commit()
        return True
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar los socios por defecto: {exc}") from exc
    finally:
        session.close()


# --- Proveedores ---------------------------------------------------------


def create_proveedor(
    nombre: str,
    contacto: str = "",
    telefono: str = "",
    email: str = "",
    notas: str = "",
) -> Proveedor:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del proveedor es obligatorio.")

    session = get_session()
    try:
        proveedor = Proveedor(
            nombre=nombre,
            contacto=contacto.strip() or None,
            telefono=telefono.strip() or None,
            email=email.strip() or None,
            notas=notas.strip() or None,
        )
        session.add(proveedor)
        session.commit()
        return proveedor
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo crear el proveedor: {exc}") from exc
    finally:
        session.close()


def load_proveedores_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        proveedores = session.execute(select(Proveedor).order_by(Proveedor.nombre.asc())).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": proveedor.id,
                    "nombre": proveedor.nombre,
                    "contacto": proveedor.contacto or "",
                    "telefono": proveedor.telefono or "",
                    "email": proveedor.email or "",
                    "notas": proveedor.notas or "",
                }
                for proveedor in proveedores
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar los proveedores: {exc}") from exc
    finally:
        session.close()


def save_proveedor_changes(edited_df: pd.DataFrame) -> int:
    if edited_df.empty:
        return 0

    session = get_session()
    try:
        updated_rows = 0
        for record in edited_df.to_dict(orient="records"):
            proveedor = session.get(Proveedor, int(record["id"]))
            if proveedor is None:
                continue

            changed = False
            for column in ["contacto", "telefono", "email", "notas"]:
                new_value = (str(record[column]).strip() or None) if record[column] is not None else None
                current_value = getattr(proveedor, column)
                if current_value != new_value:
                    setattr(proveedor, column, new_value)
                    changed = True

            if changed:
                updated_rows += 1

        session.commit()
        return updated_rows
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudieron guardar los cambios de proveedores: {exc}") from exc
    finally:
        session.close()


# --- Compras --------------------------------------------------------------


def register_purchase(
    *,
    fecha: date,
    proveedor_id: int,
    proveedor_nombre: str,
    producto_id: int,
    producto_nombre: str,
    cantidad: int,
    costo_unitario: float,
    monto_pagado: float,
    referencia: str = "",
) -> Compra:
    proveedor_nombre = proveedor_nombre.strip()
    producto_nombre = producto_nombre.strip()
    if not proveedor_nombre or not producto_nombre:
        raise ValueError("El proveedor y el producto son obligatorios.")
    _validate_finite_numbers(
        cantidad=cantidad,
        costo_unitario=costo_unitario,
        monto_pagado=monto_pagado,
    )
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    if costo_unitario < 0 or monto_pagado < 0:
        raise ValueError("Los importes de la compra no pueden ser negativos.")

    monto_total = round(costo_unitario * cantidad, 2)
    if monto_pagado > monto_total:
        raise ValueError("El monto pagado no puede superar el monto total de la compra.")

    session = get_session()
    try:
        with session.begin():
            producto = session.execute(
                select(Producto).where(Producto.id == producto_id).with_for_update()
            ).scalar_one_or_none()
            if producto is None:
                raise ValueError("Producto no encontrado.")

            producto.stock = int(producto.stock or 0) + int(cantidad)
            producto.costo = costo_unitario

            saldo = round(monto_total - monto_pagado, 2)
            if saldo < 0.005:
                saldo = 0.0

            compra = Compra(
                fecha=fecha,
                proveedor_id=proveedor_id,
                proveedor_nombre=proveedor_nombre,
                producto_id=producto_id,
                producto_nombre=producto_nombre,
                cantidad=cantidad,
                costo_unitario=costo_unitario,
                monto_total=monto_total,
                monto_pagado=monto_pagado,
                saldo=saldo,
                estatus="PAGADO" if saldo == 0 else "PENDIENTE",
                referencia=referencia.strip() or None,
            )
            session.add(compra)
            session.flush()
            return compra
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo registrar la compra: {exc}") from exc
    finally:
        session.close()


def load_compras_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        compras = session.execute(select(Compra).order_by(Compra.id.desc())).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": compra.id,
                    "fecha": compra.fecha,
                    "proveedor": compra.proveedor_nombre,
                    "producto": compra.producto_nombre,
                    "cantidad": int(compra.cantidad or 0),
                    "costo_unitario": float(compra.costo_unitario or 0),
                    "monto_total": float(compra.monto_total or 0),
                    "monto_pagado": float(compra.monto_pagado or 0),
                    "saldo": float(compra.saldo or 0),
                    "estatus": compra.estatus,
                    "referencia": compra.referencia or "",
                }
                for compra in compras
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo cargar el historial de compras: {exc}") from exc
    finally:
        session.close()


def load_pending_payables_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        compras = (
            session.execute(select(Compra).where(Compra.saldo > 0).order_by(Compra.saldo.desc()))
            .scalars()
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "id": compra.id,
                    "fecha": compra.fecha,
                    "proveedor": compra.proveedor_nombre,
                    "producto": compra.producto_nombre,
                    "monto_total": float(compra.monto_total or 0),
                    "saldo": float(compra.saldo or 0),
                    "estatus": compra.estatus,
                }
                for compra in compras
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar las cuentas por pagar: {exc}") from exc
    finally:
        session.close()


def load_payables_total() -> float:
    session = get_session()
    try:
        return float(
            session.execute(text("SELECT COALESCE(SUM(saldo), 0) FROM compras WHERE saldo > 0")).scalar_one()
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular el total de cuentas por pagar: {exc}") from exc
    finally:
        session.close()


def register_payable_payment(
    *,
    compra_id: int,
    fecha: date,
    monto: float,
    referencia: str = "",
) -> tuple[float, str]:
    _validate_finite_numbers(monto=monto)
    if monto <= 0:
        raise ValueError("El monto del abono debe ser mayor a cero.")
    if compra_id <= 0:
        raise ValueError("La compra debe ser válida.")

    session = get_session()
    try:
        with session.begin():
            compra = session.execute(
                select(Compra).where(Compra.id == compra_id).with_for_update()
            ).scalar_one_or_none()
            if compra is None:
                raise ValueError("Compra no encontrada.")

            saldo_actual = float(compra.saldo or 0)
            if saldo_actual <= 0:
                raise ValueError("La compra ya está pagada.")
            if monto > saldo_actual + 0.005:
                raise ValueError(
                    f"El abono (${monto:,.2f}) supera el saldo pendiente (${saldo_actual:,.2f})."
                )

            pago = PagoCompra(
                compra_id=compra_id,
                fecha=fecha,
                monto=monto,
                referencia=referencia.strip() or None,
            )
            session.add(pago)

            nuevo_saldo = max(0.0, saldo_actual - monto)
            if nuevo_saldo < 0.005:
                nuevo_saldo = 0.0
            compra.monto_pagado = float(compra.monto_pagado or 0) + monto
            compra.saldo = nuevo_saldo
            compra.estatus = "PAGADO" if nuevo_saldo == 0 else "PENDIENTE"
            session.flush()
            return nuevo_saldo, compra.estatus
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo registrar el abono a proveedor: {exc}") from exc
    finally:
        session.close()


# --- Gastos Generales -------------------------------------------------------


def create_gasto(
    *,
    fecha: date,
    categoria: str,
    descripcion: str,
    monto: float,
) -> GastoGeneral:
    categoria = categoria.strip()
    if not categoria:
        raise ValueError("La categoría del gasto es obligatoria.")
    _validate_finite_numbers(monto=monto)
    if monto <= 0:
        raise ValueError("El monto del gasto debe ser mayor a cero.")

    session = get_session()
    try:
        gasto = GastoGeneral(
            fecha=fecha,
            categoria=categoria,
            descripcion=descripcion.strip() or None,
            monto=monto,
        )
        session.add(gasto)
        session.commit()
        return gasto
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudo registrar el gasto: {exc}") from exc
    finally:
        session.close()


def load_gastos_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        gastos = session.execute(select(GastoGeneral).order_by(GastoGeneral.fecha.desc())).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": gasto.id,
                    "fecha": gasto.fecha,
                    "categoria": gasto.categoria,
                    "descripcion": gasto.descripcion or "",
                    "monto": float(gasto.monto or 0),
                }
                for gasto in gastos
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar los gastos generales: {exc}") from exc
    finally:
        session.close()


def load_gastos_total() -> float:
    session = get_session()
    try:
        return float(
            session.execute(text("SELECT COALESCE(SUM(monto), 0) FROM gastos_generales")).scalar_one()
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular el total de gastos generales: {exc}") from exc
    finally:
        session.close()


# --- Socios / Inversión -----------------------------------------------------


def load_socios_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        socios = session.execute(select(Socio).order_by(Socio.nombre.asc())).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": socio.id,
                    "nombre": socio.nombre,
                    "capital_invertido": float(socio.capital_invertido or 0),
                }
                for socio in socios
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudieron cargar los socios: {exc}") from exc
    finally:
        session.close()


def save_socio_changes(edited_df: pd.DataFrame) -> int:
    if edited_df.empty:
        return 0

    session = get_session()
    try:
        updated_rows = 0
        for record in edited_df.to_dict(orient="records"):
            socio = session.get(Socio, int(record["id"]))
            if socio is None:
                continue

            _validate_finite_numbers(capital_invertido=record["capital_invertido"])
            if float(record["capital_invertido"]) < 0:
                raise ValueError("El capital invertido no puede ser negativo.")

            new_value = record["capital_invertido"]
            if float(socio.capital_invertido or 0) != float(new_value):
                socio.capital_invertido = new_value
                updated_rows += 1

        session.commit()
        return updated_rows
    except SQLAlchemyError:
        session.rollback()
        raise
    except Exception as exc:
        raise RuntimeError(f"No se pudieron guardar los cambios de socios: {exc}") from exc
    finally:
        session.close()


def load_socios_investment_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        socios = session.execute(select(Socio).order_by(Socio.nombre.asc())).scalars().all()
        _, _, utilidad_neta_real = _compute_utilidad_neta_real(session)

        capital_total = sum(float(socio.capital_invertido or 0) for socio in socios)

        rows = []
        for socio in socios:
            capital = float(socio.capital_invertido or 0)
            participacion = (capital / capital_total * 100) if capital_total > 0 else 0.0
            ganancia_atribuida = utilidad_neta_real * (capital / capital_total) if capital_total > 0 else 0.0
            roi = (ganancia_atribuida / capital * 100) if capital > 0 else 0.0
            rows.append(
                {
                    "socio": socio.nombre,
                    "capital_invertido": round(capital, 2),
                    "participacion_pct": round(participacion, 2),
                    "ganancia_atribuida": round(ganancia_atribuida, 2),
                    "roi_pct": round(roi, 2),
                }
            )

        return pd.DataFrame(rows)
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular la inversión por socio: {exc}") from exc
    finally:
        session.close()


# --- Analítica financiera ---------------------------------------------------


def _compute_utilidad_neta_real(session) -> tuple[float, float, float]:
    total_profit = float(
        session.execute(text("SELECT COALESCE(SUM(ganancia), 0) FROM ventas")).scalar_one()
    )
    total_gastos = float(
        session.execute(text("SELECT COALESCE(SUM(monto), 0) FROM gastos_generales")).scalar_one()
    )
    utilidad_neta_real = total_profit - total_gastos
    return total_profit, total_gastos, utilidad_neta_real


def load_weekly_profitability_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        ventas = session.execute(
            select(Venta.fecha, Venta.ganancia).where(Venta.fecha.is_not(None))
        ).all()
        if not ventas:
            return pd.DataFrame(columns=["semana", "inicio_semana", "ganancia_total"])

        df = pd.DataFrame(
            [{"fecha": fecha, "ganancia": float(ganancia or 0)} for fecha, ganancia in ventas]
        )
        df["fecha"] = pd.to_datetime(df["fecha"])
        periodo_semanal = df["fecha"].dt.to_period("W")
        df["semana"] = periodo_semanal.astype(str)
        df["inicio_semana"] = periodo_semanal.apply(lambda p: p.start_time.date())

        resumen = (
            df.groupby(["semana", "inicio_semana"], as_index=False)["ganancia"]
            .sum()
            .rename(columns={"ganancia": "ganancia_total"})
            .sort_values("ganancia_total", ascending=False)
        )
        resumen["ganancia_total"] = resumen["ganancia_total"].round(2)
        return resumen.reset_index(drop=True)
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular la rentabilidad semanal: {exc}") from exc
    finally:
        session.close()


def load_product_margin_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        ventas = session.execute(
            select(Venta.producto, Venta.cantidad, Venta.costo, Venta.precio_venta, Venta.ganancia)
        ).all()
        if not ventas:
            return pd.DataFrame(
                columns=[
                    "producto",
                    "unidades_vendidas",
                    "costo_total",
                    "ingresos_total",
                    "ganancia_total",
                    "margen_pct",
                ]
            )

        producto_map: dict[str, dict[str, float]] = {}
        for producto, cantidad, costo, precio_venta, ganancia in ventas:
            nombre = str(producto or "Sin producto").strip() or "Sin producto"
            registro = producto_map.setdefault(
                nombre,
                {"unidades_vendidas": 0, "costo_total": 0.0, "ingresos_total": 0.0, "ganancia_total": 0.0},
            )
            registro["unidades_vendidas"] += int(cantidad or 0)
            registro["costo_total"] += float(costo or 0)
            registro["ingresos_total"] += float(precio_venta or 0)
            registro["ganancia_total"] += float(ganancia or 0)

        rows = []
        for nombre, registro in producto_map.items():
            margen = (
                registro["ganancia_total"] / registro["ingresos_total"] * 100
                if registro["ingresos_total"]
                else 0.0
            )
            rows.append(
                {
                    "producto": nombre,
                    "unidades_vendidas": int(registro["unidades_vendidas"]),
                    "costo_total": round(registro["costo_total"], 2),
                    "ingresos_total": round(registro["ingresos_total"], 2),
                    "ganancia_total": round(registro["ganancia_total"], 2),
                    "margen_pct": round(margen, 2),
                }
            )

        return pd.DataFrame(rows).sort_values("ganancia_total", ascending=False).reset_index(drop=True)
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular el margen por producto: {exc}") from exc
    finally:
        session.close()


def load_top_products_dataframe(limit: int = 10) -> pd.DataFrame:
    session = get_session()
    try:
        rows = session.execute(
            select(
                Venta.producto,
                func.coalesce(func.sum(Venta.cantidad), 0).label("unidades_vendidas"),
                func.coalesce(func.sum(Venta.precio_venta), 0).label("ingresos_total"),
            )
            .group_by(Venta.producto)
            .order_by(func.coalesce(func.sum(Venta.cantidad), 0).desc())
            .limit(limit)
        ).all()
        return pd.DataFrame(
            [
                {
                    "producto": producto or "Sin producto",
                    "unidades_vendidas": int(unidades or 0),
                    "ingresos_total": round(float(ingresos or 0), 2),
                }
                for producto, unidades, ingresos in rows
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular el ranking de productos: {exc}") from exc
    finally:
        session.close()


def load_top_clients_dataframe(limit: int = 10) -> pd.DataFrame:
    session = get_session()
    try:
        rows = session.execute(
            select(
                Venta.cliente,
                func.count(Venta.id).label("compras_realizadas"),
                func.coalesce(func.sum(Venta.precio_venta), 0).label("total_comprado"),
            )
            .group_by(Venta.cliente)
            .order_by(func.coalesce(func.sum(Venta.precio_venta), 0).desc())
            .limit(limit)
        ).all()
        return pd.DataFrame(
            [
                {
                    "cliente": cliente,
                    "compras_realizadas": int(compras or 0),
                    "total_comprado": round(float(total or 0), 2),
                }
                for cliente, compras, total in rows
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular el ranking de clientes: {exc}") from exc
    finally:
        session.close()


def load_out_of_stock_demand_dataframe() -> pd.DataFrame:
    session = get_session()
    try:
        demanda_subquery = (
            select(
                Venta.producto.label("producto"),
                func.coalesce(func.sum(Venta.cantidad), 0).label("demanda_historica"),
            )
            .group_by(Venta.producto)
            .subquery()
        )

        rows = session.execute(
            select(
                Producto.nombre,
                func.coalesce(demanda_subquery.c.demanda_historica, 0).label("demanda_historica"),
            )
            .select_from(Producto)
            .outerjoin(demanda_subquery, Producto.nombre == demanda_subquery.c.producto)
            .where(Producto.stock == 0)
            .order_by(func.coalesce(demanda_subquery.c.demanda_historica, 0).desc())
        ).all()

        return pd.DataFrame(
            [
                {"nombre": nombre, "demanda_historica": int(demanda or 0)}
                for nombre, demanda in rows
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo calcular los productos agotados con demanda: {exc}") from exc
    finally:
        session.close()
