package expo.modules.ridefilter

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Reads ride offers of RapidoCar and MooveCar, each with its own filters, and taps "Aceitar"
 * when the offer passes them. Every evaluated offer is stored so the JS app can sync it.
 */
class RideAccessibilityService : AccessibilityService() {
  private val handler = Handler(Looper.getMainLooper())
  private val lastSignature = HashMap<String, String>()
  private val lastTime = HashMap<String, Long>()
  private val lastCapture = HashMap<String, Long>()

  private val priceRe = Regex("""R\$\s*(\d{1,3}(?:\.\d{3})*,\d{1,2}|\d+(?:[.,]\d{1,2})?)""")
  private val kmRe = Regex("""(\d+(?:[.,]\d+)?)\s*km\b""", RegexOption.IGNORE_CASE)

  companion object {
    val APP_KEYS = listOf("rapido", "moove")
    @Volatile var instance: RideAccessibilityService? = null
  }

  override fun onServiceConnected() {
    super.onServiceConnected()
    instance = this
    applyPackageFilter()
  }

  override fun onDestroy() {
    instance = null
    super.onDestroy()
  }

  override fun onInterrupt() {}

  override fun onAccessibilityEvent(event: AccessibilityEvent?) {
    if (event == null) return
    val pkg = event.packageName?.toString() ?: return
    if (pkg == packageName) return
    val cfg = RideFilterStore.config(this) ?: return
    val apps = cfg.optJSONObject("apps") ?: return
    val key = matchApp(pkg.lowercase(), apps) ?: return
    val appCfg = apps.optJSONObject(key) ?: return

    if (RideFilterStore.isLearning(this)) captureScreen(key, pkg)

    if (!appCfg.optBoolean("enabled", false)) return
    if (!inSchedule(cfg)) return
    val root = rootInActiveWindow ?: return
    acceptIfMatches(root, key, appCfg, cfg)
  }

  private fun matchApp(pkgLower: String, apps: JSONObject): String? {
    for (key in APP_KEYS) {
      val target = apps.optJSONObject(key)?.optString("target_package", "")?.trim()?.lowercase() ?: continue
      if (target.isNotEmpty() && pkgLower.contains(target)) return key
    }
    return null
  }

  /**
   * Speed: ask Android to deliver events ONLY from RapidoCar and MooveCar.
   * Called on connect and on every config change.
   */
  fun applyPackageFilter() {
    handler.post {
      val apps = RideFilterStore.config(this)?.optJSONObject("apps") ?: return@post
      val pkgs = APP_KEYS.mapNotNull { k ->
        val target = apps.optJSONObject(k)?.optString("target_package", "")?.trim()?.lowercase() ?: ""
        findLaunchablePackage(target)
      }.distinct()
      val info = serviceInfo ?: return@post
      // If nothing matched (app not installed / wrong name), listen to all apps so nothing is missed.
      info.packageNames = if (pkgs.isEmpty()) null else pkgs.toTypedArray()
      info.notificationTimeout = 0
      serviceInfo = info
    }
  }

  private fun findLaunchablePackage(sub: String): String? {
    if (sub.isEmpty()) return null
    val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
    return packageManager.queryIntentActivities(intent, 0)
      .map { it.activityInfo.packageName }
      .firstOrNull { it.lowercase().contains(sub) && it != packageName }
  }

  // ---------------- auto-accept ----------------

  private fun acceptIfMatches(root: AccessibilityNodeInfo, key: String, appCfg: JSONObject, cfg: JSONObject) {
    // Cheapest check first: is there an accept button on screen at all?
    val button = findLabeledNode(root, readList(appCfg.optJSONArray("accept_texts"), listOf("Aceitar", "Accept"))) ?: return

    val texts = mutableListOf<String>()
    collectTexts(root, texts, 0)
    val all = texts.joinToString(" | ")
    val price = priceRe.find(all)?.groupValues?.get(1)?.let { parseNumber(it) } ?: return
    val kms = kmRe.findAll(all).mapNotNull { parseNumber(it.groupValues[1]) }.toList()
    if (kms.isEmpty()) return
    val pickupKm = if (kms.size >= 2) kms[0] else 0.0
    val tripKm = if (kms.size >= 2) kms[1] else kms[0]
    if (tripKm <= 0.0) return

    val signature = "$price|$tripKm|$pickupKm"
    val now = System.currentTimeMillis()
    if (signature == lastSignature[key] && now - (lastTime[key] ?: 0L) < 20000) return
    lastSignature[key] = signature
    lastTime[key] = now

    val ppk = Math.round(price / tripKm * 100.0) / 100.0
    val reasons = JSONArray()
    if (ppk < appCfg.optDouble("min_price_per_km", 0.0)) reasons.put("R$/km abaixo do mínimo")
    if (price < appCfg.optDouble("min_fare", 0.0)) reasons.put("Valor abaixo do mínimo")
    if (pickupKm > appCfg.optDouble("max_pickup_km", Double.MAX_VALUE)) reasons.put("Busca muito longe")

    val accepted = reasons.length() == 0
    if (accepted) {
      clickNode(button)
      if (cfg.optBoolean("alert_enabled", true)) playAlert()
    }

    RideFilterStore.appendEvent(this, JSONObject().apply {
      put("app", key)
      put("source", if (key == "moove") "moovecar" else "rapidocar")
      put("price", price)
      put("trip_km", tripKm)
      put("pickup_km", pickupKm)
      put("price_per_km", ppk)
      put("accepted", accepted)
      put("reasons", reasons)
      put("created_at", isoNow())
    })
  }

