"""semilla: usuarios, parametros de precio, configuracion y plantillas

Datos, no estructura. Lo que entra:

 1. **Un solo usuario: Hidelberg, el superadmin.** Los otros dos socios existen como
    filas de `socios` (para el reparto de utilidad) pero **sin cuenta**: Hidelberg les
    crea el perfil desde la app y ellos cambian la contrasena al entrar. Es lo que
    pidio el dueno, y es mejor que sembrar tres cuentas: no hay direcciones de correo
    inventadas ni cuentas que nadie reclama.

    Se siembra con el hash bloqueado, asi que ni siquiera Hidelberg puede entrar hasta
    fijar su contrasena con `python -m app.cli establecer-password`. Sembrar una
    contrasena conocida seria peor que no sembrar ninguna.

 2. **Los parametros de precio**, versionados con vigencia desde 2026-06-01 (la
    primera venta del libro es del 19/06). Los cuatro primeros salen de la hoja
    `PARAMETROS` del libro v2 y son politica de negocio confirmada por el dueno:
    la ganancia se mide **sobre el costo**, no sobre el precio de venta.

 3. **`configuracion`**, incluida la clave `datos_pago` que mata el bug de los
    `V-XX.XXX.XXX`. Se siembra **vacia a proposito**: el renderizador levanta
    `AJUSTES_PAGO_INCOMPLETOS` mientras falte un campo, asi que no puede existir un
    mensaje renderizable con un placeholder adentro. Hay que completarla desde la
    app antes de poder enviar un solo recordatorio. Eso es el diseno, no un pendiente.

 4. **Las 5 plantillas de mensaje** (backend/seeds/plantillas_mensaje.yaml).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22

"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
import yaml

from alembic import op
from app.core.seguridad import HASH_BLOQUEADO

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIR_SEEDS = Path(__file__).resolve().parents[2] / "seeds"

#: Desde cuando rigen los parametros. La primera venta del libro es del 19/06/2026.
VIGENCIA_DESDE = "2026-06-01"

# (clave, valor, motivo)
PARAMETROS = (
    (
        "GANANCIA_DIVISA",
        "0.70",
        "Politica de precios del libro v2 (hoja PARAMETROS): +70 % sobre el COSTO "
        "cuando el cliente paga en divisa o USDT. precio = costo x 1,70",
    ),
    (
        "GANANCIA_BCV",
        "1.20",
        "Politica de precios del libro v2: +120 % sobre el COSTO cuando el cliente "
        "paga a tasa BCV. precio = costo x 2,20",
    ),
    ("DESC_TEAM", "0.25", "Descuento del equipo sobre la lista de originales"),
    ("DESC_REVENDEDOR", "0.15", "Descuento de revendedores sobre la lista de originales"),
    (
        "PLAZO_CREDITO_DIAS",
        "15",
        "Plazo por defecto de una venta a credito cuando no se define un plan de cuotas",
    ),
    (
        "TOLERANCIA_PRECIO_PCT",
        "0.05",
        "Cuanto puede desviarse el precio cobrado del precio de politica antes de exigir un motivo",
    ),
    (
        "DIAS_POR_VENCER",
        "3",
        "Antelacion del estado 'por vencer': es el unico momento en que un "
        "recordatorio evita la mora en vez de perseguirla",
    ),
    (
        "DIAS_MORA_PARA_MOROSO",
        "15",
        "Dias de atraso desde los que una venta pasa de vencida a morosa",
    ),
    (
        "DIAS_ENTRE_RECORDATORIOS",
        "7",
        "Cooldown entre recordatorios de la misma venta. El indice unico por dia es "
        "la red; esto es la regla de negocio",
    ),
    (
        "MAX_RECORDATORIOS_POR_VENTA_MES",
        "4",
        "Techo mensual de recordatorios por venta",
    ),
    ("TASA_COMISION", "0.10", "Comision del vendedor sobre la ganancia"),
)

CONFIGURACION = (
    (
        "datos_pago",
        {"banco": "", "codigo_banco": "", "documento": "", "telefono": "", "titular": ""},
        False,
        "Datos del pago movil que se insertan en los recordatorios con la variable "
        "{{ datos_pago }}. Se siembra VACIA a proposito: mientras falte un campo, "
        "generar un recordatorio falla. Nunca escribir estos datos en una plantilla.",
    ),
    ("nombre_negocio", {"valor": "Sistema Marfil"}, False, "Nombre que aparece en los mensajes"),
    (
        "proveedor_notificaciones",
        {"valor": "whatsapp_manual"},
        False,
        "whatsapp_manual (link wa.me que el socio abre) | whatsapp_api | twilio. "
        "Cambiar esta clave es todo lo que hace falta para enchufar un proveedor real.",
    ),
    ("zona_horaria", {"valor": "America/Caracas"}, False, "Zona para vencimientos y jobs"),
)

#: Los tres socios, para el reparto de utilidad. Se siembran solo si la tabla esta
#: vacia. **Tener una fila en `socios` no es tener una cuenta**: los perfiles los crea
#: el superadmin desde la app, con las direcciones reales de cada uno.
SOCIOS_FUNDADORES = ("Gregory", "Hidelberg", "Gregor")

#: El superadmin. Es el unico usuario que crea la migracion.
SUPERADMIN_NOMBRE = "Hidelberg"
SUPERADMIN_EMAIL = "hm@intelli-next.com"


def upgrade() -> None:
    conexion = op.get_bind()
    op.execute("SELECT set_config('app.actor_tipo', 'migracion', true)")

    # 1. Los socios como usuarios admin.
    #
    # En la base viva las tres filas de `socios` ya existen (las sembro la app). En
    # una instalacion nueva no, y sin ellas no habria ningun usuario con el que
    # entrar al sistema: se siembran.
    if conexion.execute(sa.text("SELECT count(*) FROM socios")).scalar_one() == 0:
        for nombre in SOCIOS_FUNDADORES:
            conexion.execute(
                sa.text("INSERT INTO socios (nombre) VALUES (:n) ON CONFLICT DO NOTHING"),
                {"n": nombre},
            )

    # Solo el superadmin. Los demas socios quedan como filas de `socios` sin cuenta:
    # el reparto de utilidad no necesita un login, y las cuentas las crea Hidelberg.
    usuario_id = conexion.execute(
        sa.text(
            "INSERT INTO usuarios (email, nombre, password_hash, rol, "
            "debe_cambiar_password) VALUES (:email, :nombre, :hash, 'admin', TRUE) "
            "ON CONFLICT (email) DO UPDATE SET nombre = EXCLUDED.nombre RETURNING id"
        ),
        {"email": SUPERADMIN_EMAIL, "nombre": SUPERADMIN_NOMBRE, "hash": HASH_BLOQUEADO},
    ).scalar_one()
    conexion.execute(
        sa.text("UPDATE socios SET usuario_id = :u WHERE nombre = :n"),
        {"u": usuario_id, "n": SUPERADMIN_NOMBRE},
    )

    # 2. Parámetros de precio
    for clave, valor, motivo in PARAMETROS:
        conexion.execute(
            sa.text(
                "INSERT INTO parametros_precio (clave, valor, vigencia, motivo) "
                "VALUES (:clave, :valor, daterange(:desde, NULL), :motivo)"
            ),
            {"clave": clave, "valor": valor, "desde": VIGENCIA_DESDE, "motivo": motivo},
        )

    # 3. Configuración
    for clave, valor, es_secreto, descripcion in CONFIGURACION:
        conexion.execute(
            sa.text(
                "INSERT INTO configuracion (clave, valor, es_secreto, descripcion) "
                "VALUES (:clave, CAST(:valor AS jsonb), :secreto, :desc) "
                "ON CONFLICT (clave) DO NOTHING"
            ),
            {
                "clave": clave,
                "valor": json.dumps(valor),
                "secreto": es_secreto,
                "desc": descripcion,
            },
        )

    # 4. Plantillas
    ruta = DIR_SEEDS / "plantillas_mensaje.yaml"
    plantillas = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    for plantilla in plantillas:
        conexion.execute(
            sa.text(
                "INSERT INTO plantillas_mensaje (clave, nombre, canal, cuerpo, variables) "
                "VALUES (:clave, :nombre, :canal, :cuerpo, CAST(:vars AS jsonb)) "
                "ON CONFLICT (clave) DO NOTHING"
            ),
            {
                "clave": plantilla["clave"],
                "nombre": plantilla["nombre"],
                "canal": plantilla.get("canal", "whatsapp"),
                "cuerpo": plantilla["cuerpo"],
                "vars": json.dumps(plantilla.get("variables", [])),
            },
        )
        conexion.execute(
            sa.text(
                "INSERT INTO plantillas_version (plantilla_clave, version, cuerpo) "
                "VALUES (:clave, 1, :cuerpo)"
            ),
            {"clave": plantilla["clave"], "cuerpo": plantilla["cuerpo"]},
        )


def downgrade() -> None:
    conexion = op.get_bind()
    op.execute("DELETE FROM plantillas_version")
    op.execute("DELETE FROM plantillas_mensaje")
    op.execute("DELETE FROM configuracion")
    op.execute("DELETE FROM parametros_precio")
    conexion.execute(sa.text("UPDATE socios SET usuario_id = NULL"))
    conexion.execute(sa.text("DELETE FROM usuarios WHERE email = :e"), {"e": SUPERADMIN_EMAIL})
