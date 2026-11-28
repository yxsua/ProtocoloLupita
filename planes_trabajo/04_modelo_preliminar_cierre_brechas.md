# Modelo preliminar — Modificaciones propuestas y cierre de brechas (Plan 4)

**Documento de diseño previo a implementación (v2 — alineado con Alcance Ampliado "Mosca Estéril")**  
**Referencia base:** [04_extractor_evidencia_inteligencia.md](./04_extractor_evidencia_inteligencia.md)  
**Alineación cruzada:** [Plan 1](./01_plataforma_integracion_escenarios.md) · [Plan 2](./02_siembra_atribucion_tablero_mapa.md) · [Plan 3](./03_dona_lupita_voz.md) · [Plan 5](./05_sms_portal_ciudadano.md) · *Mosca Estéril — Alcance ampliado del prototipo (PDF)*

---

## 1. Propósito y nota organizativa

Este documento define el **modelo preliminar técnico y contractual** para cerrar todas las brechas detectadas al cruzar el Plan 4 (*Extractor, evidencia y motor de inteligencia*), los planes 1, 2, 3 y 5, y el documento **Mosca Estéril — Alcance ampliado del prototipo**, **antes de iniciar la implementación en código**.

> **Nota sobre numeración de roles:** En el documento general de alcance (págs. 11–12), *Extractor, evidencia y motor de inteligencia* figura como **Persona 3**, mientras que en `planes_trabajo/` corresponde al **Integrante 4**. Ambos describen exactamente la misma responsabilidad funcional. Asimismo, conforme al orden de recorte del alcance (primero mapa, luego bandeja de SMS), los módulos de `intel/` y `evidence/` forman parte del núcleo prioritario (Prioridad 1 y 2).

El objetivo es congelar en la **Hora 0–1** los esquemas, fronteras entre módulos y reglas invariantes para que el equipo avance en paralelo sin duplicar lógica ni romper la integración offline.

---

## 2. Resumen de brechas detectadas y soluciones

| ID | Brecha detectada | Módulos/Planes afectados | Solución explícita propuesta |
|---|---|---|---|
| **B1** | `EventResult`, `EventInput` y esquemas de salida/consulta no figuran en `app/core/schemas.py` (Plan 1). | Plan 1, Plan 3, Plan 4, Plan 5 | Definir y congelar `EventInput`, `EventResult`, `ExtractedIndicator`, `AccountVerification`, `LookupResult`, `CampaignSummary` y `EvidenceRecord`. |
| **B2** | Riesgo de duplicar extracción y normalización entre `sms/`, `voice/` e `intel/`, más soporte de dígitos dictados (E04) y validación temprana (E05). | Plan 3, Plan 4, Plan 5 | Centralizar extracción, normalización de dígitos hablados, desactivación `hxxp` y validación CLABE/Luhn en funciones puras de `intel`, consumidas por Voz y SMS vía contrato. |
| **B3** | `Indicator.value_masked` oculta el dato en UI, pero la correlación entre eventos necesita comparar valores reales sin exponer PII ni cuentas crudas. | Plan 1, Plan 2, Plan 4, Plan 5 | Separar `value_masked` (público en `Indicator`) de `value_hash` (SHA-256 normalizado interno en `intel`/BD) para indexar y correlacionar de forma segura. |
| **B4** | La correlación debe agrupar SMS similares con enlaces distintos y **no** usar el número de origen (`origin_phone`) como indicador fuerte (es falsificable). | Plan 4, Plan 5, Alcance pág. 4 | Tratar `origin_phone` como dato secundario; correlacionar por indicador fuerte (`clabe`, `card`, `url`, teléfono citado en texto) o por similitud Jaccard de `template_signature` + marca. |
| **B5** | Falta estado `"sin_alerta"` para llamadas legítimas (E08) y máquina formal para fuente única (`indicio`), cruce (`corroborada`) y límite de tasa (`sin_verificar`, E14). | Plan 2, Plan 3, Plan 4, Plan 5, E07, E08, E12, E14 | Máquina de estados estricta (`sin_alerta`, `sin_verificar`, `indicio`, `corroborada`) basada en señales de fraude + conteo de `source_fingerprint` independientes, con tope `0.90`. |
| **B6** | Faltan taxonomía de 7 amenazas, etiqueta conforme al tipo penal (E02, E03), productos de inteligencia (Verificador y Boletín epidemiológico) y métrica de ventaja de tiempo. | Plan 2, Plan 4, Plan 5, Alcance págs. 7 y 11 | Incorporar `threat_category`, `legal_tag`, `lookup_indicator(...)`, `build_epidemiological_bulletin(...)` (`traps_reached_count`), avisos diferenciados y cálculo de `detection_lead_hours`. |

