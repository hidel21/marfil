-- DDL de la revision 0001, congelado.
--
-- Generado una sola vez desde Base.metadata y validado contra Postgres 18 antes de
-- congelarlo. Va literal y no reconstruido desde los modelos a proposito: una
-- migracion tiene que producir el mismo esquema aunque los modelos evolucionen.
--
-- No incluye: extensiones ni CREATE TYPE (los emite la migracion antes de este
-- archivo), las tablas que ya existian en la base viva (productos, ventas, pagos,
-- socios, importaciones, filas_importadas), ni el bloque de oferta
-- (proveedores, lotes_compra, compras, pagos_compra, gastos), que se difiere a
-- 0009 para que Streamlit conserve sus tablas legacy durante la convivencia.

CREATE TABLE conciliaciones (
	id SERIAL NOT NULL,
	ejecutado_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	tipo VARCHAR(32) NOT NULL,
	filas_revisadas INTEGER DEFAULT '0' NOT NULL,
	filas_descuadradas INTEGER DEFAULT '0' NOT NULL,
	ok BOOLEAN NOT NULL,
	detalle JSONB,
	CONSTRAINT pk_conciliaciones PRIMARY KEY (id)
);

CREATE INDEX ix_conciliaciones_tipo_fecha ON conciliaciones (tipo, ejecutado_at);

CREATE TABLE jobs_ejecuciones (
	id SERIAL NOT NULL,
	nombre VARCHAR(64) NOT NULL,
	inicio TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	fin TIMESTAMP WITH TIME ZONE,
	estado VARCHAR(16) DEFAULT 'corriendo' NOT NULL,
	filas_afectadas INTEGER DEFAULT '0' NOT NULL,
	detalle JSONB,
	error TEXT,
	CONSTRAINT pk_jobs_ejecuciones PRIMARY KEY (id)
);

CREATE INDEX ix_jobs_ejecuciones_nombre_inicio ON jobs_ejecuciones (nombre, inicio);

CREATE TABLE clientes (
	id SERIAL NOT NULL,
	nombre VARCHAR(160) NOT NULL,
	nombre_normalizado VARCHAR(160) NOT NULL,
	telefono_e164 VARCHAR(20),
	telefono_verificado BOOLEAN DEFAULT 'false' NOT NULL,
	email CITEXT,
	nivel_precio nivel_precio DEFAULT 'publico' NOT NULL,
	plazo_credito_dias SMALLINT,
	es_socio BOOLEAN DEFAULT 'false' NOT NULL,
	estado estado_registro DEFAULT 'activo' NOT NULL,
	fusionado_en_cliente_id INTEGER,
	notas TEXT,
	creado_por_usuario_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_clientes PRIMARY KEY (id),
	CONSTRAINT fk_clientes_fusionado_en_cliente_id_clientes FOREIGN KEY(fusionado_en_cliente_id) REFERENCES clientes (id)
);

CREATE INDEX ix_clientes_nombre_trgm ON clientes USING gin (nombre_normalizado gin_trgm_ops);

CREATE UNIQUE INDEX uq_clientes_nombre_normalizado ON clientes (nombre_normalizado) WHERE estado <> 'fusionado';

CREATE INDEX ix_clientes_telefono ON clientes (telefono_e164) WHERE telefono_e164 IS NOT NULL;

CREATE TABLE tasas_cambio (
	id SERIAL NOT NULL,
	fecha DATE NOT NULL,
	tipo tipo_tasa NOT NULL,
	valor NUMERIC(18, 8) NOT NULL,
	origen origen_tasa NOT NULL,
	confianza confianza_dato DEFAULT 'alta' NOT NULL,
	capturado_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	payload JSONB,
	CONSTRAINT pk_tasas_cambio PRIMARY KEY (id),
	CONSTRAINT uq_tasas_cambio_fecha_tipo UNIQUE (fecha, tipo),
	CONSTRAINT ck_tasas_cambio_valor_positivo CHECK (valor > 0)
);

