package mx.protocolo.monitor.work

enum class UploadAction {
    ACKNOWLEDGE,
    RETRY,
    BLOCK,
}

object UploadPolicy {
    fun forHttpStatus(statusCode: Int): UploadAction = when {
        statusCode == 200 || statusCode == 201 -> UploadAction.ACKNOWLEDGE
        statusCode == 408 || statusCode == 425 || statusCode == 429 || statusCode >= 500 ->
            UploadAction.RETRY
        else -> UploadAction.BLOCK
    }
}
