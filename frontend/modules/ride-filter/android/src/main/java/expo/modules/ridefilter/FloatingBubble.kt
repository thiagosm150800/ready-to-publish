package expo.modules.ridefilter

import android.accessibilityservice.AccessibilityService
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.abs

/**
 * Round floating button with the app logo, drawn over every app by the accessibility service
 * (no extra "draw over apps" permission). Tap: menu with "Ficar online" / "Ficar offline". Drag: move it.
 */
class FloatingBubble(private val svc: AccessibilityService, private val onChoose: (Boolean) -> Unit) {
  private val wm = svc.getSystemService(Context.WINDOW_SERVICE) as WindowManager
  private val dp = svc.resources.displayMetrics.density
  private val prefs = svc.getSharedPreferences("ride_filter_bubble", Context.MODE_PRIVATE)
  private var bubble: FrameLayout? = null
  private var ring: GradientDrawable? = null
  private var params: WindowManager.LayoutParams? = null
  private var menu: View? = null
  private var menuClosedAt = 0L

  /** Let a tap go through the button (the bot's own screen tap may land under it). */
  fun passThrough(ms: Long) {
    val b = bubble ?: return
    val p = params ?: return
    p.flags = p.flags or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
    try { wm.updateViewLayout(b, p) } catch (e: Exception) { /* ignored */ }
    b.postDelayed({
      p.flags = p.flags and WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE.inv()
      if (bubble === b) try { wm.updateViewLayout(b, p) } catch (e: Exception) { /* ignored */ }
    }, ms)
  }

  /** Keep the button fully on screen (it can't be dragged away and lost). */
  private fun clamp(p: WindowManager.LayoutParams) {
    val m = svc.resources.displayMetrics
    p.x = p.x.coerceIn(0, maxOf(0, m.widthPixels - px(SIZE_DP)))
    p.y = p.y.coerceIn(0, maxOf(0, m.heightPixels - px(SIZE_DP)))
  }

  private fun px(v: Int) = (v * dp).toInt()

  fun show(online: Boolean) {
    if (bubble == null) create()
    ring?.setStroke(px(4), if (online) GREEN else GREY)
  }

  fun hide() {
    closeMenu()
    bubble?.let { try { wm.removeView(it) } catch (e: Exception) { /* ignored */ } }
    bubble = null
  }

  private fun overlayParams(w: Int, h: Int, flags: Int) = WindowManager.LayoutParams(
    w, h, WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY, flags, PixelFormat.TRANSLUCENT,
  ).apply { gravity = Gravity.TOP or Gravity.START }

  @SuppressLint("ClickableViewAccessibility")
  private fun create() {
    val size = px(SIZE_DP)
    val bg = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(Color.WHITE) }
    ring = bg
    val icon = ImageView(svc).apply {
      setImageDrawable(try { svc.packageManager.getApplicationIcon(svc.packageName) } catch (e: Exception) { null })
      scaleType = ImageView.ScaleType.FIT_CENTER
    }
    val root = FrameLayout(svc).apply {
      background = bg
      elevation = px(6).toFloat()
      contentDescription = "RapidoChecker: ficar online ou offline"
      val pad = px(7)
      setPadding(pad, pad, pad, pad)
      addView(icon, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
    }
    val p = overlayParams(size, size, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS).apply {
      x = prefs.getInt("x", 0)
      y = prefs.getInt("y", px(220))
    }
    clamp(p)
    var downX = 0f; var downY = 0f; var startX = 0; var startY = 0; var moved = false
    root.setOnTouchListener { _, e ->
      when (e.action) {
        MotionEvent.ACTION_DOWN -> { downX = e.rawX; downY = e.rawY; startX = p.x; startY = p.y; moved = false }
        MotionEvent.ACTION_MOVE -> {
          val dx = e.rawX - downX; val dy = e.rawY - downY
          if (abs(dx) > px(8) || abs(dy) > px(8)) moved = true
          if (moved) {
            closeMenu()
            p.x = (startX + dx).toInt(); p.y = (startY + dy).toInt()
            clamp(p)
            try { wm.updateViewLayout(root, p) } catch (ex: Exception) { /* ignored */ }
          }
        }
        MotionEvent.ACTION_UP -> {
          if (moved) prefs.edit().putInt("x", p.x).putInt("y", p.y).apply()
          // A tap on the button while the menu is open first closes it as an "outside" tap: don't reopen.
          else if (menu != null) closeMenu()
          else if (System.currentTimeMillis() - menuClosedAt > 300) openMenu()
        }
      }
      true
    }
    try {
      wm.addView(root, p)
      bubble = root
      params = p
    } catch (e: Exception) { /* service not ready: tried again on next config change */ }
  }

  @SuppressLint("ClickableViewAccessibility")
  private fun openMenu() {
    val bp = params ?: return
    fun option(label: String, color: Int, online: Boolean) = TextView(svc).apply {
      text = label
      setTextColor(Color.WHITE)
      textSize = 16f
      gravity = Gravity.CENTER
      minHeight = px(48)
      setPadding(px(20), px(10), px(20), px(10))
      background = GradientDrawable().apply { cornerRadius = px(12).toFloat(); setColor(color) }
      contentDescription = label
      setOnClickListener { closeMenu(); onChoose(online) }
    }
    val box = LinearLayout(svc).apply {
      orientation = LinearLayout.VERTICAL
      setPadding(px(10), px(10), px(10), px(10))
      background = GradientDrawable().apply { cornerRadius = px(16).toFloat(); setColor(Color.parseColor("#EE111827")) }
      elevation = px(8).toFloat()
      addView(option("Ficar online", GREEN, true))
      addView(View(svc), LinearLayout.LayoutParams(1, px(8)))
      addView(option("Ficar offline", RED, false))
      // Tap anywhere else closes the menu.
      setOnTouchListener { _, e -> if (e.action == MotionEvent.ACTION_OUTSIDE) closeMenu(); false }
    }
    val screenW = svc.resources.displayMetrics.widthPixels
    val mp = overlayParams(
      WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
      WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
    ).apply {
      // Open on the side of the screen with more room.
      x = if (bp.x + px(SIZE_DP) / 2 < screenW / 2) bp.x + px(SIZE_DP + 8) else maxOf(0, bp.x - px(180))
      y = bp.y
    }
    try {
      wm.addView(box, mp)
      menu = box
    } catch (e: Exception) { /* ignored */ }
  }

  private fun closeMenu() {
    menu?.let {
      try { wm.removeView(it) } catch (e: Exception) { /* ignored */ }
      menuClosedAt = System.currentTimeMillis()
    }
    menu = null
  }

  companion object {
    const val SIZE_DP = 58
    val GREEN = Color.parseColor("#16A34A")
    val RED = Color.parseColor("#DC2626")
    val GREY = Color.parseColor("#9CA3AF")
  }
}
