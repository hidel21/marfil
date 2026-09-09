"""Genera el manual de uso de Marfil en PDF.

    python scripts/generar_manual.py

Vive en el repo y no en un scratchpad porque el manual **envejece con la app**: cada
pantalla nueva lo desactualiza, y regenerarlo tiene que ser un comando, no volver a
escribirlo. Cuando cambie una pantalla, se edita la seccion correspondiente aca abajo.

Dos detalles de fpdf2 que cuesta descubrir:

- Las fuentes internas son latin-1 y parten el documento en la primera "o" acentuada,
  asi que se usa DejaVu Sans. **No hay DejaVuSans-Oblique** en la mayoria de las
  distribuciones: no se registra cursiva y el enfasis va en negrita.
- `footer()` corre al cerrar la pagina, cuando la portada ya dejo de ser la actual;
  por eso se detecta con `page_no() == 1` y no con una bandera.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF, XPos, YPos

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = Path("/usr/share/fonts/truetype/dejavu")
LOGO = RAIZ / "frontend" / "public" / "brand" / "marfil-logo.png"
SALIDA = RAIZ / "docs" / "Manual-Marfil.pdf"

TINTA = (38, 36, 33)
SUAVE = (110, 104, 96)
ACENTO = (140, 109, 63)
CREMA = (250, 246, 237)
BORDE = (222, 213, 196)
ALERTA = (150, 60, 45)
CREMA_ALERTA = (252, 242, 240)

URL = "https://marfil-sistema.onrender.com"
FECHA = "Septiembre de 2026"


class Manual(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(True, margin=22)
        self.add_font("DejaVu", "", str(FUENTES / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FUENTES / "DejaVuSans-Bold.ttf"))
        self.set_margins(20, 20, 20)

    @property
    def ancho_util(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def footer(self) -> None:
        if self.page_no() == 1:
            return
        self.set_y(-16)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*SUAVE)
        self.cell(0, 5, "Marfil Parfum de l'Âme  ·  Manual de uso", align="L")
        self.set_x(-30)
        self.cell(10, 5, str(self.page_no() - 1), align="R")

    # -------------------------------------------------------------------- bloques
    def h1(self, numero: str, texto: str) -> None:
        self.add_page()
        self.set_font("DejaVu", "B", 9)
        self.set_text_color(*ACENTO)
        self.cell(0, 6, numero, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("DejaVu", "B", 19)
        self.set_text_color(*TINTA)
        self.multi_cell(0, 8.5, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.5)
        self.set_draw_color(*ACENTO)
        self.set_line_width(0.7)
        self.line(self.l_margin, self.get_y(), self.l_margin + 26, self.get_y())
        self.ln(5)

    def h2(self, texto: str) -> None:
        if self.get_y() > 235:
            self.add_page()
        self.ln(2.5)
        self.set_font("DejaVu", "B", 12)
        self.set_text_color(*TINTA)
        self.multi_cell(0, 6.5, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def p(self, texto: str) -> None:
        self.set_font("DejaVu", "", 9.6)
        self.set_text_color(*TINTA)
        self.multi_cell(0, 5.3, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def pasos(self, items: list[str]) -> None:
        for i, texto in enumerate(items, 1):
            if self.get_y() > 258:
                self.add_page()
            y = self.get_y()
            self.set_fill_color(*ACENTO)
            self.set_text_color(255, 255, 255)
            self.set_font("DejaVu", "B", 8)
            self.ellipse(self.l_margin, y + 0.4, 5, 5, style="F")
            self.set_xy(self.l_margin, y + 1.1)
            self.cell(5, 3.6, str(i), align="C")
            self.set_xy(self.l_margin + 8, y)
            self.set_font("DejaVu", "", 9.6)
            self.set_text_color(*TINTA)
            self.multi_cell(
                self.ancho_util - 8, 5.3, texto, align="L",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
            self.ln(1.6)
        self.ln(1)

    def vinetas(self, items: list[tuple[str, str]]) -> None:
        for titulo, cuerpo in items:
            if self.get_y() > 255:
                self.add_page()
            y = self.get_y()
            self.set_fill_color(*ACENTO)
            self.rect(self.l_margin + 0.6, y + 2, 1.6, 1.6, style="F")
            self.set_xy(self.l_margin + 6, y)
            ancho = self.ancho_util - 6
            self.set_font("DejaVu", "B", 9.6)
            self.set_text_color(*TINTA)
            self.multi_cell(ancho, 5.3, titulo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if cuerpo:
                self.set_x(self.l_margin + 6)
                self.set_font("DejaVu", "", 9.6)
                self.set_text_color(*SUAVE)
                self.multi_cell(ancho, 5.1, cuerpo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1.8)
        self.ln(0.5)

    def nota(self, titulo: str, cuerpo: str, alerta: bool = False) -> None:
        ancho = self.ancho_util
        self.set_font("DejaVu", "", 9.3)
        # Se mide el texto ya maquetado: estimarlo por ancho de cadena dejaba los
        # recuadros con un blanco de sobra al pie.
        lineas = self.multi_cell(ancho - 12, 4.9, cuerpo, dry_run=True, output="LINES")
        alto = 3.4 + 4.6 + len(lineas) * 4.9 + 3.6
        if self.get_y() + alto > 266:
            self.add_page()
        y0 = self.get_y()
        self.set_fill_color(*(CREMA_ALERTA if alerta else CREMA))
        self.set_draw_color(*(ALERTA if alerta else BORDE))
        self.set_line_width(0.2)
        self.rect(self.l_margin, y0, ancho, alto, style="DF")
        self.set_fill_color(*(ALERTA if alerta else ACENTO))
        self.rect(self.l_margin, y0, 1.4, alto, style="F")
        self.set_xy(self.l_margin + 6, y0 + 3.4)
        self.set_font("DejaVu", "B", 9.3)
        self.set_text_color(*(ALERTA if alerta else ACENTO))
        self.cell(0, 4.6, titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(self.l_margin + 6)
        self.set_font("DejaVu", "", 9.3)
        self.set_text_color(*TINTA)
        self.multi_cell(ancho - 12, 4.9, cuerpo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y0 + alto + 4)

    def tabla(self, cabeceras: list[str], filas: list[list[str]], pesos: list[float]) -> None:
        ancho = self.ancho_util
        anchos = [ancho * peso for peso in pesos]
        if self.get_y() + 12 + len(filas) * 7 > 268:
            self.add_page()
        self.set_font("DejaVu", "B", 8.6)
        self.set_fill_color(*TINTA)
        self.set_text_color(255, 255, 255)
        for w, texto in zip(anchos, cabeceras):
            self.cell(w, 7.5, "  " + texto, fill=True)
        self.ln(7.5)
        self.set_font("DejaVu", "", 8.8)
        for i, fila in enumerate(filas):
            altos = [
                len(self.multi_cell(w - 4, 4.6, celda, dry_run=True, output="LINES"))
                for w, celda in zip(anchos, fila)
            ]
            alto = max(altos) * 4.6 + 3.4
            if self.get_y() + alto > 270:
                self.add_page()
            y0 = self.get_y()
            x = self.l_margin
            self.set_fill_color(*(CREMA if i % 2 == 0 else (255, 255, 255)))
            self.rect(x, y0, ancho, alto, style="F")
            for w, celda in zip(anchos, fila):
                self.set_xy(x + 2, y0 + 1.7)
                self.set_text_color(*TINTA)
                self.multi_cell(w - 4, 4.6, celda, align="L")
                x += w
            self.set_draw_color(*BORDE)
            self.set_line_width(0.1)
            self.line(self.l_margin, y0 + alto, self.l_margin + ancho, y0 + alto)
            self.set_y(y0 + alto)
        self.ln(4)

    def cubierta(self) -> None:
        self.add_page()
        self.set_fill_color(*CREMA)
        self.rect(0, 0, self.w, self.h, style="F")
        if LOGO.exists():
            self.image(str(LOGO), x=(self.w - 78) / 2, y=52, w=78)

        def centrado(y: float, alto: float, texto: str) -> None:
            # Vuelve a x=0 en cada linea: tras un cell con new_x=LMARGIN el cursor
            # queda en el margen y el centrado sale corrido.
            self.set_xy(0, y)
            self.cell(self.w, alto, texto, align="C")

        self.set_font("DejaVu", "B", 27)
        self.set_text_color(*TINTA)
        centrado(108, 12, "Manual de uso")
        self.set_font("DejaVu", "", 12.5)
        self.set_text_color(*SUAVE)
        centrado(121, 8, "Sistema de gestión Marfil")
        self.set_draw_color(*ACENTO)
        self.set_line_width(0.7)
        self.line((self.w - 26) / 2, 140, (self.w + 26) / 2, 140)
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(*ACENTO)
        centrado(150, 7, "Para los socios")
        self.set_font("DejaVu", "", 9.6)
        self.set_text_color(*SUAVE)
        centrado(157.5, 6, "Perfil de administrador")
        self.set_font("DejaVu", "", 9)
        centrado(246, 5, URL)
        centrado(251, 5, FECHA)


def construir() -> Path:
    pdf = Manual()
    pdf.cubierta()

    # ----------------------------------------------------------------------- 1
    pdf.h1("SECCIÓN 1", "Tu primer acceso")
    pdf.p(
        "Marfil se usa desde el navegador, sin instalar nada. Funciona igual en "
        "computadora y en teléfono. La dirección es siempre la misma:"
    )
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*ACENTO)
    pdf.multi_cell(0, 6, URL, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    pdf.p(
        "Hidelberg te entregó un código de activación. Ese código no es tu "
        "contraseña: sirve una sola vez y solo para que elijas la tuya. Nadie más, "
        "ni él, llega a conocerla."
    )
    pdf.pasos([
        f"Entrá a {URL}/activar",
        "Escribí tu correo, exactamente el que le diste a Hidelberg.",
        "Pegá el código de activación.",
        "Elegí tu contraseña. El mínimo son 8 caracteres, pero usá una larga y que "
        "no uses en ningún otro sitio.",
        "Listo. Desde ahora entrás por la pantalla normal con tu correo y esa "
        "contraseña.",
    ])
    pdf.nota(
        "El código vence a las 72 horas",
        "Y sirve una sola vez. Si se te vence, pedile a Hidelberg que te genere otro "
        "desde Ajustes → Usuarios. No hace falta crear la cuenta de nuevo.",
    )
    pdf.h2("La primera carga del día tarda")
    pdf.p(
        "El servidor se duerme cuando nadie lo usa durante 15 minutos. La primera vez "
        "que abrís la página después de un rato, tarda cerca de un minuto en "
        "responder: la pantalla se queda quieta y el botón dice \"Entrando…\". Es "
        "normal, no está roto."
    )
    pdf.nota(
        "No vuelvas a pulsar el botón",
        "Si pulsás otra vez, cancelás el intento en curso y volvés a empezar la "
        "espera. Pulsá una sola vez y dale hasta un minuto. A partir de ahí, todo va "
        "rápido.",
    )

    # ----------------------------------------------------------------------- 2
    pdf.h1("SECCIÓN 2", "Cómo está organizado")
    pdf.p(
        "El menú de la izquierda agrupa las pantallas en tres bloques. Como socios "
        "tienen perfil de administrador, así que ven todo."
    )
    pdf.tabla(
        ["Bloque", "Pantallas", "Para qué"],
        [
            ["Principal",
             "Resumen, Cobranza, Registrar venta, Registrar abono, Recordatorios",
             "El día a día. Es donde vas a pasar casi todo el tiempo."],
            ["Operación",
             "Clientes, Productos, Compras, Gastos",
             "Los datos que alimentan las ventas: a quién le vendés, qué vendés, qué "
             "comprás y en qué gastás."],
            ["Gestión",
             "Finanzas, Socios, Reportes, Auditoría, Ajustes",
             "La mirada de arriba: resultados, reparto entre socios, informes y "
             "configuración."],
        ],
        [0.17, 0.36, 0.47],
    )
    pdf.h2("Tres ideas que conviene entender desde el principio")
    pdf.vinetas([
        ("El saldo de una venta no se escribe a mano.",
         "Lo calcula el sistema sumando los abonos registrados. Si un cliente debe de "
         "menos, es porque falta cargar un abono, no porque haya que corregir el "
         "número."),
        ("Nada se borra: se anula.",
         "Una venta anulada, un abono reversado o un producto descatalogado siguen "
         "existiendo, con quién lo hizo y por qué. Borrar dejaría los reportes con "
         "huecos y la auditoría sin cuadrar."),
        ("Auditoría avisa sola.",
         "Si aparece un número rojo junto a Auditoría en el menú, hay algo que "
         "revisar. No es urgente al segundo, pero no lo dejes crecer."),
    ])

    # ----------------------------------------------------------------------- 3
    pdf.h1("SECCIÓN 3", "Clientes")
    pdf.p(
        "Menú Operación → Clientes. Desde ahí se crean, se corrigen y se les carga el "
        "teléfono."
    )
    pdf.h2("Crear un cliente")
    pdf.p(
        "Botón \"Nuevo cliente\". Lo único obligatorio es el nombre. Además del "
        "teléfono y el correo, podés fijarle su nivel de precio habitual (público, "
        "team o revendedor) y su plazo de crédito en días, que el sistema usará por "
        "defecto en sus ventas."
    )
    pdf.nota(
        "No inventes el teléfono para salir del paso",
        "Un número inventado es peor que uno ausente: el recordatorio de cobro se va "
        "a un desconocido. Dejalo vacío y cargalo cuando lo tengas.",
    )
    pdf.h2("Corregir un cliente")
    pdf.p(
        "El lápiz al final de cada fila abre la misma ficha para editarla. Si "
        "intentás ponerle el nombre de otro cliente que ya existe, el sistema te "
        "avisa en vez de crear un duplicado: dos fichas de la misma persona parten su "
        "deuda en dos y ninguna refleja lo que debe de verdad."
    )
    pdf.p(
        "Al editar, el campo de teléfono vacío **conserva** el que ya tenía. Solo se "
        "reemplaza si escribís uno nuevo."
    )

    # ----------------------------------------------------------------------- 4
    pdf.h1("SECCIÓN 4", "Registrar una venta")
    pdf.p("Es la operación más frecuente. Menú Principal → Registrar venta.")
    pdf.pasos([
        "Elegí el cliente. Vas a ver su deuda actual antes de venderle.",
        "Elegí la moneda de cotización. Es obligatoria y no tiene valor por defecto: "
        "sin ella el botón de guardar queda gris.",
        "Elegí la condición: contado si paga ahora, crédito si queda debiendo. Con "
        "crédito podés fijar los días de plazo o dejarlo vacío para usar el del "
        "cliente.",
        "Buscá el producto. Si no está en el catálogo, el buscador te ofrece "
        "\"Crear\" ahí mismo.",
        "Elegí el nivel de precio: público, team o revendedor. El sistema trae el "
        "precio de ese nivel.",
        "Confirmá. Antes de guardar vas a ver el costo, la ganancia y el total.",
    ])
    pdf.nota(
        "Si el botón está gris, casi siempre falta la moneda",
        "Es el control que reemplazó una configuración vieja que dejaba escapar "
        "margen, por eso es obligatorio y no tiene valor por defecto.",
        alerta=True,
    )
    pdf.h2("El guardia de precio")
    pdf.p(
        "Marfil compara el precio que estás cobrando contra el precio de política del "
        "nivel elegido. No es desconfianza: es para que un cero de menos o un "
        "descuento olvidado no pase inadvertido."
    )
    pdf.tabla(
        ["Situación", "Qué hace", "Qué tenés que hacer"],
        [
            ["Cobrás bastante por debajo de la política",
             "Bloquea la venta.",
             "Escribí el motivo en el campo de justificación: \"cliente frecuente\", "
             "\"promoción\", \"precio acordado antes\". Con eso pasa, y queda "
             "registrado."],
            ["Cobrás por debajo del costo",
             "Bloquea la venta.",
             "Revisá el precio. Si de verdad vendés por debajo del costo, tiene que "
             "ser una decisión consciente y justificada."],
            ["Cobrás por encima de la política",
             "Avisa, pero deja pasar.",
             "Leé el aviso y confirmá que no sea un error de tipeo."],
            ["El producto no tiene costo cargado",
             "Avisa, pero deja pasar.",
             "La venta se registra. Cargá el costo en Productos → Revisión para que "
             "el guardia pueda protegerte la próxima vez."],
        ],
        [0.26, 0.20, 0.54],
    )
    pdf.nota(
        "Los descuentos existen; solo hay que nombrarlos",
        "El sistema nunca te impide hacer un buen precio. Lo único que pide es que "
        "digas por qué. Esa nota es la que después explica, en Auditoría, por qué un "
        "mes tuvo menos margen.",
    )
    pdf.h2("Venta sobre pedido")
    pdf.p(
        "Si el producto no tiene stock suficiente, aparece una casilla ámbar que dice "
        "\"Venta sobre pedido\". Hay que marcarla para poder guardar. El stock puede "
        "quedar en negativo, y es a propósito: es más honesto que no poder registrar "
        "una venta que sí ocurrió."
    )
    pdf.nota(
        "Al principio va a aparecer en casi todas las ventas",
        "El catálogo que se migró vino con el stock en cero, así que cualquier venta "
        "lo deja en negativo. Se soluciona cargando el stock real de cada producto, "
        "no marcando la casilla siempre.",
    )

    # ----------------------------------------------------------------------- 5
    pdf.h1("SECCIÓN 5", "Cobrar y registrar abonos")
    pdf.h2("La pantalla de Cobranza")
    pdf.p(
        "Menú Principal → Cobranza. Es la lista de quién debe, ordenada por lo que más "
        "urge. Cada fila te dice el cliente, su teléfono, cuánto debe, cuántos días "
        "lleva de atraso, cuándo abonó por última vez y cuándo se le avisó."
    )
    pdf.p(
        "Al desplegar un cliente ves sus ventas abiertas, y en cada una tres acciones: "
        "registrar abono, ver los abonos ya cargados y anular la venta."
    )
    pdf.h2("Registrar un abono")
    pdf.p("Menú Principal → Registrar abono.")
    pdf.pasos([
        "Elegí la venta que se está pagando. Vas a ver cuánto debe hoy.",
        "Poné la fecha real del pago, no la de hoy si el cliente pagó ayer. El "
        "sistema trae automáticamente la tasa que regía ese día.",
        "Elegí el método. Los de bolívares llevan tasa; los de divisa no, porque el "
        "monto ya está en dólares.",
        "Si es en bolívares, elegí con qué tasa convertir: BCV, paralelo, USDT, euro "
        "oficial o euro paralelo. Por defecto viene BCV, que es la referencia legal.",
        "Escribí el monto y la referencia de la operación.",
        "Antes de guardar, mirá el saldo que va a quedar. Si no cuadra con lo que "
        "esperabas, revisá el monto o la tasa.",
    ])
    pdf.nota(
        "La tasa se congela en el pago y no se recalcula nunca",
        "Por eso importa que la fecha sea la real: si cargás un pago de hace un mes "
        "con la fecha de hoy, se convierte con la tasa de hoy y el error queda en el "
        "libro para siempre. El sistema te dice de qué día es la tasa que está usando; "
        "si tiene más de un día de atraso, te lo marca en ámbar.",
        alerta=True,
    )
    pdf.h2("Los métodos de pago")
    pdf.tabla(
        ["En bolívares (llevan tasa)", "En divisa (sin tasa)"],
        [
            ["Pago móvil\nTransferencia\nEfectivo Bs\nOtro (en bolívares)",
             "Efectivo USD\nZelle\nBinance\nUSDT\nOtro (en divisa)"],
        ],
        [0.5, 0.5],
    )
    pdf.p(
        "El método \"Otro\" aparece de los dos lados a propósito: hay que decir en qué "
        "moneda se cobró. Sin eso, un pago de 18.000 bolívares podría quedar "
        "registrado como 18.000 dólares."
    )
    pdf.p(
        "Al guardar podés descargar el recibo en PDF y enviárselo al cliente. Es buena "
        "práctica hacerlo siempre: evita discusiones después."
    )

    # ----------------------------------------------------------------------- 6
    pdf.h1("SECCIÓN 6", "Corregir un error")
    pdf.p(
        "Todo lo que se puede cargar se puede corregir, y siempre queda registrado "
        "quién lo hizo y por qué. El motivo es obligatorio en todos los casos: no es "
        "burocracia, es lo que después explica los números del mes."
    )
    pdf.h2("Anular una venta")
    pdf.p(
        "En Cobranza, desplegá el cliente y usá \"Anular\" en la venta. Pide el motivo "
        "en dos pasos: el primer clic solo abre el campo, para que no se anule la "
        "venta de al lado por error."
    )
    pdf.p(
        "Al anularla, las unidades vuelven al stock automáticamente y la venta "
        "desaparece de cobranza."
    )
    pdf.nota(
        "Si la venta ya tiene abonos, no se anula de una",
        "El sistema se niega y te lo dice. Primero hay que reversar cada abono con su "
        "motivo, y después anular la venta. Anularla con dinero cobrado encima dejaría "
        "ese dinero registrado contra una venta que ya no vale.",
    )
    pdf.h2("Reversar un abono")
    pdf.p(
        "En la misma fila de la venta, \"Ver abonos\" lista los que tiene. Cada uno "
        "acepta un motivo y un botón para reversarlo."
    )
    pdf.p(
        "El abono original no se borra: se registra un movimiento opuesto y quedan los "
        "dos visibles. Eso es lo que permite auditar la corrección en vez de taparla. "
        "Un abono ya reversado no se puede reversar otra vez."
    )
    pdf.h2("Anular una compra")
    pdf.p(
        "En Compras, cada lote tiene \"Anular\". Al anularlo se retira del stock lo "
        "que había ingresado."
    )
    pdf.nota(
        "Con pagos al proveedor ya registrados, no se anula",
        "Ese dinero salió de verdad. Primero hay que resolver qué pasa con él —una "
        "nota de crédito, una devolución— y registrarlo, en vez de hacer desaparecer "
        "la compra y dejar el fondo sin explicación.",
    )
    pdf.h2("Quitar un producto")
    pdf.p(
        "En Productos, el botón de prohibido lo descataloga: deja de ofrecerse al "
        "vender, pero sus ventas históricas siguen intactas. Se revierte con un clic "
        "desde la casilla \"Ver descatalogados\"."
    )
    pdf.p(
        "No existe borrar un producto de verdad, y es deliberado: las ventas viejas "
        "apuntan a él, y eliminarlo dejaría la conciliación sin cuadrar y los reportes "
        "con huecos."
    )

    # ----------------------------------------------------------------------- 7
    pdf.h1("SECCIÓN 7", "Productos")
    pdf.p(
        "Menú Operación → Productos. Cada producto tiene su costo y sus tres niveles "
        "de precio: público, team y revendedor."
    )
    pdf.h2("Cargar los costos que faltan")
    pdf.p(
        "Menú Operación → Productos → **Revisión**. Ahí está la cola de los productos "
        "que quedaron sin costo al migrar el catálogo. Cada uno pide su línea, el "
        "modelo de precio y el costo, y el botón \"Aprobar\" lo activa."
    )
    pdf.tabla(
        ["Modelo de precio", "Qué significa"],
        [
            ["Margen sobre costo",
             "Se carga el costo y el sistema calcula los precios aplicando el margen. "
             "Es el caso normal."],
            ["Precio de lista",
             "Se carga el precio de lista del original. Para los perfumes originales, "
             "donde el precio no se deriva del costo."],
        ],
        [0.3, 0.7],
    )
    pdf.nota(
        "Es la tarea pendiente más útil del sistema",
        "Mientras un producto no tenga costo, el guardia de precio no puede protegerte "
        "al venderlo: no tiene con qué comparar. Cada costo que cargás es una venta "
        "futura que el sistema puede revisar.",
    )
    pdf.h2("El stock")
    pdf.p(
        "El catálogo migrado vino con el stock en cero. Se puede ajustar desde la "
        "pantalla de productos, y cada movimiento queda en un libro: siempre se puede "
        "explicar de dónde salió cada unidad."
    )

    # ----------------------------------------------------------------------- 8
    pdf.h1("SECCIÓN 8", "Compras y proveedores")
    pdf.p(
        "Menú Operación → Compras. Cada lote aumenta el stock y actualiza el costo de "
        "los productos que trae."
    )
    pdf.h2("La condición es lo más importante del formulario")
    pdf.p(
        "De ella depende qué pasa con el dinero, no solo la etiqueta:"
    )
    pdf.tabla(
        ["Condición", "Qué implica"],
        [
            ["Contado", "Ya se pagó. No aparece en cuentas por pagar."],
            ["Crédito", "Queda debiendo. Aparece en cuentas por pagar."],
            ["Consignación",
             "La mercancía está en el negocio pero no se debe hasta venderla. No "
             "aparece en cuentas por pagar, porque lo que no se vende se devuelve."],
            ["Anticipo",
             "Se pagó antes de recibir la mercancía. Sigue como exigible hasta que se "
             "registre el pago."],
        ],
        [0.22, 0.78],
    )
    pdf.p(
        "Con crédito, el campo de método de pago queda deshabilitado: todavía no se "
        "pagó nada, y el método se elige al registrar el pago."
    )
    pdf.h2("Pagar al proveedor")
    pdf.p(
        "En cada lote con saldo aparece \"Registrar pago\". Pide el monto, el método "
        "—efectivo divisa, efectivo bolívares, pago móvil, transferencia, USDT, Zelle, "
        "Binance u otro— y la referencia."
    )
    pdf.nota(
        "Dos cifras que parecen la misma y no lo son",
        "El saldo del lote es lo comprado menos lo pagado, y es la cifra que tiene que "
        "cuadrar contra el libro. Lo exigible es lo que de verdad hay que pagarle a "
        "alguien: excluye el contado, que ya salió, y la consignación, que todavía no "
        "se debe. En Finanzas verás la misma distinción entre la mercancía que entró y "
        "el dinero que salió de caja.",
    )
    pdf.h2("Proveedores")
    pdf.p(
        "El botón \"Proveedor\" abre el alta y, debajo, la lista de los registrados. "
        "El lápiz de cada uno permite corregir su nombre, contacto, teléfono y correo."
    )

    # ----------------------------------------------------------------------- 9
    pdf.h1("SECCIÓN 9", "Gastos")
    pdf.p(
        "Menú Operación → Gastos. Son los costos operativos, separados de la compra de "
        "inventario: publicidad, envíos, empaque, servicios, comisiones."
    )
    pdf.h2("Crear una categoría nueva")
    pdf.p(
        "El selector de categoría muestra las que el negocio ya usa, ordenadas por "
        "frecuencia, y al final la opción \"Crear una nueva\". Escribiendo el nombre "
        "queda creada; no hay que darla de alta en ningún otro lado."
    )
    pdf.p(
        "Eso es a propósito: un catálogo cerrado obligaría a un trámite previo para "
        "poder anotar un gasto apuntado en una hoja blanca, y entonces ese gasto no se "
        "anota nunca."
    )
    pdf.h2("La nota")
    pdf.p(
        "Además de la descripción hay un campo de nota, para el detalle que después "
        "haya que explicar: quién lo pidió, contra qué comprobante, a nombre de quién "
        "salió. La descripción dice qué se pagó; la nota, todo lo demás."
    )

    # ---------------------------------------------------------------------- 10
    pdf.h1("SECCIÓN 10", "Recordatorios de cobro")
    pdf.p(
        "Menú Principal → Recordatorios. Marfil arma el mensaje con el nombre del "
        "cliente, lo que debe y los datos para pagarte, y genera un enlace de WhatsApp "
        "con el número de esa persona. El envío lo hace una persona con un clic."
    )
    pdf.p(
        "Podés enviarlos de a uno o preparar un lote para varios deudores desde "
        "Cobranza, seleccionando a quiénes."
    )
    pdf.nota(
        "Si están bloqueados, faltan los datos de pago",
        "No es una falla. Un recordatorio sin banco ni número al que transferir solo "
        "genera una llamada de vuelta preguntando cómo pagar. Se completan en Ajustes "
        "→ Datos de pago.",
    )
    pdf.p(
        "Antes de enviar por lote, mirá la columna del último aviso en Cobranza. "
        "Avisarle dos veces el mismo día a la misma persona cansa y hace que dejen de "
        "leer los mensajes."
    )

    # ---------------------------------------------------------------------- 11
    pdf.h1("SECCIÓN 11", "Gestión y control")
    pdf.vinetas([
        ("Resumen",
         "La foto del día: ventas, cobros y lo que está por vencer. Es la pantalla con "
         "la que conviene empezar la jornada."),
        ("Finanzas",
         "Ingresos, costos, margen y cuentas por pagar del período. Distingue la "
         "mercancía que entró del dinero que salió de caja, que son dos preguntas "
         "distintas."),
        ("Socios",
         "El reparto entre los tres. Cada cuenta está ligada a su ficha de socio, así "
         "que lo que corresponde se calcula solo."),
        ("Reportes",
         "Informes descargables para revisar fuera del sistema o compartir."),
    ])
    pdf.h2("Auditoría")
    pdf.p(
        "Menú Gestión → Auditoría. Es el control de calidad del sistema y tiene cuatro "
        "miradas:"
    )
    pdf.vinetas([
        ("Conciliación",
         "Comprueba que las ventas, los pagos y el stock cuadren entre sí. Lo que "
         "querés ver siempre es \"cuadra\"."),
        ("Actividad",
         "Quién hizo qué y cuándo, incluidas todas las anulaciones y reversos con su "
         "motivo. Entre socios, esto evita conversaciones incómodas."),
        ("Fuga de precio",
         "Ventas que salieron por debajo de la política, con la justificación que se "
         "escribió. Sirve para ver si los descuentos se están volviendo la norma."),
        ("Bajo costo",
         "Productos cuyo precio quedó peligrosamente cerca del costo, o por debajo."),
    ])
    pdf.nota(
        "Si aparece un número rojo junto a Auditoría",
        "Es la cantidad de asuntos críticos por revisar. Entrá y leé qué son. Casi "
        "siempre es un dato que falta, no un problema grave, pero acumularlos hace que "
        "los números del mes dejen de ser confiables.",
    )

    # ---------------------------------------------------------------------- 12
    pdf.h1("SECCIÓN 12", "Ajustes")
    pdf.p(
        "Menú Gestión → Ajustes. Como administradores pueden tocar todo esto, así que "
        "conviene saber qué hace cada cosa antes de cambiarla."
    )
    pdf.tabla(
        ["Ajuste", "Qué controla"],
        [
            ["Datos de pago",
             "Banco, documento y teléfono que aparecen en los recordatorios y recibos. "
             "Sin esto, los recordatorios no se envían."],
            ["Tasas",
             "Las cinco series que el sistema captura solo cada día: dólar BCV, dólar "
             "paralelo, USDT, euro oficial y euro paralelo. Se puede corregir la de un "
             "día a mano con un motivo, y esa corrección no la pisa la captura "
             "automática del día siguiente."],
            ["Política",
             "Las reglas de precio contra las que compara el guardia. Cambiarlas afecta "
             "a todas las ventas siguientes."],
            ["Usuarios",
             "Crear cuentas y regenerar códigos de activación."],
            ["Automatizaciones",
             "El estado de las tareas diarias. Deberían estar todas en \"ok\"."],
            ["Mi contraseña",
             "Cambiar la tuya. Al cambiarla se cierran todas tus sesiones abiertas."],
        ],
        [0.24, 0.76],
    )

    # ---------------------------------------------------------------------- 13
    pdf.h1("SECCIÓN 13", "Cuando algo no funciona")
    pdf.tabla(
        ["Lo que ves", "Qué significa y qué hacer"],
        [
            ["La página tarda muchísimo en abrir",
             "El servidor estaba dormido. Esperá hasta un minuto sin recargar ni volver "
             "a pulsar. Pasa solo en la primera carga después de un rato sin uso."],
            ["El botón de registrar venta está gris",
             "Falta elegir la moneda de cotización, o todavía no cargaste ninguna línea."],
            ["\"No hay stock suficiente\"",
             "Marcá la casilla ámbar de venta sobre pedido. Y cargá el stock real del "
             "producto cuando puedas."],
            ["No me deja guardar la venta y hay un recuadro rojo",
             "Es el guardia de precio. El recuadro dice exactamente qué pasa. Casi "
             "siempre es escribir el motivo del descuento."],
            ["\"El correo o la contraseña no coinciden\"",
             "Revisá que no haya un espacio al final, sobre todo en el teléfono, donde "
             "el teclado lo agrega al autocompletar."],
            ["Los recordatorios están en gris",
             "Faltan los datos de pago. Ajustes → Datos de pago."],
            ["No me deja anular una venta",
             "Tiene abonos sin reversar. Reversalos primero desde \"Ver abonos\"."],
            ["Un cliente aparece dos veces",
             "Se crearon dos fichas de la misma persona. Avisá antes de seguir "
             "cargándole ventas: hay que fusionarlas para que la deuda quede en una."],
        ],
        [0.34, 0.66],
    )

    # ---------------------------------------------------------------------- 14
    pdf.h1("SECCIÓN 14", "Cuidados básicos")
    pdf.vinetas([
        ("Tu contraseña es tuya y no se comparte.",
         "El sistema registra quién hizo cada operación. Si prestás tu acceso, lo que "
         "haga esa persona queda a tu nombre."),
        ("Registrá el mismo día.",
         "Una venta o un abono anotado tres días después ya compite con la memoria. Y "
         "la fecha del formulario es la fecha real del hecho, no la del día en que lo "
         "cargás: de eso depende la tasa con que se convierte."),
        ("La referencia del pago no es opcional en la práctica.",
         "Es lo único que permite encontrar ese pago en el banco cuando algo no cuadra."),
        ("Confirmá la tasa cada mañana.",
         "El sistema la captura solo, pero vale mirarla. Es el dato que más "
         "silenciosamente descuadra las cuentas."),
        ("Al corregir, escribí un motivo que se entienda en tres meses.",
         "\"Error\" no explica nada. \"Cargada dos veces por equivocación\" sí."),
        ("Si algo te parece raro, no lo corrijas por tu cuenta.",
         "Avisá primero. Un número que parece mal casi siempre es un dato que falta, y "
         "\"arreglarlo\" a mano tapa el problema real."),
    ])
    pdf.ln(3)
    pdf.set_draw_color(*BORDE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(5)
    pdf.set_font("DejaVu", "", 9.3)
    pdf.set_text_color(*SUAVE)
    pdf.multi_cell(
        0, 5.2,
        "Ante cualquier duda, hablá con Hidelberg antes de improvisar. Es más rápido "
        "preguntar que deshacer.",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(SALIDA))
    return SALIDA


if __name__ == "__main__":
    print(f"  generado: {construir()}")
