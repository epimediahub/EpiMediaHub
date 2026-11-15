package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.Screen
import de.epimediahub.app.data.V128ParentalControl
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
internal fun V129SmartTubeGate(vm: MainViewModel, accent: Color, isTv: Boolean, onBack: () -> Unit) {
    val context = LocalContext.current
    V130SmartTubeGateContent(accent, isTv, onBack,
        onEnterKids = { vm.navigate(Screen.Home, remember = false) },
        onPinVerified = vm::refreshParentalSettings,
        loadKids = { V108SmartTubeCore.kids(context) },
        prepare = { V108SmartTubeCore.warmPlayback(context) },
        normalContent = { back -> V112SmartTubeShell(vm, accent, isTv, onBack = back) })
}

/** Kids remains usable without a PIN; only an existing parental PIN protects its exit. */
@Composable
internal fun V130SmartTubeGateContent(accent: Color, isTv: Boolean, onBack: () -> Unit,
    onEnterKids: () -> Unit, onPinVerified: () -> Unit,
    loadKids: suspend () -> Result<List<V100SmartTubeRow>>,
    prepare: suspend () -> Unit,
    normalContent: @Composable (() -> Unit) -> Unit
) {
    val context = LocalContext.current
    val store = remember(context) { V129KidsStore(context) }
    val parental = remember(context) { V128ParentalControl(context) }
    val scope = rememberCoroutineScope()
    val kidsActive = v129RememberKidsActive()
    var normal by remember { mutableStateOf(false) }
    var pinRequested by remember { mutableStateOf(false) }
    var pinError by remember { mutableStateOf("") }
    var pinBusy by remember { mutableStateOf(false) }

    fun leaveKids() { store.leave(); normal = false; pinRequested = false }
    fun requestExit() {
        if (!parental.settings().hasPin) leaveKids()
        else { pinError = ""; pinRequested = true }
    }

    when {
        kidsActive -> V129KidsScreen(isTv, onParents = ::requestExit,
            load = loadKids, exitRequiresPin = parental.settings().hasPin)
        normal -> normalContent { normal = false }
        else -> {
            BackHandler(onBack = onBack)
            V129ModeChooser(isTv, onNormal = { normal = true }, onKids = {
                onEnterKids(); store.enter()
            }, onBack = onBack)
        }
    }
    LaunchedEffect(Unit) { prepare() }

    if (pinRequested) V128PinDialog("Elternbereich entsperren", accent, pinBusy, pinError,
        onCancel = { pinRequested = false; pinError = "" }, onSubmit = { pin ->
            pinBusy = true
            scope.launch {
                try {
                    val failure = withContext(Dispatchers.IO) {
                        // The setting may have changed while this dialog was open.
                        if (!parental.settings().hasPin) null
                        else parental.verify(pin).let { if (it.accepted) null else it.message }
                    }
                    if (failure == null) { onPinVerified(); leaveKids() }
                    else pinError = failure
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { pinError = "PIN konnte nicht geprüft werden. Bitte erneut versuchen." }
                finally { pinBusy = false }
            }
        })
}
