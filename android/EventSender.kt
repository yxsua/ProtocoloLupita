package com.example.lupita

import android.util.Log
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException

internal object EventSender {

    private const val TAG = "LupitaEventSender"
    private val http = OkHttpClient()
    private val json = "application/json; charset=utf-8".toMediaType()

    fun enviar(evento: JSONObject, alTerminar: () -> Unit = {}) {
        val baseUrl = BuildConfig.LUPITA_BASE_URL.trimEnd('/')
        val deviceKey = BuildConfig.LUPITA_DEVICE_KEY
        if (baseUrl.isBlank() || deviceKey.isBlank()) {
            Log.e(TAG, "Configura LUPITA_BASE_URL y LUPITA_DEVICE_KEY en local.properties.")
            alTerminar()
            return
        }
        val endpoint = "$baseUrl/api/eventos".toHttpUrlOrNull()
        if (endpoint == null) {
            Log.e(TAG, "LUPITA_BASE_URL no es una URL válida.")
            alTerminar()
            return
        }

        val request = Request.Builder()
            .url(endpoint)
            .header("X-Device-Key", deviceKey)
            .post(evento.toString().toRequestBody(json))
            .build()

        http.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e(TAG, "No se pudo enviar el evento; no se guardó localmente.", e)
                alTerminar()
            }

            override fun onResponse(call: Call, response: Response) {
                try {
                    if (!response.isSuccessful) {
                        Log.e(TAG, "El servidor rechazó el evento: HTTP ${response.code}.")
                    }
                } finally {
                    response.close()
                    alTerminar()
                }
            }
        })
    }
}
