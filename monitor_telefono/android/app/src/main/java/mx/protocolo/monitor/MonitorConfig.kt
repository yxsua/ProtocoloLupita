package mx.protocolo.monitor

data class MonitorConfig(
    val serverUrl: String = "",
    val deviceToken: String = "",
    val deviceName: String = "",
    val allowedPackages: Set<String> = emptySet(),
    val consentAccepted: Boolean = false,
    val monitoringEnabled: Boolean = false,
    val consentText: String = "",
    val trustedContactPhone: String = "",
)
