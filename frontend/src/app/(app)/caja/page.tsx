"use client";

import clsx from "clsx";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowDownLeft, ArrowUpRight, Plus, Wallet, X } from "lucide-react";
import { Dinero } from "@/components/dinero";
import {
  Aviso,
  Boton,
  Campo,
  Cargando,
  Input,
  Insignia,
  Select,
  Tabla,
  Tarjeta,
  Td,
  Th,
  Titulo,
  Vacio,
} from "@/components/ui";
import {
  useAnularMovimientoCaja,
  useCaja,
  useRegistrarMovimientoCaja,
  useSocios,
} from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { fecha } from "@/lib/formato";
import type { MovimientoCaja } from "@/lib/tipos";

/**
 * La caja: el "capital disponible" que los socios llevaban a mano en sus informes.
 *
 * No hay que cargar nada dos veces. Cobros, reversos, gastos y pagos a proveedor
 * aparecen solos, leídos de su propio libro; aquí solo se agrega lo que no tiene otro
 * lugar: aportes de capital, retiros de un socio y ajustes de cuadre.
 *
 * El saldo de cada fila es el de TODA la historia hasta ese movimiento, no el del
 * período filtrado: así la fila de un martes dice cuánto había ese martes de verdad.
 */

const hoy = () => new Date().toISOString().slice(0, 10);

