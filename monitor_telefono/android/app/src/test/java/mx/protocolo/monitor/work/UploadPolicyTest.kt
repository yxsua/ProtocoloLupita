package mx.protocolo.monitor.work

import org.junit.Assert.assertEquals
import org.junit.Test

class UploadPolicyTest {
    @Test
    fun acceptedAndDuplicateResponsesAcknowledgeTheQueuedEvent() {
        assertEquals(UploadAction.ACKNOWLEDGE, UploadPolicy.forHttpStatus(200))
        assertEquals(UploadAction.ACKNOWLEDGE, UploadPolicy.forHttpStatus(201))
    }

    @Test
    fun temporaryResponsesAreRetried() {
        assertEquals(UploadAction.RETRY, UploadPolicy.forHttpStatus(408))
        assertEquals(UploadAction.RETRY, UploadPolicy.forHttpStatus(429))
        assertEquals(UploadAction.RETRY, UploadPolicy.forHttpStatus(503))
    }

    @Test
    fun permanentClientErrorsAreBlockedForManualCorrection() {
        assertEquals(UploadAction.BLOCK, UploadPolicy.forHttpStatus(400))
        assertEquals(UploadAction.BLOCK, UploadPolicy.forHttpStatus(401))
        assertEquals(UploadAction.BLOCK, UploadPolicy.forHttpStatus(422))
    }
}
