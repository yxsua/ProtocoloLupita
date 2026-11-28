"""Extractores deterministas de indicadores, normalización y firma de guion."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional

from .contracts import Channel, ExtractedIndicator, ThreatCategory
from .validators import verify_clabe, verify_luhn

VALUE_HASH_SALT = "lupita-intel-v1"

SHORTENER_DOMAINS: frozenset[str] = frozenset(
    {
        "bit.ly",
        "tinyurl.com",
        "t.co",
        "cutt.ly",
        "short.gy",
        "ow.ly",
        "is.gd",
        "rb.gy",
    }
)

BRAND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SAT", re.compile(r"\b(sat|servicio de administracion tributaria)\b", re.IGNORECASE)),
    ("IMSS", re.compile(r"\b(imss|seguro social)\b", re.IGNORECASE)),
    ("CFE", re.compile(r"\b(cfe|comision federal de electricidad)\b", re.IGNORECASE)),
    ("BBVA", re.compile(r"\b(bbva|bancomer)\b", re.IGNORECASE)),
    ("Banamex", re.compile(r"\b(citibanamex|banamex)\b", re.IGNORECASE)),
    ("Banco Azteca", re.compile(r"\bbanco azteca\b", re.IGNORECASE)),
    ("Santander", re.compile(r"\bsantander\b", re.IGNORECASE)),
    ("Banorte", re.compile(r"\bbanorte\b", re.IGNORECASE)),
    ("DHL", re.compile(r"\bdhl\b", re.IGNORECASE)),
    ("Estafeta", re.compile(r"\bestafeta\b", re.IGNORECASE)),
    ("FedEx", re.compile(r"\bfedex\b", re.IGNORECASE)),
    ("WhatsApp", re.compile(r"\bwhatsapp\b", re.IGNORECASE)),
    ("Telcel", re.compile(r"\btelcel\b", re.IGNORECASE)),
    ("Banco Demo", re.compile(r"\bbanco demo\b", re.IGNORECASE)),
]

REQUESTED_DATA_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("NIP", re.compile(r"\bnip\b", re.IGNORECASE)),
    ("CVV", re.compile(r"\b(cvv|codigo de seguridad)\b", re.IGNORECASE)),
    (
        "codigo_verificacion",
        re.compile(
            r"\b(codigo de verificacion|codigo sms|codigo de 6 digitos|otp|token)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "transferencia",
        re.compile(
            r"\b(depositar|deposite|deposito|transferencia|transfiere|transferir|pagar|pague|pago)\b",
            re.IGNORECASE,
        ),
    ),
]

SPOKEN_SINGLE_DIGITS: dict[str, str] = {
    "cero": "0",
    "uno": "1",
    "un": "1",
    "una": "1",
    "dos": "2",
    "tres": "3",
    "cuatro": "4",
    "cinco": "5",
    "seis": "6",
    "siete": "7",
    "ocho": "8",
    "nueve": "9",
}

SPOKEN_COMPOUND_NUMBERS: dict[str, int] = {
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintiun": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}

SPOKEN_TENS: dict[str, int] = {
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
}

SPOKEN_HUNDREDS: dict[str, int] = {
    "cien": 100,
    "ciento": 100,
    "doscientos": 200,
    "trescientos": 300,
    "cuatrocientos": 400,
    "quinientos": 500,
    "seiscientos": 600,
    "setecientos": 700,
    "ochocientos": 800,
    "novecientos": 900,
}

EXECUTABLE_EXTENSIONS: tuple[str, ...] = (".apk", ".exe", ".msi", ".bat", ".scr", ".ipa")

URL_REGEX = re.compile(
    r"(?:hxxps?|https?)://[^\s<>'\"()]+|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?/[^\s<>'\"()]*|"
    r"\b(?:[a-z0-9-]+\.)+(?:com|mx|org|net|gob|info|xyz|ly|co|gy|app|site|online)"
    r"(?:\.[a-z]{2,3})?(?:/[^\s<>'\"()]*)?",
    re.IGNORECASE,
)

DIGIT_CANDIDATE_REGEX = re.compile(r"(?<!\d)(?:\d[\s\-.]?){10,20}(?!\d)")


def strip_accents(text: str) -> str:
    """Elimina acentos manteniendo ñ y estructura de texto."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def compute_value_hash(kind: str, normalized_value: str) -> str:
    """Calcula el hash interno determinista para correlación sin exponer el dato."""
    material = f"{VALUE_HASH_SALT}|{kind}|{normalized_value}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def defang_url(url: str) -> str:
    """Convierte URLs a formato desactivado hxxp/hxxps y limpia puntuación final."""
    cleaned = url.strip().rstrip(".,;:!?)")
    lowered = cleaned.lower()
    if lowered.startswith("https://"):
        return "hxxps://" + cleaned[8:]
    if lowered.startswith("http://"):
        return "hxxp://" + cleaned[7:]
    if lowered.startswith("hxxps://") or lowered.startswith("hxxp://"):
        return lowered[: lowered.find("://") + 3] + cleaned[cleaned.find("://") + 3 :]
    return "hxxp://" + cleaned


