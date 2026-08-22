import type { Config } from "tailwindcss";

/**
 * Tema del sistema.
 *
 * Los colores están acá y no repartidos en clases sueltas porque **el color significa
 * algo**: `critico` es "esto hay que atenderlo hoy", `ambar` es "revisalo", `ok` es
 * "está bien". Si cada componente elige su rojo, el rojo deja de querer decir nada.
 *
 * Se usa Tailwind v3 y no v4 a propósito: v4 depende de un binario nativo
 * (`@tailwindcss/oxide`) que en este equipo crashea con SIGBUS contra glibc 2.43. v3 es
 * JavaScript puro, así que compila en cualquier parte —incluida la máquina de
 * despliegue— sin depender de que exista un binario para esa combinación de sistema.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        fondo: "var(--color-fondo)",
        superficie: "var(--color-superficie)",
        borde: "var(--color-borde)",
        texto: "var(--color-texto)",
        "texto-suave": "var(--color-texto-suave)",
        marca: "var(--color-marca)",
        "marca-suave": "var(--color-marca-suave)",
        acento: "var(--color-acento)",
        "acento-suave": "var(--color-acento-suave)",
        navegacion: "var(--color-navegacion)",
        critico: "var(--color-critico)",
        "critico-suave": "var(--color-critico-suave)",
        ambar: "var(--color-ambar)",
        "ambar-suave": "var(--color-ambar-suave)",
        ok: "var(--color-ok)",
        "ok-suave": "var(--color-ok-suave)",
      },
    },
  },
  plugins: [],
};

export default config;
