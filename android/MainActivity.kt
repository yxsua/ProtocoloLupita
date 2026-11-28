package com.example.lupita

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private val permisosRequeridos = arrayOf(
        Manifest.permission.RECEIVE_SMS,
        Manifest.permission.READ_CALL_LOG,
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        mostrarConsentimiento()
    }

    private fun mostrarConsentimiento() {
        val texto = TextView(this).apply {
            text = "Protocolo Lupita enviará al servidor las notificaciones visibles, " +
                "el texto de SMS entrantes y los datos básicos de llamadas nuevas " +
                "(número, sentido, fecha y duración). No graba audio ni conserva " +
                "una copia local. Debes autorizar cada permiso explícitamente."
            textSize = 16f
            setPadding(24, 24, 24, 24)
        }
        val boton = Button(this).apply {
            text = "Continuar y revisar permisos"
            setOnClickListener { solicitarPermisos() }
        }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(24, 24, 24, 24)
            addView(texto, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            addView(boton, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        setContentView(layout)
    }

    private fun solicitarPermisos() {
        if (
            BuildConfig.LUPITA_BASE_URL.isBlank() ||
            BuildConfig.LUPITA_DEVICE_KEY.isBlank() ||
            BuildConfig.LUPITA_DEVICE_ID.isBlank() ||
            BuildConfig.LUPITA_DEVICE_ID.length > 64
        ) {
            Toast.makeText(
                this,
                "Configura primero el servidor y la clave del dispositivo.",
                Toast.LENGTH_LONG,
            ).show()
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
            abrirAccesoNotificaciones()
            return
        }
        val pendientes = permisosRequeridos.filter {
            checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED
        }
        if (pendientes.isEmpty()) {
            abrirAccesoNotificaciones()
        } else {
            requestPermissions(pendientes.toTypedArray(), REQUEST_PERMISSIONS)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_PERMISSIONS) return
        if (grantResults.isNotEmpty() && grantResults.all {
                it == PackageManager.PERMISSION_GRANTED
            }
        ) {
            abrirAccesoNotificaciones()
        } else {
            Toast.makeText(
                this,
                "Sin esos permisos solo estarán disponibles las notificaciones permitidas.",
                Toast.LENGTH_LONG,
            ).show()
        }
    }

    private fun abrirAccesoNotificaciones() {
        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
    }

    private companion object {
        const val REQUEST_PERMISSIONS = 1001
    }
}
