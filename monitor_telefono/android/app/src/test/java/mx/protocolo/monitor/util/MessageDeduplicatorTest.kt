package mx.protocolo.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class MessageDeduplicatorTest {
    @Test
    fun notificationUpdateOnlyReturnsNewMessageFingerprints() {
        val first = IncomingMessage(1000, "Ana", "Hola")
        val second = IncomingMessage(2000, "Ana", "¿Llegaste?")
        val firstFingerprint = MessageDeduplicator.fingerprint(first)
        val secondFingerprint = MessageDeduplicator.fingerprint(second)

        assertEquals(
            listOf(secondFingerprint),
            MessageDeduplicator.unseenFingerprints(setOf(firstFingerprint), listOf(firstFingerprint, secondFingerprint)),
        )
    }

    @Test
    fun duplicateMessagesInOneNotificationAreOnlyReturnedOnce() {
        val fingerprint = MessageDeduplicator.fingerprint(IncomingMessage(1000, "Ana", "Hola"))

        assertEquals(
            listOf(fingerprint),
            MessageDeduplicator.unseenFingerprints(emptySet(), listOf(fingerprint, fingerprint)),
        )
    }

    @Test
    fun fingerprintIncludesMessageContents() {
        val original = MessageDeduplicator.fingerprint(IncomingMessage(1000, "Ana", "Hola"))
        val changed = MessageDeduplicator.fingerprint(IncomingMessage(1000, "Ana", "Adiós"))

        assertNotEquals(original, changed)
    }

    @Test
    fun historyKeepsMostRecentlyObservedFingerprintsWithinLimit() {
        val history = MessageDeduplicator.updatedHistory(
            previous = listOf("old", "keep"),
            current = listOf("old", "new"),
            maxEntries = 2,
        )

        assertEquals(listOf("old", "new"), history)
    }
}