---

## 3. Solución explícita por brecha

### Brecha B1 — Contratos comunes faltantes en `app/core/schemas.py`

#### Problema
- El Plan 1 enumera `Scenario`, `Event`, `Indicator`, `AttributionResult` y `ScenarioResult`, pero no define `EventResult`, la estructura de entrada con texto sanitizado (`EventInput`), ni el contrato de consulta del Verificador ciudadano o resumen de campaña.

#### Modificación propuesta
Congelar en `app/core/schemas.py` (en coordinación con Integrante 1):

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

Channel = Literal["call", "sms", "portal"]
IntelStatus = Literal["sin_alerta", "sin_verificar", "indicio", "corroborada"]
ConfidenceLevel = Literal["ninguna", "baja", "media", "alta"]
IndicatorType = Literal[
    "clabe",
    "card",
    "contact_phone",   # Teléfono citado dentro del texto/guion
    "origin_phone",    # Identificador de origen (dato secundario no confiable)
    "url",
    "brand",
    "requested_data",
]
ThreatCategory = Literal[
    "no_aplica",
    "extorsion_cobro_piso",
    "secuestro_virtual",
    "falso_ejecutivo_bancario",
    "smishing",
    "falso_premio_paquete",
    "robo_whatsapp",
    "suplantacion_familiar",
    "montadeudas_empleo_inversion",
]


class EventInput(BaseModel):
    """Entrada sanitizada enviada por Voz, SMS o Portal hacia process_event."""
    event_id: str
    occurred_at: str  # ISO-8601 UTC
    channel: Channel
    trap_id: Optional[str] = None
    attribution_id: Optional[str] = None
    text_sanitized: str = ""
    origin_phone_masked: Optional[str] = None  # Dato secundario, no confiable para atribución/fusión
    source_fingerprint: str  # Hash anónimo de sesión/trampa/reporte (sin PII)
    sender_masked: Optional[str] = None
    claimed_brand_hint: Optional[str] = None
    rate_limited: bool = False
    force_unverified: bool = False
    synthetic: bool = True


class AccountVerification(BaseModel):
    """Salida de verify_account(value, kind) para validación temprana (E01, E05)."""
    kind: Literal["clabe", "card"]
    valid: bool
    value_masked: str
    reason: str  # "ok" | "invalid_length" | "invalid_check_digit" | "invalid_luhn" | "non_numeric"
    synthetic_bank: Optional[str] = None


class ExtractedIndicator(BaseModel):
    """Resultado puro de extract_indicators(text, channel) antes de persistir."""
    type: IndicatorType
    value_masked: str
    value_hash: str  # SHA-256 interno del valor normalizado; nunca se muestra en UI
    is_primary_correlator: bool  # False para origin_phone, brand, requested_data
    valid: Optional[bool] = None
    validation_detail: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)


class EventResult(BaseModel):
    """Salida estándar de process_event(event) consumida por Voz, SMS, Portal y Tablero."""
    event_id: str
    campaign_id: Optional[str] = None  # None cuando status == "sin_alerta" (E08)
    status: IntelStatus
    confidence: float = Field(ge=0.0, le=0.90)  # Nunca 1.0 ni "fraude_confirmado"
    confidence_level: ConfidenceLevel
    threat_category: ThreatCategory = "no_aplica"
    legal_tag: str = "sin_tipificacion"  # Etiqueta orientativa para denuncia (no sentencia)
    claimed_brand: Optional[str] = None
    requested_data: list[str] = Field(default_factory=list)
    indicators: list[Indicator] = Field(default_factory=list)
    evidence_hash: str
    evidence_seq: int
    match_reason: str  # "no_threat_detected" | "exact_indicator" | "template_similarity" | "new_campaign" | "unverified_override"
    reasons: list[str]


