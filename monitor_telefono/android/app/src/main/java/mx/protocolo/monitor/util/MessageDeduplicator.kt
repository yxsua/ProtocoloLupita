package mx.protocolo.monitor.util

import java.security.MessageDigest

data class IncomingMessage(
    val timestamp: Long,
    val sender: String?,
    val text: String,
)

object MessageDeduplicator {
    fun fingerprint(message: IncomingMessage): String {
        val value = listOf(
            message.timestamp.toString(),
            message.sender.orEmpty(),
            message.text,
        ).joinToString(separator = "\u001f")
        return MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
    }

    fun unseenFingerprints(previous: Set<String>, current: List<String>): List<String> {
        val seen = previous.toMutableSet()
        return current.filter { seen.add(it) }
    }

    fun updatedHistory(previous: List<String>, current: List<String>, maxEntries: Int = 200): List<String> {
        require(maxEntries > 0)
        val ordered = LinkedHashSet<String>()
        (previous + current).forEach { fingerprint ->
            ordered.remove(fingerprint)
            ordered.add(fingerprint)
        }
        return ordered.toList().takeLast(maxEntries)
    }
}
