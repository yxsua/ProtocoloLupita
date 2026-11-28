package mx.protocolo.monitor.util

import android.net.Uri
import java.net.InetAddress
import java.net.UnknownHostException

object UrlPolicy {
    fun validateBaseUrl(value: String, debugBuild: Boolean): String {
        val input = value.trim().trimEnd('/')
        require(input.isNotEmpty()) { "Escribe la URL base del servidor." }
        val uri = Uri.parse(input)
        val scheme = uri.scheme?.lowercase()
        val host = uri.host?.lowercase()
        require(scheme == "https" || scheme == "http") { "La URL debe comenzar con http:// o https://." }
        require(!host.isNullOrBlank()) { "La URL debe incluir el host del servidor." }
        require(uri.userInfo == null && uri.query == null && uri.fragment == null) {
            "La URL no debe incluir usuario, contraseña, parámetros ni fragmento."
        }
        require(uri.path.isNullOrEmpty() || uri.path == "/") {
            "Usa la URL base del servidor, sin una ruta adicional."
        }
        if (scheme == "http") {
            require(debugBuild) { "HTTP sin cifrar solo está disponible en el build debug." }
            require(isLoopbackOrEmulatorHost(host)) {
                "HTTP solo se permite para localhost o el emulador Android; usa HTTPS para otros dispositivos."
            }
        }
        return input
    }

    fun healthUrl(baseUrl: String): String = "${baseUrl.trimEnd('/')}/api/salud"

    private fun isLoopbackOrEmulatorHost(host: String): Boolean {
        if (host == "localhost" || host == "10.0.2.2") return true
        val isIpLiteral = host.contains(':') || host.matches(Regex("[0-9.]+"))
        if (!isIpLiteral) return false
        val address = try {
            InetAddress.getByName(host)
        } catch (_: UnknownHostException) {
            return false
        }
        return address.isLoopbackAddress
    }
}
