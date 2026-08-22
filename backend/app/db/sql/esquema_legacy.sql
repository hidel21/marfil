-- Las 12 tablas que la app Streamlit creaba con Base.metadata.create_all().
--
-- Existe para que la cadena de migraciones se pueda replayar en una base VACIA
-- (CI, staging, la maquina de otro socio) y no solo sobre la base viva. Sin esto
-- 0001 arranca renombrando `filas_excel` y falla donde esa tabla nunca existio.
--
-- Es la forma ANTERIOR, transcrita del information_schema de produccion el
-- 2026-08-22. No se toca: las revisiones siguientes la evolucionan igual que
-- evolucionan la base real, asi que los dos caminos convergen en el mismo esquema.

CREATE TABLE IF NOT EXISTS productos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL,
    categoria VARCHAR(100),
    costo NUMERIC(10,2) NOT NULL DEFAULT 0,
    precio_divisa NUMERIC(10,2) NOT NULL DEFAULT 0,
    precio_bcv NUMERIC(10,2) NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT 0,
    precio_unitario NUMERIC(10,2) NOT NULL DEFAULT 0,
    precio_original NUMERIC(10,2) NOT NULL DEFAULT 0,
    precio_team NUMERIC(10,2) NOT NULL DEFAULT 0,
    precio_revendedor NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ventas (
    id SERIAL PRIMARY KEY,
    fecha DATE,
    cliente VARCHAR(200) NOT NULL,
    vendedor VARCHAR(50),
    producto VARCHAR(200),
    cantidad INTEGER NOT NULL DEFAULT 1,
    precio_venta NUMERIC(10,2) NOT NULL DEFAULT 0,
    costo NUMERIC(10,2) NOT NULL DEFAULT 0,
    ganancia NUMERIC(10,2) NOT NULL DEFAULT 0,
    moneda VARCHAR(10) NOT NULL DEFAULT 'BCV',
    deuda NUMERIC(10,2) NOT NULL DEFAULT 0,
    estatus VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    total NUMERIC(10,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pagos (
    id SERIAL PRIMARY KEY,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    fecha DATE,
    cliente VARCHAR(200) NOT NULL,
    producto VARCHAR(200),
    monto_bs NUMERIC(10,2) NOT NULL DEFAULT 0,
    monto_usd NUMERIC(10,2) NOT NULL DEFAULT 0,
    referencia VARCHAR(100) NOT NULL,
    tasa_bcv NUMERIC(10,2) NOT NULL DEFAULT 0,
    nro_cuota INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS items_venta (
    id SERIAL PRIMARY KEY,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL,
    precio_unitario NUMERIC(10,2) NOT NULL,
    subtotal NUMERIC(10,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS cuotas (
    id SERIAL PRIMARY KEY,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    numero INTEGER NOT NULL,
    fecha_vencimiento DATE NOT NULL,
    monto NUMERIC(10,2) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'
);

CREATE TABLE IF NOT EXISTS socios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL UNIQUE,
    capital_invertido NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS proveedores (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL,
    contacto VARCHAR(200),
    telefono VARCHAR(50),
    email VARCHAR(200),
    notas VARCHAR(500),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS compras (
    id SERIAL PRIMARY KEY,
    fecha DATE,
    proveedor_id INTEGER NOT NULL REFERENCES proveedores(id),
    proveedor_nombre VARCHAR(200) NOT NULL,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    producto_nombre VARCHAR(200) NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 1,
    costo_unitario NUMERIC(10,2) NOT NULL DEFAULT 0,
    monto_total NUMERIC(10,2) NOT NULL DEFAULT 0,
    monto_pagado NUMERIC(10,2) NOT NULL DEFAULT 0,
    saldo NUMERIC(10,2) NOT NULL DEFAULT 0,
    estatus VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    referencia VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pagos_compra (
    id SERIAL PRIMARY KEY,
    compra_id INTEGER NOT NULL REFERENCES compras(id),
    fecha DATE,
    monto NUMERIC(10,2) NOT NULL DEFAULT 0,
    referencia VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gastos_generales (
    id SERIAL PRIMARY KEY,
    fecha DATE,
    categoria VARCHAR(100) NOT NULL,
    descripcion VARCHAR(500),
    monto NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS importaciones_excel (
    id SERIAL PRIMARY KEY,
    archivo VARCHAR(255) NOT NULL,
    archivo_hash VARCHAR(64) NOT NULL UNIQUE,
    importado_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS filas_excel (
    id SERIAL PRIMARY KEY,
    importacion_id INTEGER NOT NULL REFERENCES importaciones_excel(id),
    "pestaña" VARCHAR(200) NOT NULL,
    numero_fila INTEGER NOT NULL,
    datos JSON NOT NULL
);
