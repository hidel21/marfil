"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Monto } from "@/lib/dinero";
import type {
  Cliente,
  ClienteEnCobranza,
  Compra,
  Conciliacion,
  Cotizacion,
  DatosPago,
  FugaPrecio,
  Gasto,
  LoteRecordatorios,
  ResumenCobranza,
  ResumenDashboard,
  ResumenFinanzas,
  ResumenSocios,
  RespuestaSugerencias,
  TarjetaCalidad,
  Usuario,
  UsuarioCreado,
  Proveedor,
  Automatizacion,
} from "@/lib/tipos";

/**
 * Las consultas.
 *
 * `staleTime` por recurso, no uno global: el catálogo casi no cambia y la cobranza sí.
 * Es la diferencia concreta con la app anterior, donde cada clic reejecutaba las 37
 * consultas de la pantalla.
 */

const MINUTO = 60_000;

export function useResumenCobranza() {
  return useQuery({
    queryKey: ["cobranza", "resumen"],
    queryFn: () => api.get<ResumenCobranza>("/cobranza/resumen"),
    staleTime: 30_000,
  });
}

export type FiltrosCobranza = {
  tramo?: string;
  semaforo?: string;
  sin_abonos?: boolean;
  sin_telefono?: boolean;
  incluir_socios?: boolean;
};

export function useCobranza(filtros: FiltrosCobranza = {}) {
  return useQuery({
    queryKey: ["cobranza", "clientes", filtros],
    queryFn: () => api.get<ClienteEnCobranza[]>("/cobranza", filtros),
    staleTime: 30_000,
  });
}

export function useCalidad(enabled = true) {
  return useQuery({
    queryKey: ["auditoria", "calidad"],
    queryFn: () => api.get<TarjetaCalidad[]>("/auditoria/calidad"),
    staleTime: MINUTO,
    enabled,
  });
}

export function useConciliacion(tipo: "ventas" | "pagos" | "stock") {
  return useQuery({
    queryKey: ["auditoria", "conciliacion", tipo],
    queryFn: () => api.get<Conciliacion>("/auditoria/conciliacion", { tipo }),
    staleTime: MINUTO,
  });
}

export function useFugaPrecio() {
  return useQuery({
    queryKey: ["auditoria", "fuga-precio"],
    queryFn: () => api.get<FugaPrecio>("/auditoria/fuga-precio"),
    staleTime: MINUTO,
  });
}

export function useDatosPago(enabled = true) {
  return useQuery({
    queryKey: ["ajustes", "pagos"],
    queryFn: () => api.get<DatosPago>("/ajustes/pagos"),
    staleTime: 5 * MINUTO,
    enabled,
  });
}

export function useGuardarDatosPago() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datos: Record<string, string>) => api.put("/ajustes/pagos", datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ajustes", "pagos"] });
      qc.invalidateQueries({ queryKey: ["auditoria", "calidad"] });
    },
  });
}

export type FiltrosClientes = {
  q?: string;
  sin_telefono?: boolean;
  con_deuda?: boolean;
  a_revisar?: boolean;
};

export function useClientes(filtros: FiltrosClientes = {}) {
  return useQuery({
    queryKey: ["clientes", filtros],
    queryFn: () => api.get<Cliente[]>("/clientes", filtros),
    staleTime: MINUTO,
  });
}

export function useGuardarTelefono() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, telefono }: { id: number; telefono: string }) =>
      api.put(`/clientes/${id}/telefono`, { telefono }),
    onSuccess: () => {
      // Cargar un teléfono cambia la cobranza y las tarjetas de calidad a la vez.
      qc.invalidateQueries({ queryKey: ["clientes"] });
      qc.invalidateQueries({ queryKey: ["cobranza"] });
      qc.invalidateQueries({ queryKey: ["auditoria", "calidad"] });
    },
  });
}

export function useSugerenciasProducto(q: string, moneda: string) {
  return useQuery({
    queryKey: ["productos", "sugerencias", q, moneda],
    queryFn: () => api.get<RespuestaSugerencias>("/productos/sugerencias", { q, moneda }),
    // El catálogo casi no cambia: 5 minutos evita una consulta por tecla.
    staleTime: 5 * MINUTO,
    enabled: q.trim().length >= 2,
  });
}

export function useAltaRapida() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datos: { nombre: string; costo_usd?: string }) =>
      api.post<{ producto_id: number; nombre: string; estado: string; ya_existia: boolean }>(
        "/productos/alta-rapida",
        datos,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["productos"] }),
  });
}

export function useCotizar() {
  return useMutation({
    mutationFn: (cuerpo: unknown) => api.post<Cotizacion>("/ventas/cotizar", cuerpo),
  });
}

export function useCrearVenta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: unknown) => api.post<Record<string, unknown>>("/ventas", cuerpo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cobranza"] });
      qc.invalidateQueries({ queryKey: ["ventas"] });
      qc.invalidateQueries({ queryKey: ["auditoria"] });
    },
  });
}

