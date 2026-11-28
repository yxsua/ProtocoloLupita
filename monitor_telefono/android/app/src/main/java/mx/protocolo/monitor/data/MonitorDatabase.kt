package mx.protocolo.monitor.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

@Entity(
    tableName = "monitor_events",
    indices = [Index(value = ["state"]), Index(value = ["created_at"])],
)
data class StoredEvent(
    @PrimaryKey
    @androidx.room.ColumnInfo(name = "event_id")
    val eventId: String,
    val tipo: String,
    val app: String,
    val remitente: String?,
    val texto: String,
    val direccion: String?,
    @androidx.room.ColumnInfo(name = "duracion_s")
    val duracionS: Int?,
    val fecha: String,
    val state: String = STATE_PENDING,
    val attempts: Int = 0,
    @androidx.room.ColumnInfo(name = "last_error")
    val lastError: String? = null,
    @androidx.room.ColumnInfo(name = "created_at")
    val createdAt: Long = System.currentTimeMillis(),
) {
    companion object {
        const val STATE_PENDING = "pending"
        const val STATE_SENT = "sent"
        const val STATE_FAILED = "failed"
    }
}

@Entity(tableName = "notification_cursors")
data class NotificationCursor(
    @PrimaryKey
    @androidx.room.ColumnInfo(name = "notification_key")
    val notificationKey: String,
    @androidx.room.ColumnInfo(name = "seen_fingerprints_json")
    val seenFingerprintsJson: String,
    @androidx.room.ColumnInfo(name = "updated_at")
    val updatedAt: Long,
)

@Dao
interface MonitorDao {
    @Insert
    suspend fun insertEvent(event: StoredEvent)

    @Insert(onConflict = androidx.room.OnConflictStrategy.REPLACE)
    suspend fun saveCursor(cursor: NotificationCursor)

    @Query("SELECT * FROM notification_cursors WHERE notification_key = :key")
    suspend fun getCursor(key: String): NotificationCursor?

    @Query(
        "SELECT * FROM monitor_events WHERE state = 'pending' " +
            "ORDER BY created_at ASC LIMIT :limit",
    )
    suspend fun getPending(limit: Int): List<StoredEvent>

    @Query("UPDATE monitor_events SET state = 'sent', last_error = NULL WHERE event_id = :eventId")
    suspend fun markSent(eventId: String)

    @Query(
        "UPDATE monitor_events SET attempts = attempts + 1, last_error = :error " +
            "WHERE event_id = :eventId",
    )
    suspend fun markAttempt(eventId: String, error: String)

    @Query(
        "UPDATE monitor_events SET state = 'failed', last_error = :error " +
            "WHERE event_id = :eventId",
    )
    suspend fun markFailed(eventId: String, error: String)

    @Query(
        "UPDATE monitor_events SET state = 'pending', last_error = NULL " +
            "WHERE state = 'failed'",
    )
    suspend fun retryFailed()

    @Query("SELECT COUNT(*) FROM monitor_events WHERE state = 'pending'")
    suspend fun pendingCount(): Int

    @Query("SELECT * FROM monitor_events ORDER BY created_at DESC")
    suspend fun getAllForStatus(): List<StoredEvent>

    @Query("DELETE FROM monitor_events")
    suspend fun clearEvents()

    @Query("DELETE FROM notification_cursors")
    suspend fun clearCursors()
}

@Database(
    entities = [StoredEvent::class, NotificationCursor::class],
    version = 1,
    exportSchema = false,
)
abstract class MonitorDatabase : RoomDatabase() {
    abstract fun monitorDao(): MonitorDao

    companion object {
        @Volatile
        private var instance: MonitorDatabase? = null

        fun get(context: Context): MonitorDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    MonitorDatabase::class.java,
                    "monitor_local.db",
                ).build().also { instance = it }
            }
    }
}
