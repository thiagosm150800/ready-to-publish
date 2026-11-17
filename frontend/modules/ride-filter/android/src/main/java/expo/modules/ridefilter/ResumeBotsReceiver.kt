package expo.modules.ridefilter

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.widget.Toast

/** "Voltar online" button on the ride-accepted notification: both bots online, without opening the app. */
class ResumeBotsReceiver : BroadcastReceiver() {
  companion object {
    const val ACTION = "expo.modules.ridefilter.RESUME_BOTS"
    const val EXTRA_ID = "notification_id"
  }

  override fun onReceive(context: Context, intent: Intent) {
    if (intent.action != ACTION) return
    RideFilterStore.clearBusy(context)
    val id = intent.getIntExtra(EXTRA_ID, -1)
    if (id >= 0) {
      try {
        (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).cancel(id)
      } catch (e: Exception) { /* ignored */ }
    }
    Toast.makeText(context, "Todos os robôs estão online", Toast.LENGTH_SHORT).show()
  }
}