/**
 * La tasa que corresponde a **la fecha del pago**, no a hoy.
 *
 * Antes no se pasaba `en_fecha` y el formulario prefijaba siempre la tasa del día:
 * cargar un pago del 10 de agosto lo convertía a la tasa de septiembre. Como la tasa
 * se congela en el pago y no se recalcula nunca, ese error queda para siempre en el
 * libro.
 */
export function useTasaSugerida(enFecha: string, tipo: string) {
  return useQuery({
    queryKey: ["pagos", "tasa", enFecha, tipo],
    queryFn: () =>
      api.get<{
        disponible: boolean;
        tipo?: string;
        valor?: string;
        procedencia?: string;
        es_respaldo?: boolean;
        mensaje?: string;
      }>("/pagos/tasa-sugerida", { en_fecha: enFecha, tipo }),
    staleTime: 5 * MINUTO,
  });
}

export function useRegistrarPago() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: unknown) => api.post<Record<string, unknown>>("/pagos", cuerpo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cobranza"] });
      qc.invalidateQueries({ queryKey: ["ventas"] });
    },
  });
}

export function usePrevisualizarLote() {
  return useMutation({
    mutationFn: (cuerpo: { cliente_ids?: number[]; plantilla_clave?: string }) =>
      api.post<LoteRecordatorios>("/recordatorios/previsualizar", cuerpo),
  });
}

export function useGenerarLote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: { cliente_ids?: number[]; plantilla_clave?: string }) =>
      api.post<LoteRecordatorios>("/recordatorios/lote", cuerpo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordatorios"] }),
  });
}

export function useMarcarEnviado() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post(`/recordatorios/${id}/marcar-enviado`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recordatorios"] }),
  });
}

export function useUsuarios() {
  return useQuery({
    queryKey: ["usuarios"],
    queryFn: () => api.get<Usuario[]>("/usuarios", { incluir_inactivos: true }),
    staleTime: MINUTO,
  });
}

export function useCambiarEstadoUsuario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, activo }: { id: number; activo: boolean }) =>
      api.put(`/usuarios/${id}/estado`, { activo, motivo: activo ? "Reactivación administrativa" : "Desactivación administrativa" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios"] }),
  });
}

export function useSociosSinCuenta() {
  return useQuery({
    queryKey: ["usuarios", "socios-sin-cuenta"],
    queryFn: () =>
      api.get<Array<{ id: number; nombre: string; capital_invertido: string }>>(
        "/usuarios/socios-sin-cuenta",
      ),
    staleTime: MINUTO,
  });
}

export function useCrearUsuario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: {
      email: string;
      nombre: string;
      rol: string;
      socio_id?: number | null;
      cliente_id?: number | null;
    }) => api.post<UsuarioCreado>("/usuarios", cuerpo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["usuarios"] }),
  });
}

export function useDashboard(dias = 30) {
  return useQuery({
    queryKey: ["dashboard", dias],
    queryFn: () => api.get<ResumenDashboard>("/dashboard/resumen", { dias }),
    staleTime: 30_000,
  });
}

export function useProveedores() {
  return useQuery({
    queryKey: ["compras", "proveedores"],
    queryFn: () => api.get<Proveedor[]>("/compras/proveedores"),
    staleTime: MINUTO,
  });
}

export function useCrearProveedor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: unknown) => api.post("/compras/proveedores", cuerpo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["compras", "proveedores"] }),
  });
}

export function useCompras() {
  return useQuery({
    queryKey: ["compras", "lotes"],
    queryFn: () => api.get<Compra[]>("/compras"),
    staleTime: 30_000,
  });
}

export function useCrearCompra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: unknown) => api.post("/compras", cuerpo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["compras"] });
      qc.invalidateQueries({ queryKey: ["productos"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function usePagarCompra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ loteId, ...cuerpo }: { loteId: number; monto_usd: string; fecha: string; canal?: string; referencia?: string }) =>
      api.post(`/compras/${loteId}/pagos`, cuerpo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["compras"] }),
  });
}

export function useGastos(filtros: { desde?: string; hasta?: string; categoria?: string } = {}) {
  return useQuery({
    queryKey: ["gastos", filtros],
    queryFn: () => api.get<{ items: Gasto[]; total_usd: Monto }>("/gastos", filtros),
    staleTime: 30_000,
  });
}

export function useCrearGasto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: unknown) => api.post("/gastos", cuerpo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["gastos"] });
      qc.invalidateQueries({ queryKey: ["finanzas"] });
    },
  });
}

export function useFinanzas() {
  return useQuery({
    queryKey: ["finanzas", "resumen"],
    queryFn: () => api.get<ResumenFinanzas>("/finanzas/resumen"),
    staleTime: MINUTO,
  });
}

export function useComisiones() {
  return useQuery({
    queryKey: ["finanzas", "comisiones"],
    queryFn: () => api.get<{ desde: string; hasta: string; tasa: Monto; items: Array<{ usuario_id: number; vendedor: string; ventas: number; vendido_usd: Monto; comision_usd: Monto }> }>("/finanzas/comisiones"),
    staleTime: MINUTO,
  });
}

