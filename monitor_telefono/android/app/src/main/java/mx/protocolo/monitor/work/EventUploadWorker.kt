package mx.protocolo.monitor.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import mx.protocolo.monitor.BuildConfig
import mx.protocolo.monitor.ConfigStoreException
import mx.protocolo.monitor.MonitorConfig
import mx.protocolo.monitor.SecureConfigStore
import mx.protocolo.monitor.data.MonitorDatabase
import mx.protocolo.monitor.data.StoredEvent
import mx.protocolo.monitor.util.UrlPolicy
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class EventUploadWorker(
    context: Context,
    parameters: WorkerParameters,
) : CoroutineWorker(context, parameters) {
    private val dao = MonitorDatabase.get(applicationContext).monitorDao()

    override suspend fun doWork(): Result {
        val config = try {
            SecureConfigStore(applicationContext).load()
        } catch (error: ConfigStoreException) {
            RuntimeStatus.record(applicationContext, "No se pudo leer la configuración protegida.")
            return Result.failure()
        }
        if (config == null) {
            RuntimeStatus.record(applicationContext, "Configura el servidor y el consentimiento antes de enviar.")
            return Result.failure()
        }

        if (!config.isReadyToUpload()) {
            RuntimeStatus.record(
                applicationContext,
                "La captura está pausada o falta aceptar el consentimiento y configurar el servidor.",
            )
            return Result.failure()
        }

        val baseUrl = try {
            UrlPolicy.validateBaseUrl(config.serverUrl, BuildConfig.DEBUG)
        } catch (error: IllegalArgumentException) {
            RuntimeStatus.record(applicationContext, error.message ?: "La URL del servidor no es válida.")
            return Result.failure()
        }

        val events = dao.getPending(BATCH_SIZE)
        if (events.isEmpty()) {
            RuntimeStatus.record(applicationContext, "Cola sincronizada.")
            return Result.success()
        }

        for (event in events) {
            val request = createRequest(baseUrl, config.deviceToken, event)
            try {
                httpClient.newCall(request).execute().use { response ->
                    when (UploadPolicy.forHttpStatus(response.code)) {
                        UploadAction.ACKNOWLEDGE -> {
                            dao.markSent(event.eventId)
                            RuntimeStatus.record(
                                applicationContext,
                                "Evento enviado al servidor.",
                                sent = true,
                            )
                        }

                        UploadAction.RETRY -> {
                            dao.markAttempt(event.eventId, "HTTP ${response.code}")
                            RuntimeStatus.record(
                                applicationContext,
                                "El servidor pidió reintentar; el evento sigue en cola.",
                            )
                            return Result.retry()
                        }

                        UploadAction.BLOCK -> {
                            dao.markFailed(
                                event.eventId,
                                "HTTP ${response.code}; revisa la URL y la clave del dispositivo.",
                            )
                            RuntimeStatus.record(
                                applicationContext,
                                "El servidor rechazó un evento. Revisa la clave y la configuración.",
                            )
                            return Result.failure()
                        }
                    }
                }
            } catch (error: IOException) {
                dao.markAttempt(event.eventId, "Error de red")
                RuntimeStatus.record(
                    applicationContext,
                    "Sin conexión con el servidor; el evento se reintentará.",
                )
                return Result.retry()
            }
        }

        return if (dao.pendingCount() > 0) Result.retry() else Result.success()
    }

    private fun createRequest(baseUrl: String, token: String, event: StoredEvent): Request {
        val payload = JSONObject()
            .put("id_evento", event.eventId)
            .put("tipo", event.tipo)
            .put("app", event.app)
            .put("texto", event.texto)
            .put("fecha", event.fecha)
        event.remitente?.let { payload.put("remitente", it) }
        event.direccion?.let { payload.put("direccion", it) }
        event.duracionS?.let { payload.put("duracion_s", it) }

        return Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/eventos")
            .header("X-Device-Key", token)
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
    }

    private fun MonitorConfig.isReadyToUpload(): Boolean =
        consentAccepted &&
            monitoringEnabled &&
            serverUrl.isNotBlank() &&
            deviceToken.isNotBlank()

    companion object {
        const val BATCH_SIZE = 25
        const val UNIQUE_WORK_NAME = "monitor_event_upload"
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val httpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}
