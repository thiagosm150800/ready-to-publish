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
      put("rapido", read("rapido"))
      put("moove", read("moove"))
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
