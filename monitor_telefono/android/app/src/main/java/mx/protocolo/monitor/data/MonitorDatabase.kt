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
    @androidx.room.ColumnInfo(name = "fraud_score")
    val fraudScore: Int = 0,
    @androidx.room.ColumnInfo(name = "risk_level")
    val riskLevel: String = "bajo",
    @androidx.room.ColumnInfo(name = "risk_reasons_json")
    val riskReasonsJson: String = "",
    @androidx.room.ColumnInfo(name = "review_state")
    val reviewState: String? = null,
    @androidx.room.ColumnInfo(name = "reviewed_at")
    val reviewedAt: String? = null,
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
        "UPDATE monitor_events SET fraud_score = :score, risk_level = :level, " +
            "risk_reasons_json = :reasonsJson WHERE event_id = :eventId",
    )
    suspend fun updateFraudVerdict(eventId: String, score: Int, level: String, reasonsJson: String)

    @Query(
        "UPDATE monitor_events SET review_state = :state, reviewed_at = :reviewedAt " +
            "WHERE event_id = :eventId",
    )
    suspend fun updateReviewStatus(eventId: String, state: String, reviewedAt: String?)

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
    version = 2,
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
                )
                    .addMigrations(MIGRATION_1_2)
                    .build().also { instance = it }
            }

        private val MIGRATION_1_2 = object : androidx.room.migration.Migration(1, 2) {
            override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE monitor_events ADD COLUMN fraud_score INTEGER NOT NULL DEFAULT 0")
                db.execSQL("ALTER TABLE monitor_events ADD COLUMN risk_level TEXT NOT NULL DEFAULT 'bajo'")
                db.execSQL("ALTER TABLE monitor_events ADD COLUMN risk_reasons_json TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE monitor_events ADD COLUMN review_state TEXT")
                db.execSQL("ALTER TABLE monitor_events ADD COLUMN reviewed_at TEXT")
            }
        }
    }
}
