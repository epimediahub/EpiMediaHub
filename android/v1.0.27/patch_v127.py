#!/usr/bin/env python3
"""One-OK recap skip, draw-phase category effects and a stronger original logo heartbeat."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent


def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f'{path}: expected exactly one anchor: {old[:100]}'
    path.write_text(text.replace(old, new, 1))


gradle = root / 'app/build.gradle.kts'
replace_once(gradle, 'versionCode = 1026', 'versionCode = 1027')
replace_once(gradle, 'versionName = "1.0.26"', 'versionName = "1.0.27"')
for path in java.rglob('*.kt'):
    text = path.read_text()
    if '1.0.26' in text:
        path.write_text(text.replace('1.0.26', '1.0.27'))

chrome = java / 'ui/V115PlayerChrome.kt'
replace_once(chrome,
    '    val intro = active.firstOrNull { it.kind == V115SegmentKind.INTRO }',
    '''    // Recap wins when trusted windows overlap; focus one visible skip action per interval.
    val focusSegment = active.firstOrNull { it.kind == V115SegmentKind.RECAP }
        ?: active.firstOrNull { it.kind == V115SegmentKind.INTRO }''')
text = chrome.read_text()
for old, new in [('introFocus', 'segmentFocus'), ('focusedIntro', 'focusedSegment'),
                 ('introKey', 'segmentKey'), ('intro?.let', 'focusSegment?.let'),
                 ('intro != null', 'focusSegment != null'), ('restore == "intro"', 'restore == "segment"'),
                 ('restore = "intro"', 'restore = "segment"')]:
    text = text.replace(old, new)
text = text.replace('"${it.startMs}:${it.endMs}"', '"${it.kind}:${it.startMs}:${it.endMs}"')
assert text.count('if (segment.kind == V115SegmentKind.INTRO) Modifier.focusRequester(segmentFocus)') == 1
text = text.replace('if (segment.kind == V115SegmentKind.INTRO) Modifier.focusRequester(segmentFocus)',
                    'if (segment == focusSegment) Modifier.focusRequester(segmentFocus)')
chrome.write_text(text)

hub = java / 'ui/V060CinematicHub.kt'
replace_once(hub,
    '''    val recent = u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }
    val continueItems = u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }
    val newest = u.catalogRows["__recently_added__"].orEmpty()
        .filter { it.categoryId !in u.hiddenCategoryIds }
        .sortedByDescending { it.addedAt }
    val visibleCategories = u.categories.filter {
        it.id != "__recently_added__" &&
            it.id !in u.hiddenCategoryIds &&
            u.catalogRows[it.id].orEmpty().isNotEmpty()
    }
    val firstCatalog = visibleCategories.asSequence().mapNotNull { u.catalogRows[it.id]?.firstOrNull() }.firstOrNull()''',
    '''    val recent = remember(kind, u.recentlyWatched) {
        u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }
    }
    val continueItems = remember(kind, u.continueWatching) {
        u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }
    }
    val newest = remember(u.catalogRows, u.hiddenCategoryIds) {
        u.catalogRows["__recently_added__"].orEmpty()
            .filter { it.categoryId !in u.hiddenCategoryIds }
            .sortedByDescending { it.addedAt }
    }
    val visibleCategories = remember(u.categories, u.hiddenCategoryIds, u.catalogRows) {
        u.categories.filter {
            it.id != "__recently_added__" && it.id !in u.hiddenCategoryIds && u.catalogRows[it.id].orEmpty().isNotEmpty()
        }
    }
    val firstCatalog = remember(visibleCategories, u.catalogRows) {
        visibleCategories.asSequence().mapNotNull { u.catalogRows[it.id]?.firstOrNull() }.firstOrNull()
    }''')
replace_once(hub, '    val scope = rememberCoroutineScope()',
    '''    val scope = rememberCoroutineScope()
    var categoryScrollJob by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }
    fun scrollToCategory(index: Int) {
        categoryScrollJob?.cancel()
        categoryScrollJob = scope.launch {
            // Long jumps should not decode dozens of intermediate poster rows.
            if (kotlin.math.abs(contentState.firstVisibleItemIndex - index) > 4) contentState.scrollToItem(index)
            else contentState.animateScrollToItem(index)
        }
    }''')
replace_once(hub, 'scope.launch { contentState.animateScrollToItem(0) }', 'scrollToCategory(0)')
replace_once(hub, 'scope.launch { contentState.animateScrollToItem(categoryStartIndex + index) }',
    'scrollToCategory(categoryStartIndex + index)')
replace_once(hub, 'items(visibleCategories, key = { "category:" + it.id })',
    'items(visibleCategories, key = { "category:" + it.id }, contentType = { "category-posters" })')
replace_once(hub, 'itemsIndexed(categories, key = { _, category -> "rail:" + category.id })',
    'itemsIndexed(categories, key = { _, category -> "rail:" + category.id }, contentType = { _, _ -> "category" })')
text = hub.read_text()
start = text.index('@Composable\ninternal fun V071CategoryRailItem(')
end = text.index('@Composable\nprivate fun V060Hero(', start)
text = text[:start] + text[end:]
hub.write_text(text)

# One animation state, sampled exclusively in the graphics/draw phases, replaces four.
replace_once(hub, 'import androidx.compose.ui.draw.clip',
    'import androidx.compose.ui.draw.drawWithContent\nimport androidx.compose.ui.draw.clip')
replace_once(hub, 'private fun V060Poster(item:', 'internal fun V060Poster(item:')
replace_once(hub,
    '''    val scale by animateFloatAsState(
        targetValue = if (focused) 1.035f else 1f,
        animationSpec = tween(155, easing = FastOutSlowInEasing),
        label = "posterScale"
    )
    val shadow by animateDpAsState(
        targetValue = if (focused) 14.dp else 2.dp,
        animationSpec = tween(155, easing = FastOutSlowInEasing),
        label = "posterShadow"
    )
    val borderWidth by animateDpAsState(
        targetValue = if (focused) 2.dp else 1.dp,
        animationSpec = tween(135, easing = FastOutSlowInEasing),
        label = "posterBorderWidth"
    )
    val borderColor by animateColorAsState(
        targetValue = if (focused) Color.White.copy(.96f) else Color.White.copy(.10f),
        animationSpec = tween(135, easing = FastOutSlowInEasing),
        label = "posterBorderColor"
    )''',
    '''    val focusProgress = animateFloatAsState(
        targetValue = if (focused) 1f else 0f,
        animationSpec = tween(120, easing = FastOutSlowInEasing), label = "posterFocus"
    )''')
replace_once(hub,
    '''            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(shadow, shape)''',
    '''            .testTag("poster-${item.resumeKey}")
            .graphicsLayer {
                val progress = focusProgress.value
                scaleX = 1f + .025f * progress; scaleY = scaleX
                shadowElevation = (2f + 6f * progress).dp.toPx()
                this.shape = shape
            }''')
replace_once(hub, '            .border(borderWidth, borderColor, shape)',
    '''            .drawWithContent {
                drawContent()
                val progress = focusProgress.value
                val line = (1f + progress).dp.toPx()
                drawRoundRect(Color.White.copy(alpha = .10f + .86f * progress),
                    topLeft = androidx.compose.ui.geometry.Offset(line / 2f, line / 2f),
                    size = androidx.compose.ui.geometry.Size(size.width - line, size.height - line),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(14.dp.toPx()),
                    style = androidx.compose.ui.graphics.drawscope.Stroke(line))
            }''')

live = java / 'ui/V076LiveTv.kt'
replace_once(live, 'itemsIndexed(categories, key = { _, it -> it.id }) { index, category ->',
    'itemsIndexed(categories, key = { _, it -> it.id }, contentType = { _, _ -> "category" }) { index, category ->')
text = live.read_text()
start = text.index('@Composable\nprivate fun V076CategoryRow(')
end = text.index('@Composable\ninternal fun V076ChannelPane(', start)
live.write_text(text[:start] + text[end:])

shutil.copyfile(here / 'V127CategoryRows.kt', java / 'ui/V127CategoryRows.kt')
tests = root / 'app/src/test/java/de/epimediahub/app/ui'
for source in here.glob('*Test.kt'):
    shutil.copyfile(source, tests / source.name)
print('Android 1.0.27: recap focus, stable category geometry and draw-phase poster effects installed')