CREATE INDEX ix_tasas_cambio_tipo_fecha ON tasas_cambio (tipo, fecha);

CREATE TABLE clientes_alias (
	id SERIAL NOT NULL,
	cliente_id INTEGER NOT NULL,
	alias VARCHAR(160) NOT NULL,
	alias_normalizado VARCHAR(160) NOT NULL,
	origen VARCHAR(32) NOT NULL,
	CONSTRAINT pk_clientes_alias PRIMARY KEY (id),
	CONSTRAINT fk_clientes_alias_cliente_id_clientes FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE,
	CONSTRAINT uq_clientes_alias_alias_normalizado UNIQUE (alias_normalizado)
);

CREATE TABLE usuarios (
	id SERIAL NOT NULL,
	email CITEXT NOT NULL,
	nombre VARCHAR(120) NOT NULL,
	password_hash TEXT NOT NULL,
	rol rol_usuario NOT NULL,
	activo BOOLEAN DEFAULT 'true' NOT NULL,
	telefono_e164 VARCHAR(20),
	permisos_extra JSONB DEFAULT '{}' NOT NULL,
	debe_cambiar_password BOOLEAN DEFAULT 'true' NOT NULL,
	ultimo_login_at TIMESTAMP WITH TIME ZONE,
	cliente_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_usuarios PRIMARY KEY (id),
	CONSTRAINT ck_usuarios_afiliado_exige_cliente CHECK (rol <> 'afiliado' OR cliente_id IS NOT NULL),
	CONSTRAINT uq_usuarios_email UNIQUE (email),
	CONSTRAINT fk_usuarios_cliente_id_clientes FOREIGN KEY(cliente_id) REFERENCES clientes (id)
);

CREATE INDEX ix_usuarios_rol ON usuarios (rol);