class CampaignSummary(BaseModel):
    """Resumen consolidado para tablero, boletín epidemiológico y cálculo de ventaja de tiempo."""
    campaign_id: str
    status: Literal["sin_verificar", "indicio", "corroborada"]
    confidence: float = Field(ge=0.0, le=0.90)
    confidence_level: ConfidenceLevel
    threat_category: ThreatCategory
    legal_tag: str
    channels_observed: list[Channel]
    traps_reached_count: int
    independent_sources_count: int
    claimed_brands: list[str]
    template_variants: list[str]
    indicators: list[Indicator]
    first_trap_seen_at: Optional[str] = None
    first_citizen_report_at: Optional[str] = None
    detection_lead_hours: Optional[float] = None  # Métrica clave: ventaja de tiempo en horas


class LookupResult(BaseModel):
    """Salida de lookup_indicator(...) para el Verificador ciudadano instantáneo."""
    found: bool
    campaign_id: Optional[str] = None
    status: IntelStatus = "sin_alerta"
    confidence_level: ConfidenceLevel = "ninguna"
    threat_category: ThreatCategory = "no_aplica"
    matched_by: Optional[Literal["exact_indicator", "template_similarity"]] = None
    message: str
```

---

### Brecha B2 — Frontera de extracción, dígitos dictados (E04/E05) y no duplicación

#### Problema
- Voz (Plan 3) necesita validar dígitos dictados (E01, E04, E05) en tiempo real y pedir repetición si el dígito verificador falla.
- SMS (Plan 5) menciona extraer remitente, enlaces, teléfonos y cuentas, con riesgo de duplicar reglas respecto a `intel/extractors.py`.

#### Modificación propuesta
1. **Única fuente de extracción en `app/modules/intel/extractors.py`:**
   - `extract_indicators(text, channel)` extrae y normaliza `clabe`, `card`, `contact_phone`, `url` (siempre convertida a `hxxp://` o `hxxps://`), `brand` y `requested_data`.
   - `verify_account(value, kind)` se expone como función pura síncrona para validación inmediata en Voz (`E01`, `E05`).
2. **Normalizador de números hablados (`normalize_spoken_digits` para E04):**
   - Convierte secuencias en español (`"cero"`, `"uno"`, ..., `"nueve"`, `"doble cero"`, `"veintitrés"`, separadores `"con"`, `"y"`) a cadena numérica cuando conformen un bloque dictado, conservando el texto original para el análisis de guion/intención.
3. **Resistencia a prompt injection (E06, E11):**
   - Ningún componente de `extractors.py`, `validators.py` ni el clasificador de amenazas ejecuta instrucciones ni usa generación libre sobre el texto entrante. Toda regla es determinista.
4. **Adaptador en Plan 5 (`app/modules/sms/`):**
   - `analyze_sms(input)` llama a `extract_indicators(text, "sms")` para obtener indicadores normalizados/enmascarados y añade únicamente la comparación contra catálogo local de dominios oficiales, acortadores y punycode antes de invocar `process_event(...)`.

---

### Brecha B3 — Correlación segura con `value_masked` vs `value_hash`

#### Problema
- Mostrar `value_masked` es obligatorio por privacidad/diseño, pero comparar valores enmascarados generaría colisiones falsas entre cuentas distintas con mismos dígitos visibles.

#### Modificación propuesta
- Al normalizar un indicador en `extractors.py`, se genera:
  - `value_masked`: único valor expuesto hacia `Indicator`, UI, tablero y paquetes (`9990**********0015`, `****-****-****-1234`, `******7890`, `hxxp://...`).
  - `value_hash`: $\text{SHA-256}(\text{"lupita-intel-v1|" + kind + "|" + normalized\_value})$, almacenado únicamente en el índice interno de correlación de `intel` / tabla interna no renderizada en vistas ni exportada en paquetes.

---

### Brecha B4 — Número de origen secundario y agrupación híbrida de campañas

