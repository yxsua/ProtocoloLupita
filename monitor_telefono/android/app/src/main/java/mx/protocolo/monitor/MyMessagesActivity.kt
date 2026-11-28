package mx.protocolo.monitor

import android.graphics.Color
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mx.protocolo.monitor.util.UrlPolicy
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class MyMessagesActivity : ComponentActivity() {
    private lateinit var entries: LinearLayout
    private lateinit var status: TextView
    private var config: MonitorConfig? = null
    private var pendingExportJson: String? = null
    private val exportDocumentLauncher =
        registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
            val exportJson = pendingExportJson
            pendingExportJson = null
            if (uri != null && exportJson != null) {
                lifecycleScope.launch {
                    try {
                        withContext(Dispatchers.IO) {
                            val output = contentResolver.openOutputStream(uri)
                                ?: throw IOException("No se pudo crear el archivo seleccionado.")
                            output.use { it.write(exportJson.toByteArray(Charsets.UTF_8)) }
                        }
                        status.text = "Exportación guardada."
                    } catch (error: IOException) {
                        status.text = error.message ?: "No se pudo guardar la exportación."
                    }
                }
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this).apply {
            setBackgroundColor(Color.rgb(244, 247, 251))
            setPadding(dp(16), dp(12), dp(16), dp(24))
        }
        entries = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        scroll.addView(
            entries,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )
        setContentView(scroll)
        text("Mis mensajes y alertas", 24, bold = true)
        text("Solo se consultan los eventos vinculados a este teléfono.", 14)
        status = text("Cargando…", 14)
        Button(this).apply {
            text = "Actualizar"
            setOnClickListener { loadEvents() }
            entries.addView(this)
        }
        Button(this).apply {
            text = "Exportar mis datos"
            setOnClickListener { exportMyData() }
            entries.addView(this)
        }
        config = try {
            SecureConfigStore(applicationContext).load()
        } catch (error: ConfigStoreException) {
            status.text = error.message ?: "No se pudo leer la vinculación protegida."
            null
        }
        loadEvents()
    }

    private fun loadEvents() {
        val current = config
        if (current == null || current.deviceToken.isBlank()) {
            status.text = "Este teléfono no está vinculado."
            return
        }
        status.text = "Consultando tus mensajes…"
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val baseUrl = UrlPolicy.validateBaseUrl(current.serverUrl, BuildConfig.DEBUG)
                    val request = Request.Builder()
                        .url("${baseUrl.trimEnd('/')}/api/mis-eventos")
                        .header("X-Device-Key", current.deviceToken)
                        .get()
                        .build()
                    httpClient.newCall(request).execute().use { response ->
                        val body = response.body?.string().orEmpty()
                        if (!response.isSuccessful) {
                            throw IOException("El servidor respondió HTTP ${response.code}.")
                        }
                        JSONObject(body).optJSONArray("items") ?: JSONArray()
                    }
                } catch (error: IOException) {
                    return@withContext error
                } catch (error: IllegalArgumentException) {
                    return@withContext IOException(error.message ?: "La URL del servidor no es válida.")
                } catch (error: JSONException) {
                    return@withContext IOException("El servidor respondió con un formato inesperado.", error)
                }
            }
            entries.removeViews(5, (entries.childCount - 5).coerceAtLeast(0))
            when (result) {
                is IOException -> status.text = result.message
                is JSONArray -> {
                    status.text = if (result.length() == 0) {
                        "Aún no hay mensajes sincronizados."
                    } else {
                        "Mensajes recientes: ${result.length()}"
                    }
                    for (index in 0 until result.length()) {
                        val item = result.optJSONObject(index) ?: continue
                        addEventCard(item)
                    }
                }
            }
        }
    }

    private fun exportMyData() {
        val current = config
        if (current == null || current.deviceToken.isBlank()) {
            status.text = "Este teléfono no está vinculado."
            return
        }
        status.text = "Preparando la exportación segura…"
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val baseUrl = UrlPolicy.validateBaseUrl(current.serverUrl, BuildConfig.DEBUG)
                    val request = Request.Builder()
                        .url("${baseUrl.trimEnd('/')}/api/mis-eventos/exportar")
                        .header("X-Device-Key", current.deviceToken)
                        .get()
                        .build()
                    httpClient.newCall(request).execute().use { response ->
                        val body = response.body?.string().orEmpty()
                        if (!response.isSuccessful) {
                            throw IOException("El servidor respondió HTTP ${response.code}.")
                        }
                        JSONObject(body)
                        body
                    }
                } catch (error: IOException) {
                    return@withContext error
                } catch (error: IllegalArgumentException) {
                    return@withContext IOException(error.message ?: "La URL del servidor no es válida.")
                } catch (error: JSONException) {
                    return@withContext IOException("El servidor respondió con una exportación inválida.", error)
                }
            }
            when (result) {
                is IOException -> status.text = result.message
                is String -> {
                    pendingExportJson = result
                    exportDocumentLauncher.launch("mis-datos-monitor.json")
                }
            }
        }
    }

    private fun addEventCard(item: JSONObject) {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            setBackgroundColor(Color.WHITE)
        }
        val level = item.optString("nivel_riesgo", "bajo").uppercase()
        val heading = "${item.optString("fecha")} · ${item.optString("app")}"
        val sender = item.optString("remitente").ifBlank { "Remitente no identificado" }
        val text = item.optString("texto").ifBlank { "El texto se eliminó según la retención configurada." }
        addText(card, heading, 13, bold = true)
        addText(card, "Riesgo: $level (${item.optInt("riesgo")}/100) · $sender", 14, bold = true)
        addText(card, text, 15)
        val reasons = item.optJSONArray("razones_riesgo") ?: JSONArray()
        for (index in 0 until reasons.length()) {
            addText(card, "• ${reasons.optJSONObject(index)?.optString("detalle").orEmpty()}", 13)
        }
        val review = item.optString("revision_estado")
        if (review.isNotBlank() && review != "null") {
            addText(card, "Revisión: $review", 13, bold = true)
        } else if (level != "BAJO") {
            addText(card, "Revisión pendiente", 13, bold = true)
        }
        entries.addView(
            card,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { bottomMargin = dp(10) },
        )
    }

    private fun text(value: String, size: Int, bold: Boolean = false): TextView =
        TextView(this).apply {
            text = value
            textSize = size.toFloat()
            setTextColor(Color.rgb(27, 38, 53))
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(0, 0, 0, dp(10))
            entries.addView(this)
        }

    private fun addText(parent: LinearLayout, value: String, size: Int, bold: Boolean = false) {
        val view = TextView(this).apply {
            text = value
            textSize = size.toFloat()
            setTextColor(Color.rgb(27, 38, 53))
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        parent.addView(view)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private companion object {
        val httpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}
