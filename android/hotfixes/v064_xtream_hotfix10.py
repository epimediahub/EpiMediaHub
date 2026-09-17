#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
build = root / "app/build.gradle.kts"
replace_once(build, 'versionCode = 612', 'versionCode = 613', 'hotfix10 versionCode')
replace_once(build, 'versionName = "0.6.4.9"', 'versionName = "0.6.4.10"', 'hotfix10 versionName')

home = java / "ui/V044Home.kt"
replace_once(home, "0.6.4.9", "0.6.4.10", "hotfix10 visible version")


# ---------------------------------------------------------------------------
# Shared top bar: remove the visual Back control everywhere. Physical/system
# Back remains wired through each screen's BackHandler, on TV and mobile.
# Keep the onBack argument in the API so all existing call sites stay compatible.
# ---------------------------------------------------------------------------
common = java / "ui/Common.kt"
s = common.read_text()
old_back = '''            if(onBack!=null){
                TextButton(onClick=onBack,shape=RoundedCornerShape(12.dp),contentPadding=PaddingValues(horizontal=8.dp,vertical=5.dp)){
                    Text("‹ Zurück",color=Color.White,fontWeight=FontWeight.Bold,fontSize=14.sp)
                }
                Spacer(Modifier.width(4.dp))
            }
'''
if old_back not in s:
    raise SystemExit("EpiTopBar visual back control anchor missing")
s = s.replace(old_back, '''            // Back navigation is handled by the device/system Back action.
''', 1)
common.write_text(s)


# ---------------------------------------------------------------------------
# Mediathek: a TV TextField as the first focus target caused the IME to open
# immediately and trap D-pad navigation. On TV show a normal Search button and
# only create/focus the TextField inside an explicit search dialog. Mobile keeps
# the inline search field.
# ---------------------------------------------------------------------------
parity = java / "ui/ParityScreens.kt"
s = parity.read_text()

focus_import = 'import androidx.compose.ui.focus.onFocusChanged\n'
if focus_import not in s:
    raise SystemExit("ParityScreens focus import anchor missing")
if 'import androidx.compose.ui.focus.FocusRequester\n' not in s:
    s = s.replace(
        focus_import,
        'import androidx.compose.ui.focus.FocusRequester\nimport androidx.compose.ui.focus.focusRequester\n' + focus_import,
        1,
    )

state_anchor = '''    var reload by remember { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(false) }
'''
state_new = '''    var reload by remember { mutableIntStateOf(0) }
    var searchDialog by remember(providerId) { mutableStateOf(false) }
    val searchFocusRequester = remember(providerId) { FocusRequester() }
    var loading by remember { mutableStateOf(false) }
'''
if state_anchor not in s:
    raise SystemExit("Mediathek search state anchor missing")
s = s.replace(state_anchor, state_new, 1)

column_anchor = '''    Column(Modifier.fillMaxSize()) {
        EpiTopBar(provider?.label ?: "MEDIATHEK", R.drawable.brand_header, { vm.back() }, actions = {
'''
dialog_block = '''    if (isTv && searchDialog) {
        AlertDialog(
            onDismissRequest = { searchDialog = false },
            title = { Text("Mediathek durchsuchen") },
            text = {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text("Suchbegriff") },
                    leadingIcon = { Icon(Icons.Default.Search, null) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().focusRequester(searchFocusRequester)
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        submitted = query.trim()
                        reload++
                        searchDialog = false
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = accent)
                ) { Text("Suchen") }
            },
            dismissButton = {
                TextButton(onClick = { searchDialog = false }) { Text("Abbrechen") }
            }
        )
        LaunchedEffect(searchDialog) {
            if (searchDialog) {
                kotlinx.coroutines.delay(120)
                runCatching { searchFocusRequester.requestFocus() }
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(provider?.label ?: "MEDIATHEK", R.drawable.brand_header, { vm.back() }, actions = {
'''
if column_anchor not in s:
    raise SystemExit("Mediathek dialog insertion anchor missing")
