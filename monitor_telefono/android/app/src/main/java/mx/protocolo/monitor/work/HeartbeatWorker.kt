package mx.protocolo.monitor.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import mx.protocolo.monitor.BuildConfig
import mx.protocolo.monitor.ConfigStoreException
import mx.protocolo.monitor.SecureConfigStore
import mx.protocolo.monitor.data.MonitorDatabase
import mx.protocolo.monitor.util.UrlPolicy
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

class HeartbeatWorker(
    context: Context,
    parameters: WorkerParameters,
) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val config = try {
            SecureConfigStore(applicationContext).load()
        } catch (_: ConfigStoreException) {
            RuntimeStatus.record(applicationContext, "No se pudo leer la vinculación protegida.")
            return Result.failure()
        } ?: return Result.success()
        if (!config.consentAccepted || config.deviceToken.isBlank()) return Result.success()

        val baseUrl = try {
            UrlPolicy.validateBaseUrl(config.serverUrl, BuildConfig.DEBUG)
        } catch (error: IllegalArgumentException) {
            RuntimeStatus.record(applicationContext, error.message ?: "La URL del servidor no es válida.")
            return Result.failure()
        }
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/latido")
            .header("X-Device-Key", config.deviceToken)
            .post("{}".toRequestBody(JSON_MEDIA_TYPE))
            .build()
        return try {
            httpClient.newCall(request).execute().use { response ->
                when {
                    response.isSuccessful -> {
                        syncReviewUpdates(response.body?.string().orEmpty())
                        RuntimeStatus.record(applicationContext, "Latido enviado al servidor.")
                        Result.success()
                    }
                    response.code == 401 -> {
                        RuntimeStatus.record(applicationContext, "Vínculo revocado; vuelve a enrolar el teléfono.")
                        Result.failure()
                    }
                    else -> Result.retry()
                }
            }
        } catch (_: IOException) {
            RuntimeStatus.record(applicationContext, "No se pudo completar el latido; se reintentará.")
            Result.retry()
        }
    }

    private suspend fun syncReviewUpdates(body: String) {
        val updates = try {
            org.json.JSONObject(body).optJSONArray("actualizaciones_revision")
        } catch (error: org.json.JSONException) {
            throw IOException("El servidor respondió con un latido inválido.", error)
        } ?: throw IOException("El servidor omitió las actualizaciones de revisión.")
        val dao = MonitorDatabase.get(applicationContext).monitorDao()
        for (index in 0 until updates.length()) {
            val update = updates.optJSONObject(index) ?: continue
            val eventId = update.optString("id_evento")
            val status = update.optString("revision_estado")
            if (eventId.isBlank() || status.isBlank() || status == "null") continue
            dao.updateReviewStatus(
                eventId,
                status,
                update.optString("revisado_en").takeIf { it.isNotBlank() && it != "null" },
            )
        }
    }

    companion object {
        const val UNIQUE_WORK_NAME = "monitor_device_heartbeat"
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val httpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}
