"""Catálogo, alias y movimientos de stock.

Tres decisiones que vale la pena leer antes de tocar esto:

1. **`costo_usd` es NULLABLE.** El cero-como-desconocido de los 217 productos sin
   costo es lo que dejaba que la lista mostrara `$0,00` como si fuera un precio.

2. **No hay columnas de precio calculado.** `precio_divisa`, `precio_bcv`,
   `precio_team` y `precio_revendedor` se borran: son funciones de `costo_usd` /
   `precio_original_usd` y de los parámetros vigentes, y guardarlas es el mismo
   defecto de "66 valores a mano en columnas calculadas" que encontró la auditoría,
   reproducido en SQL. Se leen de la vista `v_precio_vigente`.

3. **La clave de unicidad es `(nombre_normalizado, es_original)`, nunca el nombre
   solo.** `bharara king` existe en `PRECIOS PERF TOP QUALITY` *y* en `PRECIOS PERF
   ORIGINALES` —de ahí las 3 filas en la base—, y un clon Top Quality y un original
   son SKUs distintos con costos distintos.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._comun import MarcasDeTiempo, enum_pg
from app.models.enums import EstadoProducto, ModeloPrecio, TipoMovimientoStock


class Producto(Base, MarcasDeTiempo):
    __tablename__ = "productos"
    __table_args__ = (
        Index(
            "uq_productos_nombre_es_original",
            "nombre_normalizado",
            "es_original",
            unique=True,
            postgresql_where="estado <> 'fusionado'",
        ),
        Index(
            "ix_productos_por_revisar",
            "estado",
            postgresql_where="estado = 'borrador_por_revisar'",
        ),
        Index(
            "ix_productos_nombre_trgm",
            "nombre_normalizado",
            postgresql_using="gin",
            postgresql_ops={"nombre_normalizado": "gin_trgm_ops"},
        ),
        CheckConstraint(
            "estado <> 'fusionado' OR fusionado_en_producto_id IS NOT NULL",
            name="fusionado_exige_destino",
        ),
        CheckConstraint(
            "modelo_precio <> 'lista' OR precio_original_usd IS NOT NULL",
            name="modelo_lista_exige_precio",
        ),
        CheckConstraint("costo_usd IS NULL OR costo_usd >= 0", name="costo_no_negativo"),
        CheckConstraint("stock_minimo >= 0", name="stock_minimo_no_negativo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre_normalizado: Mapped[str] = mapped_column(String(200), nullable=False)
    es_original: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    modelo_precio: Mapped[ModeloPrecio] = mapped_column(
        enum_pg(ModeloPrecio), nullable=False, server_default=ModeloPrecio.COSTO.value
    )
    #: 'SIN LINEA' | 'LINEA ARABE' | 'LINEA CLASICA O DISENADOR'
    linea: Mapped[str | None] = mapped_column(String(80))
    categoria: Mapped[str | None] = mapped_column(String(80))
    #: NULL = costo desconocido. Nunca 0 para decir "no sé".
    costo_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    #: Entrada de `modelo_precio = 'lista'` (los perfumes originales).
    precio_original_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    #: Caché de `SUM(movimientos_stock.cantidad)`, mantenido por trigger.
    stock: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    stock_minimo: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estado: Mapped[EstadoProducto] = mapped_column(
        enum_pg(EstadoProducto),
        nullable=False,
        server_default=EstadoProducto.ACTIVO.value,
    )
    fusionado_en_producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("productos.id", name="fk_productos_fusionado_en_producto_id_productos")
    )
    #: catalogo | venta_rapida | compra | import
    origen_alta: Mapped[str] = mapped_column(String(24), nullable=False, server_default="catalogo")
    creado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", name="fk_productos_creado_por_usuario_id_usuarios")
    )
    revisado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revisado_por_usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", name="fk_productos_revisado_por_usuario_id_usuarios")
    )
    notas: Mapped[str | None] = mapped_column(Text)

    alias: Mapped[list[ProductoAlias]] = relationship(
        "ProductoAlias", back_populates="producto", cascade="all, delete-orphan"
    )

    @property
    def costo_conocido(self) -> bool:
        return self.costo_usd is not None

    @property
    def necesita_revision(self) -> bool:
        return self.estado == EstadoProducto.BORRADOR_POR_REVISAR


class ProductoAlias(Base):
    """Las 21 grafías del catálogo apuntando al producto sobreviviente.

    `es_original` va en la clave única por la misma razón que en `productos`.
    """

    __tablename__ = "productos_alias"
    __table_args__ = (
        UniqueConstraint("alias_normalizado", "es_original", name="uq_productos_alias_norm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(
        ForeignKey("productos.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    alias_normalizado: Mapped[str] = mapped_column(String(200), nullable=False)
    es_original: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    origen: Mapped[str] = mapped_column(String(32), nullable=False)

    producto: Mapped[Producto] = relationship("Producto", back_populates="alias")


class MovimientoStock(Base):
    """Hace auditable el stock. `productos.stock` pasa a ser un caché de esta tabla.

    Antes el stock era un entero que se sumaba y restaba sin dejar rastro: si no
    cuadraba con la realidad física, no había forma de saber dónde se fue.
    """

    __tablename__ = "movimientos_stock"
    __table_args__ = (
        CheckConstraint("cantidad <> 0", name="cantidad_no_cero"),
        Index("ix_movimientos_stock_producto", "producto_id", "ocurrido_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), nullable=False)
    ocurrido_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tipo: Mapped[TipoMovimientoStock] = mapped_column(enum_pg(TipoMovimientoStock), nullable=False)
    #: Con signo: negativo descuenta.
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_despues: Mapped[int] = mapped_column(Integer, nullable=False)
    referencia_tabla: Mapped[str | None] = mapped_column(String(32))
    referencia_id: Mapped[int | None] = mapped_column(Integer)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    notas: Mapped[str | None] = mapped_column(Text)