  // ---------------- learning mode ----------------

  private fun captureScreen(key: String, pkg: String) {
    val now = System.currentTimeMillis()
    if (now - (lastCapture[key] ?: 0L) < 1500) return
    val root = rootInActiveWindow ?: return
    if (root.packageName?.toString() != pkg) return
    lastCapture[key] = now
    val texts = mutableListOf<String>()
    collectTexts(root, texts, 0)
    val clean = texts.map { it.trim() }.filter { it.isNotEmpty() && it.length <= 60 }.distinct().take(120)
    if (clean.isNotEmpty()) RideFilterStore.saveScreen(this, key, pkg, clean)
  }

  // ---------------- helpers ----------------

  /** Days: 0=Sunday..6=Saturday. Times "HH:MM". Window may cross midnight. */
  private fun inSchedule(cfg: JSONObject): Boolean {
    if (!cfg.optBoolean("schedule_enabled", false)) return true
    val cal = Calendar.getInstance()
    val day = cal.get(Calendar.DAY_OF_WEEK) - 1
    val minutes = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE)
    val days = cfg.optJSONArray("schedule_days")
    if (days != null) {
      val allowed = (0 until days.length()).map { days.optInt(it) }
      if (!allowed.contains(day)) return false
    }
    val start = toMinutes(cfg.optString("schedule_start", "00:00"))
    val end = toMinutes(cfg.optString("schedule_end", "23:59"))
    return if (start <= end) minutes in start until end else (minutes >= start || minutes < end)
  }

  private fun toMinutes(hhmm: String): Int {
    val parts = hhmm.split(":")
    return (parts.getOrNull(0)?.toIntOrNull() ?: 0) * 60 + (parts.getOrNull(1)?.toIntOrNull() ?: 0)
  }

  private fun playAlert() {
    try {
      val tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)
      tone.startTone(ToneGenerator.TONE_PROP_ACK, 500)
      handler.postDelayed({ tone.release() }, 800)
    } catch (e: Exception) { /* ignored */ }
    try {
      @Suppress("DEPRECATION")
      val vib = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        vib?.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 250, 120, 250), -1))
      } else {
        @Suppress("DEPRECATION")
        vib?.vibrate(longArrayOf(0, 250, 120, 250), -1)
      }
    } catch (e: Exception) { /* ignored */ }
  }

  private fun isoNow(): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US).apply {
    timeZone = TimeZone.getTimeZone("UTC")
  }.format(Date())

  private fun readList(arr: JSONArray?, fallback: List<String>): List<String> {
    if (arr == null || arr.length() == 0) return fallback
    return (0 until arr.length()).map { arr.optString(it).trim() }.filter { it.isNotEmpty() }
  }

  private fun parseNumber(raw: String): Double? {
    val s = raw.trim()
    val normalized = if (s.contains(",")) s.replace(".", "").replace(",", ".") else s
    return normalized.toDoubleOrNull()
  }

  private fun collectTexts(node: AccessibilityNodeInfo?, out: MutableList<String>, depth: Int) {
    if (node == null || depth > 40) return
    node.text?.toString()?.takeIf { it.isNotBlank() }?.let { out.add(it) }
    node.contentDescription?.toString()?.takeIf { it.isNotBlank() }?.let { out.add(it) }
    for (i in 0 until node.childCount) collectTexts(node.getChild(i), out, depth + 1)
  }

  private fun findLabeledNode(node: AccessibilityNodeInfo?, labels: List<String>): AccessibilityNodeInfo? {
    if (node == null) return null
    val text = (node.text ?: node.contentDescription)?.toString()?.trim()
    if (text != null && labels.any { text.equals(it, ignoreCase = true) || text.startsWith(it, ignoreCase = true) }) {
      return node
    }
    for (i in 0 until node.childCount) {
      val found = findLabeledNode(node.getChild(i), labels)
      if (found != null) return found
    }
    return null
  }

  private fun clickNode(node: AccessibilityNodeInfo) {
    var current: AccessibilityNodeInfo? = node
    while (current != null && !current.isClickable) current = current.parent
    (current ?: node).performAction(AccessibilityNodeInfo.ACTION_CLICK)
  }
}