export function useSocios() {
  return useQuery({
    queryKey: ["finanzas", "socios"],
    queryFn: () => api.get<ResumenSocios>("/finanzas/socios"),
    staleTime: MINUTO,
  });
}

export function useActualizarSocio() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, capital_invertido }: { id: number; capital_invertido: string }) =>
      api.put(`/finanzas/socios/${id}`, { capital_invertido }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finanzas", "socios"] }),
  });
}

export function useAutomatizaciones() {
  return useQuery({
    queryKey: ["automatizaciones"],
    queryFn: () => api.get<Automatizacion[]>("/automatizaciones"),
    staleTime: 30_000,
  });
}

export function useEjecutarAutomatizacion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (nombre: string) => api.post(`/automatizaciones/${nombre}/ejecutar`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automatizaciones"] }),
  });
}

// ---------------------------------------------------------------- correcciones
/**
 * Los hooks que permiten arreglar lo que se cargó mal.
 *
 * Hasta ahora el sistema solo sabía crear: una venta con el cliente equivocado o un
 * producto duplicado se quedaban ahí para siempre. Ninguno de estos borra nada —el
 * backend deja autor, fecha y motivo— así que la corrección se puede auditar.
 */

export function useCrearCliente() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datos: {
      nombre: string;
      telefono?: string;
      email?: string;
      nivel_precio?: string;
      plazo_credito_dias?: number;
      notas?: string;
    }) => api.post<{ cliente_id: number; nombre: string }>("/clientes", datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clientes"] });
      qc.invalidateQueries({ queryKey: ["cobranza"] });
    },
  });
}

export function useEditarCliente() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...datos }: { id: number; nombre: string; telefono?: string;
      email?: string; nivel_precio?: string; plazo_credito_dias?: number; notas?: string }) =>
      api.put<{ cliente_id: number }>(`/clientes/${id}`, datos),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clientes"] });
      qc.invalidateQueries({ queryKey: ["cobranza"] });
    },
  });
}

export function useAnularVenta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.post<{ codigo: string; unidades_devueltas: number }>(`/ventas/${id}/anular`, { motivo }),
    onSuccess: () => {
      // Anular mueve saldo, stock y auditoría a la vez: se invalida todo lo derivado.
      for (const clave of ["ventas", "cobranza", "productos", "dashboard", "auditoria", "finanzas"]) {
        qc.invalidateQueries({ queryKey: [clave] });
      }
    },
  });
}

export function useReversarPago() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.post<{ reverso_id: number }>(`/pagos/${id}/reversar`, { motivo }),
    onSuccess: () => {
      for (const clave of ["pagos", "cobranza", "dashboard", "finanzas"]) {
        qc.invalidateQueries({ queryKey: [clave] });
      }
    },
  });
}

export function useAnularCompra() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, motivo }: { id: number; motivo: string }) =>
      api.post<{ codigo: string; unidades_retiradas: number }>(`/compras/${id}/anular`, { motivo }),
    onSuccess: () => {
      for (const clave of ["compras", "productos", "dashboard", "finanzas"]) {
        qc.invalidateQueries({ queryKey: [clave] });
      }
    },
  });
}

export function useEditarProveedor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...datos }: { id: number; nombre: string; contacto?: string;
      telefono?: string; email?: string; notas?: string }) =>
      api.put<{ proveedor_id: number }>(`/compras/proveedores/${id}`, datos),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["compras"] }),
  });
}

/** Descatalogar no borra: el producto deja de ofrecerse pero sus ventas siguen ahí. */
export function useCambiarEstadoProducto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, estado }: { id: number; estado: "activo" | "descatalogado" }) =>
      api.put(`/productos/${id}`, { estado }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["productos"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

/**
 * Las categorías de gasto que el negocio usa de verdad, ordenadas por uso.
 *
 * No hay tabla de categorías: `gastos.categoria` es texto libre y esto es un
 * `GROUP BY`. Escribir una categoría nueva la crea, y eso es a propósito: una tabla
 * de catálogo obligaría a un alta previa para poder anotar un gasto de mil bolívares
 * en una hoja blanca.
 */
export function useCategoriasGasto() {
  return useQuery({
    queryKey: ["gastos", "categorias"],
    queryFn: () => api.get<{ categoria: string; usos: number }[]>("/gastos/categorias"),
    staleTime: 5 * MINUTO,
  });
}

/** Los abonos de una venta, para poder reversar el que se cargó mal. */
export function usePagosDeVenta(ventaId: number | null) {
  return useQuery({
    queryKey: ["pagos", "de-venta", ventaId],
    queryFn: () =>
      api.get<
        {
          id: number;
          fecha: string;
          tipo: string;
          monto_usd: string;
          canal: string | null;
          referencia: string | null;
          motivo: string | null;
        }[]
      >("/pagos", { venta_id: ventaId ?? undefined }),
    enabled: ventaId != null,
    staleTime: 30_000,
  });
}
