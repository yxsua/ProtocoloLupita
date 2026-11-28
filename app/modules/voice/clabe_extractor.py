"""
clabe_extractor.py — Conversión y validación de CLABEs dictadas por voz.

Responsabilidades:
  1. Convertir números dictados en palabras ("cero uno dos ...") a dígitos.
  2. Validar el dígito verificador de una CLABE de 18 dígitos.
  3. Detectar confianza baja cuando la CLABE proviene de una sola fuente.
"""

from __future__ import annotations

import re
from typing import Optional

from app.modules.voice.models import IndicadorCandidato, NivelConfianza


# ---------------------------------------------------------------------------
# Tabla de conversión: palabras → dígitos
# ---------------------------------------------------------------------------

_PALABRAS_A_DIGITO: dict[str, str] = {
    # Español estándar
    "cero": "0", "uno": "1", "una": "1", "dos": "2", "tres": "3",
    "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7",
    "ocho": "8", "nueve": "9",
    # Variantes coloquiales / regionalismos
    "zero": "0", "un": "1",
    # Números en inglés (por si Whisper los devuelve así)
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # Dígitos como texto
    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
}

# Factores de ponderación CLABE (módulo 10 ponderado)
_CLABE_PESOS: list[int] = [3, 7, 1] * 6  # 18 posiciones, patrón repetido


# ---------------------------------------------------------------------------
# Funciones de conversión
# ---------------------------------------------------------------------------

def palabras_a_digitos(texto: str) -> str:
    """
    Convierte una cadena con números dictados en palabras a una cadena de dígitos.

    Ejemplos:
        "cero uno dos tres" → "0123"
        "cinco, seis, siete" → "567"
        "012345678901234567" → "012345678901234567"

    Ignora tokens no reconocidos (artículos, conjunciones, ruido).
    """
    # Normalizar: minúsculas, quitar puntuación excepto espacios
    texto_limpio = re.sub(r"[^\w\s]", " ", texto.lower().strip())
    tokens = texto_limpio.split()

    digitos: list[str] = []
    for token in tokens:
        if token in _PALABRAS_A_DIGITO:
            digitos.append(_PALABRAS_A_DIGITO[token])
        # Si es un grupo de dígitos pegados (ej. "012"), expandirlos
        elif token.isdigit():
            digitos.extend(list(token))
        # Ignorar tokens no reconocidos (artículos, conjunciones, etc.)

    return "".join(digitos)


def validar_digito_verificador_clabe(clabe: str) -> bool:
    """
    Valida el dígito verificador de una CLABE interbancaria de 18 dígitos.

    Algoritmo:
      1. Multiplicar cada dígito por su peso [3,7,1] cíclico.
      2. Tomar módulo 10 de cada producto.
      3. Sumar todos los residuos.
      4. El dígito verificador es (10 - (suma % 10)) % 10.
      5. Comparar con el último dígito de la CLABE.

    Returns:
        True si la CLABE tiene 18 dígitos y el verificador es correcto.
    """
    if len(clabe) != 18 or not clabe.isdigit():
        return False

    suma = 0
    for i in range(17):
        producto = int(clabe[i]) * _CLABE_PESOS[i]
        suma += producto % 10

    verificador_calculado = (10 - (suma % 10)) % 10
    return verificador_calculado == int(clabe[17])


def es_clabe_formato_valido(valor: str) -> bool:
    """Verifica que el valor tenga exactamente 18 dígitos."""
    return len(valor) == 18 and valor.isdigit()


# ---------------------------------------------------------------------------
# Extracción principal
# ---------------------------------------------------------------------------

def extraer_clabe(
    texto: str,
    fuente: str = "dictado",
    indicador_previo: Optional[IndicadorCandidato] = None,
) -> Optional[IndicadorCandidato]:
    """
    Extrae una CLABE del texto dictado (en palabras o dígitos).

    Args:
        texto: Transcripción del usuario con la CLABE.
        fuente: Identificador de la fuente (ej. "dictado_1", "dictado_2").
        indicador_previo: Si ya existe un indicador para esta CLABE,
                          se actualiza la lista de fuentes y la confianza.

    Returns:
        IndicadorCandidato con la CLABE, o None si no se pudo extraer.
    """
    digitos = palabras_a_digitos(texto)

    # Intentar extraer exactamente 18 dígitos consecutivos
    # (puede haber tokens extra antes/después)
    match = re.search(r"\d{18}", digitos)
    if match:
        clabe = match.group(0)
    elif len(digitos) == 18:
        clabe = digitos
    else:
        return None

    # Validar formato básico
    if not es_clabe_formato_valido(clabe):
        return None

    # Validar dígito verificador
    dv_ok = validar_digito_verificador_clabe(clabe)

    # Si hay indicador previo, actualizar fuentes y confianza
    if indicador_previo is not None and indicador_previo.valor == clabe:
        if fuente not in indicador_previo.fuentes:
            indicador_previo.fuentes.append(fuente)
        indicador_previo.digito_verificador_ok = dv_ok
        # Elevar confianza si hay confirmación cruzada
        if len(indicador_previo.fuentes) >= 2 and dv_ok:
            indicador_previo.confianza = NivelConfianza.ALTA
        elif dv_ok:
            indicador_previo.confianza = NivelConfianza.MEDIA
        indicador_previo.enmascarar()
        return indicador_previo

    # Crear nuevo indicador
    indicador = IndicadorCandidato(
        tipo="clabe",
        valor=clabe,
        confianza=NivelConfianza.BAJA if not dv_ok else NivelConfianza.MEDIA,
        fuentes=[fuente],
        digito_verificador_ok=dv_ok,
    )
    indicador.enmascarar()
    return indicador


def formatear_digitos_para_voz(clabe: str, grupo: int = 3) -> str:
    """
    Formatea una CLABE en grupos para lectura por voz.

    Ejemplo:
        "012345678901234567" → "cero uno dos, tres cuatro cinco, ..."
    """
    _DIGITO_A_PALABRA: dict[str, str] = {
        "0": "cero", "1": "uno", "2": "dos", "3": "tres",
        "4": "cuatro", "5": "cinco", "6": "seis", "7": "siete",
        "8": "ocho", "9": "nueve",
    }

    palabras = [_DIGITO_A_PALABRA.get(d, d) for d in clabe if d.isdigit()]
    grupos = [" ".join(palabras[i:i + grupo]) for i in range(0, len(palabras), grupo)]
    return ", ".join(grupos)
