package mx.protocolo.monitor

import android.Manifest
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.net.Uri
import android.text.InputType
import android.text.method.PasswordTransformationMethod
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.lifecycleScope
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mx.protocolo.monitor.data.EventRepository
import mx.protocolo.monitor.data.MonitorDatabase
import mx.protocolo.monitor.data.StoredEvent
import mx.protocolo.monitor.service.MonitorNotificationListener
import mx.protocolo.monitor.service.MonitoringNotification
import mx.protocolo.monitor.util.UrlPolicy
import mx.protocolo.monitor.work.EventUploadWorker
import mx.protocolo.monitor.work.RuntimeStatus
import mx.protocolo.monitor.work.WorkScheduler
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                continuePermissionSetup()
            } else {
                permissionSetupInProgress = false
                showToast("Concede notificaciones para mantener visible el indicador del monitoreo.")
            }
        }
    private val secureStore by lazy { SecureConfigStore(applicationContext) }
    private val repository by lazy { EventRepository(applicationContext) }
    private val refreshHandler = Handler(Looper.getMainLooper())
    private var config = MonitorConfig(serverUrl = BuildConfig.DEFAULT_SERVER_URL)
    private var storageError: String? = null
    private var selectedPackages = mutableSetOf<String>()
    private var enrollmentCode = ""
    private var enrollmentServerUrl = BuildConfig.DEFAULT_SERVER_URL
    private var enrollmentPreview: EnrollmentPreview? = null
    private var enrollmentMessage: String? = null
    private var awaitingNotificationAccess = false
    private var awaitingAppNotifications = false
    private var awaitingBatteryExemption = false
    private var permissionSetupInProgress = false

    private lateinit var content: LinearLayout
    private lateinit var urlInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var deviceNameInput: EditText
    private lateinit var packageList: LinearLayout
    private lateinit var packageInput: EditText
    private lateinit var permissionStatus: TextView
    private lateinit var batteryStatus: TextView
    private lateinit var runtimeStatus: TextView
    private lateinit var queueStatus: TextView
    private lateinit var eventHistory: TextView
    private lateinit var connectionTestStatus: TextView
    private lateinit var enrollmentCodeInput: EditText
    private lateinit var enrollmentNameInput: EditText
    private lateinit var enrollmentAppsLayout: LinearLayout
    private lateinit var enrollmentConsent: CheckBox
    private lateinit var enrollmentMessageView: TextView
    private var enrollmentServerInput: EditText? = null

    private val refreshRunnable = object : Runnable {
        override fun run() {
            refreshStatus()
            refreshHandler.postDelayed(this, STATUS_REFRESH_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            config = secureStore.load()
                ?: MonitorConfig(serverUrl = BuildConfig.DEFAULT_SERVER_URL)
        } catch (error: ConfigStoreException) {
            storageError = error.message
            config = MonitorConfig()
        }
        if (!BuildConfig.DEBUG) {
            val storedServer = config.serverUrl
            config = config.copy(serverUrl = BuildConfig.DEFAULT_SERVER_URL)
            if (config.deviceToken.isNotBlank() && storedServer != config.serverUrl) {
                try {
                    secureStore.save(config)
                } catch (error: ConfigStoreException) {
                    storageError = error.message
                }
            }
        } else if (config.serverUrl.isBlank()) {
            config = config.copy(serverUrl = BuildConfig.DEFAULT_SERVER_URL)
        }
        selectedPackages = config.allowedPackages.toMutableSet()
        handleEnrollmentIntent(intent)
        render()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleEnrollmentIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        if (::permissionStatus.isInitialized) updatePermissionStatus()
        if (config.consentAccepted && config.deviceToken.isNotBlank()) {
            WorkScheduler.scheduleHeartbeat(this)
        }
        if (awaitingNotificationAccess) {
            awaitingNotificationAccess = false
            if (hasNotificationAccess()) {
                if (permissionSetupInProgress) continuePermissionSetup()
            } else if (permissionSetupInProgress) {
                permissionSetupInProgress = false
                showToast("El acceso sigue desactivado; puedes volver a configurarlo cuando quieras.")
            }
        } else if (awaitingAppNotifications) {
            awaitingAppNotifications = false
            if (canShowOngoingNotification()) {
                if (permissionSetupInProgress) continuePermissionSetup()
            } else if (permissionSetupInProgress) {
                permissionSetupInProgress = false
                showToast("Activa las notificaciones de la app para habilitar el indicador permanente.")
            }
        } else if (awaitingBatteryExemption) {
            awaitingBatteryExemption = false
            if (permissionSetupInProgress && isBatteryExempt()) {
                continuePermissionSetup()
            } else {
                val shouldEnableAfterBatteryPrompt = permissionSetupInProgress
                permissionSetupInProgress = false
                if (!isBatteryExempt()) {
                    showToast("La exclusión de batería se puede activar después; Android podría retrasar envíos.")
                }
                if (shouldEnableAfterBatteryPrompt &&
                    config.consentAccepted &&
                    hasNotificationAccess() &&
                    canShowOngoingNotification()
                ) {
                    enableMonitoringAfterPermissions()
                }
            }
        }
        if (config.monitoringEnabled && !hasNotificationAccess()) {
            pauseMonitoring("Se pausó el monitoreo porque se retiró el acceso a notificaciones.")
        } else if (config.monitoringEnabled && !canShowOngoingNotification()) {
            pauseMonitoring("Se pausó el monitoreo porque se desactivó el permiso del indicador.")
        }
        refreshHandler.removeCallbacks(refreshRunnable)
        refreshHandler.post(refreshRunnable)
    }

    override fun onPause() {
        refreshHandler.removeCallbacks(refreshRunnable)
        super.onPause()
    }

    private fun render() {
        val scrollView = ScrollView(this).apply {
            setBackgroundColor(Color.rgb(244, 247, 251))
            clipToPadding = false
            setPadding(dp(16), dp(12), dp(16), dp(24))
        }
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        scrollView.addView(
            content,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )
        setContentView(scrollView)

        addText(content, getString(R.string.app_name), 27, bold = true, color = COLOR_DARK)
        addText(
            content,
            "Recopila únicamente notificaciones de las aplicaciones que autorices y envíalas a tu servidor.",
            15,
            color = COLOR_MUTED,
            bottom = 16,
        )

        storageError?.let {
            addNotice(content, it, COLOR_ERROR)
        }
        if (config.deviceToken.isBlank()) {
            renderEnrollment()
            return
        }
        renderConsent()
        renderConfiguration()
        renderPermissions()
        renderAppSelection()
        renderMonitoring()
        renderStatus()
        renderPrivacyActions()
    }

    private fun renderEnrollment() {
        val card = section(
            "Vincular este teléfono",
            "Escanea el QR del administrador o escribe el código corto. No necesitas copiar una clave.",
        )
        addText(
            card,
            "El código vence en 15 minutos. Antes de registrar el teléfono podrás revisar y cambiar qué aplicaciones compartir.",
            14,
            color = COLOR_MUTED,
            bottom = 10,
        )
        if (BuildConfig.DEBUG) {
            enrollmentServerInput = addInput(
                card,
                label = "URL del servidor (solo debug)",
                value = enrollmentServerUrl,
                hint = "https://monitor.example.com",
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI,
            )
        } else {
            enrollmentServerInput = null
            addText(card, "Servidor de esta versión: ${BuildConfig.DEFAULT_SERVER_URL}", 13, color = COLOR_MUTED)
        }
        addButton(card, "Escanear código QR") { startEnrollmentScanner() }
        enrollmentCodeInput = addInput(
            card,
            label = "Código de 8 caracteres",
            value = enrollmentCode,
            hint = "ABCDEFGH",
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS,
        ).apply {
            filters = arrayOf(android.text.InputFilter.LengthFilter(8))
        }
        addButton(card, "Continuar con el código") {
            val code = enrollmentCodeInput.text.toString().trim().replace(" ", "").uppercase()
            val baseUrl = currentEnrollmentServerUrl()
            loadEnrollmentPreview("monitortelefono://enroll?server=${Uri.encode(baseUrl)}&code=${Uri.encode(code)}")
        }
        enrollmentMessageView = addText(
            card,
            enrollmentMessage.orEmpty(),
            14,
            color = COLOR_MUTED,
            bottom = 8,
        )

        val preview = enrollmentPreview ?: return
        val details = section(
            "Revisa antes de vincular",
            "El servidor solo recibe el nombre y la selección que confirmes. No se envían notificaciones hasta que actives el monitoreo.",
        )
        enrollmentNameInput = addInput(
            details,
            label = "Nombre del teléfono",
            value = preview.suggestedName,
            hint = "Mi teléfono",
            inputType = InputType.TYPE_CLASS_TEXT,
        )
        addText(
            details,
            "Selecciona las aplicaciones que autorizas. Puedes desmarcar sugerencias; la app solo procesa estas aplicaciones.",
            14,
            color = COLOR_MUTED,
            bottom = 8,
        )
        enrollmentAppsLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val appOptions = APP_OPTIONS.toMutableList()
        val knownPackages = appOptions.mapTo(mutableSetOf()) { it.packageName }
        selectedPackages.filterNot(knownPackages::contains).sorted().forEach { packageName ->
            appOptions.add(AppOption(packageName, packageName))
        }
        appOptions.forEach { option ->
            val checkbox = CheckBox(this).apply {
                text = "${option.label} (${option.packageName})"
                isChecked = option.packageName in selectedPackages
                setTextColor(COLOR_DARK)
                setOnCheckedChangeListener { _, checked ->
                    if (checked) selectedPackages.add(option.packageName)
                    else selectedPackages.remove(option.packageName)
                }
            }
            enrollmentAppsLayout.addView(checkbox)
        }
        details.addView(enrollmentAppsLayout)
        enrollmentConsent = CheckBox(this).apply {
            text = "Leí y acepto compartir solo las notificaciones de las aplicaciones seleccionadas."
            setTextColor(COLOR_DARK)
        }
        details.addView(enrollmentConsent)
        addText(
            details,
            "Los mensajes se guardan en el servidor en la nube del administrador hasta el borrado manual o el vencimiento de la retención configurada (30 días por defecto). Puedes desvincular este teléfono después.",
            13,
            color = COLOR_MUTED,
            bottom = 8,
        )
        addButton(details, "Aceptar y vincular teléfono") { redeemEnrollment() }
    }

    private fun currentEnrollmentServerUrl(): String {
        val entered = enrollmentServerInput?.text?.toString()?.trim()
        return if (BuildConfig.DEBUG && !entered.isNullOrBlank()) {
            entered
        } else {
            enrollmentServerUrl.ifBlank { BuildConfig.DEFAULT_SERVER_URL }
        }
    }

    private fun handleEnrollmentIntent(intent: Intent?) {
        val value = intent?.dataString ?: return
        if (config.deviceToken.isNotBlank()) {
            showToast("Este teléfono ya está vinculado. Desvincúlalo antes de usar otro código.")
            return
        }
        loadEnrollmentPreview(value)
    }

    private fun startEnrollmentScanner() {
        GmsBarcodeScanning.getClient(this).startScan()
            .addOnSuccessListener { barcode ->
                val value = barcode.rawValue
                if (value.isNullOrBlank()) {
                    showToast("El QR no contiene un enlace de enrolamiento.")
                } else {
                    loadEnrollmentPreview(value)
                }
            }
            .addOnFailureListener {
                showToast("No se pudo abrir el lector de QR. Escribe el código manualmente.")
            }
    }

    private fun loadEnrollmentPreview(value: String) {
        if (config.deviceToken.isNotBlank()) {
            showToast("Desvincula este teléfono antes de iniciar otro enrolamiento.")
            return
        }
        val link = try {
            EnrollmentLinkParser.parse(
                value = value,
                defaultServerUrl = BuildConfig.DEFAULT_SERVER_URL,
                debugBuild = BuildConfig.DEBUG,
            )
        } catch (error: IllegalArgumentException) {
            enrollmentMessage = error.message
            if (::enrollmentMessageView.isInitialized) enrollmentMessageView.text = enrollmentMessage
            else render()
            return
        }
        val baseUrl = try {
            UrlPolicy.validateBaseUrl(link.serverUrl, BuildConfig.DEBUG)
        } catch (error: IllegalArgumentException) {
            enrollmentMessage = error.message
            if (::enrollmentMessageView.isInitialized) enrollmentMessageView.text = enrollmentMessage
            else render()
            return
        }
        enrollmentCode = link.code
        enrollmentServerUrl = baseUrl
        enrollmentPreview = null
        enrollmentMessage = "Validando código con el servidor…"
        if (::enrollmentMessageView.isInitialized) enrollmentMessageView.text = enrollmentMessage
        lifecycleScope.launch {
            try {
                val preview = withContext(Dispatchers.IO) {
                    EnrollmentApi().preview(baseUrl, link.code)
                }
                enrollmentPreview = preview
                selectedPackages = preview.suggestedApps.toMutableSet()
                enrollmentMessage = "Código válido. Revisa el nombre, las aplicaciones y el consentimiento."
                render()
            } catch (error: IOException) {
                enrollmentPreview = null
                enrollmentMessage = error.message ?: "No se pudo validar el código con el servidor."
                render()
            } catch (error: org.json.JSONException) {
                enrollmentPreview = null
                enrollmentMessage = "El servidor respondió con un formato inesperado."
                render()
            }
        }
    }

    private fun redeemEnrollment() {
        if (!::enrollmentConsent.isInitialized || !enrollmentConsent.isChecked) {
            showToast("Acepta el consentimiento antes de vincular el teléfono.")
            return
        }
        val baseUrl = try {
            UrlPolicy.validateBaseUrl(currentEnrollmentServerUrl(), BuildConfig.DEBUG)
        } catch (error: IllegalArgumentException) {
            enrollmentMessageView.text = error.message
            return
        }
        if (baseUrl != enrollmentServerUrl) {
            enrollmentMessageView.text = "El servidor cambió. Valida de nuevo el código antes de continuar."
            return
        }
        val name = enrollmentNameInput.text.toString().trim()
        if (name.isBlank() || name.length > 80) {
            enrollmentMessageView.text = "Escribe un nombre de hasta 80 caracteres."
            return
        }
        val code = enrollmentCode
        if (code.isBlank() || enrollmentPreview == null) {
            enrollmentMessageView.text = "Primero valida un código de enrolamiento vigente."
            return
        }
        enrollmentMessageView.text = "Vinculando el teléfono…"
        lifecycleScope.launch {
            try {
                val enrolled = withContext(Dispatchers.IO) {
                    EnrollmentApi().enroll(baseUrl, code, name, selectedPackages.toSet())
                }
                config = MonitorConfig(
                    serverUrl = baseUrl,
                    deviceToken = enrolled.token,
                    deviceName = name,
                    allowedPackages = selectedPackages.toSet(),
                    consentAccepted = true,
                    monitoringEnabled = false,
                )
                if (!saveConfigOrShowError("Teléfono vinculado. La clave quedó guardada de forma cifrada.")) {
                    val revokeError = withContext(Dispatchers.IO) {
                        try {
                            EnrollmentApi().unlink(baseUrl, enrolled.token)
                            null
                        } catch (error: IOException) {
                            error.message
                        } catch (_: org.json.JSONException) {
                            "respuesta inválida"
                        }
                    }
                    config = MonitorConfig(serverUrl = BuildConfig.DEFAULT_SERVER_URL)
                    enrollmentCode = ""
                    enrollmentPreview = null
                    enrollmentMessage = if (revokeError == null) {
                        "No se pudo guardar el token; el servidor revocó el alta. Pide un código nuevo."
                    } else {
                        "No se pudo guardar el token ni confirmar la revocación en el servidor. Contacta al administrador y pide un código nuevo."
                    }
                    render()
                    return@launch
                }
                WorkScheduler.scheduleHeartbeat(this@MainActivity)
                WorkScheduler.sendHeartbeatNow(this@MainActivity)
                enrollmentCode = ""
                enrollmentPreview = null
                enrollmentMessage = null
                permissionSetupInProgress = true
                render()
                continuePermissionSetup()
            } catch (error: IOException) {
                enrollmentMessageView.text = error.message ?: "No se pudo vincular el teléfono."
            } catch (error: org.json.JSONException) {
                enrollmentMessageView.text = "El servidor respondió con un formato inesperado."
            }
        }
    }

    private fun renderConsent() {
        val card = section(
            "Consentimiento y datos",
            "Antes de continuar, revisa qué se comparte y acepta de forma expresa.",
        )
        addText(
            card,
            "Cuando actives el monitoreo se compartirán solo las notificaciones de las apps que selecciones: paquete de origen, remitente, texto y fecha. No se graban llamadas ni audio, no se leen contactos ni SMS desde la base del teléfono. Las notificaciones pueden incluir mensajes privados.",
            14,
            color = COLOR_DARK,
            bottom = 12,
        )
        addText(
            card,
            "El contenido se envía al servidor que configures y queda en la cola local hasta entregarse o hasta que borres los datos. Comparte únicamente teléfonos propios y con autorización de sus usuarios.",
            14,
            color = COLOR_MUTED,
            bottom = 12,
        )

        if (config.consentAccepted) {
            addNotice(card, "Consentimiento aceptado en este dispositivo.", COLOR_SUCCESS)
        } else {
            val acceptance = CheckBox(this).apply {
                text = "Leí la información y acepto compartir las notificaciones seleccionadas."
                setTextColor(COLOR_DARK)
            }
            card.addView(acceptance)
            addButton(card, "Aceptar y continuar") {
                if (!acceptance.isChecked) {
                    showToast("Marca la casilla para aceptar antes de continuar.")
                    return@addButton
                }
                config = config.copy(consentAccepted = true)
                if (saveConfigOrShowError()) render()
            }
        }
    }

    private fun renderConfiguration() {
        val card = section(
            "Configuración del servidor",
            "La vinculación se administra desde la app. La URL de producción viene fijada en el build.",
        )
        if (BuildConfig.DEBUG) {
            urlInput = addInput(
                card,
                label = "URL base (solo debug)",
                value = config.serverUrl,
                hint = "https://servidor o http://localhost:8100",
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI,
            )
            tokenInput = addInput(
                card,
                label = "Clave heredada (solo debug)",
                value = config.deviceToken,
                hint = "Usa el enrolamiento QR para instalaciones nuevas",
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD,
            ).apply {
                transformationMethod = PasswordTransformationMethod.getInstance()
            }
        } else {
            urlInput = EditText(this)
            tokenInput = EditText(this)
            addText(card, "Servidor fijado en esta versión: ${BuildConfig.DEFAULT_SERVER_URL}", 14, color = COLOR_DARK)
            addText(card, "La clave de dispositivo se guarda cifrada y no se muestra en pantalla.", 13, color = COLOR_MUTED)
        }
        deviceNameInput = addInput(
            card,
            label = "Nombre para reconocer este teléfono",
            value = config.deviceName,
            hint = "Mi teléfono",
            inputType = InputType.TYPE_CLASS_TEXT,
        )
        addText(
            card,
            "El nombre es una etiqueta administrativa. No se envía con cada notificación.",
            13,
            color = COLOR_MUTED,
            bottom = 8,
        )

        val buttons = horizontalRow(card)
        addButton(buttons, "Guardar configuración") { saveConfiguration() }
        addButton(buttons, "Probar servidor") { testServerConnection() }
        connectionTestStatus = addText(card, "", 13, color = COLOR_MUTED)
        if (!config.consentAccepted) disableChildren(card)
    }

    private fun renderPermissions() {
        val card = section(
            "Permisos del teléfono",
            "El asistente abre Ajustes y comprueba los permisos al volver. Sin acceso a notificaciones no se captura ningún mensaje.",
        )
        permissionStatus = addText(card, "", 14, color = COLOR_DARK, bottom = 8)
        val listenerButton = addButton(card, "Abrir acceso a notificaciones") {
            awaitingNotificationAccess = true
            openSettings(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        }
        val batteryButton = addButton(card, "Revisar optimización de batería") {
            awaitingBatteryExemption = true
            openSettings(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
        }
        addButton(card, "Configurar permisos y activar") { startMonitoring() }
        batteryStatus = addText(card, "", 13, color = COLOR_MUTED, bottom = 8)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            addNotice(
                card,
                "Si Android muestra “Permitir ajustes restringidos” (instalación fuera de Google Play), abre la información de esta app, toca ⋮ > Permitir ajustes restringidos y vuelve a activar el acceso a notificaciones.",
                COLOR_WARNING,
            )
        }
        if (!config.consentAccepted) {
            listenerButton.isEnabled = false
            batteryButton.isEnabled = false
        }
        updatePermissionStatus()
    }

    private fun renderAppSelection() {
        val card = section(
            "Aplicaciones autorizadas",
            "Revisa las aplicaciones sugeridas durante el enrolamiento. Puedes cambiar la selección en cualquier momento.",
        )
        packageList = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val options = APP_OPTIONS.toMutableList()
        val knownPackages = options.mapTo(mutableSetOf()) { it.packageName }
        selectedPackages.filterNot(knownPackages::contains).sorted().forEach { packageName ->
            options.add(AppOption(packageName, packageName))
        }
        options.forEach { option ->
            addPackageCheckbox(option)
        }
        card.addView(packageList)

        packageInput = addInput(
            card,
            label = "Añadir otra app por nombre de paquete",
            value = "",
            hint = "por.ejemplo.app",
            inputType = InputType.TYPE_CLASS_TEXT,
        )
        addButton(card, "Añadir a la selección") {
            val packageName = packageInput.text.toString().trim()
            if (!PACKAGE_NAME.matches(packageName)) {
                showToast("Escribe un nombre de paquete Android válido.")
                return@addButton
            }
            if (options.any { it.packageName == packageName }) {
                showToast("Ese paquete ya aparece en la lista.")
                return@addButton
            }
            selectedPackages.add(packageName)
            config = config.copy(allowedPackages = selectedPackages.toSet())
            if (saveConfigOrShowError()) {
                addPackageCheckbox(AppOption(packageName, packageName))
                packageInput.setText("")
            }
        }
        addButton(card, "Guardar selección de apps") {
            config = config.copy(allowedPackages = selectedPackages.toSet())
            saveConfigOrShowError("Selección de aplicaciones guardada.")
        }
        if (!config.consentAccepted) disableChildren(card)
    }

    private fun addPackageCheckbox(option: AppOption) {
        val checkbox = CheckBox(this).apply {
            text = "${option.label}  (${option.packageName})"
            isChecked = option.packageName in selectedPackages
            setTextColor(COLOR_DARK)
            setOnCheckedChangeListener { _, checked ->
                if (checked) selectedPackages.add(option.packageName)
                else selectedPackages.remove(option.packageName)
            }
        }
        packageList.addView(checkbox)
    }

    private fun renderMonitoring() {
        val card = section(
            "Estado y control",
            "Al activar, se muestra una notificación persistente. Pausar detiene la captura y los envíos pendientes.",
        )
        val state = if (config.monitoringEnabled) "Monitoreo activo" else "Monitoreo pausado"
        addNotice(card, state, if (config.monitoringEnabled) COLOR_SUCCESS else COLOR_MUTED)
        if (config.monitoringEnabled) {
            addButton(card, "Pausar monitoreo") { pauseMonitoring("Monitoreo pausado por la persona usuaria.") }
        } else {
            addButton(card, "Activar monitoreo") { startMonitoring() }
        }
        addButton(card, "Reintentar eventos con error") {
            lifecycleScope.launch {
                withContext(Dispatchers.IO) {
                    repository.retryFailedAndEnqueue()
                }
                showToast("Los eventos fallidos regresaron a la cola.")
                refreshStatus()
            }
        }
    }

    private fun renderStatus() {
        val card = section(
            "Conexión, cola y eventos",
            "Los eventos se conservan con el mismo UUID durante los reintentos para que el servidor no los duplique.",
        )
        runtimeStatus = addText(card, "Consultando estado…", 14, color = COLOR_DARK, bottom = 6)
        queueStatus = addText(card, "Cola pendiente: …", 14, color = COLOR_DARK, bottom = 8)
        eventHistory = addText(card, "Todavía no hay eventos guardados.", 13, color = COLOR_MUTED)
    }

    private fun renderPrivacyActions() {
        val card = section(
            "Desvincular este teléfono",
            "La app solicita revocar el token al servidor y, si confirma, borra el token cifrado, la cola y el historial local. Los eventos ya enviados se conservan en la nube hasta su borrado administrativo o la retención configurada.",
        )
        addButton(card, "Desvincular teléfono y borrar datos locales") {
            AlertDialog.Builder(this)
                .setTitle("Desvincular teléfono")
                .setMessage("Se avisará al servidor para revocar este teléfono. Después se borrarán el token y la cola local. Los eventos ya recibidos por el servidor no se eliminan automáticamente.")
                .setNegativeButton("Cancelar", null)
                .setPositiveButton("Borrar") { _, _ -> clearConfigurationAndQueue() }
                .show()
        }
    }

    private fun saveConfiguration(): Boolean {
        val baseUrl = try {
            if (BuildConfig.DEBUG) {
                UrlPolicy.validateBaseUrl(urlInput.text.toString(), true)
            } else {
                UrlPolicy.validateBaseUrl(BuildConfig.DEFAULT_SERVER_URL, false)
            }
        } catch (error: IllegalArgumentException) {
            connectionTestStatus.text = error.message
            return false
        }
        val token = if (BuildConfig.DEBUG) tokenInput.text.toString().trim() else config.deviceToken
        val deviceName = deviceNameInput.text.toString().trim()
        if (token.isBlank()) {
            connectionTestStatus.text = "Pega la clave de dispositivo generada por el servidor."
            return false
        }
        if (!DEVICE_TOKEN.matches(token)) {
            connectionTestStatus.text = "La clave debe contener solo caracteres válidos de token de dispositivo."
            return false
        }
        if (deviceName.isBlank()) {
            connectionTestStatus.text = "Escribe un nombre o etiqueta para reconocer el teléfono."
            return false
        }
        if (deviceName.length > 80) {
            connectionTestStatus.text = "La etiqueta local puede tener hasta 80 caracteres."
            return false
        }

        config = config.copy(
            serverUrl = baseUrl,
            deviceToken = token,
            deviceName = deviceName,
            allowedPackages = selectedPackages.toSet(),
        )
        return saveConfigOrShowError("Configuración guardada cifrada en este dispositivo.")
    }

    private fun testServerConnection() {
        val baseUrl = try {
            if (BuildConfig.DEBUG) {
                UrlPolicy.validateBaseUrl(urlInput.text.toString(), true)
            } else {
                UrlPolicy.validateBaseUrl(BuildConfig.DEFAULT_SERVER_URL, false)
            }
        } catch (error: IllegalArgumentException) {
            connectionTestStatus.text = error.message
            return
        }
        connectionTestStatus.text = "Consultando /api/salud…"
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val request = Request.Builder()
                        .url(UrlPolicy.healthUrl(baseUrl))
                        .get()
                        .build()
                    httpClient.newCall(request).execute().use { response ->
                        if (!response.isSuccessful) {
                            "El servidor respondió HTTP ${response.code}."
                        } else {
                            val state = response.body?.string()?.let { JSONObject(it).optString("estado") }
                            if (state == "ok") {
                                "Servidor disponible. Este chequeo no valida la clave; se comprobará al enviar el primer evento."
                            } else {
                                "El servidor respondió, pero no reconoció /api/salud."
                            }
                        }
                    }
                } catch (error: IOException) {
                    "No se pudo conectar. Verifica la URL, la red y que el servidor esté activo."
                } catch (error: org.json.JSONException) {
                    "El servidor respondió con un formato inesperado."
                }
            }
            connectionTestStatus.text = result
        }
    }

    private fun startMonitoring() {
        if (!config.consentAccepted) {
            showToast("Acepta el consentimiento antes de activar el monitoreo.")
            return
        }
        if (!saveConfiguration()) return
        if (config.allowedPackages.isEmpty()) {
            showToast("Selecciona al menos una aplicación autorizada.")
            return
        }
        permissionSetupInProgress = true
        continuePermissionSetup()
    }

    private fun continuePermissionSetup() {
        if (config.allowedPackages.isEmpty()) {
            permissionSetupInProgress = false
            showToast("Selecciona al menos una aplicación autorizada antes de activar.")
            render()
            return
        }
        if (!hasNotificationAccess()) {
            awaitingNotificationAccess = true
            showToast("Activa el acceso a notificaciones; al volver revisaré el permiso.")
            openSettings(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
            return
        }
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }
        if (!NotificationManagerCompat.from(this).areNotificationsEnabled()) {
            showToast("Activa las notificaciones de esta app para mostrar el indicador persistente.")
            awaitingAppNotifications = true
            openAppNotificationSettings()
            return
        }
        if (!isBatteryExempt()) {
            awaitingBatteryExemption = true
            showToast("Revisa la exclusión de batería; al volver comprobaré el estado.")
            openSettings(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
            return
        }
        permissionSetupInProgress = false
        enableMonitoringAfterPermissions()
    }

    private fun enableMonitoringAfterPermissions() {
        permissionSetupInProgress = false
        config = config.copy(monitoringEnabled = true)
        if (!saveConfigOrShowError()) return
        try {
            MonitoringNotification.show(this)
        } catch (error: SecurityException) {
            pauseMonitoring("Android no permitió mostrar el indicador persistente.")
            showToast("Concede el permiso de notificaciones para activar el indicador.")
            return
        }
        WorkScheduler.scheduleHeartbeat(this)
        repository.enqueuePendingUpload()
        RuntimeStatus.record(this, "Monitoreo activado; esperando notificaciones autorizadas.")
        render()
        refreshStatus()
    }

    private fun pauseMonitoring(message: String) {
        config = config.copy(monitoringEnabled = false)
        saveConfigOrShowError()
        WorkManagerCancellation.cancel(this)
        MonitoringNotification.cancel(this)
        RuntimeStatus.record(this, message)
        if (::runtimeStatus.isInitialized) {
            render()
            refreshStatus()
        }
    }

    private fun clearConfigurationAndQueue() {
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    if (config.deviceToken.isNotBlank()) {
                        EnrollmentApi().unlink(config.serverUrl, config.deviceToken)
                    }
                    repository.clearQueueAndHistory()
                    secureStore.clear()
                }
                WorkScheduler.cancelHeartbeat(this@MainActivity)
                config = MonitorConfig(serverUrl = BuildConfig.DEFAULT_SERVER_URL)
                selectedPackages.clear()
                storageError = null
                RuntimeStatus.clear(this@MainActivity)
                MonitoringNotification.cancel(this@MainActivity)
                render()
                showToast("Teléfono desvinculado; token y cola local borrados. Los eventos del servidor conservan su retención normal.")
            } catch (error: IOException) {
                showToast("No se pudo confirmar la desvinculación con el servidor. La configuración local se conservó para reintentar.")
            } catch (error: ConfigStoreException) {
                showToast(error.message ?: "No se pudo borrar la configuración.")
            }
        }
    }

    private fun saveConfigOrShowError(successMessage: String? = null): Boolean {
        return try {
            secureStore.save(config)
            storageError = null
            successMessage?.let(::showToast)
            true
        } catch (error: ConfigStoreException) {
            storageError = error.message
            showToast(error.message ?: "No se pudo guardar la configuración.")
            false
        }
    }

    private fun refreshStatus() {
        if (!::runtimeStatus.isInitialized) return
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                val dao = MonitorDatabase.get(applicationContext).monitorDao()
                dao.pendingCount() to dao.getAllForStatus()
            }
            val snapshot = RuntimeStatus.read(applicationContext)
            runtimeStatus.text = buildString {
                append(snapshot.message)
                append("\nÚltimo envío correcto: ")
                append(RuntimeStatus.formattedTime(snapshot.lastSentAt))
            }
            val failed = result.second.count { it.state == StoredEvent.STATE_FAILED }
            queueStatus.text = "Pendientes: ${result.first} · Con error: $failed · En historial local: ${result.second.size}"
            eventHistory.text = if (result.second.isNotEmpty()) {
                result.second.joinToString(separator = "\n\n") { formatEventForStatus(it) }
            } else {
                "Todavía no hay eventos guardados."
            }
        }
    }

    private fun formatEventForStatus(event: StoredEvent): String {
        val stateLabel = when (event.state) {
            StoredEvent.STATE_SENT -> "Enviado"
            StoredEvent.STATE_FAILED -> "Error: ${event.lastError.orEmpty()}"
            else -> "Pendiente"
        }
        return buildString {
            append(event.fecha)
            append(" · ")
            append(event.app)
            append(" · ")
            append(event.tipo)
            append(" · ")
            append(stateLabel)
            event.remitente?.let {
                append("\n")
                append(it)
            }
            append("\n")
            append(event.texto)
        }
    }

    private fun updatePermissionStatus() {
        if (!::permissionStatus.isInitialized || !::batteryStatus.isInitialized) return
        permissionStatus.text = buildString {
            append(if (hasNotificationAccess()) "Acceso a notificaciones: concedido." else "Acceso a notificaciones: pendiente.")
            append("\n")
            append(
                if (canShowOngoingNotification()) {
                    "Notificaciones de la app: habilitadas."
                } else {
                    "Notificaciones de la app: habilita el permiso para el indicador persistente."
                },
            )
        }
        val exempt = isBatteryExempt()
        batteryStatus.text = if (exempt) {
            "Optimización de batería: desactivada para esta app."
        } else {
            "Optimización de batería: activa; puede retrasar la cola si Android detiene procesos."
        }
    }

    private fun hasNotificationAccess(): Boolean {
        val component = ComponentName(this, MonitorNotificationListener::class.java)
        val enabled = Settings.Secure.getString(
            contentResolver,
            "enabled_notification_listeners",
        ).orEmpty()
        return enabled.split(':').any { ComponentName.unflattenFromString(it) == component }
    }

    private fun isBatteryExempt(): Boolean =
        getSystemService(PowerManager::class.java)?.isIgnoringBatteryOptimizations(packageName) == true

    private fun canShowOngoingNotification(): Boolean =
        NotificationManagerCompat.from(this).areNotificationsEnabled() &&
            (
                Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                    checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
                )

    private fun openSettings(action: String) {
        try {
            startActivity(Intent(action))
        } catch (error: ActivityNotFoundException) {
            showToast("No se encontró la pantalla de Ajustes requerida.")
        }
    }

    private fun openAppNotificationSettings() {
        try {
            startActivity(
                Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                    .putExtra("app_package", packageName),
            )
        } catch (error: ActivityNotFoundException) {
            showToast("No se encontró la pantalla de notificaciones de esta app.")
        }
    }

    private fun addInput(
        parent: LinearLayout,
        label: String,
        value: String,
        hint: String,
        inputType: Int,
    ): EditText {
        addText(parent, label, 14, bold = true, color = COLOR_DARK, bottom = 4)
        return EditText(this).apply {
            setSingleLine(true)
            this.inputType = inputType
            this.hint = hint
            setText(value)
            setTextColor(COLOR_DARK)
            setHintTextColor(COLOR_MUTED)
            backgroundTintList = android.content.res.ColorStateList.valueOf(COLOR_BORDER)
            contentDescription = label
            parent.addView(
                this,
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(52),
                ).apply { bottomMargin = dp(12) },
            )
        }
    }

    private fun section(title: String, description: String): LinearLayout {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(16))
            background = GradientDrawable().apply {
                setColor(Color.WHITE)
                cornerRadius = dp(14).toFloat()
                setStroke(dp(1), COLOR_BORDER)
            }
        }
        content.addView(
            card,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                bottomMargin = dp(14)
            },
        )
        addText(card, title, 19, bold = true, color = COLOR_DARK, bottom = 4)
        addText(card, description, 14, color = COLOR_MUTED, bottom = 10)
        return card
    }

    private fun addText(
        parent: LinearLayout,
        text: String,
        size: Int,
        bold: Boolean = false,
        color: Int = COLOR_DARK,
        bottom: Int = 0,
    ): TextView = TextView(this).apply {
        this.text = text
        textSize = size.toFloat()
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        setPadding(0, 0, 0, dp(bottom))
        parent.addView(
            this,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )
    }

    private fun addNotice(parent: LinearLayout, text: String, color: Int): TextView =
        addText(parent, text, 14, bold = true, color = color, bottom = 10)

    private fun addButton(parent: LinearLayout, label: String, action: () -> Unit): Button =
        Button(this).apply {
            text = label
            isAllCaps = false
            setTextColor(Color.WHITE)
            backgroundTintList = android.content.res.ColorStateList.valueOf(COLOR_ACCENT)
            setOnClickListener { action() }
            val horizontal = parent.orientation == LinearLayout.HORIZONTAL
            parent.addView(
                this,
                LinearLayout.LayoutParams(
                    if (horizontal) 0 else ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    if (horizontal) 1f else 0f,
                ).apply {
                    topMargin = dp(4)
                    bottomMargin = dp(6)
                    if (horizontal) marginEnd = dp(6)
                },
            )
        }

    private fun horizontalRow(parent: LinearLayout): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            parent.addView(
                this,
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
        }

    private fun disableChildren(view: ViewGroup) {
        for (index in 0 until view.childCount) {
            val child = view.getChildAt(index)
            child.isEnabled = false
            if (child is ViewGroup) disableChildren(child)
        }
    }

    private fun showToast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private data class AppOption(val packageName: String, val label: String)

    private object WorkManagerCancellation {
        fun cancel(activity: ComponentActivity) {
            androidx.work.WorkManager.getInstance(activity)
                .cancelUniqueWork(EventUploadWorker.UNIQUE_WORK_NAME)
        }
    }

    private companion object {
        const val STATUS_REFRESH_MS = 3000L
        val COLOR_DARK = Color.rgb(27, 38, 53)
        val COLOR_MUTED = Color.rgb(93, 107, 125)
        val COLOR_ACCENT = Color.rgb(36, 87, 197)
        val COLOR_BORDER = Color.rgb(215, 222, 232)
        val COLOR_SUCCESS = Color.rgb(31, 119, 78)
        val COLOR_WARNING = Color.rgb(137, 92, 9)
        val COLOR_ERROR = Color.rgb(166, 45, 50)
        val PACKAGE_NAME = Regex("[A-Za-z0-9_]+(?:\\.[A-Za-z0-9_]+)+")
        val DEVICE_TOKEN = Regex("[A-Za-z0-9_-]{32,256}")
        val APP_OPTIONS = listOf(
            AppOption("com.whatsapp", "WhatsApp"),
            AppOption("org.telegram.messenger", "Telegram"),
            AppOption("com.facebook.orca", "Messenger"),
            AppOption("com.google.android.apps.messaging", "Mensajes de Google (SMS)"),
            AppOption("com.android.messaging", "Mensajes Android (SMS)"),
            AppOption("com.android.mms", "Mensajes del sistema (SMS)"),
            AppOption("org.thoughtcrime.securesms", "Signal"),
            AppOption("com.instagram.android", "Instagram"),
        )
        val httpClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}
