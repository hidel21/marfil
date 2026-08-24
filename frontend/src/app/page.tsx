"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Cargando } from "@/components/ui";

export default function Inicio() {
  const router = useRouter();
  useEffect(() => router.replace("/dashboard"), [router]);
  return <Cargando que="Abriendo Marfil" />;
}
