package mx.protocolo.monitor.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import mx.protocolo.monitor.MainActivity
import mx.protocolo.monitor.R

object MonitoringNotification {
    private const val CHANNEL_ID = "monitoring_active"
    private const val NOTIFICATION_ID = 4210

    @Suppress("DEPRECATION")
    fun show(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Monitor activo",
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = "Indicador visible mientras se comparten notificaciones autorizadas."
                    setShowBadge(false)
                },
            )
        }

        val openApp = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(context, CHANNEL_ID)
        } else {
            Notification.Builder(context)
        }
        val notification = builder
            .setSmallIcon(android.R.drawable.ic_popup_sync)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText("Compartiendo solo las apps que seleccionaste.")
            .setContentIntent(openApp)
            .setOngoing(true)
            .setCategory(Notification.CATEGORY_SERVICE)
            .build()
        manager.notify(NOTIFICATION_ID, notification)
    }

    fun cancel(context: Context) {
        context.getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
    }
}
