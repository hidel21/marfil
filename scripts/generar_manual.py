"""Genera el manual de usuario de Marfil en PDF.

Se escribe con fpdf2 (ya está en requirements.txt) y DejaVu Sans, que sí trae los
acentos y la eñe: las fuentes internas de fpdf son latin-1 y parten el documento en
la primera "ó".
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF, XPos, YPos

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = Path("/usr/share/fonts/truetype/dejavu")
LOGO = RAIZ / "frontend/public/brand/marfil-logo.png"
SALIDA = RAIZ / "docs/Manual-Marfil.pdf"

TINTA = (38, 36, 33)
SUAVE = (110, 104, 96)
ACENTO = (140, 109, 63)
CREMA = (250, 246, 237)
BORDE = (222, 213, 196)
ALERTA = (150, 60, 45)
CREMA_ALERTA = (252, 242, 240)
URL = "https://marfil-sistema.onrender.com"


class Manual(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(True, margin=22)
        self.add_font("DejaVu", "", str(FUENTE / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FUENTE / "DejaVuSans-Bold.ttf"))
        self.set_margins(20, 20, 20)
        self.portada = True

    # ------------------------------------------------------------------ plantilla
    def footer(self) -> None:
        # `page_no()` y no un atributo: footer() corre al cerrar la página, cuando
        # cubierta() ya dejó la bandera en False y la portada se llevaría un pie.
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
        x = self.get_x()
        self.set_draw_color(*ACENTO)
        self.set_line_width(0.7)
        self.line(x, self.get_y(), x + 26, self.get_y())
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
                self.w - self.l_margin - self.r_margin - 8, 5.3, texto,
                align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
            self.ln(1.6)
        self.ln(1)

    def vinetas(self, items: list[tuple[str, str]]) -> None:
        for titulo, cuerpo in items:
            if self.get_y() > 258:
                self.add_page()
            y = self.get_y()
            self.set_fill_color(*ACENTO)
            self.rect(self.l_margin + 0.6, y + 2, 1.6, 1.6, style="F")
            self.set_xy(self.l_margin + 6, y)
            ancho = self.w - self.l_margin - self.r_margin - 6
            self.set_font("DejaVu", "B", 9.6)
            self.set_text_color(*TINTA)
            self.multi_cell(ancho, 5.3, titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if cuerpo:
                self.set_x(self.l_margin + 6)
                self.set_font("DejaVu", "", 9.6)
                self.set_text_color(*SUAVE)
                self.multi_cell(ancho, 5.1, cuerpo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(1.8)
        self.ln(0.5)

    def nota(self, titulo: str, cuerpo: str, alerta: bool = False) -> None:
        ancho = self.w - self.l_margin - self.r_margin
        self.set_font("DejaVu", "", 9.3)
        # Se mide el texto ya maquetado en vez de estimarlo: la estimación por ancho
        # de cadena dejaba los recuadros con un blanco de sobra al pie.
        lineas = self.multi_cell(ancho - 12, 4.9, cuerpo, dry_run=True, output="LINES")
        alto = 3.4 + 4.6 + len(lineas) * 4.9 + 3.6
        if self.get_y() + alto > 268:
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
        ancho = self.w - self.l_margin - self.r_margin
        anchos = [ancho * peso for peso in pesos]
        if self.get_y() + 12 + len(filas) * 7 > 270:
            self.add_page()
        self.set_font("DejaVu", "B", 8.6)
        self.set_fill_color(*TINTA)
        self.set_text_color(255, 255, 255)
        for w, texto in zip(anchos, cabeceras):
            self.cell(w, 7.5, "  " + texto, fill=True)
        self.ln(7.5)
        self.set_font("DejaVu", "", 8.8)
        for i, fila in enumerate(filas):
            altos = []
            for w, celda in zip(anchos, fila):
                altos.append(len(self.multi_cell(w - 4, 4.6, celda, dry_run=True, output="LINES")))
            alto = max(altos) * 4.6 + 3.4
            if self.get_y() + alto > 272:
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

    # -------------------------------------------------------------------- portada
    def cubierta(self) -> None:
        self.add_page()
        self.set_fill_color(*CREMA)
        self.rect(0, 0, self.w, self.h, style="F")
        if LOGO.exists():
            self.image(str(LOGO), x=(self.w - 78) / 2, y=52, w=78)
        # Cada línea vuelve a x=0 antes de centrarse: tras un cell con
        # new_x=LMARGIN el cursor queda en el margen y el centrado sale corrido.
        def centrado(y: float, alto: float, texto: str) -> None:
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
        centrado(150, 7, "Para Gregory y Gregor")
        self.set_font("DejaVu", "", 9.6)
        self.set_text_color(*SUAVE)
        centrado(157.5, 6, "Socios · Perfil de administrador")
        self.set_font("DejaVu", "", 9)
        centrado(246, 5, URL)
        centrado(251, 5, "Septiembre de 2026")
        self.portada = False


def construir() -> Path:
    pdf = Manual()
    pdf.cubierta()

    # ------------------------------------------------------------------------- 1
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
        "ni Hidelberg, llega a conocerla."
    )
    pdf.pasos([
        f"Entrá a {URL}/activar",
        "Escribí tu correo, exactamente el que le diste a Hidelberg.",
        "Pegá el código de activación que recibiste.",
        "Elegí tu contraseña. Mínimo 8 caracteres, pero usá una larga y que no "
        "uses en ningún otro sitio.",
        "Listo. Desde ahora entrás por la pantalla normal con tu correo y esa "
        "contraseña.",
    ])
    pdf.nota(
        "El código vence a las 72 horas",
        "Y sirve una sola vez. Si se te vence o lo usás sin querer dos veces, "
        "pedile a Hidelberg que te genere otro desde Ajustes → Usuarios. No hace "
        "falta crear la cuenta de nuevo.",
    )
    pdf.h2("La primera carga del día tarda")
    pdf.p(
        "El servidor se duerme cuando nadie lo usa durante 15 minutos. La primera "
        "vez que abrís la página después de un rato, tarda cerca de un minuto en "
        "responder: la pantalla se queda quieta y el botón dice \"Entrando…\". Es "
        "normal, no está roto."
    )
    pdf.nota(
        "No vuelvas a pulsar el botón",
        "Si pulsás otra vez, cancelás el intento que estaba en curso y volvés a "
        "empezar la espera. Pulsá una sola vez y dale hasta un minuto. A partir de "
        "ahí, todo va rápido.",
    )

    # ------------------------------------------------------------------------- 2
    pdf.h1("SECCIÓN 2", "Cómo está organizado")
    pdf.p(
        "El menú de la izquierda agrupa las pantallas en tres bloques. Los dos "
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
             "Los datos que alimentan las ventas: a quién le vendés, qué vendés, "
             "qué comprás y en qué gastás."],
            ["Gestión",
             "Finanzas, Socios, Reportes, Auditoría, Ajustes",
             "La mirada de arriba: resultados, reparto entre socios, informes y "
             "configuración."],
        ],
        [0.17, 0.36, 0.47],
    )
    pdf.h2("Dos ideas que conviene entender desde el principio")
    pdf.vinetas([
        ("El saldo de una venta no se escribe a mano.",
         "Lo calcula el sistema sumando los abonos registrados. Si un cliente debe "
         "de menos, es porque falta cargar un abono, no porque haya que corregir "
         "el número."),
        ("Auditoría avisa sola.",
         "Si aparece un número rojo junto a Auditoría en el menú, hay algo que "
         "revisar. No es urgente al segundo, pero no lo dejes crecer."),
    ])

    # ------------------------------------------------------------------------- 3
    pdf.h1("SECCIÓN 3", "Registrar una venta")
    pdf.p(
        "Es la operación más frecuente. Menú Principal → Registrar venta."
    )
    pdf.pasos([
        "Elegí el cliente. Si es nuevo, lo podés crear ahí mismo.",
        "Elegí el producto y la cantidad.",
        "Elegí el nivel de precio: Público, Team o Revendedor. El sistema trae el "
        "precio de ese nivel automáticamente.",
        "Revisá la fecha, y si la venta es a crédito, poné el plazo. El sistema "
        "calcula la fecha de vencimiento.",
        "Confirmá. Vas a ver el costo, la ganancia y el total antes de guardar.",
    ])
    pdf.h2("El guardia de precio")
    pdf.p(
        "Marfil revisa el precio que estás cobrando contra el precio de política "
        "del nivel elegido. No es para desconfiar de vos: es para que un cero de "
        "menos o un descuento olvidado no pase inadvertido."
    )
    pdf.tabla(
        ["Situación", "Qué hace el sistema", "Qué tenés que hacer"],
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
        ],
        [0.27, 0.24, 0.49],
    )
    pdf.nota(
        "Los descuentos existen; solo hay que nombrarlos",
        "El sistema nunca te impide hacer un buen precio. Lo único que pide es que "
        "digas por qué. Esa nota es la que después explica, en Auditoría, por qué "
        "un mes tuvo menos margen.",
    )
    pdf.h2("Si el producto no está en el catálogo")
    pdf.p(
        "La venta no se bloquea por eso, ni porque el stock esté en cero. Marfil "
        "prefiere que registres la venta real y ordenes el catálogo después, antes "
        "que perder la venta por un dato faltante."
    )

    # ------------------------------------------------------------------------- 4
    pdf.h1("SECCIÓN 4", "Cobrar y registrar abonos")
    pdf.h2("La pantalla de Cobranza")
    pdf.p(
        "Menú Principal → Cobranza. Es la lista de quién debe, ordenada por lo que "
        "más urge. Cada fila te dice el cliente, su teléfono, cuánto debe, cuántos "
        "días lleva de atraso, cuándo abonó por última vez y cuándo se le avisó "
        "por última vez."
    )
    pdf.nota(
        "Si ves el botón \"Cargar teléfonos\"",
        "Es que hay deudores sin número registrado. Sin teléfono no se les puede "
        "enviar recordatorio, así que conviene completarlos apenas puedas.",
    )
    pdf.h2("Registrar un abono")
    pdf.p("Menú Principal → Registrar abono.")
    pdf.pasos([
        "Elegí la venta que se está pagando. Vas a ver cuánto debe hoy.",
        "Poné la fecha real del pago, no la de hoy si el cliente pagó ayer.",
        "Elegí el método y escribí la referencia de la transferencia o el pago "
        "móvil. Esa referencia es lo que después permite encontrar el pago en el "
        "banco.",
        "Escribí el monto. Si es en bolívares, el sistema aplica la tasa del día y "
        "te muestra cuál usó.",
        "Antes de guardar, mirá el saldo que va a quedar. Si no cuadra con lo que "
        "esperabas, revisá el monto.",
    ])
    pdf.p(
        "Al guardar podés descargar el recibo en PDF y enviárselo al cliente. Es "
        "buena práctica hacerlo siempre: evita discusiones después."
    )

    # ------------------------------------------------------------------------- 5
    pdf.h1("SECCIÓN 5", "Recordatorios de cobro")
    pdf.p(
        "Menú Principal → Recordatorios. Marfil arma el mensaje con el nombre del "
        "cliente, lo que debe y los datos para pagarte. Podés enviarlos de a uno o "
        "por lote a varios deudores."
    )
    pdf.nota(
        "Están bloqueados hasta completar los datos de pago",
        "No es una falla. Un recordatorio sin banco ni número al que transferir "
        "solo genera una llamada de vuelta preguntando cómo pagar. Completá "
        "Ajustes → Datos de pago (banco, documento y teléfono) y se habilitan "
        "solos.",
        alerta=True,
    )
    pdf.p(
        "Antes de enviar por lote, mirá la columna del último aviso en Cobranza. "
        "Avisarle dos veces en el mismo día a la misma persona cansa y hace que "
        "dejen de leer los mensajes."
    )

    # ------------------------------------------------------------------------- 6
    pdf.h1("SECCIÓN 6", "Clientes y productos")
    pdf.h2("Clientes")
    pdf.p(
        "Menú Operación → Clientes. Cada cliente tiene su teléfono y su historial "
        "de compras y pagos. Si intentás crear uno que ya existe, el sistema te "
        "avisa en vez de duplicarlo: dos fichas de la misma persona parten su "
        "deuda en dos y ninguna refleja lo que debe de verdad."
    )
    pdf.h2("Productos")
    pdf.p(
        "Menú Operación → Productos. Cada producto tiene su costo y sus tres "
        "niveles de precio: Público, Team y Revendedor."
    )
    pdf.nota(
        "Hay productos esperando revisión",
        "Al migrar el catálogo histórico, los productos a los que les falta el "
        "costo o algún nivel de precio quedaron marcados como \"por revisar\". "
        "Están en Productos → Revisión. Mientras un producto siga así, el guardia "
        "de precio no puede protegerte al venderlo, porque no sabe con qué "
        "comparar. Completarlos es la tarea pendiente más útil del sistema.",
    )

    # ------------------------------------------------------------------------- 7
    pdf.h1("SECCIÓN 7", "Gestión y control")
    pdf.vinetas([
        ("Resumen",
         "La foto del día: ventas, cobros y lo que está por vencer. Es la pantalla "
         "con la que conviene empezar la jornada."),
        ("Finanzas",
         "Ingresos, costos y margen del período. Responde \"cómo nos fue\"."),
        ("Socios",
         "El reparto entre los tres. Tu cuenta ya está ligada a tu ficha de socio, "
         "así que lo que te corresponde se calcula solo."),
        ("Reportes",
         "Informes descargables para revisar fuera del sistema o compartir."),
        ("Compras y Gastos",
         "Lo que sale: reposición de inventario y gastos generales. Sin esto "
         "cargado, el margen que muestra Finanzas es optimista."),
    ])
    pdf.h2("Auditoría")
    pdf.p(
        "Menú Gestión → Auditoría. Es el control de calidad del sistema y tiene "
        "cuatro miradas:"
    )
    pdf.vinetas([
        ("Conciliación",
         "Comprueba que las ventas, los pagos y el stock cuadren entre sí. Lo que "
         "querés ver siempre es \"cuadra\"."),
        ("Actividad",
         "Quién hizo qué y cuándo. Entre socios, esto evita conversaciones "
         "incómodas."),
        ("Fuga de precio",
         "Ventas que salieron por debajo de la política. Sirve para ver si los "
         "descuentos se están volviendo la norma."),
        ("Bajo costo",
         "Productos cuyo precio quedó peligrosamente cerca del costo, o por "
         "debajo."),
    ])
    pdf.nota(
        "Si aparece un número rojo junto a Auditoría",
        "Es la cantidad de asuntos críticos por revisar. Entrá y leé qué son. Casi "
        "siempre es un dato que falta, no un problema grave, pero acumularlos hace "
        "que los números del mes dejen de ser confiables.",
    )

    # ------------------------------------------------------------------------- 8
    pdf.h1("SECCIÓN 8", "Ajustes")
    pdf.p(
        "Menú Gestión → Ajustes. Como administradores pueden tocar todo esto, así "
        "que conviene saber qué hace cada cosa antes de cambiarla."
    )
    pdf.tabla(
        ["Ajuste", "Qué controla"],
        [
            ["Datos de pago",
             "Banco, documento y teléfono que aparecen en los recordatorios y "
             "recibos. Sin esto, los recordatorios no se envían."],
            ["Tasas",
             "La tasa del día que convierte bolívares a dólares. Confirmala cada "
             "mañana: si la tasa está vieja, todos los abonos en bolívares del día "
             "quedan mal convertidos."],
            ["Política",
             "Las reglas de precio contra las que compara el guardia. Cambiarlas "
             "afecta a todas las ventas siguientes."],
            ["Usuarios",
             "Crear cuentas nuevas y regenerar códigos de activación."],
            ["Automatizaciones",
             "El estado de las tareas diarias. Deberían estar todas en \"ok\"."],
            ["Mi contraseña",
             "Cambiar la tuya. Al cambiarla se cierran todas tus sesiones abiertas."],
        ],
        [0.26, 0.74],
    )

    # ------------------------------------------------------------------------- 9
    pdf.h1("SECCIÓN 9", "Cuando algo no funciona")
    pdf.tabla(
        ["Lo que ves", "Qué significa y qué hacer"],
        [
            ["La página tarda muchísimo en abrir",
             "El servidor estaba dormido. Esperá hasta un minuto sin recargar ni "
             "volver a pulsar. Pasa solo en la primera carga después de un rato "
             "sin uso."],
            ["\"El correo o la contraseña no coinciden\"",
             "Revisá que no haya un espacio al final, sobre todo en el teléfono, "
             "donde el teclado lo agrega al autocompletar. Si sigue, pedile a "
             "Hidelberg un código nuevo desde Ajustes → Usuarios."],
            ["No me deja guardar la venta",
             "Es el guardia de precio. Leé el recuadro rojo: te dice exactamente "
             "qué pasa y qué falta. Casi siempre es escribir el motivo del "
             "descuento."],
            ["Los recordatorios están en gris",
             "Faltan los datos de pago. Ajustes → Datos de pago."],
            ["El sistema me sacó de la sesión",
             "Por seguridad la sesión caduca. Volvé a entrar. Si pasa muy seguido, "
             "avisá."],
            ["Un cliente aparece dos veces",
             "Se crearon dos fichas de la misma persona. Avisá antes de seguir "
             "cargándole ventas: hay que fusionarlas para que la deuda quede en "
             "una sola."],
        ],
        [0.33, 0.67],
    )

    # ------------------------------------------------------------------------ 10
    pdf.h1("SECCIÓN 10", "Cuidados básicos")
    pdf.vinetas([
        ("Tu contraseña es tuya y no se comparte.",
         "El sistema registra quién hizo cada operación. Si prestás tu acceso, lo "
         "que haga esa persona queda a tu nombre."),
        ("Registrá el mismo día.",
         "Una venta o un abono que se anota tres días después ya compite con la "
         "memoria. La fecha del formulario es la fecha real del hecho, no la del "
         "día en que lo cargás."),
        ("La referencia del pago no es opcional en la práctica.",
         "Es lo único que permite encontrar ese pago en el banco cuando algo no "
         "cuadra."),
        ("Confirmá la tasa cada mañana.",
         "Es el ajuste que más silenciosamente descuadra las cuentas."),
        ("Si algo te parece raro, no lo corrijas por tu cuenta.",
         "Avisá primero. Un número que parece mal casi siempre es un dato que "
         "falta, y \"arreglarlo\" a mano tapa el problema real."),
    ])
    pdf.ln(4)
    pdf.set_draw_color(*BORDE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(5)
    pdf.set_font("DejaVu", "", 9.3)
    pdf.set_text_color(*SUAVE)
    pdf.multi_cell(
        0, 5.2,
        "Ante cualquier duda, hablá con Hidelberg antes de improvisar. Es más "
        "rápido preguntar que deshacer.",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(SALIDA))
    return SALIDA


if __name__ == "__main__":
    ruta = construir()
    print(f"  generado: {ruta}")
