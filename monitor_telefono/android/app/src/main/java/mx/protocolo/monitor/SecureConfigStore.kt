package mx.protocolo.monitor

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class ConfigStoreException(message: String, cause: Throwable? = null) : Exception(message, cause)

class SecureConfigStore(context: Context) {
    private val preferences =
        context.applicationContext.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    @Synchronized
    fun load(): MonitorConfig? {
        val encrypted = preferences.getString(KEY_CIPHERTEXT, null) ?: return null
        val encodedIv = preferences.getString(KEY_IV, null)
            ?: throw ConfigStoreException("La configuración cifrada está incompleta.")
        return try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            val iv = Base64.decode(encodedIv, Base64.NO_WRAP)
            val ciphertext = Base64.decode(encrypted, Base64.NO_WRAP)
            cipher.init(Cipher.DECRYPT_MODE, loadOrCreateKey(), GCMParameterSpec(GCM_TAG_LENGTH_BITS, iv))
            val plaintext = cipher.doFinal(ciphertext)
            fromJson(JSONObject(String(plaintext, Charsets.UTF_8)))
        } catch (error: GeneralSecurityException) {
            throw ConfigStoreException("No se pudo descifrar la configuración local.", error)
        } catch (error: IOException) {
            throw ConfigStoreException("No se pudo abrir Android Keystore.", error)
        } catch (error: IllegalArgumentException) {
            throw ConfigStoreException("La configuración cifrada no es válida.", error)
        } catch (error: JSONException) {
            throw ConfigStoreException("La configuración cifrada no tiene un formato válido.", error)
        }
    }

    @Synchronized
    fun save(config: MonitorConfig) {
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, loadOrCreateKey())
            val ciphertext = cipher.doFinal(toJson(config).toString().toByteArray(Charsets.UTF_8))
            val saved = preferences.edit()
                .putString(KEY_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .putString(KEY_CIPHERTEXT, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
                .commit()
            if (!saved) throw ConfigStoreException("No se pudo guardar la configuración cifrada.")
        } catch (error: GeneralSecurityException) {
            throw ConfigStoreException("No se pudo cifrar la configuración local.", error)
        } catch (error: IOException) {
            throw ConfigStoreException("No se pudo abrir Android Keystore.", error)
        } catch (error: JSONException) {
            throw ConfigStoreException("No se pudo serializar la configuración.", error)
        }
    }

    @Synchronized
    fun clear() {
        if (!preferences.edit().clear().commit()) {
            throw ConfigStoreException("No se pudieron borrar los datos cifrados.")
        }
        try {
            val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE)
            keyStore.load(null)
            if (keyStore.containsAlias(KEY_ALIAS)) keyStore.deleteEntry(KEY_ALIAS)
        } catch (error: GeneralSecurityException) {
            throw ConfigStoreException("No se pudo borrar la clave local cifrada.", error)
        } catch (error: IOException) {
            throw ConfigStoreException("No se pudo abrir Android Keystore.", error)
        }
    }

    private fun loadOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE)
        keyStore.load(null)
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private fun toJson(config: MonitorConfig): JSONObject =
        JSONObject()
            .put("server_url", config.serverUrl)
            .put("device_token", config.deviceToken)
            .put("device_name", config.deviceName)
            .put("allowed_packages", JSONArray(config.allowedPackages.sorted()))
            .put("consent_accepted", config.consentAccepted)
            .put("monitoring_enabled", config.monitoringEnabled)
            .put("consent_text", config.consentText)
            .put("trusted_contact_phone", config.trustedContactPhone)

    private fun fromJson(json: JSONObject): MonitorConfig {
        val packages = json.optJSONArray("allowed_packages") ?: JSONArray()
        val allowedPackages = buildSet {
            for (index in 0 until packages.length()) {
                packages.optString(index).takeIf(String::isNotBlank)?.let(::add)
            }
        }
        return MonitorConfig(
            serverUrl = json.optString("server_url"),
            deviceToken = json.optString("device_token"),
            deviceName = json.optString("device_name"),
            allowedPackages = allowedPackages,
            consentAccepted = json.optBoolean("consent_accepted"),
            monitoringEnabled = json.optBoolean("monitoring_enabled"),
            consentText = json.optString("consent_text"),
            trustedContactPhone = json.optString("trusted_contact_phone"),
        )
    }

    private companion object {
        const val PREFERENCES_NAME = "monitor_vault"
        const val KEY_CIPHERTEXT = "encrypted_config"
        const val KEY_IV = "config_iv"
        const val KEY_ALIAS = "monitor_config_v1"
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_TAG_LENGTH_BITS = 128
    }
}