function rangoMes(desplazamiento: number): [string, string] {
  const d = new Date();
  const inicio = new Date(d.getFullYear(), d.getMonth() + desplazamiento, 1);
  const fin = new Date(d.getFullYear(), d.getMonth() + desplazamiento + 1, 0);
  const iso = (x: Date) =>
    `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  return [iso(inicio), desplazamiento === 0 ? hoy() : iso(fin)];
}

const ATAJOS: Array<{ clave: string; etiqueta: string; rango: () => [string, string] }> = [
  { clave: "todo", etiqueta: "Toda la historia", rango: () => ["", ""] },
  { clave: "mes", etiqueta: "Este mes", rango: () => rangoMes(0) },
  { clave: "mes-ant", etiqueta: "Mes anterior", rango: () => rangoMes(-1) },
];

const NOMBRE_TIPO: Record<MovimientoCaja["tipo"], string> = {
  cobro: "Cobro",
  reverso_cobro: "Reverso de cobro",
  gasto: "Gasto",
  compra: "Compra de mercancía",
  aporte: "Aporte de socio",
  retiro: "Retiro de socio",
  ajuste: "Ajuste",
};

const CANALES = [
  ["pago_movil", "Pago móvil"],
  ["transferencia", "Transferencia"],
  ["efectivo_bs", "Efectivo Bs"],
  ["efectivo_usd", "Efectivo USD"],
  ["zelle", "Zelle"],
  ["binance", "Binance"],
  ["usdt", "USDT"],
] as const;

export default function Caja() {
  const [atajo, setAtajo] = useState("todo");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [formulario, setFormulario] = useState(false);
  const filtros = useMemo(
    () => ({ ...(desde ? { desde } : {}), ...(hasta ? { hasta } : {}) }),
    [desde, hasta],
  );
  const caja = useCaja(filtros);
  const d = caja.data;

  function elegirAtajo(clave: string) {
    const a = ATAJOS.find((x) => x.clave === clave);
    if (!a) return;
    const [ini, fin] = a.rango();
    setAtajo(clave);
    setDesde(ini);
    setHasta(fin);
  }

  // Un saldo negativo en algún punto de la historia casi siempre es un aporte que no
  // se registró: los primeros lotes se pagaron con capital de los socios.
  const minimo = (d?.movimientos ?? []).reduce<number | null>((m, x) => {
    const s = Number(x.saldo_usd);
    return m === null || s < m ? s : m;
  }, null);

  return (
    <>
      <Titulo
        detalle="El dinero del negocio: entra con cada cobro, sale con cada compra o gasto."
        accion={
          <Boton onClick={() => setFormulario(!formulario)}>
            <Plus className="size-4" />
            Aporte, retiro o ajuste
          </Boton>
        }
      >
        Caja
      </Titulo>

      {formulario && <NuevoMovimiento alCerrar={() => setFormulario(false)} />}

      <div className="mb-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <Tarjeta className="flex items-start justify-between">
          <div>
            <p className="text-xs text-texto-suave">En caja hoy</p>
            <p
              className={clsx(
                "marca-serif mt-2 text-4xl font-semibold",
                d && Number(d.saldo_actual_usd) < 0 && "text-critico",
              )}
            >
              {d ? <Dinero valor={d.saldo_actual_usd} /> : "…"}
            </p>
            <p className="mt-2 text-xs text-texto-suave">
              Cobros − compras pagadas − gastos, más aportes y menos retiros.
            </p>
          </div>
          <span className="grid size-10 place-items-center rounded-xl bg-acento-suave text-marca [&>svg]:size-5">
            <Wallet />
          </span>
        </Tarjeta>

        <Tarjeta>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <Campo etiqueta="Período">
              <Select value={atajo} onChange={(e) => elegirAtajo(e.target.value)}>
                {ATAJOS.map((a) => (
                  <option key={a.clave} value={a.clave}>
                    {a.etiqueta}
                  </option>
                ))}
                <option value="custom">Personalizado</option>
              </Select>
            </Campo>
            <Campo etiqueta="Desde">
              <Input
                type="date"
                value={desde}
                max={hasta || undefined}
                onChange={(e) => {
                  setAtajo("custom");
                  setDesde(e.target.value);
                }}
              />
            </Campo>
            <Campo etiqueta="Hasta">
              <Input
                type="date"
                value={hasta}
                min={desde || undefined}
                onChange={(e) => {
                  setAtajo("custom");
                  setHasta(e.target.value);
                }}
              />
            </Campo>
          </div>
          {d && (
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Cifra etiqueta="Saldo al inicio" valor={d.periodo.saldo_inicial_usd} />
              <Cifra etiqueta="Entró" valor={d.periodo.entradas_usd} tono="ok" />
              <Cifra etiqueta="Salió" valor={d.periodo.salidas_usd} tono="critico" />
              <Cifra etiqueta="Saldo al final" valor={d.periodo.saldo_final_usd} fuerte />
            </dl>
          )}
        </Tarjeta>
      </div>

      {minimo !== null && minimo < 0 && (
        <div className="mb-5">
          <Aviso tono="ambar" titulo="La caja llega a quedar en negativo">
            En algún momento salió más plata de la que había entrado (
            <Dinero valor={minimo.toFixed(2)} /> en el peor punto). Casi siempre es un
            aporte de capital que no se registró: las compras pagadas con dinero de los socios
            necesitan su aporte, con la fecha en que se puso la plata.
          </Aviso>
        </div>
      )}

      {d && (d.por_tipo.length > 0 || d.por_socio.some((s) => Number(s.aportado_usd) || Number(s.retirado_usd))) && (
        <div className="mb-5 grid gap-4 lg:grid-cols-2">
          <Tarjeta>
            <p className="mb-3 text-sm font-medium">En el período, por tipo</p>
            <ul className="space-y-1.5 text-sm">
              {d.por_tipo.map((t) => (
                <li key={t.tipo} className="flex items-center justify-between gap-3">
                  <span>
                    {NOMBRE_TIPO[t.tipo] ?? t.tipo}{" "}
                    <span className="text-xs text-texto-suave">· {t.movimientos}</span>
                  </span>
                  <Monto valor={t.monto_usd} />
                </li>
              ))}
            </ul>
          </Tarjeta>
          <Tarjeta>
            <p className="mb-1 text-sm font-medium">Aportes y retiros por socio</p>
            <p className="mb-3 text-xs text-texto-suave">
              De toda la historia. El capital del reparto se sigue fijando en Socios.
            </p>
            <ul className="space-y-1.5 text-sm">
              {d.por_socio.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-3">
                  <span>{s.nombre}</span>
                  <span className="text-xs text-texto-suave">
                    aportó <Dinero valor={s.aportado_usd} cero="$0.00" className="text-texto" />
                    {Number(s.retirado_usd) > 0 && (
                      <>
                        {" "}· retiró <Dinero valor={s.retirado_usd} className="text-texto" />
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Tarjeta>
        </div>
      )}

      {caja.isLoading ? (
        <Cargando que="Cargando la caja" />
      ) : caja.isError ? (
        <Aviso tono="critico" titulo="No se pudo cargar la caja">
          {caja.error instanceof FalloApi ? caja.error.mensaje : "Probá de nuevo en un momento."}
        </Aviso>
      ) : !d?.movimientos.length ? (
        <Vacio titulo="No hay movimientos en este período" />
      ) : (
        <>
          <Movimientos movimientos={d.movimientos} />
          {d.truncado && (
            <p className="mt-2 text-xs text-texto-suave">
              Se muestran los {d.movimientos.length} más recientes del período. Acotá las fechas
              para ver el resto.
            </p>
          )}
        </>
      )}
    </>
  );
}

function Cifra({
  etiqueta,
  valor,
  tono,
  fuerte,
}: {
  etiqueta: string;
  valor: string;
  tono?: "ok" | "critico";
  fuerte?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-texto-suave">{etiqueta}</dt>
      <dd
        className={clsx(
          "mt-1 tabular",
          fuerte ? "text-lg font-semibold" : "font-medium",
          tono === "ok" && "text-ok",
          tono === "critico" && "text-critico",
        )}
      >
        <Dinero valor={valor} cero="$0.00" />
      </dd>
    </div>
  );
}

/** Un monto con signo: verde lo que entra, rojo lo que sale. */
function Monto({ valor }: { valor: string }) {
  const n = Number(valor);
  return (
    <span className={clsx("tabular font-medium", n > 0 ? "text-ok" : n < 0 ? "text-critico" : "")}>
      {n > 0 ? "+" : ""}
      <Dinero valor={valor} />
    </span>
  );
}

function Movimientos({ movimientos }: { movimientos: MovimientoCaja[] }) {
  const anular = useAnularMovimientoCaja();
  const [anulando, setAnulando] = useState<{ id: number; motivo: string } | null>(null);

  async function confirmar() {
    if (!anulando) return;
    try {
      await anular.mutateAsync({ id: anulando.id, motivo: anulando.motivo.trim() });
      toast.success("Movimiento anulado", { description: "Deja de contar, pero queda registrado." });
      setAnulando(null);
    } catch (err) {
      toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo anular");
    }
  }

  return (
    <Tabla>
      <thead>
        <tr>
          <Th>Fecha</Th>
          <Th>Movimiento</Th>
          <Th>Método</Th>
          <Th className="text-right">Monto</Th>
          <Th className="text-right">Saldo</Th>
          <Th />
        </tr>
      </thead>
      <tbody>
        {movimientos.map((m) => (
          <tr key={`${m.origen}-${m.origen_id}`} className={m.tipo === "reverso_cobro" ? "bg-critico-suave/35" : undefined}>
            <Td className="whitespace-nowrap">{fecha(m.fecha)}</Td>
            <Td>
              <div className="flex items-center gap-2">
                {Number(m.monto_usd) >= 0 ? (
                  <ArrowDownLeft className="size-4 shrink-0 text-ok" aria-label="Entra" />
                ) : (
                  <ArrowUpRight className="size-4 shrink-0 text-critico" aria-label="Sale" />
                )}
                <div className="min-w-0">
                  <p className="font-medium">{m.concepto}</p>
                  <p className="text-xs text-texto-suave">
                    <Insignia tono={m.origen === "manual" ? "ambar" : "neutro"}>
                      {NOMBRE_TIPO[m.tipo] ?? m.tipo}
                    </Insignia>
                    {m.detalle && <span className="ml-2">{m.detalle}</span>}
                    {m.moneda === "VES" && (
                      <span className="ml-2">
                        <Dinero valor={m.monto_moneda} moneda="VES" />
                      </span>
                    )}
                  </p>
                </div>
              </div>
              {anulando?.id === m.origen_id && m.origen === "manual" && (
                <div className="mt-2 flex min-w-72 gap-2">
                  <Input
                    autoFocus
                    placeholder="Motivo de la anulación"
                    value={anulando.motivo}
                    onChange={(e) => setAnulando({ ...anulando, motivo: e.target.value })}
                  />
                  <Boton
                    variante="peligro"
                    disabled={anulando.motivo.trim().length < 5 || anular.isPending}
                    onClick={confirmar}
                  >
                    Anular
                  </Boton>
                  <Boton variante="fantasma" onClick={() => setAnulando(null)} aria-label="Cancelar">
                    <X className="size-4" />
                  </Boton>
                </div>
              )}
            </Td>
            <Td className="capitalize text-texto-suave">{m.canal?.replaceAll("_", " ") ?? "—"}</Td>
            <Td className="text-right">
              <Monto valor={m.monto_usd} />
            </Td>
            <Td className={clsx("text-right tabular", Number(m.saldo_usd) < 0 && "text-critico")}>
              <Dinero valor={m.saldo_usd} cero="$0.00" />
            </Td>
            <Td>
              {m.origen === "manual" && anulando?.id !== m.origen_id && (
                <Boton
                  variante="fantasma"
                  className="px-2 py-1 text-xs"
                  title="Anular este movimiento"
                  onClick={() => setAnulando({ id: m.origen_id, motivo: "" })}
                >
                  Anular
                </Boton>
              )}
            </Td>
          </tr>
        ))}
      </tbody>
    </Tabla>
  );
}

function NuevoMovimiento({ alCerrar }: { alCerrar: () => void }) {
  const registrar = useRegistrarMovimientoCaja();
  const socios = useSocios();
  const [tipo, setTipo] = useState<"aporte" | "retiro" | "ajuste">("aporte");
  const [sentido, setSentido] = useState<"entrada" | "salida">("entrada");
  const [socio, setSocio] = useState("");
  const [fechaMov, setFechaMov] = useState(hoy());
  const [monto, setMonto] = useState("");
  const [concepto, setConcepto] = useState("");
  const [canal, setCanal] = useState("");
  const [notas, setNotas] = useState("");

  const conceptoSugerido =
    tipo === "aporte" ? "Aporte de capital" : tipo === "retiro" ? "Retiro de socio" : "Ajuste de cuadre";

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    try {
      await registrar.mutateAsync({
        fecha: fechaMov,
        tipo,
        monto_usd: monto,
        concepto: concepto.trim() || conceptoSugerido,
        ...(tipo === "ajuste" ? { sentido } : { socio_id: Number(socio) }),
        ...(canal ? { canal } : {}),
        ...(notas.trim() ? { notas: notas.trim() } : {}),
      });
      toast.success(
        tipo === "aporte" ? "Aporte registrado" : tipo === "retiro" ? "Retiro registrado" : "Ajuste registrado",
      );
      alCerrar();
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudo registrar", { description: fallo?.sugerencia });
    }
  }

  return (
    <Tarjeta className="mb-5">
      <form onSubmit={guardar} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Campo etiqueta="Tipo" requerido>
          <Select value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)}>
            <option value="aporte">Aporte de un socio (entra)</option>
            <option value="retiro">Retiro de un socio (sale)</option>
            <option value="ajuste">Ajuste o saldo inicial</option>
          </Select>
        </Campo>
        {tipo === "ajuste" ? (
          <Campo
            etiqueta="Sentido"
            requerido
            ayuda="Para arrancar la caja con lo que había, usá un ajuste de entrada con esa fecha."
          >
            <Select value={sentido} onChange={(e) => setSentido(e.target.value as typeof sentido)}>
              <option value="entrada">Entra a la caja</option>
              <option value="salida">Sale de la caja</option>
            </Select>
          </Campo>
        ) : (
          <Campo etiqueta="Socio" requerido>
            <Select value={socio} onChange={(e) => setSocio(e.target.value)} required>
              <option value="">Elegí un socio…</option>
              {(socios.data?.items ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                </option>
              ))}
            </Select>
          </Campo>
        )}
        <Campo etiqueta="Fecha" requerido ayuda="El día en que se movió la plata.">
          <Input type="date" value={fechaMov} max={hoy()} onChange={(e) => setFechaMov(e.target.value)} required />
        </Campo>
        <Campo etiqueta="Monto USD" requerido>
          <Input
            type="number"
            min="0.01"
            step="0.01"
            value={monto}
            onChange={(e) => setMonto(e.target.value)}
            required
          />
        </Campo>
        <Campo etiqueta="Concepto">
          <Input
            value={concepto}
            onChange={(e) => setConcepto(e.target.value)}
            placeholder={conceptoSugerido}
            maxLength={300}
          />
        </Campo>
        <Campo etiqueta="Método">
          <Select value={canal} onChange={(e) => setCanal(e.target.value)}>
            <option value="">No especificado</option>
            {CANALES.map(([valor, etiqueta]) => (
              <option key={valor} value={valor}>
                {etiqueta}
              </option>
            ))}
          </Select>
        </Campo>
        <div className="sm:col-span-2 lg:col-span-3">
          <Campo etiqueta="Nota" ayuda="Para qué fue, contra qué comprobante: lo que después haya que explicar.">
            <Input value={notas} onChange={(e) => setNotas(e.target.value)} maxLength={1000} placeholder="Opcional" />
          </Campo>
        </div>
        <div className="flex gap-2 sm:col-span-2 lg:col-span-3">
          <Boton type="submit" disabled={registrar.isPending || !monto || (tipo !== "ajuste" && !socio)}>
            Guardar
          </Boton>
          <Boton type="button" variante="secundario" onClick={alCerrar}>
            Cancelar
          </Boton>
        </div>
      </form>
    </Tarjeta>
  );
}