#### Problema
- El documento de alcance (pág. 4) establece: *"El número de origen no es confiable. El identificador de llamada se puede falsificar. La CLABE y el guion son los indicadores fuertes; el número de origen se guarda como dato secundario."*
- Además, SMS con contenido similar y enlaces distintos deben agruparse en la misma campaña (Plan 4 y pág. 6).

#### Modificación propuesta
En `app/modules/intel/campaigns.py`:

1. **Regla explícita sobre `origin_phone`:**
   - Si el evento incluye `origin_phone_masked`, se guarda en los metadatos/indicadores secundarios con `is_primary_correlator=False`.
   - **Nunca** fusiona dos eventos en la misma campaña por sí solo ni suma peso de corroboración.
2. **Etapa 1 — Coincidencia exacta por indicador fuerte (`exact_indicator`):**
   - Busca en el índice `value_hash -> campaign_id` únicamente para indicadores fuertes: `clabe` (preferentemente válida), `card`, `url` y `contact_phone` extraído del cuerpo del mensaje/guion.
   - Si coincide (ej. E01 y E12 comparten la misma CLABE), asocia al `campaign_id` existente.
3. **Etapa 2 — Similitud de plantilla de guion/mensaje (`template_similarity`):**
   - `extractors.build_template_signature(text)` normaliza minúsculas, acentos y reemplaza URLs por `<URL>`, cuentas por `<ACCOUNT>`, teléfonos por `<PHONE>`, montos por `<AMOUNT>` y folios por `<NUM>`.
   - Calcula similitud de Jaccard sobre 3-gramas de palabras $J(A, B) = |A \cap B| / |A \cup B|$ contra campañas activas compatibles (`threat_category` o `claimed_brand` coincidente):
     - Si comparten marca o `threat_category` y $J(A, B) \ge 0.60$, o sin marca con $J(A, B) \ge 0.75$: agrupa en el mismo `campaign_id` con `match_reason="template_similarity"` y añade la variante al listado `template_variants`.
   - Si no hay coincidencia, crea una nueva campaña `CMP-XXXX`.

---

### Brecha B5 — Estado `"sin_alerta"` (E08) y máquina de confianza por corroboración

#### Problema
- E08 (*llamada legítima equivocada a un número trampa*) debe terminar en `"Sin alerta: no hay cobro ni guion de fraude"`, sin contaminar campañas ni alertas.
- E07, E12 y E14 exigen distinguir fuente única (`indicio`), corroboración independiente (`corroborada`) y límite de tasa (`sin_verificar`).

#### Modificación propuesta
Reglas ordenadas en `app/modules/intel/confidence.py`:

1. **Filtro de llamada/evento sin señal de fraude (`sin_alerta`, E08):**
   - Si el evento no contiene indicadores financieros (`clabe`, `card`), ni URL sospechosa, ni solicitud de datos sensibles (`NIP`, `CVV`, `código`), ni coincidencia con patrones de guion de las 7 categorías de amenaza, y `rate_limited=False`:
     - Retorna `status = "sin_alerta"`, `campaign_id = None`, `confidence = 0.0`, `confidence_level = "ninguna"`, `threat_category = "no_aplica"`, `match_reason = "no_threat_detected"`.
     - **No crea ni modifica ninguna campaña.** (Opcionalmente registra el evento en la cadena de evidencia con etiqueta `"no_alert"` para trazabilidad de pruebas).
2. **Retención por límite de tasa o bandera sin verificar (`sin_verificar`, E14):**
   - Si `rate_limited=True` o `force_unverified=True`:
     - Retorna `status = "sin_verificar"`, `confidence = 0.0`, `confidence_level = "baja"`, `match_reason = "unverified_override"`.
     - **No** se agrega `source_fingerprint` al conjunto de fuentes independientes de la campaña ni incrementa su confianza.
3. **Fuente única independiente (`indicio`, E07, E09 inicial):**
   - Cuando la campaña tiene `1` `source_fingerprint` válido independiente:
     - `status = "indicio"`, `confidence = 0.30` (o `0.35` si incluye CLABE/tarjeta válida + solicitud de NIP/transferencia), `confidence_level = "baja"`.
