#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# --- Rich Mediathek cards + stronger text contrast ---
parity = java / "ui/ParityScreens.kt"
s = parity.read_text()

import_anchor = "import androidx.compose.ui.graphics.Color\n"
if s.count(import_anchor) != 1:
    raise SystemExit("ParityScreens import anchor mismatch")
s = s.replace(
    import_anchor,
    import_anchor
    + "import androidx.compose.ui.layout.ContentScale\n"
    + "import androidx.compose.ui.text.style.TextOverflow\n"
    + "coil.compose.AsyncImage\n"
    + "import java.text.SimpleDateFormat\n"
    + "import java.util.Date\n"
    + "import java.util.Locale\n",
    1,
)
# Fix accidental missing import prefix if source formatting changes.
s = s.replace("coil.compose.AsyncImage\n", "import coil.compose.AsyncImage\n")

s = s.replace(
    "var entries by remember { mutableStateOf<List<MediaEntry>>(emptyList()) }",
    "var entries by remember { mutableStateOf<List<MediathekClient.Item>>(emptyList()) }",
    1,
)
s = s.replace(
    'provider?.availability?.takeIf { it.isNotBlank() }?.let { Text(it, color = Color.White.copy(.55f), fontSize = 12.sp) }',
    'provider?.availability?.takeIf { it.isNotBlank() }?.let { Text(it, color = Color.White.copy(.90f), fontSize = 13.sp, fontWeight = FontWeight.SemiBold) }',
    1,
)
s = s.replace(
    'Text(error, color = Color.White.copy(.68f), modifier = Modifier.padding(top = 8.dp))',
    'Text(error, color = Color.White.copy(.92f), fontSize = 15.sp, modifier = Modifier.padding(top = 8.dp))',
    1,
)
s = s.replace(
    'provider?.info?.takeIf { it.isNotBlank() && it != error }?.let { Text(it, color = Color.White.copy(.52f), fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp)) }',
    'provider?.info?.takeIf { it.isNotBlank() && it != error }?.let { Text(it, color = Color.White.copy(.82f), fontSize = 14.sp, modifier = Modifier.padding(top = 10.dp)) }',
    1,
)
s = s.replace("columns = GridCells.Fixed(if (isTv) 5 else 2),", "columns = GridCells.Fixed(if (isTv) 4 else 2),", 1)
s = s.replace(
    "MediaCard(media, accent, media.plot) { vm.play(media) }",
    "V042MediathekCard(media, accent, isTv) { vm.play(media.media) }",
    1,
)

# Country/provider readability.
s = s.replace('Text(meta, color = accent.copy(.90f), fontSize = 12.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))',
              'Text(meta, color = accent, fontSize = 14.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 5.dp))')
s = s.replace('Text(info, color = Color.White.copy(.52f), fontSize = 11.sp, maxLines = 2, modifier = Modifier.padding(top = 4.dp))',
              'Text(info, color = Color.White.copy(.86f), fontSize = 13.sp, maxLines = 3, modifier = Modifier.padding(top = 6.dp))')
s = s.replace('Text(provider.label, fontWeight = FontWeight.Black, fontSize = 17.sp)',
              'Text(provider.label, color = Color.White, fontWeight = FontWeight.Black, fontSize = 19.sp)')
s = s.replace('Text(provider.availability, color = accent.copy(.85f), fontSize = 11.sp, fontWeight = FontWeight.Bold)',
              'Text(provider.availability, color = accent, fontSize = 13.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 2.dp))')
s = s.replace('Text(provider.info, color = Color.White.copy(.48f), fontSize = 11.sp, maxLines = 2)',
              'Text(provider.info, color = Color.White.copy(.84f), fontSize = 13.sp, maxLines = 3, modifier = Modifier.padding(top = 3.dp))')

# EPG was also too dim.
s = s.replace('color = Color.White.copy(.55f)', 'color = Color.White.copy(.82f)')
s = s.replace('color = Color.White.copy(.52f)', 'color = Color.White.copy(.82f)')
s = s.replace('color = Color.White.copy(.56f)', 'color = Color.White.copy(.84f)')
s = s.replace('color = Color.White.copy(.48f), fontSize = 11.sp', 'color = Color.White.copy(.82f), fontSize = 13.sp')
s = s.replace('color = Color.White.copy(.42f), fontSize = 10.sp', 'color = Color.White.copy(.74f), fontSize = 12.sp')

