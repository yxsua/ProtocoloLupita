package mx.protocolo.monitor

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

data class EnrollmentLink(
    val serverUrl: String,
    val code: String,
)

object EnrollmentLinkParser {
    private val codePattern = Regex("^[A-HJ-NP-Z2-9]{8}$")

    fun parse(
        value: String,
        defaultServerUrl: String,
        debugBuild: Boolean,
    ): EnrollmentLink {
        val uri = try {
            URI(value.trim())
        } catch (_: Exception) {
            throw IllegalArgumentException("El QR o enlace no tiene un formato válido.")
        }
        val query = parseQuery(uri.rawQuery.orEmpty())
        val code = query["code"].orEmpty().trim().replace(" ", "").uppercase()
        require(codePattern.matches(code)) { "El QR no contiene un código de enrolamiento válido." }

        val candidateServer = when {
            uri.scheme.equals("monitortelefono", ignoreCase = true) &&
                uri.host.equals("enroll", ignoreCase = true) ->
                query["server"] ?: defaultServerUrl
            uri.scheme.equals("https", ignoreCase = true) &&
                uri.path == "/enroll" && !uri.rawAuthority.isNullOrBlank() ->
                "https://${uri.rawAuthority}"
            uri.scheme.equals("http", ignoreCase = true) &&
                uri.path == "/enroll" && !uri.rawAuthority.isNullOrBlank() ->
                "http://${uri.rawAuthority}"
            else -> throw IllegalArgumentException("El enlace no corresponde a una página de enrolamiento.")
        }
        val base = normalizeBaseUrl(candidateServer)
        if (!debugBuild && base.startsWith("http://")) {
            throw IllegalArgumentException("La vinculación en producción requiere HTTPS.")
        }
        if (!debugBuild && normalizeBaseUrl(defaultServerUrl) != base) {
            throw IllegalArgumentException("Este build solo puede vincularse con el servidor configurado.")
        }
        return EnrollmentLink(base, code)
    }

    private fun normalizeBaseUrl(value: String): String {
        val parsed = try {
            URI(value.trim().trimEnd('/'))
        } catch (_: Exception) {
            throw IllegalArgumentException("La URL del servidor configurada no es válida.")
        }
        require(parsed.scheme.equals("https", ignoreCase = true) ||
            parsed.scheme.equals("http", ignoreCase = true)
        ) { "La URL del servidor debe usar HTTPS." }
        require(!parsed.host.isNullOrBlank() && parsed.rawUserInfo == null) {
            "La URL debe incluir el host y no puede contener credenciales."
        }
        require(parsed.rawPath.isNullOrEmpty() || parsed.rawPath == "/") {
            "La URL del servidor no debe incluir una ruta."
        }
        require(parsed.rawQuery == null && parsed.rawFragment == null) {
            "La URL del servidor no debe incluir parámetros ni fragmentos."
        }
        return "${parsed.scheme.lowercase()}://${parsed.rawAuthority.lowercase()}"
    }

    private fun parseQuery(rawQuery: String): Map<String, String> =
        rawQuery.split('&')
            .filter(String::isNotBlank)
            .mapNotNull { item ->
                val parts = item.split('=', limit = 2)
                val key = decode(parts[0])
                val value = decode(parts.getOrElse(1) { "" })
                key to value
            }
            .toMap()

    private fun decode(value: String): String =
        URLDecoder.decode(value, StandardCharsets.UTF_8.name())
}
