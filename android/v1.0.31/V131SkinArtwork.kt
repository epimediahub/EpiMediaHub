package de.epimediahub.app.ui

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.ImageLoader
import coil.compose.AsyncImage
import coil.memory.MemoryCache
import org.json.JSONObject

internal fun V131BaseTheme(id: String): String = when {
    id.endsWith("__players") -> id.removeSuffix("__players")
    id.endsWith("__legends") -> id.removeSuffix("__legends")
    else -> id
}

internal data class V131Portrait(val name: String, val asset: String, val transparent: Boolean)
internal data class V131SkinVariant(val id: String, val label: String,
    val portraits: List<V131Portrait> = emptyList(), val pairAsset: String = "")

/** Metadata is small; picture decoding is lazy and limited to visible cards. */
internal object V131SkinArtwork {
    @Volatile private var metadata: Map<String, List<V131SkinVariant>>? = null
    @Volatile private var pictureLoader: ImageLoader? = null

    fun load(context: Context): Map<String, List<V131SkinVariant>> = metadata ?: synchronized(this) {
        metadata ?: run {
            val root = JSONObject(context.assets.open("skin_variants_v131.json").bufferedReader().use { it.readText() })
            val teams = root.getJSONArray("teams")
            buildMap {
                for (i in 0 until teams.length()) {
                    val team = teams.getJSONObject(i)
                    val id = team.getString("id")
                    val variants = team.getJSONArray("variants")
                    put(id, List(variants.length()) { j ->
                        val variant = variants.getJSONObject(j)
                        val people = variant.optJSONArray("portraits")
                        V131SkinVariant(variant.getString("id"), variant.getString("label"),
                            List(people?.length() ?: 0) { n ->
                                val portrait = people!!.getJSONObject(n)
                                V131Portrait(portrait.getString("name"), portrait.getString("asset"), portrait.optBoolean("transparent"))
                            }, variant.optString("pairAsset"))
                    })
                }
            }.also { metadata = it }
        }
    }

    fun variants(context: Context, id: String): List<V131SkinVariant> =
        load(context)[V131BaseTheme(id)].orEmpty()

    fun variant(context: Context, id: String): V131SkinVariant? = variants(context, id).firstOrNull { it.id == id }

    fun imageLoader(context: Context): ImageLoader = pictureLoader ?: synchronized(this) {
        pictureLoader ?: ImageLoader.Builder(context.applicationContext)
            .memoryCache { MemoryCache.Builder(context.applicationContext).maxSizeBytes(8 * 1024 * 1024).build() }
            .allowHardware(false).crossfade(false).build().also { pictureLoader = it }
    }
}

/** Decorative only: no focus or pointer target is introduced behind the menu. */
@Composable
internal fun V131PortraitLayer(themeId: String, modifier: Modifier = Modifier, preview: Boolean = false) {
    val context = LocalContext.current
    val variant = V131SkinArtwork.variant(context, themeId) ?: return
    if (variant.portraits.isEmpty()) return
    val loader = V131SkinArtwork.imageLoader(context)
    Box(modifier.fillMaxSize()) {
        if (variant.pairAsset.isNotBlank()) {
            AsyncImage("file:///android_asset/" + variant.pairAsset, null,
                imageLoader = loader, contentScale = ContentScale.Fit,
                modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth(.98f)
                    .fillMaxHeight(if (preview) .95f else .85f).graphicsLayer { alpha = .94f })
        } else {
            variant.portraits.take(2).forEachIndexed { index, portrait ->
                AsyncImage("file:///android_asset/" + portrait.asset, null, imageLoader = loader,
                    contentScale = if (portrait.transparent) ContentScale.Fit else ContentScale.Crop,
                    modifier = Modifier.align(if (index == 0) Alignment.BottomStart else Alignment.BottomEnd)
                        .fillMaxWidth(if (preview) .36f else .32f)
                        .fillMaxHeight(if (preview) .91f else .72f)
                        .padding(horizontal = if (preview) 6.dp else 16.dp, vertical = if (preview) 0.dp else 20.dp)
                        .clip(androidx.compose.foundation.shape.RoundedCornerShape(18.dp))
                        .graphicsLayer { alpha = if (portrait.transparent) .91f else .78f })
            }
        }
        if (!preview) {
            variant.portraits.take(2).forEachIndexed { index, portrait ->
                Text(portrait.name,
                    modifier = Modifier.align(if (index == 0) Alignment.BottomStart else Alignment.BottomEnd)
                        .padding(horizontal = 22.dp, vertical = 7.dp).widthIn(max = 270.dp),
                    fontFamily = FontFamily.Cursive, fontSize = 23.sp,
                    color = Color.White.copy(.84f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}
