package mx.protocolo.monitor.work

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

object WorkScheduler {
    fun scheduleHeartbeat(context: Context) {
        val request = PeriodicWorkRequestBuilder<HeartbeatWorker>(15, TimeUnit.MINUTES)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .build()
        WorkManager.getInstance(context.applicationContext).enqueueUniquePeriodicWork(
            HeartbeatWorker.UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    fun sendHeartbeatNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<HeartbeatWorker>()
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .build()
        WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
            HEARTBEAT_NOW_WORK_NAME,
            ExistingWorkPolicy.KEEP,
            request,
        )
    }

    fun cancelHeartbeat(context: Context) {
        WorkManager.getInstance(context.applicationContext).apply {
            cancelUniqueWork(HeartbeatWorker.UNIQUE_WORK_NAME)
            cancelUniqueWork(HEARTBEAT_NOW_WORK_NAME)
        }
    }

    private const val HEARTBEAT_NOW_WORK_NAME = "monitor_device_heartbeat_now"
}
