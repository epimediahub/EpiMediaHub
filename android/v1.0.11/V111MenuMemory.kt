package de.epimediahub.app.ui

import android.app.UiModeManager
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.grid.LazyGridState
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.distinctUntilChanged
import java.util.concurrent.ConcurrentHashMap

/**
 * Session-wide menu memory. Every screen may store the currently focused item
 * and first visible list/grid index here. Because this object is not tied to a
 * single composable, Back navigation restores the previous place instead of
 * jumping to the first item.
 */
internal object V111MenuMemory {
    private val indices = ConcurrentHashMap<String, Int>()
    private val ids = ConcurrentHashMap<String, String>()
    private val texts = ConcurrentHashMap<String, String>()

    fun remember(key: String, index: Int, id: String = "") {
        indices[key] = index.coerceAtLeast(0)
        if (id.isNotBlank()) ids[key] = id
    }

    fun index(key: String): Int = indices[key]?.coerceAtLeast(0) ?: 0
    fun id(key: String): String = ids[key].orEmpty()

    fun rememberText(key: String, value: String) {
        texts[key] = value
    }

    fun text(key: String): String = texts[key].orEmpty()
}

@Composable
internal fun v111RememberLazyListState(key: String): LazyListState {
    val state = rememberLazyListState(
        initialFirstVisibleItemIndex = V111MenuMemory.index(key)
    )
    LaunchedEffect(state, key) {
        snapshotFlow { state.firstVisibleItemIndex }
            .distinctUntilChanged()
            .collect { V111MenuMemory.remember(key, it) }
    }
    return state
}

@Composable
internal fun v111RememberLazyGridState(key: String): LazyGridState {
    val state = rememberLazyGridState(
        initialFirstVisibleItemIndex = V111MenuMemory.index(key)
    )
    LaunchedEffect(state, key) {
        snapshotFlow { state.firstVisibleItemIndex }
            .distinctUntilChanged()
            .collect { V111MenuMemory.remember(key, it) }
    }
    return state
}

/**
 * Attach to any focusable card/row. The last focused child of the menu is
 * requested again when that screen is composed after Back.
 */
@Composable
internal fun v111RememberFocus(
    menuKey: String,
    itemId: String,
    index: Int,
    enabled: Boolean = true,
    restoreDelayMs: Long = 110L
): Modifier {
    val requester = remember(menuKey, itemId) { FocusRequester() }
    val rememberedId = V111MenuMemory.id(menuKey)

    LaunchedEffect(enabled, rememberedId, itemId) {
        if (enabled && rememberedId.isNotBlank() && rememberedId == itemId) {
            delay(restoreDelayMs)
            runCatching { requester.requestFocus() }
        }
    }

    return Modifier
        .focusRequester(requester)
        .onFocusChanged {
            if (it.isFocused) V111MenuMemory.remember(menuKey, index, itemId)
        }
}


@Composable
internal fun v111IsTvDevice(): Boolean {
    val context = LocalContext.current
    return remember(context) {
        val uiMode = context.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
        val pm = context.packageManager
        uiMode?.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION ||
            pm.hasSystemFeature(PackageManager.FEATURE_LEANBACK) ||
            pm.hasSystemFeature(PackageManager.FEATURE_TELEVISION)
    }
}
