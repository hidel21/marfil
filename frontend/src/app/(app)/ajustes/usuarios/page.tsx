"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Copy, KeyRound, Power, UserPlus } from "lucide-react";
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
} from "@/components/ui";
import { useCambiarEstadoUsuario, useCrearUsuario, useSociosSinCuenta, useUsuarios } from "@/hooks/datos";
import { FalloApi } from "@/lib/api";
import { fechaHora } from "@/lib/formato";
import type { UsuarioCreado } from "@/lib/tipos";

/**
 * Usuarios.
 *
 * El superadmin crea el perfil y el sistema devuelve un **código de un solo uso**. La
 * persona elige su propia contraseña al activarlo.
 *
 * No es un paso extra por gusto: significa que la contraseña de otro nunca pasa por las
 * manos de quien creó la cuenta, ni queda en un chat, ni en un log, ni en la memoria de
 * nadie.
 */
export default function Usuarios() {
  const usuarios = useUsuarios();
  const socios = useSociosSinCuenta();
  const crear = useCrearUsuario();
  const cambiarEstado = useCambiarEstadoUsuario();

  const [email, setEmail] = useState("");
  const [nombre, setNombre] = useState("");
  const [rol, setRol] = useState("vendedor");
  const [socioId, setSocioId] = useState<string>("");
  const [creado, setCreado] = useState<UsuarioCreado | null>(null);

  async function onCrear(e: React.FormEvent) {
    e.preventDefault();
    try {
      const r = await crear.mutateAsync({
        email,
        nombre,
        rol,
        socio_id: socioId ? Number(socioId) : null,
      });
      setCreado(r);
      setEmail("");
      setNombre("");
      setSocioId("");
      toast.success(`Perfil de ${r.nombre} creado`);
    } catch (err) {
      const fallo = err instanceof FalloApi ? err : null;
      toast.error(fallo?.mensaje ?? "No se pudo crear", {
        description: fallo?.sugerencia,
      });
    }
  }

  return (
    <>
      <Titulo detalle="Vos creás el perfil; cada uno elige su contraseña al entrar.">
        Usuarios
      </Titulo>

      {creado && (
        <div className="mb-5">
          <Aviso tono="ok" titulo={`Código para ${creado.nombre}`}>
            <p className="mb-2">{creado.instrucciones}</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-superficie px-2 py-1 font-mono text-sm">
                {creado.codigo_activacion}
              </code>
              <Boton
                variante="secundario"
                onClick={() =>
                  navigator.clipboard.writeText(creado.codigo_activacion).then(
                    () => toast.success("Código copiado"),
                    () => toast.error("No se pudo copiar"),
                  )
                }
              >
                <Copy className="size-4" />
                Copiar
              </Boton>
              <span className="text-xs">vence {fechaHora(creado.expira_at)}</span>
            </div>
          </Aviso>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[20rem_1fr]">
        <Tarjeta>
          <p className="mb-3 flex items-center gap-2 text-sm font-medium">
            <UserPlus className="size-4" />
            Crear un perfil
          </p>
          <form onSubmit={onCrear} className="space-y-4">
            <Campo etiqueta="Nombre" requerido>
              <Input value={nombre} onChange={(e) => setNombre(e.target.value)} required />
            </Campo>
            <Campo etiqueta="Correo" requerido ayuda="Con este correo va a entrar.">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </Campo>
            <Campo etiqueta="Rol" requerido>
              <Select value={rol} onChange={(e) => setRol(e.target.value)}>
                <option value="admin">Socio (ve todo)</option>
                <option value="vendedor">Vendedor (no ve costos)</option>
                <option value="afiliado">Afiliado (solo lo suyo)</option>
              </Select>
            </Campo>
            {rol === "admin" && (socios.data ?? []).length > 0 && (
              <Campo
                etiqueta="Ligar a un socio"
                ayuda="Lo conecta con su reparto de utilidad."
              >
                <Select value={socioId} onChange={(e) => setSocioId(e.target.value)}>
                  <option value="">Sin ligar</option>
                  {(socios.data ?? []).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre}
                    </option>
                  ))}
                </Select>
              </Campo>
            )}
            <Boton type="submit" disabled={crear.isPending} className="w-full">
              {crear.isPending ? "Creando…" : "Crear y generar código"}
            </Boton>
          </form>
        </Tarjeta>

        <div>
          {(socios.data ?? []).length > 0 && (
            <div className="mb-4">
              <Aviso
                tono="ambar"
                titulo={`${socios.data!.length} socio(s) sin perfil`}
              >
                {socios.data!.map((s) => s.nombre).join(", ")} están en el reparto de
                utilidad pero todavía no pueden entrar al sistema.
              </Aviso>
            </div>
          )}

          {usuarios.isLoading ? (
            <Cargando />
          ) : (
            <Tabla>
              <thead>
                <tr>
                  <Th>Nombre</Th>
                  <Th>Correo</Th>
                  <Th>Rol</Th>
                  <Th>Estado</Th>
                  <Th>Último ingreso</Th>
                  <Th>Acción</Th>
                </tr>
              </thead>
              <tbody>
                {(usuarios.data ?? []).map((u) => (
                  <tr key={u.id}>
                    <Td className="font-medium">{u.nombre}</Td>
                    <Td className="text-xs">{u.email}</Td>
                    <Td>
                      <Insignia tono={u.rol === "admin" ? "marca" : "neutro"}>
                        {u.rol}
                      </Insignia>
                    </Td>
                    <Td>
                      {u.sin_password ? (
                        <Insignia tono="ambar">
                          <KeyRound className="size-3" />
                          sin activar
                        </Insignia>
                      ) : u.activo ? (
                        <Insignia tono="ok">activo</Insignia>
                      ) : (
                        <Insignia tono="critico">inactivo</Insignia>
                      )}
                    </Td>
                    <Td className="text-xs text-texto-suave">
                      {u.ultimo_login_at ? fechaHora(u.ultimo_login_at) : "nunca"}
                    </Td>
                    <Td>
                      <Boton variante="fantasma" disabled={cambiarEstado.isPending} onClick={async () => { try { await cambiarEstado.mutateAsync({ id: u.id, activo: !u.activo }); toast.success(u.activo ? "Cuenta desactivada" : "Cuenta reactivada"); } catch (err) { toast.error(err instanceof FalloApi ? err.mensaje : "No se pudo cambiar el estado"); } }}>
                        <Power className="size-4" />{u.activo ? "Desactivar" : "Reactivar"}
                      </Boton>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Tabla>
          )}
        </div>
      </div>
    </>
  );
}