CREATE TABLE auditoria (
	id SERIAL NOT NULL,
	ocurrido_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	actor_tipo actor_auditoria DEFAULT 'sistema' NOT NULL,
	usuario_id INTEGER,
	accion accion_auditoria NOT NULL,
	tabla VARCHAR(48) NOT NULL,
	registro_id TEXT NOT NULL,
	antes JSONB,
	despues JSONB,
	campos_cambiados TEXT[],
	motivo TEXT,
	request_id UUID,
	ip INET,
	user_agent TEXT,
	CONSTRAINT pk_auditoria PRIMARY KEY (id),
	CONSTRAINT fk_auditoria_usuario_id_usuarios FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_auditoria_entidad ON auditoria (tabla, registro_id, ocurrido_at);

CREATE INDEX ix_auditoria_con_motivo ON auditoria (ocurrido_at) WHERE motivo IS NOT NULL;

CREATE INDEX ix_auditoria_ocurrido_at_brin ON auditoria USING brin (ocurrido_at);

CREATE INDEX ix_auditoria_usuario ON auditoria (usuario_id, ocurrido_at);

CREATE TABLE parametros_precio (
	id SERIAL NOT NULL,
	clave VARCHAR(48) NOT NULL,
	valor NUMERIC(12, 6) NOT NULL,
	vigencia DATERANGE NOT NULL,
	motivo TEXT,
	creado_por_usuario_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_parametros_precio PRIMARY KEY (id),
	CONSTRAINT uq_parametros_precio_sin_solape EXCLUDE USING gist (clave WITH =, vigencia WITH &&),
	CONSTRAINT ck_parametros_precio_vigencia_no_vacia CHECK (NOT isempty(vigencia)),
	CONSTRAINT fk_parametros_precio_creado_por_usuario_id_usuarios FOREIGN KEY(creado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_parametros_precio_clave ON parametros_precio (clave);

CREATE TABLE configuracion (
	clave VARCHAR(64) NOT NULL,
	valor JSONB NOT NULL,
	es_secreto BOOLEAN DEFAULT 'false' NOT NULL,
	descripcion TEXT,
	actualizado_por_usuario_id INTEGER,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_configuracion PRIMARY KEY (clave),
	CONSTRAINT fk_configuracion_actualizado_por_usuario_id_usuarios FOREIGN KEY(actualizado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE TABLE plantillas_mensaje (
	clave VARCHAR(48) NOT NULL,
	nombre VARCHAR(120) NOT NULL,
	canal VARCHAR(24) DEFAULT 'whatsapp' NOT NULL,
	cuerpo TEXT NOT NULL,
	variables JSONB,
	version SMALLINT DEFAULT '1' NOT NULL,
	activa BOOLEAN DEFAULT 'true' NOT NULL,
	actualizado_por_usuario_id INTEGER,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_plantillas_mensaje PRIMARY KEY (clave),
	CONSTRAINT fk_plantillas_mensaje_actualizado_por_usuario_id_usuarios FOREIGN KEY(actualizado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE TABLE refresh_tokens (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	usuario_id INTEGER NOT NULL,
	token_hash TEXT NOT NULL,
	familia_id UUID NOT NULL,
	expira_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revocado_at TIMESTAMP WITH TIME ZONE,
	ip INET,
	user_agent TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
	CONSTRAINT fk_refresh_tokens_usuario_id_usuarios FOREIGN KEY(usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE,
	CONSTRAINT uq_refresh_tokens_token_hash UNIQUE (token_hash)
);

CREATE INDEX ix_refresh_tokens_familia_id ON refresh_tokens (familia_id);

CREATE INDEX ix_refresh_tokens_vigentes ON refresh_tokens (usuario_id) WHERE revocado_at IS NULL;

CREATE TABLE productos_alias (
	id SERIAL NOT NULL,
	producto_id INTEGER NOT NULL,
	alias VARCHAR(200) NOT NULL,
	alias_normalizado VARCHAR(200) NOT NULL,
	es_original BOOLEAN DEFAULT 'false' NOT NULL,
	origen VARCHAR(32) NOT NULL,
	CONSTRAINT pk_productos_alias PRIMARY KEY (id),
	CONSTRAINT uq_productos_alias_norm UNIQUE (alias_normalizado, es_original),
	CONSTRAINT fk_productos_alias_producto_id_productos FOREIGN KEY(producto_id) REFERENCES productos (id) ON DELETE CASCADE
);

CREATE TABLE movimientos_stock (
	id SERIAL NOT NULL,
	producto_id INTEGER NOT NULL,
	ocurrido_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	tipo tipo_movimiento_stock NOT NULL,
	cantidad INTEGER NOT NULL,
	saldo_despues INTEGER NOT NULL,
	referencia_tabla VARCHAR(32),
	referencia_id INTEGER,
	usuario_id INTEGER,
	notas TEXT,
	CONSTRAINT pk_movimientos_stock PRIMARY KEY (id),
	CONSTRAINT ck_movimientos_stock_cantidad_no_cero CHECK (cantidad <> 0),
	CONSTRAINT fk_movimientos_stock_producto_id_productos FOREIGN KEY(producto_id) REFERENCES productos (id),
	CONSTRAINT fk_movimientos_stock_usuario_id_usuarios FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_movimientos_stock_producto ON movimientos_stock (producto_id, ocurrido_at);

CREATE TABLE plantillas_version (
	id SERIAL NOT NULL,
	plantilla_clave VARCHAR(48) NOT NULL,
	version SMALLINT NOT NULL,
	cuerpo TEXT NOT NULL,
	guardado_por_usuario_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_plantillas_version PRIMARY KEY (id),
	CONSTRAINT fk_plantillas_version_plantilla_clave_plantillas_mensaje FOREIGN KEY(plantilla_clave) REFERENCES plantillas_mensaje (clave) ON DELETE CASCADE,
	CONSTRAINT fk_plantillas_version_guardado_por_usuario_id_usuarios FOREIGN KEY(guardado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_plantillas_version_clave ON plantillas_version (plantilla_clave, version);

CREATE TABLE venta_items (
	id SERIAL NOT NULL,
	venta_id INTEGER NOT NULL,
	linea SMALLINT NOT NULL,
	producto_id INTEGER NOT NULL,
	descripcion_libre VARCHAR(200),
	cantidad INTEGER NOT NULL,
	precio_unitario_usd NUMERIC(14, 2) NOT NULL,
	costo_unitario_usd NUMERIC(14, 2) DEFAULT '0' NOT NULL,
	precio_lista_usd NUMERIC(14, 2),
	subtotal_usd NUMERIC(14, 2) GENERATED ALWAYS AS (cantidad * precio_unitario_usd) STORED NOT NULL,
	ganancia_usd NUMERIC(14, 2) GENERATED ALWAYS AS (cantidad * (precio_unitario_usd - costo_unitario_usd)) STORED NOT NULL,
	desviacion_pct NUMERIC(7, 4) GENERATED ALWAYS AS (CASE WHEN precio_lista_usd IS NULL OR precio_lista_usd = 0 THEN NULL ELSE (precio_unitario_usd - precio_lista_usd) / precio_lista_usd END) STORED,
	motivo_desviacion TEXT,
	aprobado_por_usuario_id INTEGER,
	sobreventa BOOLEAN DEFAULT 'false' NOT NULL,
	CONSTRAINT pk_venta_items PRIMARY KEY (id),
	CONSTRAINT uq_venta_items_venta_id_linea UNIQUE (venta_id, linea),
	CONSTRAINT ck_venta_items_cantidad_positiva CHECK (cantidad > 0),
	CONSTRAINT ck_venta_items_precio_no_negativo CHECK (precio_unitario_usd >= 0),
	CONSTRAINT ck_venta_items_costo_no_negativo CHECK (costo_unitario_usd >= 0),
	CONSTRAINT fk_venta_items_venta_id_ventas FOREIGN KEY(venta_id) REFERENCES ventas (id) ON DELETE CASCADE,
	CONSTRAINT fk_venta_items_producto_id_productos FOREIGN KEY(producto_id) REFERENCES productos (id),
	CONSTRAINT fk_venta_items_aprobado_por_usuario_id_usuarios FOREIGN KEY(aprobado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_venta_items_producto ON venta_items (producto_id);

CREATE TABLE cuotas (
	id SERIAL NOT NULL,
	venta_id INTEGER NOT NULL,
	numero SMALLINT NOT NULL,
	fecha_vencimiento DATE NOT NULL,
	monto_usd NUMERIC(14, 2) NOT NULL,
	monto_abonado_usd NUMERIC(14, 2) DEFAULT '0' NOT NULL,
	implicita BOOLEAN DEFAULT 'false' NOT NULL,
	CONSTRAINT pk_cuotas PRIMARY KEY (id),
	CONSTRAINT uq_cuotas_venta_id_numero UNIQUE (venta_id, numero),
	CONSTRAINT ck_cuotas_monto_positivo CHECK (monto_usd > 0),
	CONSTRAINT ck_cuotas_abonado_no_negativo CHECK (monto_abonado_usd >= 0),
	CONSTRAINT ck_cuotas_abonado_no_supera_monto CHECK (monto_abonado_usd <= monto_usd),
	CONSTRAINT fk_cuotas_venta_id_ventas FOREIGN KEY(venta_id) REFERENCES ventas (id) ON DELETE CASCADE
);

CREATE INDEX ix_cuotas_impagas ON cuotas (fecha_vencimiento) WHERE monto_abonado_usd < monto_usd;

CREATE TABLE enlaces_importacion (
	id SERIAL NOT NULL,
	fila_id INTEGER NOT NULL,
	tabla_destino VARCHAR(48) NOT NULL,
	registro_id INTEGER NOT NULL,
	metodo metodo_enlace NOT NULL,
	score NUMERIC(5, 4),
	confianza confianza_dato DEFAULT 'alta' NOT NULL,
	revisado_at TIMESTAMP WITH TIME ZONE,
	revisado_por_usuario_id INTEGER,
	notas TEXT,
	CONSTRAINT pk_enlaces_importacion PRIMARY KEY (id),
	CONSTRAINT uq_enlaces_importacion_destino UNIQUE (fila_id, tabla_destino, registro_id),
	CONSTRAINT fk_enlaces_importacion_fila_id_filas_importadas FOREIGN KEY(fila_id) REFERENCES filas_importadas (id) ON DELETE CASCADE,
	CONSTRAINT fk_enlaces_importacion_revisado_por_usuario_id_usuarios FOREIGN KEY(revisado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_enlaces_importacion_destino ON enlaces_importacion (tabla_destino, registro_id);

CREATE INDEX ix_enlaces_importacion_revision ON enlaces_importacion (confianza) WHERE confianza = 'baja';

CREATE TABLE recordatorios (
	id SERIAL NOT NULL,
	cliente_id INTEGER NOT NULL,
	venta_id INTEGER,
	cuota_id INTEGER,
	ventas_incluidas INTEGER[],
	canal VARCHAR(24) DEFAULT 'whatsapp_manual' NOT NULL,
	plantilla_clave VARCHAR(48) NOT NULL,
	plantilla_version SMALLINT NOT NULL,
	cuerpo_renderizado TEXT NOT NULL,
	destino VARCHAR(64),
	saldo_usd_al_generar NUMERIC(14, 2) NOT NULL,
	tasa_al_generar NUMERIC(18, 8),
	dias_mora_al_generar INTEGER DEFAULT '0' NOT NULL,
	estado estado_recordatorio DEFAULT 'borrador' NOT NULL,
	motivo_omision motivo_omision,
	generado_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	enviado_at TIMESTAMP WITH TIME ZONE,
	generado_por_usuario_id INTEGER,
	marcado_enviado_por_usuario_id INTEGER,
	proveedor VARCHAR(32),
	proveedor_mensaje_id VARCHAR(128),
	error TEXT,
	dia_generacion DATE GENERATED ALWAYS AS ((generado_at AT TIME ZONE 'UTC')::date) STORED NOT NULL,
	CONSTRAINT pk_recordatorios PRIMARY KEY (id),
	CONSTRAINT fk_recordatorios_cliente_id_clientes FOREIGN KEY(cliente_id) REFERENCES clientes (id),
	CONSTRAINT fk_recordatorios_venta_id_ventas FOREIGN KEY(venta_id) REFERENCES ventas (id),
	CONSTRAINT fk_recordatorios_cuota_id_cuotas FOREIGN KEY(cuota_id) REFERENCES cuotas (id),
	CONSTRAINT fk_recordatorios_plantilla_clave_plantillas_mensaje FOREIGN KEY(plantilla_clave) REFERENCES plantillas_mensaje (clave),
	CONSTRAINT fk_recordatorios_generado_por_usuario_id_usuarios FOREIGN KEY(generado_por_usuario_id) REFERENCES usuarios (id),
	CONSTRAINT fk_recordatorios_marcado_enviado_por_usuario_id_usuarios FOREIGN KEY(marcado_enviado_por_usuario_id) REFERENCES usuarios (id)
);

CREATE INDEX ix_recordatorios_cliente ON recordatorios (cliente_id, generado_at);

CREATE UNIQUE INDEX uq_recordatorios_dia ON recordatorios (venta_id, canal, dia_generacion) WHERE estado <> 'omitido';

CREATE INDEX ix_recordatorios_estado ON recordatorios (estado);

ALTER TABLE clientes ADD CONSTRAINT fk_clientes_creado_por_usuario_id_usuarios FOREIGN KEY(creado_por_usuario_id) REFERENCES usuarios (id);
