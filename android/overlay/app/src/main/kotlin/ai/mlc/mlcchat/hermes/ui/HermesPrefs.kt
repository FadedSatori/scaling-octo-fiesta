package ai.mlc.mlcchat.hermes.ui

import android.content.Context
import android.content.SharedPreferences

/**
 * Tiny SharedPreferences wrapper. DataStore would be nicer but adds a
 * dependency for a single boolean.
 */
class HermesPrefs(ctx: Context) {
    private val sp: SharedPreferences =
        ctx.getSharedPreferences("hermes-prefs", Context.MODE_PRIVATE)

    var wizardComplete: Boolean
        get() = sp.getBoolean(KEY_WIZARD, false)
        set(value) { sp.edit().putBoolean(KEY_WIZARD, value).apply() }

    companion object { private const val KEY_WIZARD = "wizard_complete" }
}
