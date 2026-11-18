package expo.modules.ridefilter

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

object RideFilterStore {
  private const val PREFS = "ride_filter_prefs"
  const val KEY_CONFIG = "config"
  const val KEY_EVENTS = "events"
  private const val KEY_LEARNING = "learning"
  private const val KEY_SCREEN_PREFIX = "screen_"
  private const val MAX_EVENTS = 300

  fun prefs(context: Context): SharedPreferences =
    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

  @Volatile private var cachedRaw: String? = null
  @Volatile private var cachedConfig: JSONObject? = null

  /** Parsed once per change (not on every accessibility event) for speed. */
  fun config(context: Context): JSONObject? {
    val raw = prefs(context).getString(KEY_CONFIG, null) ?: return null
    if (raw == cachedRaw) return cachedConfig
    val parsed = try { JSONObject(raw) } catch (e: Exception) { null }
    cachedRaw = raw
    cachedConfig = parsed
    return parsed
  }

  // ---- Learning mode: capture visible texts of RapidoCar / MooveCar screens ----
  fun isLearning(context: Context): Boolean = prefs(context).getBoolean(KEY_LEARNING, false)

  fun setLearning(context: Context, on: Boolean) {
    prefs(context).edit().putBoolean(KEY_LEARNING, on).apply()
  }

  // ---- Diagnostics written by the service, read by the app ----
  fun saveDiag(context: Context, json: String) {
    prefs(context).edit().putString("diag", json).apply()
  }

  fun diag(context: Context): String = prefs(context).getString("diag", "{}") ?: "{}"

  // ---- Manual online/offline from the floating button: kept until the JS app saves it to the server ----
  private const val KEY_MANUAL = "manual_toggle"

  fun manual(context: Context): Boolean? =
    if (prefs(context).contains(KEY_MANUAL)) prefs(context).getBoolean(KEY_MANUAL, false) else null

  fun clearManual(context: Context) {
    prefs(context).edit().remove(KEY_MANUAL).apply()
  }

  /** Every bot on/off in the stored config right away (the service reads it on the next offer). */
  fun setManual(context: Context, on: Boolean) {
    val raw = prefs(context).getString(KEY_CONFIG, null) ?: return
    prefs(context).edit().putString(KEY_CONFIG, withAllEnabled(raw, on)).putBoolean(KEY_MANUAL, on).commit()
  }

  /** Config sent by the app, with a pending manual choice applied so it is not undone before syncing. */
  fun applyManual(context: Context, raw: String): String = manual(context)?.let { withAllEnabled(raw, it) } ?: raw

  private fun withAllEnabled(raw: String, on: Boolean): String = try {
    val cfg = JSONObject(raw)
    val apps = cfg.optJSONObject("apps")
    apps?.keys()?.forEach { k -> apps.optJSONObject(k)?.put("enabled", on) }
    cfg.toString()
  } catch (e: Exception) { raw }

  // ---- Ride in progress: {"app":"moove","since":ms}; the other app's bot stays off-line ----
  private const val KEY_BUSY = "busy"

  fun busy(context: Context): JSONObject? =
    prefs(context).getString(KEY_BUSY, null)?.let { try { JSONObject(it) } catch (e: Exception) { null } }

  fun setBusy(context: Context, app: String, notificationId: Int = -1) {
    // A second accept while busy: close the previous ride's notification so only one button remains.
    val prev = busy(context)?.optInt("notification_id", -1) ?: -1
    if (prev >= 0 && prev != notificationId) {
      try {
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager).cancel(prev)
      } catch (e: Exception) { /* ignored */ }
    }
    prefs(context).edit().putString(
      KEY_BUSY,
      JSONObject().put("app", app).put("since", System.currentTimeMillis()).put("notification_id", notificationId).toString()
    ).apply()
  }

  /** Both bots online again; also removes the "Voltar online" notification of that ride. */
  fun clearBusy(context: Context) {
    val id = busy(context)?.optInt("notification_id", -1) ?: -1
    prefs(context).edit().remove(KEY_BUSY).apply()
    if (id >= 0) {
      try {
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager).cancel(id)
      } catch (e: Exception) { /* ignored */ }
    }
  }

  fun saveScreen(context: Context, key: String, pkg: String, texts: List<String>) {
    val obj = JSONObject().apply {
      put("package", pkg)
      put("at", System.currentTimeMillis())
      put("texts", JSONArray(texts))
    }
    prefs(context).edit().putString(KEY_SCREEN_PREFIX + key, obj.toString()).apply()
  }

  /** JSON: {learning, rapido: {...}|null, moove: {...}|null} */
  fun capturedScreens(context: Context): String {
    val p = prefs(context)
    fun read(k: String): Any = p.getString(KEY_SCREEN_PREFIX + k, null)?.let {
      try { JSONObject(it) } catch (e: Exception) { JSONObject.NULL }
    } ?: JSONObject.NULL
    return JSONObject().apply {
      put("learning", p.getBoolean(KEY_LEARNING, false))
      for (k in RideAccessibilityService.APP_KEYS) put(k, read(k))
    }.toString()
  }

  @Synchronized
  fun appendEvent(context: Context, event: JSONObject) {
    val p = prefs(context)
    val current = try { JSONArray(p.getString(KEY_EVENTS, "[]")) } catch (e: Exception) { JSONArray() }
    current.put(event)
    val out = JSONArray()
    val start = maxOf(0, current.length() - MAX_EVENTS)
    for (i in start until current.length()) out.put(current.get(i))
    p.edit().putString(KEY_EVENTS, out.toString()).apply()
  }
}
