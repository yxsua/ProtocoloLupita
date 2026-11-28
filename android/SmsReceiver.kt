package com.example.lupita

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import org.json.JSONObject
import java.time.Instant

class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        val partes = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (partes.isNullOrEmpty()) return

        val remitente = partes.firstOrNull()?.originatingAddress?.take(256)
        val texto = partes.joinToString(separator = "") { it.messageBody.orEmpty() }
            .take(4000)
        if (texto.isBlank()) return

        val appOrigen = Telephony.Sms.getDefaultSmsPackage(context) ?: "android"
        val evento = JSONObject().apply {
            put("dispositivo", BuildConfig.LUPITA_DEVICE_ID)
            put("tipo", "sms")
            put("app", appOrigen.take(128))
            if (!remitente.isNullOrBlank()) put("remitente", remitente)
            put("texto", texto)
            put("direccion", "entrante")
            put("fecha", Instant.ofEpochMilli(partes.maxOf { it.timestampMillis }).toString())
        }

        val resultado = goAsync()
        EventSender.enviar(evento) { resultado.finish() }
    }
}
