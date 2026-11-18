package expo.modules.ridefilter

import android.content.Context
import android.content.Intent
import android.provider.Settings
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class RideFilterModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw IllegalStateException("React context not available")

  override fun definition() = ModuleDefinition {
    Name("RideFilter")

    Function("setConfig") { json: String ->
      RideFilterStore.prefs(context).edit().putString(RideFilterStore.KEY_CONFIG, RideFilterStore.applyManual(context, json)).commit()
      RideAccessibilityService.instance?.applyPackageFilter()
    }

    // Floating button choice not yet saved on the server: "on", "off" or "".
    Function("getManualToggle") {
      when (RideFilterStore.manual(context)) { true -> "on"; false -> "off"; null -> "" }
    }

    Function("clearManualToggle") {
      RideFilterStore.clearManual(context)
    }

    Function("isServiceEnabled") {
      val enabled = Settings.Secure.getString(
        context.contentResolver,
        Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
      ) ?: ""
      enabled.contains(context.packageName + "/") && enabled.contains("RideAccessibilityService")
    }

    Function("openAccessibilitySettings") {
      val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      context.startActivity(intent)
    }

    Function("getPendingEvents") {
      RideFilterStore.prefs(context).getString(RideFilterStore.KEY_EVENTS, "[]") ?: "[]"
    }

    Function("setLearning") { on: Boolean ->
      RideFilterStore.setLearning(context, on)
    }

    Function("getCapturedScreens") {
      RideFilterStore.capturedScreens(context)
    }

    Function("getDiagnostics") {
      RideFilterStore.diag(context)
    }

    Function("getBusy") {
      RideFilterStore.busy(context)?.toString() ?: ""
    }

    Function("clearBusy") {
      RideFilterStore.clearBusy(context)
      RideAccessibilityService.instance?.refreshBubble()
    }

    Function("clearPendingEvents") {
      RideFilterStore.prefs(context).edit().putString(RideFilterStore.KEY_EVENTS, "[]").apply()
    }
  }
}