s = s.replace(column_anchor, dialog_block, 1)

old_search = '''            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text("Mediathek durchsuchen") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            Button(onClick = { submitted = query.trim(); reload++ }, colors = ButtonDefaults.buttonColors(containerColor = accent)) { Text("Suchen") }
            OutlinedButton(onClick = { reload++ }) { Text("Neu laden") }
'''
new_search = '''            if (isTv) {
                OutlinedButton(onClick = { searchDialog = true }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Search, null)
                    Spacer(Modifier.width(8.dp))
                    Text("Mediathek durchsuchen")
                }
            } else {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text("Mediathek durchsuchen") },
                    leadingIcon = { Icon(Icons.Default.Search, null) },
                    singleLine = true,
                    modifier = Modifier.weight(1f)
                )
                Button(onClick = { submitted = query.trim(); reload++ }, colors = ButtonDefaults.buttonColors(containerColor = accent)) { Text("Suchen") }
            }
            OutlinedButton(onClick = { reload++ }) { Text("Neu laden") }
'''
if old_search not in s:
    raise SystemExit("Mediathek inline search anchor missing")
s = s.replace(old_search, new_search, 1)
parity.write_text(s)


# ---------------------------------------------------------------------------
# Netflix-style movie/series hub: remove the 12-row ceiling. Build a category
# index once, then create rows for all provider categories without repeatedly
# scanning the full VOD catalog for every category.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
old_rows = '''                    val all = xtreamLibrary(profile, kind)
                    categories.take(12).mapNotNull { category ->
                        val row = if (category.id == "__all__") {
                            all.take(24)
                        } else {
                            all.asSequence().filter { entry -> entry.categoryId == category.id }.take(24).toList()
                        }
                        if (row.isEmpty()) null else category.id to row
                    }.toMap()
'''
new_rows = '''                    val all = xtreamLibrary(profile, kind)
                    val byCategory = all.groupBy { entry -> entry.categoryId }
                    categories.mapNotNull { category ->
                        val row = if (category.id == "__all__") {
                            all.take(24)
                        } else {
                            byCategory[category.id].orEmpty().take(24)
                        }
                        if (row.isEmpty()) null else category.id to row
                    }.toMap()
'''
if old_rows not in s:
    raise SystemExit("catalog 12-row data cap anchor missing")
s = s.replace(old_rows, new_rows, 1)
vm.write_text(s)

hub = java / "ui/V060CinematicHub.kt"
s = hub.read_text()
old_ui_cap = '            items(u.categories.take(12), key = { "category:${it.id}" }) { category ->\n'
new_ui_cap = '            items(u.categories, key = { "category:${it.id}" }) { category ->\n'
if old_ui_cap not in s:
    raise SystemExit("cinematic 12-row UI cap anchor missing")
s = s.replace(old_ui_cap, new_ui_cap, 1)
hub.write_text(s)


checks = [
    (build, 'versionName = "0.6.4.10"'),
    (build, 'versionCode = 613'),
    (common, '// Back navigation is handled by the device/system Back action.'),
    (parity, 'var searchDialog by remember(providerId) { mutableStateOf(false) }'),
    (parity, 'OutlinedButton(onClick = { searchDialog = true }, modifier = Modifier.weight(1f))'),
    (parity, 'modifier = Modifier.fillMaxWidth().focusRequester(searchFocusRequester)'),
    (vm, 'val byCategory = all.groupBy { entry -> entry.categoryId }'),
    (vm, 'categories.mapNotNull { category ->'),
    (hub, 'items(u.categories, key = { "category:${it.id}" })'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix10 marker {marker} in {path}")

if 'items(u.categories.take(12)' in hub.read_text():
    raise SystemExit("cinematic UI still has 12-category cap")

print("Android v0.6.4.10 top-bar cleanup, TV Mediathek search focus and unlimited cinematic category rows applied")
