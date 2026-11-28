package mx.protocolo.monitor.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import mx.protocolo.monitor.MyMessagesActivity

object FraudAlertNotification {
    private const val CHANNEL_ID = "fraud_alerts"

    fun show(
        context: Context,
        eventId: String,
        level: String,
        score: Int,
        trustedContact: String,
    ) {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Alertas de posible fraude",
                    NotificationManager.IMPORTANCE_HIGH,
                ).apply {
                    description = "Avisos locales sobre mensajes que parecen posibles fraudes."
                    setShowBadge(true)
                },
            )
        }

        val openMessages = PendingIntent.getActivity(
            context,
            eventId.hashCode(),
            Intent(context, MyMessagesActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Posible fraude")
            .setContentText("Este mensaje parece un posible fraude. No compartas códigos ni hagas pagos.")
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    "Este mensaje parece un posible fraude. No compartas códigos ni hagas pagos. " +
                        "Riesgo $level ($score/100).",
                ),
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openMessages)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)

        dialableContact(trustedContact)?.let { phone ->
            val dial = PendingIntent.getActivity(
                context,
                eventId.hashCode() xor 0x41,
                Intent(Intent.ACTION_DIAL, Uri.parse("tel:$phone")),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            builder.addAction(0, "Llamar a contacto de confianza", dial)
        }
        androidx.core.app.NotificationManagerCompat.from(context)
            .notify(eventId.hashCode(), builder.build())
    }

    private fun dialableContact(value: String): String? {
        if (!Regex("^\\+?[0-9][0-9\\s().-]{5,24}$").matches(value.trim())) return null
        val digits = value.filter(Char::isDigit)
        return value.trim().takeIf { digits.length in 7..15 }
    }
}
