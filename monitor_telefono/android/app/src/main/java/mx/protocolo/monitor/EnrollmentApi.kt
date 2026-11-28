package mx.protocolo.monitor

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

data class EnrollmentPreview(
    val suggestedName: String,
    val suggestedApps: List<String>,
)

data class EnrolledDevice(
    val token: String,
)

class EnrollmentApi {
    @Throws(IOException::class, JSONException::class)
    fun preview(serverUrl: String, code: String): EnrollmentPreview {
        val result = post(serverUrl, "/api/enrolar/preview", JSONObject().put("code", code))
        val packages = result.optJSONArray("apps_sugeridas") ?: JSONArray()
        return EnrollmentPreview(
            suggestedName = result.optString("nombre_sugerido"),
            suggestedApps = buildList {
                for (index in 0 until packages.length()) {
                    packages.optString(index).takeIf(String::isNotBlank)?.let(::add)
                }
            },
        )
    }

    @Throws(IOException::class, JSONException::class)
    fun enroll(
        serverUrl: String,
        code: String,
        name: String,
        allowedPackages: Set<String>,
    ): EnrolledDevice {
        val payload = JSONObject()
            .put("code", code)
            .put("nombre", name)
            .put("apps_permitidas", JSONArray(allowedPackages.sorted()))
            .put("consentimiento", true)
        val result = post(serverUrl, "/api/enrolar", payload)
        val token = result.optString("token")
        if (token.isBlank()) throw IOException("El servidor no entregó la clave de vinculación.")
        return EnrolledDevice(token)
    }

    @Throws(IOException::class, JSONException::class)
    fun unlink(serverUrl: String, token: String) {
        val payload = JSONObject().put("accion", "desvincular")
        post(serverUrl, "/api/desvincular", payload, token)
    }

    private fun post(
        serverUrl: String,
        path: String,
        payload: JSONObject,
        token: String? = null,
    ): JSONObject {
        val requestBuilder = Request.Builder()
            .url("${serverUrl.trimEnd('/')}$path")
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
        token?.let { requestBuilder.header("X-Device-Key", it) }
        httpClient.newCall(requestBuilder.build()).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val detail = try {
                    JSONObject(body).optString("detail").ifBlank { "HTTP ${response.code}" }
                } catch (_: JSONException) {
                    "HTTP ${response.code}"
                }
                throw IOException(detail)
            }
            return try {
                JSONObject(body)
            } catch (error: JSONException) {
                throw IOException("El servidor respondió con un formato inválido.", error)
            }
        }
    }

    private companion object {
        val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        val httpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}
