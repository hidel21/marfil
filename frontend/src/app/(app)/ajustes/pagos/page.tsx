"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ShieldCheck } from "lucide-react";
import {
  Aviso,
  Boton,
  Campo,
  Cargando,
  Input,
  Select,
  Tarjeta,
  Titulo,
} from "@/components/ui";
import { useDatosPago, useGuardarDatosPago } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";

/**
 * Datos de pago.
 *
 * Es la pantalla que cierra el bug más serio que tenía la app: el recordatorio de
 * WhatsApp llevaba los marcadores literales `C.I.: V-XX.XXX.XXX` y
 * `Teléfono: 04XX-XXX-XXXX`, y eso se estaba enviando a clientes reales.
 *
 * Ahora los datos viven acá y las plantillas los invocan con una variable, así que es
 * estructuralmente imposible que un mensaje salga con un dato de relleno. Mientras
 * falte alguno, generar un recordatorio falla: no es un descuido, es el diseño.
 */
export default function DatosPagoAjustes() {
  const consulta = useDatosPago();

  if (consulta.isLoading) return <Cargando />;
  if (!consulta.data) {
    return (
      <Aviso tono="critico" titulo="No se pudieron cargar los datos de pago">
        Recargá la página para intentarlo de nuevo.
      </Aviso>
    );
  }

  return (
    <FormularioDatosPago
      key={JSON.stringify(consulta.data.campos)}
      datos={consulta.data}
    />
  );
}

type DatosPago = NonNullable<ReturnType<typeof useDatosPago>["data"]>;

function FormularioDatosPago({ datos }: { datos: DatosPago }) {
  const guardar = useGuardarDatosPago();
  const campos = datos.campos;

  const [titular, setTitular] = useState(campos.titular ?? "");
  const [banco, setBanco] = useState(campos.codigo_banco ?? "");
  const [documento, setDocumento] = useState(campos.documento ?? "");
  const [telefono, setTelefono] = useState(campos.telefono ?? "");

  async function onGuardar(e: React.FormEvent) {
    e.preventDefault();
    try {
      await guardar.mutateAsync({
        titular,
        codigo_banco: banco,
        documento,
        telefono,
      });
      toast.success("Datos de pago guardados", {
        description: "Ya se pueden generar recordatorios.",
      });
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudo guardar", {
        description: fallo?.sugerencia,
      });
    }
  }

  return (
    <>
      <Titulo detalle="Se insertan en los recordatorios con la variable {{ datos_pago }}.">
        Datos de pago
      </Titulo>

      <div className="grid gap-5 lg:grid-cols-2">
        <Tarjeta>
          <form onSubmit={onGuardar} className="space-y-4">
            <Campo etiqueta="Titular de la cuenta" requerido>
              <Input value={titular} onChange={(e) => setTitular(e.target.value)} required />
            </Campo>

            <Campo etiqueta="Banco" requerido>
              <Select value={banco} onChange={(e) => setBanco(e.target.value)} required>
                <option value="">Elegí el banco…</option>
                {datos.bancos.map((b) => (
                  <option key={b.codigo} value={b.codigo}>
                    {b.codigo} — {b.nombre}
                  </option>
                ))}
              </Select>
            </Campo>

            <Campo
              etiqueta="Cédula o RIF"
              requerido
              ayuda="Formato V-12345678. No se aceptan marcadores tipo V-XX.XXX.XXX."
            >
              <Input
                value={documento}
                onChange={(e) => setDocumento(e.target.value)}
                placeholder="V-12345678"
                required
              />
            </Campo>

            <Campo
              etiqueta="Teléfono del pago móvil"
              requerido
              ayuda="Un móvil venezolano: 0412, 0414, 0416, 0424 o 0426."
            >
              <Input
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
                placeholder="0412-1234567"
                required
              />
            </Campo>

            <Boton type="submit" disabled={guardar.isPending}>
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </Boton>
          </form>
        </Tarjeta>

        <div className="space-y-4">
          {datos.completo ? (
            <Aviso tono="ok" titulo="Listos">
              Los recordatorios ya se pueden generar.
            </Aviso>
          ) : (
            <Aviso tono="critico" titulo="Falta completar">
              {datos.faltantes.join(", ")}. Hasta entonces no se puede generar
              ningún recordatorio.
            </Aviso>
          )}

          <Tarjeta>
            <p className="mb-2 flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="size-4 text-ok" />
              Cómo se va a ver en el mensaje
            </p>
            <pre className="rounded-lg bg-fondo p-3 text-xs whitespace-pre-wrap">
              {datos.vista_previa ??
                "Datos para el pago móvil:\n(completá el formulario para verlo)"}
            </pre>
            <p className="mt-3 text-xs text-texto-suave">
              Estos datos nunca se escriben dentro de una plantilla: se insertan desde
              acá. Por eso no puede quedar un dato viejo, ni de relleno, en un mensaje ya
              enviado.
            </p>
          </Tarjeta>
        </div>
      </div>
    </>
  );
}
