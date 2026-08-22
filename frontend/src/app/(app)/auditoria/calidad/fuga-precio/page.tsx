"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Cargando } from "@/components/ui";

export default function FugaPrecio() {
  const router = useRouter();
  useEffect(() => router.replace("/auditoria"), [router]);
  return <Cargando que="Abriendo el informe" />;
}
