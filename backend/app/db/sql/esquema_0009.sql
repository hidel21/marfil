-- DDL de la revision 0009, congelado.
--
-- Generado una sola vez desde Base.metadata y validado contra Postgres 18 antes de
-- congelarlo. Va literal y no reconstruido desde los modelos a proposito: una
-- migracion tiene que producir el mismo esquema aunque los modelos evolucionen.
--
-- El bloque de oferta. Se separa de 0001 porque Streamlit sigue escribiendo en
-- `proveedores`, `compras`, `pagos_compra` y `gastos_generales` durante la
-- convivencia, y esos nombres colisionan con la forma nueva.

CREATE TABLE proveedores (
	id SERIAL NOT NULL,
	nombre VARCHAR(200) NOT NULL,
	nombre_normalizado VARCHAR(200) NOT NULL,
	contacto VARCHAR(200),
	telefono_e164 VARCHAR(20),
	telefono VARCHAR(50),
	email VARCHAR(200),
	estado estado_registro DEFAULT 'activo' NOT NULL,
	notas TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_proveedores PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_proveedores_nombre_normalizado ON proveedores (nombre_normalizado) WHERE estado <> 'fusionado';

CREATE TABLE lotes_compra (
	id SERIAL NOT NULL,
	codigo VARCHAR(64) NOT NULL,
	fecha DATE,
	proveedor_id INTEGER,
	canal canal_pago,
	subtotal_declarado_usd NUMERIC(14, 2),
	subtotal_calculado_usd NUMERIC(14, 2) DEFAULT '0' NOT NULL,
	diferencia_usd NUMERIC(14, 2) GENERATED ALWAYS AS (COALESCE(subtotal_declarado_usd, 0) - subtotal_calculado_usd) STORED,
	texto_original TEXT,
	notas TEXT,
	importacion_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_lotes_compra PRIMARY KEY (id),
	CONSTRAINT uq_lotes_compra_codigo UNIQUE (codigo),
	CONSTRAINT fk_lotes_compra_proveedor_id_proveedores FOREIGN KEY(proveedor_id) REFERENCES proveedores (id),
	CONSTRAINT fk_lotes_compra_importacion_id_importaciones FOREIGN KEY(importacion_id) REFERENCES importaciones (id)
);

CREATE INDEX ix_lotes_compra_fecha ON lotes_compra (fecha);

CREATE TABLE compras (
	id SERIAL NOT NULL,
	lote_id INTEGER NOT NULL,
	producto_id INTEGER,
	descripcion_libre VARCHAR(200) NOT NULL,
	cantidad INTEGER DEFAULT '1' NOT NULL,
	costo_unitario_usd NUMERIC(14, 2) NOT NULL,
	monto_bs NUMERIC(18, 2),
	tasa_aplicada NUMERIC(18, 8),
	texto_original TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_compras PRIMARY KEY (id),
	CONSTRAINT ck_compras_cantidad_positiva CHECK (cantidad > 0),
	CONSTRAINT ck_compras_costo_no_negativo CHECK (costo_unitario_usd >= 0),
	CONSTRAINT fk_compras_lote_id_lotes_compra FOREIGN KEY(lote_id) REFERENCES lotes_compra (id) ON DELETE CASCADE,
	CONSTRAINT fk_compras_producto_id_productos FOREIGN KEY(producto_id) REFERENCES productos (id)
);

CREATE INDEX ix_compras_producto ON compras (producto_id);

CREATE INDEX ix_compras_lote ON compras (lote_id);

CREATE TABLE pagos_compra (
	id SERIAL NOT NULL,
	lote_id INTEGER NOT NULL,
	fecha DATE NOT NULL,
	monto_usd NUMERIC(14, 2) NOT NULL,
	monto_bs NUMERIC(18, 2),
	tasa_aplicada NUMERIC(18, 8),
	canal canal_pago,
	referencia VARCHAR(64),
	registrado_por_usuario_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_pagos_compra PRIMARY KEY (id),
	CONSTRAINT fk_pagos_compra_lote_id_lotes_compra FOREIGN KEY(lote_id) REFERENCES lotes_compra (id),
	CONSTRAINT fk_pagos_compra_registrado_por_usuario_id_usuarios FOREIGN KEY(registrado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE TABLE gastos (
	id SERIAL NOT NULL,
	fecha DATE NOT NULL,
	lote_id INTEGER,
	categoria VARCHAR(64) NOT NULL,
	descripcion VARCHAR(300) NOT NULL,
	monto_usd NUMERIC(14, 2) NOT NULL,
	monto_bs NUMERIC(18, 2),
	tasa_aplicada NUMERIC(18, 8),
	canal canal_pago,
	texto_original TEXT,
	notas TEXT,
	creado_por_usuario_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_gastos PRIMARY KEY (id),
	CONSTRAINT fk_gastos_lote_id_lotes_compra FOREIGN KEY(lote_id) REFERENCES lotes_compra (id),
	CONSTRAINT fk_gastos_creado_por_usuario_id_usuarios FOREIGN KEY(creado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_gastos_fecha ON gastos (fecha);
