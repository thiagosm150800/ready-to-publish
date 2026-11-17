package expo.modules.ridefilter

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Path
import android.graphics.Rect
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
    const val NOTIFY_CHANNEL = "rides_accepted"
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
    val pkg = event.packageName?.toString()
    if (pkg == packageName) return
    val cfg = RideFilterStore.config(this) ?: return
    val apps = cfg.optJSONObject("apps") ?: return
    // Pop-up offers (e.g. MooveCar "modo padrão") open in their own overlay window; window-change
    // events may arrive without a package, so then every configured app is checked.
    val keys = when {
      pkg != null -> listOfNotNull(matchApp(pkg.lowercase(), apps))
      event.eventType == AccessibilityEvent.TYPE_WINDOWS_CHANGED -> APP_KEYS
      else -> emptyList()
    }
    for (key in keys) {
      val appCfg = apps.optJSONObject(key) ?: continue
      val target = appCfg.optString("target_package", "").trim().lowercase()
      val roots = targetRoots(target)
      if (roots.isEmpty()) continue

      if (RideFilterStore.isLearning(this)) captureScreen(key, roots)

      if (!appCfg.optBoolean("enabled", false)) continue
      if (!inSchedule(cfg)) continue
      for (root in roots) if (acceptIfMatches(root, key, appCfg, cfg)) break
    }
  }

  /** Every window of the target app: the pop-up overlay is often NOT the active window. */
  private fun targetRoots(target: String): List<AccessibilityNodeInfo> {
    if (target.isEmpty()) return emptyList()
    val out = mutableListOf<AccessibilityNodeInfo>()
    fun matches(r: AccessibilityNodeInfo) = r.packageName?.toString()?.lowercase()?.contains(target) == true
    try {
      windows?.forEach { w -> w.root?.let { if (matches(it)) out.add(it) } }
    } catch (e: Exception) { /* ignored */ }
    rootInActiveWindow?.let { r -> if (matches(r) && out.none { it == r }) out.add(r) }
    return out
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

  /** Returns true when an offer with an accept button was found in this window. */
  private fun acceptIfMatches(root: AccessibilityNodeInfo, key: String, appCfg: JSONObject, cfg: JSONObject): Boolean {
    // Cheapest check first: is there an accept button on screen at all?
    val labels = readList(appCfg.optJSONArray("accept_texts"), listOf("Aceitar", "Accept"))
    val button = findLabeledNode(root, labels) ?: return false

    // Read price/km only from the offer card around the button, so prices of the screen
    // behind the pop-up (e.g. "Premium R$ 15,00") are ignored.
    val (priceText, kmText) = offerText(button, root)
    val price = priceRe.find(priceText)?.groupValues?.get(1)?.let { parseNumber(it) } ?: return false
    val kms = kmRe.findAll(kmText).mapNotNull { parseNumber(it.groupValues[1]) }.toList()
    if (kms.isEmpty()) return false
    val pickupKm = if (kms.size >= 2) kms[0] else 0.0
    val tripKm = if (kms.size >= 2) kms[1] else kms[0]
    if (tripKm <= 0.0) return false

    val signature = "$price|$tripKm|$pickupKm"
    val now = System.currentTimeMillis()
    if (signature == lastSignature[key] && now - (lastTime[key] ?: 0L) < 20000) return true
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
      retryIfStillShown(appCfg.optString("target_package", "").trim().lowercase(), labels, price)
      if (cfg.optBoolean("alert_enabled", true)) playAlert()
      if (cfg.optBoolean("notify_enabled", true)) notifyAccepted(key, price, tripKm, pickupKm, ppk)
    } else if (appCfg.optBoolean("reject_enabled", false)) {
      // Auto-reject: tap the reject button right away instead of waiting for the timer.
      val rejectLabels = readList(appCfg.optJSONArray("reject_texts"), listOf("Recusar"))
      findLabeledNode(root, rejectLabels)?.let {
        clickNode(it)
        retryIfStillShown(appCfg.optString("target_package", "").trim().lowercase(), rejectLabels, price)
      }
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
    return true
  }

  /**
   * Text of the offer card around the button: (text used for the price, text used for the km).
   * The price comes from the smallest card that shows one, so prices of the screen behind the
   * pop-up are never used; the km may come from a slightly larger card when needed.
   */
  private fun offerText(button: AccessibilityNodeInfo, root: AccessibilityNodeInfo): Pair<String, String> {
    var priceText: String? = null
    var priceCount = 0
    var kmFallback: String? = null
    var scope: AccessibilityNodeInfo? = button.parent
    while (scope != null) {
      val texts = mutableListOf<String>()
      collectTexts(scope, texts, 0)
      val all = texts.joinToString(" | ")
      if (priceText == null && priceRe.containsMatchIn(all)) {
        priceText = all
        priceCount = priceRe.findAll(all).count()
      }
      if (priceText != null) {
        // A larger area with more prices is the screen behind the pop-up: stop, use the card only.
        if (priceRe.findAll(all).count() > priceCount) break
        val kmCount = kmRe.findAll(all).count()
        if (kmCount >= 2) return Pair(priceText, all)
        if (kmCount >= 1 && kmFallback == null) kmFallback = all
      }
      scope = scope.parent
    }
    if (priceText != null) return Pair(priceText, kmFallback ?: priceText)
    val texts = mutableListOf<String>()
    collectTexts(root, texts, 0)
    val whole = texts.joinToString(" | ")
    return Pair(priceText ?: whole, kmFallback ?: whole)
  }

  /** Some pop-ups ignore the accessibility click: if the SAME offer is still there, tap it on screen. */
  private fun retryIfStillShown(target: String, labels: List<String>, price: Double) {
    handler.postDelayed({
      for (r in targetRoots(target)) {
        val still = findLabeledNode(r, labels) ?: continue
        val samePrice = priceRe.find(offerText(still, r).first)?.groupValues?.get(1)?.let { parseNumber(it) }
        if (samePrice == price) tap(still)
        break
      }
    }, 700)
  }

  // ---------------- learning mode ----------------

  private fun captureScreen(key: String, roots: List<AccessibilityNodeInfo>) {
    val now = System.currentTimeMillis()
    if (now - (lastCapture[key] ?: 0L) < 1500) return
    val pkg = roots.first().packageName?.toString() ?: return
    lastCapture[key] = now
    val texts = mutableListOf<String>()
    for (root in roots) collectTexts(root, texts, 0)
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

  /** Phone notification: "Corrida aceita · MooveCar" + price and km. Silent (the beep is separate). */
  private fun notifyAccepted(key: String, price: Double, tripKm: Double, pickupKm: Double, ppk: Double) {
    try {
      val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        val ch = NotificationChannel(NOTIFY_CHANNEL, "Corridas aceitas", NotificationManager.IMPORTANCE_HIGH)
        ch.setSound(null, null)
        nm.createNotificationChannel(ch)
      }
      val br = Locale("pt", "BR")
      val label = if (key == "moove") "MooveCar" else "RapidoCar"
      val text = String.format(br, "R$ %.2f · %.2f km · busca %.2f km · R$ %.2f/km", price, tripKm, pickupKm, ppk)
      @Suppress("DEPRECATION")
      val b = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, NOTIFY_CHANNEL) else Notification.Builder(this)
      b.setSmallIcon(android.R.drawable.ic_dialog_info)
        .setContentTitle("Corrida aceita · $label")
        .setContentText(text)
        .setAutoCancel(true)
      packageManager.getLaunchIntentForPackage(packageName)?.let {
        b.setContentIntent(PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
      }
      nm.notify((System.currentTimeMillis() % 1000000).toInt(), b.build())
    } catch (e: Exception) { /* no permission or blocked: ignore */ }
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
    val ok = current?.performAction(AccessibilityNodeInfo.ACTION_CLICK) ?: false
    if (!ok) tap(node)
  }

  /** Real screen tap at the center of the node (works on overlays that ignore ACTION_CLICK). */
  private fun tap(node: AccessibilityNodeInfo): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false
    val r = Rect()
    node.getBoundsInScreen(r)
    if (r.isEmpty) return false
    val x = maxOf(0f, r.exactCenterX())
    val y = maxOf(0f, r.exactCenterY())
    return try {
      val path = Path().apply { moveTo(x, y) }
      val gesture = GestureDescription.Builder()
        .addStroke(GestureDescription.StrokeDescription(path, 0, 60))
        .build()
      dispatchGesture(gesture, null, null)
    } catch (e: Exception) {
      false
    }
  }
}
