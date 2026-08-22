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

export function useTasaSugerida() {
  return useQuery({
    queryKey: ["pagos", "tasa"],
    queryFn: () =>
      api.get<{
        disponible: boolean;
        valor?: string;
        procedencia?: string;
        es_respaldo?: boolean;
        mensaje?: string;
      }>("/pagos/tasa-sugerida"),
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
    mutationFn: ({ loteId, ...cuerpo }: { loteId: number; monto_usd: string; fecha: string; referencia?: string }) =>
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
