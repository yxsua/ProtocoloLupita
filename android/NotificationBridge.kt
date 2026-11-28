package com.example.lupita

import android.Manifest
import android.app.Notification
import android.content.ContentObserver
import android.content.Intent
import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.provider.CallLog
import android.provider.Telephony
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import org.json.JSONObject
import java.time.Instant

/**
 * Reenvía notificaciones y nuevos registros de llamadas, sin grabar audio.
 */
class NotificationBridge : NotificationListenerService() {

    private val paquetesSms = setOf(
        "com.google.android.apps.messaging",
        "com.samsung.android.messaging",
    )
    private val idsLlamadasVistos = LinkedHashSet<Long>()
    private var hiloLlamadas: HandlerThread? = null
    private var handlerLlamadas: Handler? = null
    private var observadorLlamadas: ContentObserver? = null
    private var tareaEscaneo: Runnable? = null

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName) return
        val notificacion = sbn.notification
        if (notificacion.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        if (
            sbn.packageName in paquetesSms ||
            sbn.packageName == Telephony.Sms.getDefaultSmsPackage(this)
        ) return
        if (
            notificacion.category == Notification.CATEGORY_CALL ||
            notificacion.category == Notification.CATEGORY_MISSED_CALL
        ) return

        val extras = notificacion.extras
        val remitente = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()
        val texto = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString()
        if (remitente.isNullOrBlank() && texto.isNullOrBlank()) return

        val evento = JSONObject().apply {
            put("dispositivo", BuildConfig.LUPITA_DEVICE_ID)
            put("tipo", "notificacion")
            put("app", sbn.packageName.take(128))
            put("remitente", remitente?.take(256))
            put("texto", texto?.take(4000))
            put("fecha", Instant.ofEpochMilli(sbn.postTime).toString())
        }
        EventSender.enviar(evento)
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        observarRegistroDeLlamadas()
    }

    override fun onListenerDisconnected() {
        dejarDeObservarLlamadas()
        super.onListenerDisconnected()
    }

    override fun onDestroy() {
        dejarDeObservarLlamadas()
        super.onDestroy()
    }

    private fun observarRegistroDeLlamadas() {
        if (!tienePermisoRegistroLlamadas()) {
            Log.w(TAG, "READ_CALL_LOG no concedido; no se transmitirán eventos de llamadas.")
            return
        }
        if (observadorLlamadas != null) return

        val hilo = HandlerThread("LupitaCallLog").apply { start() }
        val handler = Handler(hilo.looper)
        hiloLlamadas = hilo
        handlerLlamadas = handler
        val observador = object : ContentObserver(handler) {
            override fun onChange(selfChange: Boolean) {
                programarEscaneo()
            }

            override fun onChange(selfChange: Boolean, uri: Uri?) {
                programarEscaneo()
            }
        }
        observadorLlamadas = observador
        contentResolver.registerContentObserver(CallLog.Calls.CONTENT_URI, true, observador)
        handler.post { escanearRegistroDeLlamadas(inicial = true) }
    }

    private fun dejarDeObservarLlamadas() {
        observadorLlamadas?.let(contentResolver::unregisterContentObserver)
        observadorLlamadas = null
        tareaEscaneo?.let { handlerLlamadas?.removeCallbacks(it) }
        tareaEscaneo = null
        handlerLlamadas = null
        hiloLlamadas?.quitSafely()
        hiloLlamadas = null
    }

    private fun programarEscaneo() {
        val handler = handlerLlamadas ?: return
        tareaEscaneo?.let(handler::removeCallbacks)
        val tarea = Runnable { escanearRegistroDeLlamadas(inicial = false) }
        tareaEscaneo = tarea
        handler.postDelayed(tarea, CALL_LOG_DEBOUNCE_MS)
    }

    private fun escanearRegistroDeLlamadas(inicial: Boolean) {
        if (!tienePermisoRegistroLlamadas()) {
            return
        }
        val columnas = arrayOf(
            CallLog.Calls._ID,
            CallLog.Calls.NUMBER,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
            CallLog.Calls.TYPE,
        )
        val cursor = contentResolver.query(
            CallLog.Calls.CONTENT_URI,
            columnas,
            null,
            null,
            "${CallLog.Calls.DATE} DESC",
        ) ?: return

        cursor.use { filas ->
            var leidas = 0
            while (filas.moveToNext() && leidas < CALL_LOG_SCAN_LIMIT) {
                leidas += 1
                val id = filas.getLong(filas.getColumnIndexOrThrow(CallLog.Calls._ID))
                if (!recordarLlamada(id)) continue
                if (inicial) continue
                registrarLlamada(filas)
            }
        }
    }

    private fun recordarLlamada(id: Long): Boolean {
        val nueva = idsLlamadasVistos.add(id)
        if (idsLlamadasVistos.size > MAX_SEEN_CALL_IDS) {
            val iterator = idsLlamadasVistos.iterator()
            if (iterator.hasNext()) {
                iterator.next()
                iterator.remove()
            }
        }
        return nueva
    }

    private fun registrarLlamada(fila: Cursor) {
        val numero = fila.getString(fila.getColumnIndexOrThrow(CallLog.Calls.NUMBER))
        val fecha = fila.getLong(fila.getColumnIndexOrThrow(CallLog.Calls.DATE))
        val duracion = fila.getLong(fila.getColumnIndexOrThrow(CallLog.Calls.DURATION))
            .coerceIn(0, MAX_CALL_DURATION_SECONDS)
        val tipo = fila.getInt(fila.getColumnIndexOrThrow(CallLog.Calls.TYPE))
        val direccion = when (tipo) {
            CallLog.Calls.INCOMING_TYPE -> "entrante"
            CallLog.Calls.OUTGOING_TYPE -> "saliente"
            CallLog.Calls.MISSED_TYPE -> "perdida"
            else -> null
        }
        val appOrigen = packageManager.resolveActivity(
            Intent(Intent.ACTION_DIAL),
            PackageManager.MATCH_DEFAULT_ONLY,
        )?.activityInfo?.packageName ?: "android"

        val evento = JSONObject().apply {
            put("dispositivo", BuildConfig.LUPITA_DEVICE_ID)
            put("tipo", "llamada")
            put("app", appOrigen.take(128))
            if (!numero.isNullOrBlank()) put("remitente", numero.take(256))
            put("duracion_s", duracion)
            if (direccion != null) put("direccion", direccion)
            put("fecha", Instant.ofEpochMilli(fecha).toString())
        }
        EventSender.enviar(evento)
    }

    private fun tienePermisoRegistroLlamadas(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.M ||
            checkSelfPermission(Manifest.permission.READ_CALL_LOG) == PackageManager.PERMISSION_GRANTED

    private companion object {
        const val TAG = "LupitaNotificationBridge"
        const val CALL_LOG_DEBOUNCE_MS = 1500L
        const val CALL_LOG_SCAN_LIMIT = 100
        const val MAX_SEEN_CALL_IDS = 200
        const val MAX_CALL_DURATION_SECONDS = 86400L
    }
}
