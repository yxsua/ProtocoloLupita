package mx.protocolo.monitor.data

import android.content.Context
import androidx.room.withTransaction
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import mx.protocolo.monitor.util.IncomingMessage
import mx.protocolo.monitor.util.MessageDeduplicator
import mx.protocolo.monitor.work.EventUploadWorker
import org.json.JSONArray
import java.time.Instant
import java.util.UUID
import java.util.concurrent.TimeUnit

class EventRepository(context: Context) {
    private val appContext = context.applicationContext
    private val database = MonitorDatabase.get(appContext)
    private val dao = database.monitorDao()

    suspend fun saveNewNotificationMessages(
        notificationKey: String,
        appPackage: String,
        type: String,
        messages: List<IncomingMessage>,
    ): Int {
        if (messages.isEmpty()) return 0
        val savedCount = database.withTransaction {
            val fingerprints = messages.map { MessageDeduplicator.fingerprint(it) }
            val previousJson = dao.getCursor(notificationKey)?.seenFingerprintsJson
            val previous = decodeFingerprints(previousJson)
            val workingSet = previous.toMutableSet()
            val fresh = messages.zip(fingerprints).filter { (_, fingerprint) ->
                workingSet.add(fingerprint)
            }
            val updatedHistory = MessageDeduplicator.updatedHistory(
                previous = previous,
                current = fingerprints,
            )
            dao.saveCursor(
                NotificationCursor(
                    notificationKey = notificationKey,
                    seenFingerprintsJson = JSONArray(updatedHistory).toString(),
                    updatedAt = System.currentTimeMillis(),
                ),
            )

            fresh.forEach { (message, _) ->
                dao.insertEvent(
                    StoredEvent(
                        eventId = UUID.randomUUID().toString(),
                        tipo = type,
                        app = appPackage.take(128),
                        remitente = message.sender?.take(256),
                        texto = message.text.take(4000),
                        direccion = null,
                        duracionS = null,
                        fecha = Instant.ofEpochMilli(message.timestamp).toString(),
                    ),
                )
            }
            fresh.size
        }

        if (savedCount > 0) enqueuePendingUpload()
        return savedCount
    }

    suspend fun pendingCount(): Int = dao.pendingCount()

    suspend fun allEventsForStatus(): List<StoredEvent> = dao.getAllForStatus()

    suspend fun retryFailedAndEnqueue() {
        dao.retryFailed()
        enqueuePendingUpload()
    }

    fun enqueuePendingUpload() {
        enqueueUpload()
    }

    suspend fun clearQueueAndHistory() {
        database.withTransaction {
            dao.clearEvents()
            dao.clearCursors()
        }
        WorkManager.getInstance(appContext).cancelUniqueWork(EventUploadWorker.UNIQUE_WORK_NAME)
    }

    private fun enqueueUpload() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = OneTimeWorkRequestBuilder<EventUploadWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(appContext).enqueueUniqueWork(
            EventUploadWorker.UNIQUE_WORK_NAME,
            ExistingWorkPolicy.APPEND_OR_REPLACE,
            request,
        )
    }

    private fun decodeFingerprints(json: String?): List<String> {
        if (json == null) return emptyList()
        val values = JSONArray(json)
        return buildList {
            for (index in 0 until values.length()) {
                values.optString(index).takeIf(String::isNotBlank)?.let(::add)
            }
        }
    }
}