4. **Múltiples fuentes independientes (`corroborada`, E01 + E12):**
   - Cuando la campaña acumula $\ge 2$ `source_fingerprint` independientes (ej. llamada a número trampa + reporte ciudadano sanitizado, o $\ge 2$ trampas distintas):
     - `status = "corroborada"`, `confidence` entre `0.65` y `0.85` (**tope duro `0.90`**), `confidence_level = "media"` (`0.50–0.74`) o `"alta"` (`>= 0.75`).
5. **Invariante de lenguaje:**
   - Prohibido emitir `"fraude confirmado"`, `"100%"` o afirmaciones punitivas; toda explicación refleja nivel de indicio o corroboración.

---

### Brecha B6 — Taxonomía de amenazas, tipo penal, 5 productos de inteligencia y ventaja de tiempo

#### Problema
- El documento de alcance define 7 tipos de amenaza, etiquetado conforme al tipo penal (Ley General contra la Extorsión DOF 28-11-2025), 5 productos de inteligencia concretos y la métrica clave en horas entre el primer contacto a una trampa y el primer reporte ciudadano.

#### Modificación propuesta
1. **Clasificador determinista de amenaza y etiqueta penal (`threat_classifier` en `extractors.py` / `confidence.py`):**
   - Mapeo por reglas de guion, canal e indicadores hacia `ThreatCategory` y `legal_tag`:
     - `extorsion_cobro_piso` / `secuestro_virtual` (E01, E02) $\rightarrow$ `"posible_extorsion_ley_general_2025"`
     - `falso_ejecutivo_bancario` (E03) / `smishing` (E09) / `falso_premio_paquete` (E10) / `suplantacion_familiar` / `robo_whatsapp` / `montadeudas_empleo_inversion` $\rightarrow$ `"posible_fraude_suplantacion"`
     - `no_aplica` (E08) $\rightarrow$ `"sin_tipificacion"`
   - Nota explicita en paquete: la etiqueta facilita la canalización de denuncia y **no** sustituye la calificación jurídica de la Fiscalía.
2. **Funciones para los productos de inteligencia (pág. 7):**
   - **Verificador ciudadano (`lookup_indicator(query: str, kind: Optional[str] = None) -> LookupResult`):**
     - Normaliza el valor o texto consultado (cuenta, teléfono, URL desactivada `hxxp` o texto de SMS), calcula su `value_hash` / `template_signature` y devuelve si coincide con campañas conocidas, su `status` (`sin_verificar`, `indicio`, `corroborada`), `confidence_level` y `threat_category`, **sin exponer PII ni datos crudos**.
   - **Boletín epidemiológico (`build_epidemiological_bulletin() -> dict`):**
     - Lista campañas activas (excluyendo `"sin_alerta"` y campañas únicamente `"sin_verificar"` sin corroborar si son por rate-limit), variantes de guion anonimizadas y `traps_reached_count` (conteo de `trap_id` distintos alcanzados). Cero audios, cero PII.
   - **Aviso a institución suplantada (`build_impersonated_brand_notice(campaign_id)`):**
     - Enfocado a marca suplantada (SAT, banco, paquetería): entrega marca, URL desactivada (`hxxp`), indicadores de dominio imitado y plantilla anonimizada para gestión de baja.
   - **Paquete para la autoridad (`build_authority_package(campaign_id)`):**
     - Enfocado a Fiscalía / Policía Cibernética / UIF: incluye `legal_tag`, indicadores validados/enmascarados, resumen de plantilla y referencias `event_id` + `evidence_hash` + `seq`. Incluye aviso explícito: `"Este sistema reporta indicios; no bloquea líneas ni congela cuentas por sí mismo."`
   - **Atribución de fugas para Contraloría:** cubierta mediante `attribution_id` / `trap_id` ligado al módulo de Plan 2 dentro del resumen de campaña.
3. **Métrica clave de ventaja de tiempo (`detection_lead_hours`):**
   - En `campaigns.py`, cada campaña registra `first_trap_seen_at` (primer evento de canal `call` o `sms` con `trap_id` no nulo) y `first_citizen_report_at` (primer evento válido de canal `portal`, excluyendo `rate_limited`).
   - Calcula `detection_lead_hours = round((first_citizen_report_at - first_trap_seen_at).total_seconds() / 3600, 2)` cuando ambos existen (ej. cruce **E01 -> E12**).

