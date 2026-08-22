/**
 * Los tipos de la API.
 *
 * Todo lo que es dinero es `Monto` (string), no `number`: es el contrato del backend
 * y lo que impide que un total se calcule con floats. Ver `lib/dinero.ts`.
 */

import type { Monto } from "./dinero";

export type Rol = "admin" | "vendedor" | "afiliado";

export type Sesion = {
  access_token: string;
  expira_en_segundos: number;
  usuario_id: number;
  nombre: string;
  rol: Rol;
  debe_cambiar_password: boolean;
};

export type Yo = {
  id: number;
  nombre: string;
  email: string;
  rol: Rol;
  cliente_id: number | null;
  debe_cambiar_password: boolean;
  ve_costos: boolean;
};

export type Drill = { endpoint: string; params: Record<string, unknown> };

export type Metrica = {
  clave: string;
  etiqueta: string;
  valor: string | null;
  es_monto: boolean;
  moneda: string | null;
  definicion: string;
  calculado_at: string;
  drill: Drill | null;
};

export type Tramo = {
  clave: string;
  etiqueta: string;
  cantidad: number;
  monto_usd: Monto;
};

export type ResumenCobranza = {
  metricas: Metrica[];
  tramos: Tramo[];
  semaforos: Tramo[];
  calculado_at: string;
};

export type Semaforo = "al_dia" | "por_vencer" | "vencido" | "moroso" | "incobrable";

export type VentaEnCobranza = {
  venta_id: number;
  codigo: string;
  fecha: string;
  producto: string | null;
  total_usd: Monto;
  saldo_usd: Monto;
  fecha_vencimiento: string;
  dias_mora: number;
  semaforo: Semaforo;
  cantidad_abonos: number;
};

export type ClienteEnCobranza = {
  cliente_id: number;
  cliente: string;
  telefono_e164: string | null;
  puede_notificar: boolean;
  es_socio: boolean;
  vendedor: string | null;
  ventas_abiertas: number;
  deuda_usd: Monto;
  dias_mora_maximo: number;
  vencimiento_mas_viejo: string | null;
  ultimo_abono_fecha: string | null;
  ultimo_recordatorio_at: string | null;
  nunca_abono: boolean;
  semaforo: Semaforo;
  etiqueta_semaforo: string;
  ventas: VentaEnCobranza[];
};

export type Severidad = "critica" | "alta" | "media";

export type TarjetaCalidad = {
  clave: string;
  etiqueta: string;
  severidad: Severidad;
  cantidad: number;
  monto_usd: Monto | null;
  explicacion: string;
  accion: string;
  ruta: string;
};

export type DatosPago = {
  campos: Record<string, string>;
  faltantes: string[];
  completo: boolean;
  bloquea_recordatorios: boolean;
  vista_previa: string | null;
  bancos: Array<{ codigo: string; nombre: string }>;
};

export type Cliente = {
  id: number;
  nombre: string;
  telefono_e164: string | null;
  telefono_verificado: boolean;
  email: string | null;
  nivel_precio: string;
  es_socio: boolean;
  notas: string | null;
  plazo_credito_dias: number | null;
  deuda_usd: Monto;
  ventas_abiertas: number;
  dias_mora_maximo: number;
  compras: number;
  alias: string[] | null;
};

export type SugerenciaProducto = {
  producto_id: number;
  nombre: string;
  linea: string | null;
  estado: string;
  stock: number;
  costo_usd: Monto | null;
  precio_politica_usd: Monto | null;
  sin_base_de_precio: boolean;
  coincide_por_alias: string | null;
};

export type Similar = {
  producto_id: number;
  nombre: string;
  puntaje: number;
  ventas: number;
};

export type RespuestaSugerencias = {
  exactos: SugerenciaProducto[];
  similares: Similar[];
  puede_crear: boolean;
  nombre_propuesto: string | null;
};

export type Advertencia = {
  codigo: string;
  mensaje: string;
  bloqueante: boolean;
  exige_admin: boolean;
  sugerencia: string | null;
  detalles: Record<string, string | boolean>;
};

export type LineaCotizada = {
  indice: number;
  producto_id: number;
  producto: string;
  descripcion_libre: string;
  cantidad: number;
  precio_unitario_usd: Monto;
  costo_unitario_usd?: Monto;
  precio_politica_usd: Monto | null;
  precio_otro_nivel_usd: Monto | null;
  subtotal_usd: Monto;
  desviacion_pct: Monto | null;
  stock_actual: number;
  stock_resultante: number;
  sobreventa: boolean;
  motivo: string | null;
  advertencias: Advertencia[];
};

