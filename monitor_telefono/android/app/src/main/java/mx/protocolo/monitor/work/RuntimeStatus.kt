package mx.protocolo.monitor.work

import android.content.Context
import java.time.Instant

data class RuntimeSnapshot(
    val message: String,
    val updatedAt: Long,
    val lastSentAt: Long,
)

object RuntimeStatus {
    private const val PREFERENCES = "monitor_runtime_status"
    private const val KEY_MESSAGE = "message"
    private const val KEY_UPDATED_AT = "updated_at"
    private const val KEY_LAST_SENT_AT = "last_sent_at"

    fun record(context: Context, message: String, sent: Boolean = false) {
        val now = System.currentTimeMillis()
        context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_MESSAGE, message)
            .putLong(KEY_UPDATED_AT, now)
            .apply {
                if (sent) putLong(KEY_LAST_SENT_AT, now)
            }
            .apply()
    }

    fun read(context: Context): RuntimeSnapshot {
        val preferences =
            context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        return RuntimeSnapshot(
            message = preferences.getString(KEY_MESSAGE, "Todavía no hay actividad.") ?: "",
            updatedAt = preferences.getLong(KEY_UPDATED_AT, 0),
            lastSentAt = preferences.getLong(KEY_LAST_SENT_AT, 0),
        )
    }

    fun clear(context: Context) {
        context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .edit()
            .clear()
            .apply()
    }

    fun formattedTime(timestamp: Long): String =
        if (timestamp <= 0) "Nunca" else Instant.ofEpochMilli(timestamp).toString()
}
