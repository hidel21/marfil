# Despliegue de Marfil

La ruta preparada en este repositorio cuesta **USD 0 al mes para una puesta en marcha
de bajo tráfico**:

```text
Navegador ──HTTPS──> Render (Next estático + FastAPI) ──TLS──> Neon PostgreSQL
                          │
                          └── GitHub Actions: jobs y respaldos cifrados
```

Frontend y API se publican en el mismo dominio. Esto evita cookies de terceros, CORS
innecesario y dos arranques en frío. El contenedor compila Next, sirve sus archivos
desde FastAPI, aplica las migraciones de Alembic al arrancar y conserva todo dato en
Neon; el disco local de Render no se usa como almacenamiento.

## Límites que debes conocer

- **Render Free** apaga el servicio tras 15 minutos sin tráfico. La primera apertura
  puede tardar cerca de un minuto. Render describe el plan gratuito como apto para
  pruebas/hobby, no como infraestructura de producción. Para eliminar ese arranque y
  tener soporte operativo, el primer upgrade futuro es la instancia web de pago.
- **Neon Free** no vence: actualmente incluye 0,5 GB y 100 CU-horas por proyecto al
  mes, con suspensión automática cuando no hay consultas. Es suficiente para el
  volumen actual de Marfil, pero hay que vigilar Storage y Compute en su panel.
- No se usa Vercel Hobby: aunque técnicamente ejecutaría Next, sus condiciones limitan
  el plan gratuito a uso personal/no comercial y Marfil es una operación comercial.

Referencias oficiales: [Render Free](https://render.com/docs/free),
[Blueprints de Render](https://render.com/docs/blueprint-spec),
[Neon Free](https://neon.com/pricing) y
[Vercel Hobby](https://vercel.com/docs/plans/hobby).

## 1. Publicar el repositorio

Sube este proyecto a un repositorio **privado** de GitHub. No subas `.env`,
`.streamlit/secrets.toml`, dumps ni contraseñas; ya están excluidos por `.gitignore`.

Antes de publicar, la verificación local completa es:

```bash
cd backend
ruff check .
pytest -q

cd ../frontend
npm ci
npm run check
```

El workflow `.github/workflows/ci.yml` repite esa validación en cada push.

## 2. Crear la base gratuita en Neon

1. Crea una cuenta y un proyecto en [Neon](https://console.neon.tech/).
2. Elige una región de EE. UU. Este cercana a `virginia` de Render.
3. En **Connect**, copia la cadena de conexión directa con `sslmode=require`. El
   backend convierte automáticamente `postgresql://` a `postgresql+psycopg://`.
4. Guarda esa cadena: será `DATABASE_URL` en Render y `MARFIL_DATABASE_URL` en GitHub.

Para una instalación nueva no ejecutes SQL a mano: el contenedor aplica
`alembic upgrade head` automáticamente.

### Si vas a conservar la base actual

Pon el sistema anterior en solo lectura y crea un dump antes del primer despliegue:

```bash
pg_dump --format=custom --no-owner --no-acl \
  "postgresql://odoo:odoo@localhost:5432/marfil" \
  --file marfil-antes-del-corte.dump

pg_restore --no-owner --no-acl --exit-on-error \
  --dbname "postgresql://USUARIO:CLAVE@HOST/neondb?sslmode=require" \
  marfil-antes-del-corte.dump
```

Después despliega. Alembic leerá la revisión restaurada y aplicará únicamente las
migraciones pendientes, incluida la apertura segura del libro de inventario.

## 3. Crear la aplicación en Render

1. En [Render](https://dashboard.render.com/), selecciona **New → Blueprint**.
2. Conecta el repositorio y deja la ruta de Blueprint en `render.yaml`.
3. Render pedirá los valores marcados `sync: false`:
   - `DATABASE_URL`: la cadena de Neon.
   - `ADMIN_INITIAL_PASSWORD`: una clave inicial larga, única, de al menos 12
     caracteres. Solo activa al admin sembrado si todavía está bloqueado; nunca
     sobrescribe una clave ya elegida.
4. Confirma el despliegue. Render genera `JWT_SECRET` y `JOB_SECRET` de 256 bits.
5. Cuando `/api/salud` esté verde, abre la URL `onrender.com` e inicia sesión con:
   - usuario: `hm@intelli-next.com`
   - clave: el valor de `ADMIN_INITIAL_PASSWORD`.
6. Cambia la clave en **Ajustes → Mi contraseña** y elimina
   `ADMIN_INITIAL_PASSWORD` del panel de Render.

Si Render modifica el nombre `marfil-sistema`, actualiza `CORS_ORIGENES` con la URL
real. Al servirse todo desde el mismo origen, no hace falta agregar otros dominios.

## 4. Activar jobs y respaldo

El servicio gratuito duerme, por lo que APScheduler no puede ser la fuente del reloj.
Los workflows de GitHub despiertan la API y ejecutan trabajos idempotentes.

En **GitHub → Settings → Secrets and variables → Actions** crea:

| Secreto | Valor |
|---|---|
| `MARFIL_URL` | `https://marfil-sistema.onrender.com` (sin `/` final) |
| `MARFIL_JOB_SECRET` | el `JOB_SECRET` generado y visible en Render |
| `MARFIL_DATABASE_URL` | cadena directa de Neon |
| `MARFIL_BACKUP_KEY` | frase aleatoria de 32+ caracteres, distinta a las anteriores |

Luego abre **Actions** y ejecuta manualmente una vez:

- `Operación diaria`: captura tasa, concilia libros y limpia sesiones.
- `Respaldo cifrado`: produce un dump cifrado y privado, retenido 14 días.

Para restaurar un artefacto descargado:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in marfil.dump.enc -out marfil.dump \
  -pass env:MARFIL_BACKUP_KEY
pg_restore --clean --if-exists --no-owner --no-acl \
  --dbname "$DATABASE_URL" marfil.dump
```

GitHub documenta los cron con zona IANA y el uso de secretos en
[Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
y [Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## 5. Puesta en marcha dentro de Marfil

En este orden:

1. **Ajustes → Datos de pago:** completa banco, documento y teléfono. Hasta entonces
   los recordatorios están bloqueados deliberadamente.
2. **Ajustes → Usuarios:** crea a cada socio/vendedor y entrega su código de un solo
   uso. Cada persona elige su contraseña.
3. **Clientes:** carga teléfonos de deudores.
4. **Productos → Revisar pendientes:** completa costos y niveles.
5. **Ajustes → Tasas:** confirma el snapshot del día.
6. **Auditoría:** exige que ventas, pagos y stock indiquen “cuadra”.
7. Registra una venta de prueba, un abono, descarga su recibo PDF y revierte ambos
   datos de prueba si no pertenecen a la operación real.

## 6. Verificación posterior a cada despliegue

```bash
curl --fail https://TU-DOMINIO/api/salud
```

Debe devolver `ok: true`, `revision_db: "0010"` y `descuadres: 0`. Revisa además en
la interfaz **Ajustes → Automatizaciones** que las ejecuciones diarias estén en `ok`.

## Cuándo dejar el plan gratuito

Pasa el servicio web de Render a una instancia siempre activa antes de depender de
Marfil en caja si el minuto de arranque es inaceptable. Pasa Neon a un plan con una
ventana de restauración mayor antes de superar 0,5 GB o cuando el volumen de ventas
justifique recuperación con SLA. No hace falta cambiar código: solo el plan.
