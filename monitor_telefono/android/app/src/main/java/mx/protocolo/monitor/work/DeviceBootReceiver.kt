package mx.protocolo.monitor.work

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.service.notification.NotificationListenerService
import android.content.ComponentName
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import mx.protocolo.monitor.ConfigStoreException
import mx.protocolo.monitor.SecureConfigStore
import mx.protocolo.monitor.data.EventRepository
import mx.protocolo.monitor.service.MonitorNotificationListener
import mx.protocolo.monitor.service.MonitoringNotification

class DeviceBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val pendingResult = goAsync()
        val appContext = context.applicationContext
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                val config = SecureConfigStore(appContext).load()
                if (config == null || !config.consentAccepted || config.deviceToken.isBlank()) return@launch
                WorkScheduler.scheduleHeartbeat(appContext)
                if (config.monitoringEnabled) {
                    try {
                        MonitoringNotification.show(appContext)
                    } catch (_: SecurityException) {
                        RuntimeStatus.record(appContext, "Activa las notificaciones para reanudar el indicador.")
                    }
                    EventRepository(appContext).enqueuePendingUpload()
                    NotificationListenerService.requestRebind(
                        ComponentName(appContext, MonitorNotificationListener::class.java),
                    )
                }
            } catch (error: ConfigStoreException) {
                RuntimeStatus.record(appContext, "No se pudo restaurar la configuración protegida.")
                Log.w(TAG, "No se pudo restaurar la configuración tras el reinicio.")
            } finally {
                pendingResult.finish()
            }
        }
    }

    private companion object {
        const val TAG = "MonitorBootReceiver"
    }
}