---

## 4. Registro de evidencia e integridad (`app/modules/evidence/`)

```python
class EvidenceRecord(BaseModel):
    seq: int
    event_id: str
    occurred_at: str
    algorithm: Literal["SHA-256"] = "SHA-256"
    prev_hash: str          # "GENESIS" para seq == 1
    payload_hash: str       # SHA-256 de JSON canónico del evento sanitizado (sin audio ni PII)
    record_hash: str        # SHA-256(f"{seq}|{algorithm}|{prev_hash}|{payload_hash}")
    demo_integrity_note: str = (
        "Registro reproducible con hash y sello de tiempo para demo; "
        "su uso como prueba formal requiere intervención de la autoridad competente."
    )
```

- **Canonicalización:** `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`.
- **Verificación (`verify_chain`):** comprueba continuidad `1..N`, enlace `prev_hash` y recalcula `payload_hash` y `record_hash`, reportando `{intact, checked_count, broken_at_seq, reason}`.

---

## 5. Matriz de impacto y acuerdos en Hora 0–2

| Integrante (Plan / Alcance) | Acción de alineación antes de implementar |
|---|---|
| **Integrante 1 (Plataforma y escenarios)** | Congelar `EventInput`, `EventResult`, `AccountVerification`, `ExtractedIndicator`, `CampaignSummary`, `LookupResult` y `EvidenceRecord` en `app/core/schemas.py`; reservar almacenamiento para campañas, `value_hash` interno y cadena de evidencia; medir métricas reales de escenarios (CLABE válida en llamadas, SMS clasificados, ventaja en horas). |
| **Integrante 2 (Siembra, atribución, tablero y mapa)** | Consumir `CampaignSummary`, `EventResult` y `build_epidemiological_bulletin()` sin reclasificar; mostrar etiqueta `"Sintético"` y la métrica `detection_lead_hours`. |
| **Integrante 3 / Persona 2 (Voz — Doña Lupita)** | Invocar `verify_account(value, "clabe")` ante dígitos dictados (E01/E04/E05) y enviar `EventInput` con `text_sanitized` y `origin_phone_masked` (sin audio) a `process_event`. |
| **Integrante 5 / Persona 4 (SMS y portal ciudadano)** | Reutilizar `extract_indicators(text, "sms")` y `lookup_indicator(...)` para el Verificador ciudadano; enviar `source_fingerprint` sin PII y `rate_limited=True` en eventos bloqueados por tasa (E14). |

---

## 6. Cobertura de escenarios E01–E14 relevantes al motor

- **E01:** Extracción de CLABE sintética (`999` + dígito verificador Banxico mod 10), `threat_category="extorsion_cobro_piso"`, `legal_tag="posible_extorsion_ley_general_2025"`, enmascaramiento, `status="indicio"`, registro en cadena de hashes.
- **E02:** Secuestro virtual: guion etiquetado como `threat_category="secuestro_virtual"`, extracción de cuenta y plantilla.
- **E03:** Falso ejecutivo bancario: `claimed_brand` detectado, `requested_data=["NIP"]`, `threat_category="falso_ejecutivo_bancario"`.
- **E04:** Conversión de dígitos dictados en palabras a 18 dígitos para verificación.
- **E05:** `verify_account` retorna `valid=False, reason="invalid_check_digit"` para que Voz solicite repetición.
- **E06 / E11:** Inyección de instrucciones ignorada; pipeline 100 % determinista.
- **E07:** Fuente única mantiene `status="indicio"`, `confidence_level="baja"`, sin reporte de fraude confirmado.
- **E08:** Llamada legítima sin indicadores de cobro ni guion de fraude retorna `status="sin_alerta"`, `campaign_id=None`.
- **E09 / E10:** SMS SAT/paquetería con `url` desactivada en `hxxp`; agrupación por `template_similarity` aunque cambie el enlace.
- **E12:** Reporte ciudadano sanitizado con indicador coincidente con E01 aporta segunda fuente independiente, eleva a `status="corroborada"` y calcula `detection_lead_hours`.
- **E14:** Reporte marcado `rate_limited=True` conserva `status="sin_verificar"` y no suma fuentes ni publica entidad.
