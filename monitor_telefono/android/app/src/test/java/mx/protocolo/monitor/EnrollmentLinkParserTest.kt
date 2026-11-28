package mx.protocolo.monitor

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class EnrollmentLinkParserTest {
    @Test
    fun parsesServerEnrollmentUrl() {
        val result = EnrollmentLinkParser.parse(
            "https://monitor.example.com/enroll?code=ABCD2345",
            "https://monitor.example.com",
            debugBuild = false,
        )

        assertEquals("https://monitor.example.com", result.serverUrl)
        assertEquals("ABCD2345", result.code)
    }

    @Test
    fun parsesCustomAppLinkWithEncodedServer() {
        val result = EnrollmentLinkParser.parse(
            "monitortelefono://enroll?server=https%3A%2F%2Fmonitor.example.com&code=abcd2345",
            "https://monitor.example.com",
            debugBuild = false,
        )

        assertEquals("https://monitor.example.com", result.serverUrl)
        assertEquals("ABCD2345", result.code)
    }

    @Test
    fun rejectsForeignServerAndMalformedCodeInRelease() {
        assertThrows(IllegalArgumentException::class.java) {
            EnrollmentLinkParser.parse(
                "https://attacker.example/enroll?code=ABCD2345",
                "https://monitor.example.com",
                debugBuild = false,
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            EnrollmentLinkParser.parse(
                "https://monitor.example.com/enroll?code=ABCD1234",
                "https://monitor.example.com",
                debugBuild = false,
            )
        }
    }
}