export type Cotizacion = {
  total_usd: Monto;
  costo_usd: Monto | null;
  ganancia_usd: Monto | null;
  plazo_dias: number;
  fecha_vencimiento: string;
  bloqueada: boolean;
  exige_admin: boolean;
  lineas: LineaCotizada[];
};

export type Preparado = {
  cliente_id: number;
  cliente: string;
  telefono_e164: string | null;
  plantilla_clave: string;
  cuerpo: string;
  deuda_usd: Monto;
  dias_mora: number;
  ventas: number[];
  accion: { tipo: "DEEP_LINK" | "ENVIO_SERVIDOR"; url: string | null };
  avisos: string[];
};

export type Omitido = {
  cliente_id: number;
  cliente: string;
  motivo: string;
  detalle: string;
  forzable: boolean;
};

export type LoteRecordatorios = {
  resumen: string;
  preparados: Preparado[];
  omitidos: Omitido[];
};

export type Conciliacion = {
  tipo: string;
  filas_revisadas: number;
  filas_descuadradas: number;
  ok: boolean;
  items: Array<Record<string, unknown>>;
};

export type FugaPrecio = {
  total_lineas: number;
  fuga_total_usd: Monto;
  por_vendedor: Array<{ vendedor: string; lineas: number; fuga_usd: Monto }>;
  items: Array<Record<string, unknown>>;
};

export type Usuario = {
  id: number;
  email: string;
  nombre: string;
  rol: Rol;
  activo: boolean;
  debe_cambiar_password: boolean;
  sin_password: boolean;
  socio_id: number | null;
  cliente_id: number | null;
  ultimo_login_at: string | null;
};

export type UsuarioCreado = {
  usuario_id: number;
  email: string;
  nombre: string;
  rol: Rol;
  codigo_activacion: string;
  expira_at: string;
  instrucciones: string;
};

export type ResumenDashboard = {
  metricas: {
    ventas_mes_usd: Monto;
    cobrado_mes_usd: Monto;
    por_cobrar_usd: Monto;
    clientes_deudores: number;
    stock_bajo: number;
    productos_sin_costo: number;
    ganancia_bruta_mes_usd: Monto;
  };
  actividad: Array<{ fecha: string; ventas_usd: Monto; cobrado_usd: Monto; ventas: number }>;
  top_productos: Array<{ nombre: string; unidades: number; ventas_usd: Monto }>;
  ventas_recientes: Array<{
    id: number;
    codigo: string;
    fecha: string;
    cliente: string;
    total_usd: Monto;
    saldo_usd: Monto;
    estado: string;
  }>;
  dias: number;
};

export type Proveedor = {
  id: number;
  nombre: string;
  contacto: string | null;
  telefono: string | null;
  telefono_e164: string | null;
  email: string | null;
  notas: string | null;
  lotes: number;
  saldo_usd: Monto;
};

export type Compra = {
  lote_id: number;
  codigo: string;
  fecha: string | null;
  proveedor: string | null;
  total_usd: Monto;
  pagado_usd: Monto;
  saldo_usd: Monto;
  diferencia_usd: Monto;
  lineas: number;
  unidades: number;
};

export type Gasto = {
  id: number;
  fecha: string;
  categoria: string;
  descripcion: string;
  monto_usd: Monto;
  monto_bs: Monto | null;
  tasa_aplicada: Monto | null;
  canal: string | null;
  notas: string | null;
  lote: string | null;
};

export type ResumenFinanzas = {
  mes_actual: Record<string, Monto | string>;
  mensual: Array<{
    mes: string;
    ventas_usd: Monto;
    cobrado_usd: Monto;
    costo_vendido_usd: Monto;
    gastos_usd: Monto;
    compras_usd: Monto;
    utilidad_bruta_usd: Monto;
    utilidad_neta_usd: Monto;
  }>;
  cuentas_por_pagar: { por_pagar_usd: Monto; cuentas_abiertas: number };
  inventario: { valor_costo_usd: Monto; unidades: number };
};

export type ResumenSocios = {
  capital_total_usd: Monto;
  utilidad_mes_usd: Monto;
  items: Array<{
    id: number;
    nombre: string;
    capital_invertido: Monto;
    usuario_id: number | null;
    email: string | null;
    participacion: Monto;
    utilidad_estimada_usd: Monto;
  }>;
};

export type Automatizacion = {
  nombre: string;
  ultima: null | {
    id: number;
    inicio: string;
    fin: string | null;
    estado: string;
    filas_afectadas: number;
    detalle: Record<string, unknown> | null;
    error: string | null;
  };
};
