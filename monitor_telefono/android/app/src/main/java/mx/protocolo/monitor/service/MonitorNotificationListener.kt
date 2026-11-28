package mx.protocolo.monitor.service

import android.app.Notification
import android.content.ComponentName
import android.os.Build
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import mx.protocolo.monitor.ConfigStoreException
import mx.protocolo.monitor.SecureConfigStore
import mx.protocolo.monitor.data.EventRepository
import mx.protocolo.monitor.work.RuntimeStatus
import mx.protocolo.monitor.util.IncomingMessage
import org.json.JSONException

class MonitorNotificationListener : NotificationListenerService() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var repository: EventRepository

    override fun onCreate() {
        super.onCreate()
        repository = EventRepository(applicationContext)
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        RuntimeStatus.record(applicationContext, "Acceso a notificaciones conectado.")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName || shouldIgnore(sbn.notification)) return

        serviceScope.launch {
            try {
                val config = SecureConfigStore(applicationContext).load() ?: return@launch
                if (!config.consentAccepted || !config.monitoringEnabled) return@launch
                if (sbn.packageName !in config.allowedPackages) return@launch

                val messages = extractMessages(sbn.notification)
                if (messages.isEmpty()) return@launch
                val saved = repository.saveNewNotificationMessages(
                    notificationKey = sbn.key,
                    appPackage = sbn.packageName,
                    type = eventTypeFor(sbn.packageName),
                    messages = messages,
                )
                if (saved > 0) {
                    RuntimeStatus.record(
                        applicationContext,
                        "$saved evento(s) nuevo(s) guardado(s) en la cola local.",
                    )
                }
            } catch (error: ConfigStoreException) {
                RuntimeStatus.record(applicationContext, "No se pudo leer la configuración protegida.")
            } catch (error: JSONException) {
                RuntimeStatus.record(applicationContext, "No se pudo procesar una notificación.")
            } catch (error: android.database.sqlite.SQLiteException) {
                RuntimeStatus.record(applicationContext, "No se pudo guardar una notificación localmente.")
            } catch (error: CancellationException) {
                throw error
            }
        }
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        RuntimeStatus.record(applicationContext, "Acceso desconectado; Android intentará vincularlo de nuevo.")
        NotificationListenerService.requestRebind(
            ComponentName(applicationContext, MonitorNotificationListener::class.java),
        )
    }

    override fun onDestroy() {
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun shouldIgnore(notification: Notification): Boolean {
        val ignoredFlags = Notification.FLAG_GROUP_SUMMARY or
            Notification.FLAG_ONGOING_EVENT or
            Notification.FLAG_FOREGROUND_SERVICE
        return notification.flags and ignoredFlags != 0
    }

    private fun extractMessages(notification: Notification): List<IncomingMessage> {
        val extraMessages = notification.extras.getParcelableArray(Notification.EXTRA_MESSAGES)
            ?.let { rawMessages ->
                Notification.MessagingStyle.Message.getMessagesFromBundleArray(rawMessages)
            }
            .orEmpty()
        val messagingMessages = extraMessages
        if (messagingMessages.isNotEmpty()) {
            val messages = messagingMessages.mapNotNull { message ->
                val text = message.text?.toString()?.trim().orEmpty()
                if (text.isBlank()) return@mapNotNull null
                val sender = messageSender(message)?.trim()?.takeIf(String::isNotBlank)
                    ?: notification.extras.getCharSequence(Notification.EXTRA_TITLE)
                        ?.toString()
                        ?.trim()
                        ?.takeIf(String::isNotBlank)
                IncomingMessage(
                    timestamp = message.timestamp.takeIf { it > 0 } ?: notification.`when`.takeIf { it > 0 }
                        ?: System.currentTimeMillis(),
                    sender = sender,
                    text = text,
                )
            }
            if (messages.isNotEmpty()) return messages
        }

        val extras: Bundle = notification.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim()
        val text = (
            extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
                ?: extras.getCharSequence(Notification.EXTRA_TEXT)
            )?.toString()?.trim().orEmpty()
        if (text.isBlank()) return emptyList()

        val timestamp = notification.`when`
            .takeIf { it > 0 }
            ?: System.currentTimeMillis()
        return listOf(
            IncomingMessage(
                timestamp = timestamp,
                sender = title?.takeIf(String::isNotBlank),
                text = text,
            ),
        )
    }

    @Suppress("DEPRECATION")
    private fun messageSender(message: Notification.MessagingStyle.Message): String? {
        val personSender = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            message.senderPerson?.name?.toString()
        } else {
            null
        }
        return personSender ?: message.sender?.toString()
    }

    private fun eventTypeFor(packageName: String): String =
        if (packageName in SMS_PACKAGES) "sms" else "notificacion"

    private companion object {
        val SMS_PACKAGES = setOf(
            "com.google.android.apps.messaging",
            "com.android.messaging",
            "com.android.mms",
        )
    }
}
