"use client";

import { useState } from "react";
import { toast } from "sonner";
import { CircleDollarSign, PackagePlus, Trash2, Truck } from "lucide-react";
import { ComboboxProducto } from "@/components/combobox-producto";
import { Dinero } from "@/components/dinero";
import { Boton, Campo, Cargando, Input, Insignia, Select, Tarjeta, Titulo, Vacio } from "@/components/ui";
import { useCompras, useCrearCompra, useCrearProveedor, usePagarCompra, useProveedores } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { fecha } from "@/lib/formato";

type Linea = { producto_id: number; descripcion: string; cantidad: string; costo_unitario_usd: string };
const hoy = () => new Date().toISOString().slice(0, 10);

export default function Compras() {
  const lotes = useCompras();
  const proveedores = useProveedores();
  const crear = useCrearCompra();
  const crearProveedor = useCrearProveedor();
  const pagar = usePagarCompra();
  const [mostrarCompra, setMostrarCompra] = useState(false);
  const [mostrarProveedor, setMostrarProveedor] = useState(false);
  const [codigo, setCodigo] = useState(`MAR-${hoy().replaceAll("-", "")}`);
  const [fechaCompra, setFechaCompra] = useState(hoy());
  const [proveedorId, setProveedorId] = useState("");
  const [declarado, setDeclarado] = useState("");
  const [pagoInicial, setPagoInicial] = useState("");
  const [lineas, setLineas] = useState<Linea[]>([]);
  const [pago, setPago] = useState<{ loteId: number; monto: string; referencia: string } | null>(null);

  function error(err: unknown) {
    toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo completar la operación");
  }

  async function registrar() {
    if (!lineas.length) return;
    try {
      await crear.mutateAsync({
        codigo, fecha: fechaCompra, proveedor_id: proveedorId ? Number(proveedorId) : null,
        subtotal_declarado_usd: declarado || null,
        pago_inicial_usd: pagoInicial || null,
        lineas: lineas.map((l) => ({ ...l, cantidad: Number(l.cantidad || 1) })),
      });
      toast.success("Compra e inventario actualizados");
      setLineas([]); setDeclarado(""); setPagoInicial(""); setMostrarCompra(false);
      setCodigo(`MAR-${Date.now().toString().slice(-8)}`);
    } catch (e) { error(e); }
  }

  async function registrarPago() {
    if (!pago) return;
    try {
      await pagar.mutateAsync({ loteId: pago.loteId, monto_usd: pago.monto, fecha: hoy(), referencia: pago.referencia || undefined });
      toast.success("Pago al proveedor registrado"); setPago(null);
    } catch (e) { error(e); }
  }

  return (
    <>
      <Titulo detalle="Entradas de inventario, costos y cuentas por pagar en un solo flujo." accion={<div className="flex gap-2"><Boton variante="secundario" onClick={() => setMostrarProveedor(!mostrarProveedor)}><Truck className="size-4" />Proveedor</Boton><Boton onClick={() => setMostrarCompra(!mostrarCompra)}><PackagePlus className="size-4" />Nueva compra</Boton></div>}>Compras</Titulo>

      {mostrarProveedor && <Tarjeta className="mb-5"><h2 className="mb-4 font-semibold">Nuevo proveedor</h2><form className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" onSubmit={async (e) => { e.preventDefault(); const f = new FormData(e.currentTarget); try { await crearProveedor.mutateAsync(Object.fromEntries(f)); toast.success("Proveedor creado"); setMostrarProveedor(false); } catch (err) { error(err); } }}><Campo etiqueta="Nombre" requerido><Input name="nombre" required /></Campo><Campo etiqueta="Contacto"><Input name="contacto" /></Campo><Campo etiqueta="Teléfono"><Input name="telefono" placeholder="0412-1234567" /></Campo><Campo etiqueta="Correo"><Input name="email" type="email" /></Campo><div className="md:col-span-2 xl:col-span-4"><Boton type="submit" disabled={crearProveedor.isPending}>Guardar proveedor</Boton></div></form></Tarjeta>}

      {mostrarCompra && <Tarjeta className="mb-5"><div className="mb-4"><h2 className="font-semibold">Registrar lote</h2><p className="text-xs text-texto-suave">Cada línea aumenta stock y actualiza el último costo del producto.</p></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><Campo etiqueta="Código" requerido><Input value={codigo} onChange={(e) => setCodigo(e.target.value)} /></Campo><Campo etiqueta="Fecha" requerido><Input type="date" value={fechaCompra} onChange={(e) => setFechaCompra(e.target.value)} /></Campo><Campo etiqueta="Proveedor"><Select value={proveedorId} onChange={(e) => setProveedorId(e.target.value)}><option value="">Sin proveedor</option>{(proveedores.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}</Select></Campo><Campo etiqueta="Total declarado"><Input type="number" min="0" step="0.01" value={declarado} onChange={(e) => setDeclarado(e.target.value)} placeholder="Opcional" /></Campo></div>
        <div className="mt-5 rounded-2xl border border-borde bg-fondo/45 p-3 sm:p-4"><p className="mb-2 text-sm font-semibold">Agregar producto</p><ComboboxProducto moneda="USD" onElegir={(p) => setLineas((xs) => [...xs, { producto_id: p.producto_id, descripcion: p.nombre, cantidad: "1", costo_unitario_usd: "" }])} /></div>
        <div className="mt-3 space-y-2">{lineas.map((l, i) => <div key={`${l.producto_id}-${i}`} className="grid gap-2 rounded-xl border border-borde p-3 md:grid-cols-[minmax(12rem,1fr)_7rem_10rem_3rem] md:items-end"><Campo etiqueta="Producto"><Input value={l.descripcion} onChange={(e) => setLineas((xs) => xs.map((x, j) => j === i ? { ...x, descripcion: e.target.value } : x))} /></Campo><Campo etiqueta="Unidades"><Input type="number" min="1" value={l.cantidad} onChange={(e) => setLineas((xs) => xs.map((x, j) => j === i ? { ...x, cantidad: e.target.value } : x))} /></Campo><Campo etiqueta="Costo unitario"><Input type="number" min="0" step="0.01" value={l.costo_unitario_usd} onChange={(e) => setLineas((xs) => xs.map((x, j) => j === i ? { ...x, costo_unitario_usd: e.target.value } : x))} /></Campo><Boton variante="fantasma" aria-label="Quitar línea" onClick={() => setLineas((xs) => xs.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Boton></div>)}</div>
        {lineas.length > 0 && <div className="mt-4 flex flex-wrap items-end justify-between gap-3"><Campo etiqueta="Pago inicial"><Input className="w-40" type="number" min="0" step="0.01" value={pagoInicial} onChange={(e) => setPagoInicial(e.target.value)} placeholder="0.00" /></Campo><div className="text-right"><p className="text-xs text-texto-suave">Total calculado</p><p className="marca-serif text-xl font-semibold">${lineas.reduce((a, l) => a + Number(l.cantidad || 0) * Number(l.costo_unitario_usd || 0), 0).toFixed(2)}</p><Boton className="mt-2" disabled={crear.isPending || lineas.some((l) => l.costo_unitario_usd === "")} onClick={registrar}>Registrar compra</Boton></div></div>}
      </Tarjeta>}

      {lotes.isLoading ? <Cargando que="Cargando compras" /> : !(lotes.data ?? []).length ? <Vacio titulo="Todavía no hay compras" detalle="Registra el primer lote para alimentar el inventario." /> : <div className="grid gap-3 lg:grid-cols-2">{lotes.data?.map((l) => <Tarjeta key={l.lote_id}><div className="flex items-start justify-between gap-3"><div><p className="font-semibold">{l.codigo}</p><p className="text-xs text-texto-suave">{l.proveedor ?? "Sin proveedor"} · {fecha(l.fecha)}</p></div><Insignia tono={Number(l.saldo_usd) > 0 ? "ambar" : "ok"}>{Number(l.saldo_usd) > 0 ? "Por pagar" : "Pagada"}</Insignia></div><div className="mt-4 grid grid-cols-3 gap-2 text-sm"><Dato etiqueta="Total"><Dinero valor={l.total_usd} /></Dato><Dato etiqueta="Pagado"><Dinero valor={l.pagado_usd} /></Dato><Dato etiqueta="Saldo"><Dinero valor={l.saldo_usd} /></Dato></div><p className="mt-3 text-xs text-texto-suave">{l.lineas} líneas · {l.unidades} unidades</p>{Number(l.saldo_usd) > 0 && <div className="mt-3 border-t border-borde pt-3">{pago?.loteId === l.lote_id ? <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]"><Input type="number" min="0.01" max={l.saldo_usd} step="0.01" placeholder={`Máx. $${l.saldo_usd}`} value={pago.monto} onChange={(e) => setPago({ ...pago, monto: e.target.value })} /><Input placeholder="Referencia" value={pago.referencia} onChange={(e) => setPago({ ...pago, referencia: e.target.value })} /><Boton onClick={registrarPago} disabled={!pago.monto || pagar.isPending}>Guardar</Boton></div> : <Boton variante="secundario" onClick={() => setPago({ loteId: l.lote_id, monto: "", referencia: "" })}><CircleDollarSign className="size-4" />Registrar pago</Boton>}</div>}</Tarjeta>)}</div>}
    </>
  );
}

function Dato({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) { return <div><p className="text-[11px] uppercase tracking-wide text-texto-suave">{etiqueta}</p><p className="font-semibold">{children}</p></div>; }
