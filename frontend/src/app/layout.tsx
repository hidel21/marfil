import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Proveedores } from "./proveedores";

export const metadata: Metadata = {
  title: {
    default: "Marfil · Gestión del negocio",
    template: "%s · Marfil",
  },
  description: "Ventas, inventario, compras, finanzas y cobranza de Marfil.",
  icons: { icon: "/brand/marfil-logo.png", apple: "/brand/marfil-logo.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#2d343a",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-VE">
      <body className="min-h-dvh antialiased">
        <Proveedores>{children}</Proveedores>
      </body>
    </html>
  );
}