def extract_domain(defanged_url: str) -> str:
    """Obtiene el host en minúsculas desde una URL desactivada."""
    without_scheme = re.sub(r"^hxxps?://", "", defanged_url, flags=re.IGNORECASE)
    host = without_scheme.split("/", 1)[0].split("?", 1)[0].split(":", 1)[0]
    return host.lower()


def _is_valid_ipv4(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def _is_executable_url(defanged_url: str) -> bool:
    without_scheme = re.sub(r"^hxxps?://", "", defanged_url, flags=re.IGNORECASE)
    if "/" not in without_scheme:
        return False
    path = "/" + without_scheme.split("/", 1)[1]
    clean_path = path.split("?", 1)[0].split("#", 1)[0].lower()
    return clean_path.endswith(EXECUTABLE_EXTENSIONS)


def mask_phone(digits_10: str) -> str:
    """Enmascara un número telefónico de 10 dígitos mostrando solo últimos 4."""
    return f"******{digits_10[-4:]}"


def _parse_spoken_number_block(tokens: list[str], start: int) -> tuple[Optional[str], int]:
    """Convierte un grupo numérico hablado (0-999 o dígito) empezando en start."""
    tok = tokens[start]
    if tok == "doble" and start + 1 < len(tokens) and tokens[start + 1] in SPOKEN_SINGLE_DIGITS:
        digit = SPOKEN_SINGLE_DIGITS[tokens[start + 1]]
        return digit * 2, start + 2

    if tok in SPOKEN_SINGLE_DIGITS:
        return SPOKEN_SINGLE_DIGITS[tok], start + 1

    if tok in SPOKEN_COMPOUND_NUMBERS:
        return str(SPOKEN_COMPOUND_NUMBERS[tok]), start + 1

    if tok in SPOKEN_TENS:
        val = SPOKEN_TENS[tok]
        idx = start + 1
        if idx + 1 < len(tokens) and tokens[idx] == "y" and tokens[idx + 1] in SPOKEN_SINGLE_DIGITS:
            val += int(SPOKEN_SINGLE_DIGITS[tokens[idx + 1]])
            idx += 2
        return str(val), idx

    if tok in SPOKEN_HUNDREDS:
        val = SPOKEN_HUNDREDS[tok]
        idx = start + 1
        if tok == "cien":
            return "100", idx
        if idx < len(tokens):
            nxt = tokens[idx]
            if nxt in SPOKEN_COMPOUND_NUMBERS:
                val += SPOKEN_COMPOUND_NUMBERS[nxt]
                idx += 1
            elif nxt in SPOKEN_TENS:
                val += SPOKEN_TENS[nxt]
                idx += 1
                if (
                    idx + 1 < len(tokens)
                    and tokens[idx] == "y"
                    and tokens[idx + 1] in SPOKEN_SINGLE_DIGITS
                ):
                    val += int(SPOKEN_SINGLE_DIGITS[tokens[idx + 1]])
                    idx += 2
            elif nxt in SPOKEN_SINGLE_DIGITS:
                val += int(SPOKEN_SINGLE_DIGITS[nxt])
                idx += 1
        return str(val), idx

    return None, start


def normalize_spoken_digits(text: str) -> str:
    """Convierte secuencias de números dictados en palabras a bloques de dígitos."""
    plain = strip_accents(text.lower())
    raw_tokens = re.findall(r"[a-z0-9]+|[,.;:]+", plain)
    output_parts: list[str] = []
    digit_buffer: list[str] = []
    i = 0

    def flush_digits() -> None:
        if digit_buffer:
            output_parts.append("".join(digit_buffer))
            digit_buffer.clear()

    while i < len(raw_tokens):
        tok = raw_tokens[i]
        if tok.isdigit():
            digit_buffer.append(tok)
            i += 1
            continue

        if tok in (",", ";", "con") and digit_buffer:
            # Permite unir bloques dictados con pausas: "cero doce, ciento ochenta..."
            i += 1
            continue

        parsed, next_i = _parse_spoken_number_block(raw_tokens, i)
        if parsed is not None:
            digit_buffer.append(parsed)
            i = next_i
            continue

        flush_digits()
        if not re.fullmatch(r"[,.;:]+", tok):
            output_parts.append(tok)
        i += 1

    flush_digits()
    return " ".join(output_parts)


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    return any(not (span[1] <= s or span[0] >= e) for s, e in occupied)


def _extract_numeric_candidates(text: str) -> list[tuple[str, tuple[int, int]]]:
    results: list[tuple[str, tuple[int, int]]] = []
    for match in DIGIT_CANDIDATE_REGEX.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if digits:
            results.append((digits, match.span()))
    return results


def _normalize_mx_phone(digits: str) -> Optional[str]:
    if len(digits) == 10:
        return digits
    if len(digits) == 12 and digits.startswith("52"):
        return digits[2:]
    if len(digits) == 13 and digits.startswith("521"):
        return digits[3:]
    return None


def extract_indicators(text: str, channel: Channel | str = "call") -> list[ExtractedIndicator]:
    """Extrae deterministamente CLABE, tarjeta, teléfono, URL, marca y datos pedidos."""
    if not text:
        return []

    indicators: list[ExtractedIndicator] = []
    seen_hashes: set[str] = set()
    occupied_spans: list[tuple[int, int]] = []

    def add_indicator(ind: ExtractedIndicator) -> None:
        key = f"{ind.type}:{ind.value_hash}"
        if key not in seen_hashes:
            seen_hashes.add(key)
            indicators.append(ind)

    # 1. URLs (desactivadas con hxxp/hxxps, sin abrirlas)
    for match in URL_REGEX.finditer(text):
        raw_url = match.group(0)
        defanged = defang_url(raw_url)
        domain = extract_domain(defanged)
        is_ip_url = _is_valid_ipv4(domain)
        if not domain or (domain.replace(".", "").isdigit() and not is_ip_url):
            continue
        occupied_spans.append(match.span())
        is_exec = _is_executable_url(defanged)
        meta = {
            "domain": domain,
            "is_shortener": "true" if domain in SHORTENER_DOMAINS else "false",
            "is_punycode": "true" if "xn--" in domain else "false",
            "is_ip_url": "true" if is_ip_url else "false",
            "is_executable_download": "true" if is_exec else "false",
            "defanged": "true",
        }
        add_indicator(
            ExtractedIndicator(
                type="url",
                value_masked=defanged,
                value_hash=compute_value_hash("url", defanged.lower()),
                is_primary_correlator=True,
                valid=None,
                validation_detail="defanged_not_opened",
                metadata=meta,
            )
        )

    # 2. Cuentas CLABE y tarjetas en texto original y en dígitos dictados (E04)
    searchable_texts = [text]
    spoken_normalized = normalize_spoken_digits(text)
    if spoken_normalized != strip_accents(text.lower()):
        searchable_texts.append(spoken_normalized)

    for idx_source, src_text in enumerate(searchable_texts):
        candidates = _extract_numeric_candidates(src_text)
        # Primero CLABEs (18 dígitos o candidatos cercanos de 17-19 si parecen cuenta bancaria)
        for digits, span in candidates:
            if len(digits) == 18:
                ver = verify_clabe(digits)
                if idx_source == 0:
                    occupied_spans.append(span)
                add_indicator(
                    ExtractedIndicator(
                        type="clabe",
                        value_masked=ver.value_masked,
                        value_hash=compute_value_hash("clabe", digits),
                        is_primary_correlator=True,
                        valid=ver.valid,
                        validation_detail=ver.reason,
                        metadata={
                            "synthetic_bank": ver.synthetic_bank or "",
                            "from_spoken": "true" if idx_source == 1 else "false",
                        },
                    )
                )

        # Luego tarjetas (13-19 dígitos excluyendo 18 ya capturados como CLABE)
        for digits, span in candidates:
            if idx_source == 0 and _overlaps(span, occupied_spans):
                continue
            if 13 <= len(digits) <= 19 and len(digits) != 18:
                ver = verify_luhn(digits)
                if idx_source == 0:
                    occupied_spans.append(span)
                add_indicator(
                    ExtractedIndicator(
                        type="card",
                        value_masked=ver.value_masked,
                        value_hash=compute_value_hash("card", digits),
                        is_primary_correlator=True,
                        valid=ver.valid,
                        validation_detail=ver.reason,
                        metadata={"synthetic_bank": ver.synthetic_bank or ""},
                    )
                )

        # Finalmente teléfonos citados en texto (excluyendo spans ya tomados)
        for digits, span in candidates:
            if idx_source == 0 and _overlaps(span, occupied_spans):
                continue
            phone_10 = _normalize_mx_phone(digits)
            if phone_10 is not None:
                if idx_source == 0:
                    occupied_spans.append(span)
                add_indicator(
                    ExtractedIndicator(
                        type="contact_phone",
                        value_masked=mask_phone(phone_10),
                        value_hash=compute_value_hash("contact_phone", phone_10),
                        is_primary_correlator=True,
                        valid=True,
                        validation_detail="mx_10_digits",
                        metadata={"channel": str(channel)},
                    )
                )

    # 3. Marcas suplantadas y datos solicitados (sobre texto sin acentos; ignora inyecciones)
    plain = strip_accents(text)
    for brand_name, pattern in BRAND_PATTERNS:
        if pattern.search(plain):
            add_indicator(
                ExtractedIndicator(
                    type="brand",
                    value_masked=brand_name,
                    value_hash=compute_value_hash("brand", brand_name.lower()),
                    is_primary_correlator=False,
                    valid=None,
                    validation_detail="keyword_match",
                )
            )

    for data_label, pattern in REQUESTED_DATA_PATTERNS:
        if pattern.search(plain):
            add_indicator(
                ExtractedIndicator(
                    type="requested_data",
                    value_masked=data_label,
                    value_hash=compute_value_hash("requested_data", data_label),
                    is_primary_correlator=False,
                    valid=None,
                    validation_detail="cue_match",
                )
            )

    return indicators


def classify_threat(
    text: str,
    channel: Channel | str,
    indicators: list[ExtractedIndicator],
) -> tuple[ThreatCategory, str, list[str]]:
    """Clasifica de forma determinista la amenaza y su etiqueta legal orientativa."""
    plain = strip_accents(text.lower())
    reasons: list[str] = []

    has_financial = any(ind.type in ("clabe", "card") for ind in indicators)
    url_indicators = [ind for ind in indicators if ind.type == "url"]
    has_url = bool(url_indicators)
    has_exec_url = any(
        ind.metadata.get("is_executable_download") == "true" for ind in url_indicators
    )
    has_ip_url = any(ind.metadata.get("is_ip_url") == "true" for ind in url_indicators)
    brands = {ind.value_masked for ind in indicators if ind.type == "brand"}
    requested = {ind.value_masked for ind in indicators if ind.type == "requested_data"}

    if has_exec_url:
        reasons.append("Enlace hacia archivo ejecutable de riesgo (.apk/.exe) desactivado.")
    if has_ip_url:
        reasons.append("Enlace apunta a una dirección IP directa en lugar de dominio oficial.")

    # Secuestro virtual / suplantación familiar (E02)
    if re.search(
        r"\b(secuestr|tenemos a tu nieto|tenemos a tu hijo|no cuelgues|rescate|lo vamos a lastimar)\b",
        plain,
    ):
        reasons.append("Patrón de secuestro virtual / coacción familiar.")
        return "secuestro_virtual", "posible_extorsion_ley_general_2025", reasons

    # Extorsión / cobro de piso (E01)
    if re.search(
        r"\b(cartel|cobro de piso|cuota|proteccion|plaza|comandante|levanton|deposite a la cuenta)\b",
        plain,
    ):
        reasons.append("Patrón de extorsión telefónica / cobro de piso.")
        return "extorsion_cobro_piso", "posible_extorsion_ley_general_2025", reasons

    # Robo de WhatsApp
    if "WhatsApp" in brands or (
        "codigo_verificacion" in requested and re.search(r"\b(whatsapp|codigo de 6 digitos|por error)\b", plain)
    ):
        reasons.append("Solicitud de código de verificación compatible con robo de cuenta.")
        return "robo_whatsapp", "posible_fraude_suplantacion", reasons

    # Falso ejecutivo bancario (E03)
    bank_brands = {"BBVA", "Banamex", "Banco Azteca", "Santander", "Banorte", "Banco Demo"}
    if (brands & bank_brands) or (
        re.search(r"\b(ejecutivo|area de fraudes|cargo no reconocido|bloquear su tarjeta|nip)\b", plain)
        and ("NIP" in requested or "CVV" in requested or "codigo_verificacion" in requested or has_financial)
    ):
        reasons.append("Suplantación de área bancaria con solicitud de credenciales o cuenta.")
        return "falso_ejecutivo_bancario", "posible_fraude_suplantacion", reasons

    # Falsos premios / paquetes retenidos (E10)
    if (brands & {"DHL", "Estafeta", "FedEx"}) or re.search(
        r"\b(paquete retenido|aduana|guia de envio|ganaste un premio|reclama tu premio)\b",
        plain,
    ):
        reasons.append("Patrón de paquete retenido o premio falso.")
        return "falso_premio_paquete", "posible_fraude_suplantacion", reasons

    # Préstamos montadeudas / empleo / inversión
    if re.search(
        r"\b(prestamo inmediato|sin buro|montadeudas|inversion garantizada|trabajo desde casa)\b",
        plain,
    ) or (has_exec_url and re.search(r"\b(prestamo|credito|descarga|instala|app)\b", plain)):
        reasons.append("Patrón de préstamo fraudulento o fraude de empleo/inversión.")
        return "montadeudas_empleo_inversion", "posible_fraude_suplantacion", reasons

    # Suplantación familiar sin secuestro explícito
    if re.search(r"\b(soy tu sobrino|soy tu nieto|cambie de numero|estoy en el aeropuerto)\b", plain) and (
        has_financial or "transferencia" in requested
    ):
        reasons.append("Patrón de suplantación de familiar solicitando dinero.")
        return "suplantacion_familiar", "posible_fraude_suplantacion", reasons

    # Smishing genérico (E09, E11)
    if channel == "sms" and (
        has_url
        or bool(brands)
        or re.search(
            r"\b(devolucion|adeudo|multa|suspendida|regularice|verifique su cuenta|actualice)\b",
            plain,
        )
    ):
        reasons.append("Patrón de smishing / suplantación institucional en SMS.")
        return "smishing", "posible_fraude_suplantacion", reasons

    # Portal o llamada con indicador financiero + solicitud de depósito aunque falten palabras clave típicas
    if has_financial and ("transferencia" in requested or "NIP" in requested or channel == "portal"):
        reasons.append("Cuenta de cobro o solicitud sensible detectada.")
        return "extorsion_cobro_piso", "posible_extorsion_ley_general_2025", reasons

    if has_url and channel == "portal":
        reasons.append("Enlace sospechoso reportado en portal ciudadano.")
        return "smishing", "posible_fraude_suplantacion", reasons

    # E08: llamada o mensaje legítimo sin cobro ni guion de fraude
    reasons.append("Sin indicadores de cobro ni patrones de guion fraudulento.")
    return "no_aplica", "sin_tipificacion", reasons


def build_template_signature(text: str) -> tuple[str, frozenset[str]]:
    """Genera firma anonimizada de plantilla y conjunto de n-gramas para agrupar variantes."""
    normalized = URL_REGEX.sub(" <URL> ", text)
    normalized = DIGIT_CANDIDATE_REGEX.sub(" <ACCOUNT_OR_PHONE> ", normalized)
    normalized = re.sub(r"\$\s*\d[\d,.]*", " <AMOUNT> ", normalized)
    normalized = strip_accents(normalized.lower())
    normalized = re.sub(r"\b\d+\b", " <NUM> ", normalized)
    normalized = re.sub(r"[^a-z0-9<>_\s]", " ", normalized)
    tokens = [tok for tok in normalized.split() if tok]
    template_str = " ".join(tokens)

    if len(tokens) < 3:
        return template_str, frozenset(tokens)
    shingles = frozenset(" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2))
    return template_str, shingles
