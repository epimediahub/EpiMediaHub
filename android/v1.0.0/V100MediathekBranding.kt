package de.epimediahub.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage

private fun v100BroadcasterDomain(label: String): String {
    val value = label.lowercase()
    return when {
        "ard" in value || "das erste" in value -> "ardmediathek.de"
        "zdf" in value -> "zdf.de"
        "arte" in value -> "arte.tv"
        "3sat" in value -> "3sat.de"
        "kika" in value -> "kika.de"
        "mdr" in value -> "mdr.de"
        "ndr" in value -> "ndr.de"
        "wdr" in value -> "wdr.de"
        "swr" in value -> "swr.de"
        value == "br" || "bayerischer" in value -> "br.de"
        value == "hr" || "hessischer" in value -> "hr.de"
        "rbb" in value -> "rbb-online.de"
        value == "sr" || "saarländ" in value -> "sr.de"
        "orf" in value -> "orf.at"
        "srf" in value -> "srf.ch"
        "servus" in value -> "servustv.com"
        "rtl" in value -> "rtl.de"
        "prosieben" in value || "pro7" in value -> "prosieben.de"
        "sat.1" in value || "sat1" in value -> "sat1.de"
        "joyn" in value -> "joyn.de"
        "rai" in value -> "raiplay.it"
        "mediaset" in value -> "mediasetinfinity.mediaset.it"
        "trt" in value -> "trtizle.com"
        "tv8" in value -> "tv8.com.tr"
        "france" in value -> "france.tv"
        "tf1" in value -> "tf1.fr"
        "rtve" in value -> "rtve.es"
        "nos" in value -> "nos.nl"
        "vrt" in value -> "vrt.be"
        value == "dr" || value.startsWith("dr ") -> "dr.dk"
        "svt" in value -> "svtplay.se"
        "nrk" in value -> "nrk.no"
        "yle" in value -> "yle.fi"
        "bbc" in value -> "bbc.co.uk"
        "itv" in value -> "itv.com"
        "abc" in value -> "abc.com"
        "cbs" in value -> "cbs.com"
        "nbc" in value -> "nbc.com"
        "cbc" in value -> "cbc.ca"
        "nhk" in value -> "nhk.or.jp"
        else -> ""
    }
}

private fun v100BroadcasterInitials(label: String): String {
    val words = label.split(Regex("[^A-Za-z0-9ÄÖÜäöüß]+"))
        .filter { it.isNotBlank() }
    return when {
        words.isEmpty() -> "TV"
        words.size == 1 -> words.first().take(3).uppercase()
        else -> words.take(3).joinToString("") { it.take(1) }.uppercase()
    }
}

@Composable
internal fun V100BroadcasterLogo(
    label: String,
    accent: Color
) {
    val isTv = LocalConfiguration.current.screenWidthDp >= 720
    val domain = v100BroadcasterDomain(label)
    val shape = RoundedCornerShape(if (isTv) 13.dp else 10.dp)
    Box(
        Modifier.fillMaxWidth()
            .height(if (isTv) 78.dp else 62.dp)
            .padding(bottom = if (isTv) 10.dp else 7.dp)
            .background(Color.White.copy(.96f), shape),
        contentAlignment = Alignment.Center
    ) {
        if (domain.isNotBlank()) {
            AsyncImage(
                model = "https://www.google.com/s2/favicons?domain=$domain&sz=128",
                contentDescription = "$label Logo",
                modifier = Modifier
                    .fillMaxWidth()
                    .height(if (isTv) 54.dp else 43.dp)
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                contentScale = ContentScale.Fit
            )
        } else {
            Text(
                v100BroadcasterInitials(label),
                color = Color(0xFF111820),
                fontSize = if (isTv) 24.sp else 19.sp,
                fontWeight = FontWeight.Black
            )
        }
        Box(
            Modifier.align(Alignment.BottomCenter)
                .fillMaxWidth()
                .height(3.dp)
                .background(accent.copy(.82f))
        )
    }
}

internal fun V100CountryFlag(labelOrId: String): String {
    val value = labelOrId.lowercase()
    return when {
        "deutsch" in value || value == "de" || "germany" in value -> "🇩🇪"
        "österreich" in value || value == "at" || "austria" in value -> "🇦🇹"
        "schweiz" in value || value == "ch" || "switzerland" in value -> "🇨🇭"
        "ital" in value || value == "it" -> "🇮🇹"
        "türk" in value || value == "tr" || "turkey" in value -> "🇹🇷"
        "frank" in value || value == "fr" || "france" in value -> "🇫🇷"
        "span" in value || value == "es" || "spain" in value -> "🇪🇸"
        "nieder" in value || value == "nl" || "netherlands" in value -> "🇳🇱"
        "belg" in value || value == "be" -> "🇧🇪"
        "brit" in value || value == "gb" || value == "uk" || "united kingdom" in value -> "🇬🇧"
        "usa" in value || value == "us" || "united states" in value -> "🇺🇸"
        else -> "🌐"
    }
}
