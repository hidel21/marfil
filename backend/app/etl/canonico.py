"""Canonicalizacion de nombres de personas y productos.

Separado del ETL porque lo usan tanto las migraciones como la importacion del libro
y la API cuando alguien crea un cliente escribiendo su nombre.
"""

from __future__ import annotations

from app.core.normalizacion import clave_nombre, normalizar_nombre

#: Particulas que no se capitalizan en medio de un nombre.
MINUSCULAS = frozenset({"de", "del", "la", "las", "los", "y", "da", "di", "van", "von"})


def nombre_canonico(texto: object) -> str:
    """'ricardo palacios' -> 'Ricardo Palacios'; 'JUAN HERRADE' -> 'Juan Herrade'.

    Conserva los acentos ('Ángel' sigue siendo 'Ángel') y no toca la ortografia:
    solo capitalizacion y espacios. Unificar dos grafias distintas es una decision
    de negocio y va por la tabla de alias, no por una funcion de formato.
    """
    if texto is None:
        return ""
    palabras = str(texto).strip().split()
    if not palabras:
        return ""

    resultado = []
    for i, palabra in enumerate(palabras):
        minuscula = palabra.lower()
        if i > 0 and minuscula in MINUSCULAS:
            resultado.append(minuscula)
        elif palabra.isupper() and len(palabra) <= 3 and not palabra.isalpha():
            # Siglas y codigos cortos con digitos ('212', '9PM'): se dejan como estan.
            resultado.append(palabra)
        else:
            resultado.append(minuscula[:1].upper() + minuscula[1:])
    return " ".join(resultado)


def agrupar_por_clave(nombres: list[str]) -> dict[str, list[str]]:
    """Agrupa grafias por su clave de unicidad.

    {'ricardopalacios': ['Ricardo palacios', 'RICARDO PALACIOS'], ...}
    """
    grupos: dict[str, list[str]] = {}
    for nombre in nombres:
        clave = clave_nombre(nombre)
        if not clave:
            continue
        grupos.setdefault(clave, [])
        if nombre not in grupos[clave]:
            grupos[clave].append(nombre)
    return grupos


def mejor_grafia(variantes: list[str], *, canonicalizar: bool = True) -> str:
    """De varias grafias del mismo nombre, la que conviene mostrar.

    `canonicalizar=True` (personas): siempre aplica capitalizacion de titulo, asi
    'Ricardo palacios' y 'RICARDO PALACIOS' quedan las dos en 'Ricardo Palacios'.
    Es seguro porque `nombre_canonico` solo cambia mayusculas y espacios.

    `canonicalizar=False` (productos): conserva la grafia de origen, eligiendo la que
    ya viene bien escrita. Para un catalogo importa la ortografia del proveedor
    ('EROS MEN VERSACHE' no se mejora convirtiendolo en 'Eros Men Versache'), y la
    auditoria del libro ya normalizo esos nombres una vez.
    """
    if not variantes:
        return ""
    if canonicalizar:
        return nombre_canonico(mejor_grafia(variantes, canonicalizar=False))

    mixtas = [
        " ".join(v.split())
        for v in variantes
        if v.strip() and not v.strip().isupper() and not v.strip().islower()
    ]
    if mixtas:
        # La mas larga: suele ser la mas completa ('Club de Nuit Urban Elixir').
        return max(mixtas, key=len)
    return " ".join(variantes[0].split())


def es_probable_prefijo(clave_corta: str, clave_larga: str) -> bool:
    """'ricardo' es prefijo de 'ricardopalacios': candidato a revision, no a fusion.

    Fusionar clientes en silencio es como se pierde una cuenta por cobrar, asi que
    esto solo marca; decidir es del dueno.
    """
    return (
        len(clave_corta) >= 4
        and clave_corta != clave_larga
        and clave_larga.startswith(clave_corta)
    )


__all__ = [
    "agrupar_por_clave",
    "clave_nombre",
    "es_probable_prefijo",
    "mejor_grafia",
    "nombre_canonico",
    "normalizar_nombre",
]