extra = r'''

@Composable
private fun V042MediathekCard(
    item: MediathekClient.Item,
    accent: Color,
    isTv: Boolean,
    onClick: () -> Unit
) {
    var focused by remember(item.id) { mutableStateOf(false) }
    var artwork by remember(item.id) { mutableStateOf(item.imageHint) }
    LaunchedEffect(item.id) {
        if (artwork.isBlank() && item.websiteUrl.isNotBlank()) {
            artwork = withContext(Dispatchers.IO) { MediathekClient.resolveArtwork(item) }
        }
    }

    val shape = RoundedCornerShape(20.dp)
    Column(
        Modifier
            .height(if (isTv) 344.dp else 318.dp)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .background(if (focused) accent.copy(.15f) else Color(0xF20A1420), shape)
            .border(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.14f), shape)
            .clickable(onClick = onClick)
    ) {
        Box(Modifier.fillMaxWidth().height(if (isTv) 170.dp else 145.dp)) {
            if (artwork.isNotBlank()) {
                AsyncImage(
                    model = artwork,
                    contentDescription = item.media.name,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop
                )
            } else {
                V042SenderArtwork(item.channel, item.topic, accent)
            }
            Box(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(.58f)))))
            Text(
                item.channel.uppercase(),
                color = Color.White,
                fontSize = 12.sp,
                fontWeight = FontWeight.Black,
                modifier = Modifier.align(Alignment.TopStart).padding(10.dp)
                    .background(Color.Black.copy(.72f), RoundedCornerShape(9.dp)).padding(horizontal = 9.dp, vertical = 5.dp)
            )
            Box(
                Modifier.align(Alignment.BottomEnd).padding(10.dp).size(34.dp)
                    .background(accent.copy(.92f), RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.PlayArrow, null, tint = Color.Black, modifier = Modifier.size(24.dp))
            }
        }

        Column(Modifier.fillMaxSize().padding(horizontal = 13.dp, vertical = 11.dp)) {
            if (item.topic.isNotBlank() && !item.media.name.contains(item.topic, ignoreCase = true)) {
                Text(
                    item.topic,
                    color = accent,
                    fontSize = if (isTv) 13.sp else 12.sp,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(Modifier.height(3.dp))
            }
            Text(
                item.media.name,
                color = Color.White,
                fontSize = if (isTv) 17.sp else 16.sp,
                fontWeight = FontWeight.Black,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
            Spacer(Modifier.height(5.dp))
            Text(
                v042Meta(item),
                color = Color.White.copy(.82f),
                fontSize = if (isTv) 12.sp else 11.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            if (item.description.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(
                    item.description,
                    color = Color.White.copy(.90f),
                    fontSize = if (isTv) 13.sp else 12.sp,
                    lineHeight = if (isTv) 17.sp else 16.sp,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }
}

@Composable
private fun V042SenderArtwork(channel: String, topic: String, accent: Color) {
    Box(
        Modifier.fillMaxSize().background(
            androidx.compose.ui.graphics.Brush.linearGradient(
                listOf(accent.copy(.50f), Color(0xFF13243A), Color(0xFF07111D))
            )
        ),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(12.dp)) {
            Text(channel.ifBlank { "MEDIATHEK" }.uppercase(), color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Black, maxLines = 1)
            if (topic.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(topic, color = Color.White.copy(.84f), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

private fun v042Meta(item: MediathekClient.Item): String {
    val parts = mutableListOf<String>()
    if (item.timestamp > 0L) {
        parts += SimpleDateFormat("dd.MM.yyyy · HH:mm", Locale.GERMANY).format(Date(item.timestamp * 1000L))
    }
    if (item.durationSeconds > 0L) {
        val minutes = item.durationSeconds / 60L
        parts += if (minutes >= 60L) "${minutes / 60L} Std ${minutes % 60L} Min" else "$minutes Min"
    }
    return parts.joinToString(" · ").ifBlank { item.channel }
}
'''

if "private fun V042MediathekCard" in s:
    raise SystemExit("V042 Mediathek card already exists")
s += extra
parity.write_text(s)

# --- Generic IPTV/VOD text readability ---
screens = java / "ui/Screens.kt"
s = screens.read_text()
s = s.replace("Android v0.4.1", "Android v0.4.2")
s = s.replace("Column(Modifier.height(245.dp)", "Column(Modifier.height(280.dp)", 1)
s = s.replace(
    "Text(media.name,fontWeight=FontWeight.ExtraBold,maxLines=2)",
    "Text(media.name,color=Color.White,fontWeight=FontWeight.Black,fontSize=17.sp,maxLines=2)",
    1,
)
s = s.replace(
    "Text(subtitle,color=Color.White.copy(.62f),fontSize=12.sp,maxLines=2)",
    "Text(subtitle,color=Color.White.copy(.88f),fontSize=13.sp,maxLines=3)",
    1,
)
for old, new in [
    ("Color.White.copy(.5f)", "Color.White.copy(.78f)"),
    ("Color.White.copy(.52f)", "Color.White.copy(.80f)"),
    ("Color.White.copy(.58f)", "Color.White.copy(.84f)"),
    ("Color.White.copy(.6f)", "Color.White.copy(.84f)"),
    ("Color.White.copy(.62f)", "Color.White.copy(.86f)"),
    ("Color.White.copy(.68f)", "Color.White.copy(.90f)"),
]:
    s = s.replace(old, new)
screens.write_text(s)

# --- Shared cards/top bar readability ---
common = java / "ui/Common.kt"
s = common.read_text()
s = s.replace(
    "listOf(Color.Black.copy(alpha = .18f), Color(0xFF07101D).copy(alpha = .42f), Color.Black.copy(alpha = .66f))",
    "listOf(Color.Black.copy(alpha = .30f), Color(0xFF07101D).copy(alpha = .58f), Color.Black.copy(alpha = .78f))",
    1,
)
s = s.replace("fontSize = 18.sp, fontWeight = FontWeight.ExtraBold", "fontSize = 20.sp, fontWeight = FontWeight.Black", 1)
s = s.replace("color = Color.White.copy(.66f), fontSize = 13.sp", "color = Color.White.copy(.90f), fontSize = 14.sp", 1)
s = s.replace("fontSize = 21.sp, fontWeight = FontWeight.ExtraBold", "fontSize = 23.sp, fontWeight = FontWeight.Black", 1)
common.write_text(s)

# --- Home text readability ---
home = java / "ui/V041Home.kt"
s = home.read_text()
s = s.replace("0.4.1", "0.4.2")
s = s.replace("color = Color.White.copy(.58f)", "color = Color.White.copy(.86f)", 1)
s = s.replace("color = Color.White.copy(.66f)", "color = Color.White.copy(.90f)", 1)
s = s.replace("fontSize = if (isTv) 12.sp else 11.sp", "fontSize = if (isTv) 14.sp else 13.sp", 1)
home.write_text(s)

print("Android v0.4.2 readability + rich Mediathek patch applied")
