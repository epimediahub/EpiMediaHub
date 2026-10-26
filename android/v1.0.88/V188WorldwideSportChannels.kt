package de.epimediahub.app.ui

import java.text.Normalizer
import java.util.Locale

/**
 * Research-backed, conservative sports-channel families: global coverage is
 * open-ended; this list is NOT a claim that every broadcaster on Earth is here.
 * M3U names often have country prefixes, "HD/FHD/4K/HEVC" delivery suffixes,
 * renamed packages and provider-specific shorthand. Lists are checked locally;
 * IPTV stream URLs and credentials are never transmitted.
 *
 * 2026-10 source families:
 * sky.de/sender/sky-sport; sky.it/tv/sky-sport;
 * movistarplus.es/comunicacion; bein.com/en/channel-list;
 * dstv.com/en-ng/explore/dstv-channels; digi.ro/grila;
 * tivibu.com.tr/canli-tv/spor; astro.com.my (sports channel revamp);
 * kayo-support.zendesk.com; iptv-org/database (global channel metadata).
 */
internal object V188WorldwideSportChannels {
    internal data class Family(val region: String, val prefix: String)

    // Family rather than individual channel numbers (1-40) handles numbering,
    // additional languages, plus encrypted provider suffixes without needing
    // a complete commercial IPTV playlist. More specific prefixes come first.
    internal val families: List<Family> = buildList {
        fun group(region: String, vararg names: String) {
            names.forEach { add(Family(region, it)) }
        }
        group("DE_AT_CH",
            "SKY SPORT BUNDESLIGA", "SKY FUSSBALL BUNDESLIGA",
            "SKY SPORT FUSSBALL BUNDESLIGA", "SKY BUNDESLIGA",
            "SKY SPORT", "SKY SPORTS", "SKY F1", "SKY NFL",
            "SKY TOP EVENT", "DAZN", "EUROSPORT", "SPORT1",
            "SPORT 1", "SPORTDIGITAL", "MAGENTA SPORT", "MAGENTASPORT",
            "MOTORVISION", "SERVUS SPORT", "SERVUSTV SPORT",
            "DF1 SPORT", "BL TV", "BUNDESLIGA TV",
            "DB LIGA", "DE BUNDESLIGA", "DB BUNDESLIGA", "BULI")
        group("IT",
            "SKY SPORT", "SKY CALCIO", "SKY FORMULA 1",
            "RAI SPORT", "RAISPORT", "SPORTITALIA", "SUPERTENNIS",
            "SUPER TENNIS", "DAZN", "ACI SPORT", "ELEVEN SPORTS",
            "ITALIA SPORT", "INTER TV", "MILAN TV", "LAZIO STYLE",
            "JUVENTUS TV", "ROMA TV")
        group("UK_IE",
            "SKY SPORTS", "TNT SPORTS", "TNT ULTIMATE",
            "PREMIER SPORTS", "EUROSPORT", "RACING TV", "AT THE RACES",
            "LFCTV", "LFC TV", "MUTV", "CHELSEA TV",
            "CELTIC TV", "RANGERS TV", "BBC SPORT",
            "VIAPLAY SPORTS", "BT SPORT", "SETANTA SPORTS")
        group("FR_BE_NL",
            "BEIN SPORTS", "BEIN SPORT", "RMC SPORT",
            "CANAL PLUS SPORT", "CANAL SPORT", "CANAL+ SPORT",
            "L EQUIPE", "LEQUIPE", "L'EQUIPE",
            "EUROSPORT", "ZIGGO SPORT", "ESPN NL", "ESPN NETHERLANDS",
            "VTM SPORT", "TIPIK SPORT", "AUTOMOTO", "MOTORS TV",
            "DAZN LIGUE", "VIAPLAY SPORT")
        group("ES_PT",
            "MOVISTAR DEPORTES", "DEPORTES POR M",
            "M DEPORTES", "LALIGA TV", "DAZN LALIGA",
            "DAZN LA LIGA", "M LALIGA", "LIGA DE CAMPEONES",
            "M LIGA DE CAMPEONES", "GOL PLAY", "GOL TV",
            "TELEDEPORTE", "TDP", "VAMOS POR M",
            "VAMOS 2", "ELLAS VAMOS", "PRIMERA FEDERACION",
            "SPORT TV", "SPORTTV", "SPORTING TV",
            "BENFICA TV", "BTV", "PORTO CANAL SPORT",
            "CANAL 11", "ELEVEN SPORTS", "DAZN")
        group("EAST_CENTRAL_EUROPE",
            "DIGI SPORT", "PRIMA SPORT", "PRO ARENA",
            "ARENA SPORT", "ARENASPORT", "SPORT KLUB", "SPORTKLUB",
            "SK SPORT", "SK1 SPORT", "NOVASPORTS", "NOVA SPORTS",
            "COSMOTE SPORT", "OTE SPORT", "MAX SPORT",
            "DIEMA SPORT", "SPORT EXTRA", "M4 SPORT",
            "M5 SPORT", "TVP SPORT", "POLSAT SPORT",
            "POLSAT SPORT PREMIUM", "ELEVEN SPORTS", "CANAL+ SPORT",
            "CANAL SPORT", "VIASAT SPORT", "SETANTA SPORTS",
            "MATCH TV", "MATCH PREMIER", "MATCH FOOTBALL",
            "FUTBOL TV", "FUTBOL 1", "FUTBOL 2", "FUTBOL 3",
            "MEGOGO SPORT", "XSPORT", "SPORT PLUS", "SPORT PLUS TV")
        group("TR",
            "BEIN SPORTS", "BEIN SPORT", "TRT SPOR",
            "TRT 3 SPOR", "TRT SPOR YILDIZ", "A SPOR",
            "S SPORT", "S SPORT PLUS", "TIVIBU SPOR",
            "HT SPOR", "FB TV", "GS TV", "BJK TV",
            "EXXEN SPOR", "SMART SPOR", "EUROSPORT",
            "COSMO SPORTS")
        group("MENA",
            "BEIN SPORTS", "BEIN SPORT", "BEIN XTRA",
            "BEIN 4K", "ALKASS", "AL KASS", "SSC SPORT",
            "SSC SPORTS", "SSC", "SAUDI SPORTS",
            "KSA SPORTS", "AD SPORTS", "ABU DHABI SPORTS",
            "DUBAI SPORTS", "DUBAI SPORT", "DUBAI RACING",
            "BAHRAIN SPORTS", "OMAN SPORTS", "KUWAIT SPORT",
            "ARRyADIA", "ARRIADIA", "AL RYADIA",
            "THMANYAH", "EL HEddAF", "ON TIME SPORTS",
            "ONTIME SPORTS", "TIME SPORTS",
            "NILE SPORTS", "NILE SPORT", "AL AHLY TV",
            "ZAMALEK TV", "KORA PLUS", "SSC EXTRA")
        group("AFRICA",
            "SUPERSPORT", "SUPER SPORT", "SS GRANDSTAND",
            "SS FOOTBALL", "SS PREMIER LEAGUE", "SS LALIGA",
            "SS LA LIGA", "SS CRICKET", "SS RUGBY",
            "SS TENNIS", "SS GOLF", "SS MOTORSPORT",
            "SS VARIETY", "SS ACTION", "SS BLITZ",
            "SS AFRICA", "SS EXTRA", "SS MAXIMO", "SS PSL",
            "SS EVENT", "AZAM SPORTS", "AZAM SPORT",
            "STAR TIMES SPORTS", "STARTIMES SPORTS",
            "ST SPORTS", "SPORTY TV", "SPORTYTV",
            "AFRICA SPORTS", "RTS SPORT",
            "NEW WORLD SPORT", "CANAL PLUS SPORT", "CANAL+ SPORT")
        group("INDIA_SOUTH_ASIA",
            "STAR SPORTS", "SONY SPORTS", "SONY SPORT",
            "SONY TEN", "SONY SIX", "TEN SPORTS",
            "SPORTS18", "SPORTS 18", "JIOSTAR SPORTS",
            "JIO STAR SPORTS", "JIOHOTSTAR SPORTS",
            "DD SPORTS", "PTV SPORTS", "A SPORTS",
            "GEO SUPER", "GEO SUPER SPORTS",
            "FANCode", "FAN CODE", "T SPORTS",
            "G TV SPORTS", "GTV SPORTS")
        group("EAST_SOUTH_EAST_ASIA",
            "SPOTV", "SPO TV", "J SPORTS", "JSPO",
            "GAORA SPORTS", "GAORA", "GOLF NETWORK",
            "NITTELE G", "NITTELE G PLUS",
            "CCTV 5", "CCTV5", "CCTV 5 PLUS", "CCTV5+",
            "CCTV 16", "MIGU SPORTS", "MIGU SPORT",
            "NOW SPORTS", "NOW SPORT", "HOY SPORTS",
            "ASTRO ARENA", "ASTRO PREMIER LEAGUE",
            "ASTRO FOOTBALL", "ASTRO SPORTS",
            "ASTRO SUPERSPORT", "TRUE SPORTS",
            "TRUE SPORT", "TRUE PREMIER FOOTBALL",
            "AIS PLAY SPORTS", "ONE SPORTS", "PBA RUSH",
            "SINGTEL SPORTS", "SINGTEL SPORT",
            "SBS SPORTS", "KBS N SPORTS",
            "MBC SPORTS", "MBC SPORTS+", "ELEVEN SPORTS",
            "VIDIO SPORTS", "CHAMPIONS TV", "SPORTS TV")
        group("USA_CANADA",
            "ESPN", "ESPN2", "ESPN 2", "ESPN U",
            "ESPNU", "ESPN DEPORTES", "FOX SPORTS",
            "FOX SOCCER PLUS", "FOX DEPORTES", "FS1", "FS2",
            "CBS SPORTS", "NBC SPORTS", "NBCSN",
            "TNT SPORTS", "TUDN", "TYC SPORTS",
            "GOL TV", "GOLTV", "GOLF CHANNEL",
            "NBA TV", "NFL NETWORK", "NFL REDZONE",
            "NHL NETWORK", "MLB NETWORK",
            "BIG TEN NETWORK", "BTN", "SEC NETWORK",
            "ACC NETWORK", "PAC 12 NETWORK",
            "PAC-12 NETWORK", "WILLOW", "WILLOW CRICKET",
            "MAVTV", "FIGHT NETWORK", "UFC FIGHT PASS",
            "SPORTSNET", "SN ONE", "TSN", "TSN2",
            "RDS", "RDS2", "TVA SPORTS",
            "NESN", "MSG NETWORK", "MSG SPORTS",
            "YES NETWORK", "MASN", "MARQUEE SPORTS",
            "ALTITUDE SPORTS", "SPACE CITY HOME NETWORK",
            "ROOT SPORTS", "FANDUEL SPORTS NETWORK")
        group("LATAM_CARIBBEAN",
            "ESPN", "ESPN BRASIL", "ESPN DEPORTES",
            "FOX SPORTS", "TNT SPORTS", "TNT SPORT",
            "TYC SPORTS", "TYC SPORT", "DSports",
            "D SPORTS", "DIRECTV SPORTS",
            "DIRECTV SPORT", "SPORTV", "SPOR TV",
            "SporTV", "PREMIERE FC", "PREMIERE CLUBES",
            "PREMIERE SPORT", "WIN SPORTS", "WIN SPORT",
            "TUDN", "GOLTV", "GOL TV",
            "GOL PERU", "GOL CARACOL", "LIGA1 MAX",
            "LIGA 1 MAX", "CLARO SPORTS", "CLARO SPORT",
            "AZTECA DEPORTES", "TDN", "VTV SPORTS",
            "TIGO SPORTS", "TIGO SPORT",
            "SPORTSMAX", "SPORTS MAX", "FLOW SPORTS",
            "GOLF CHANNEL", "NBA TV", "BEIN SPORTS",
            "DSports 2", "DSports+", "TV PUBLICA DEPORTES")
        group("AU_NZ_PACIFIC",
            "FOX SPORTS", "FOX SPORT", "FOX FOOTY",
            "FOX LEAGUE", "FOX CRICKET", "FOX NETBALL",
            "FOX SPORTS NEWS", "SKY SPORT",
            "SKY SPORTS", "SKY RACING",
            "STAN SPORT", "KAYO SPORTS",
            "RACING COM", "RACING.COM",
            "TAB TRACKSIDE", "TRACKSIDE",
            "ESPN", "BEIN SPORTS", "SUPERSPORT")
    }.distinctBy { it.prefix.uppercase(Locale.ROOT) }

    private val marks = Regex("""\p{M}+""")
    private val nonAlnum = Regex("""[^A-Z0-9]+""")
    private val spaces = Regex("""\s+""")
    private val quality = Regex(
        """\b(?:8K|4K|UHD|FHD|FULL HD|HD PLUS|HD|SD|HDR10|HDR|HEVC|H 265|H265|H 264|H264|AVC|WEB|BAHEVC|BHAEVC|1080P|2160P|720P|25\s*FPS|50\s*FPS|60\s*FPS|MULTI AUDIO|BACKUP|SOURCE [0-9]+)\b"""
    )
    private val country = Regex("""^(?:DE|AT|CH|IT|FR|ES|PT|UK|GB|IE|US|CA|BR|AR|MX|RO|PL|TR|NL|BE|RS|HR|GR|AL|MA|SA|AE|AF|IN|PK|CN|JP|KR|AU|NZ|ZA|EG|MY|PH|TH|TZ|CO|NG|KE|GH|MENA|LATAM|AFRICA|ASIA|INT|EU|VIP)\s+(?:\d+\s+)?""")

    /** Stable IPTV name tokens; NEVER use stripped quality to infer actual FPS. */
    fun clean(raw: String): String {
        val ascii = marks.replace(
            Normalizer.normalize(raw, Normalizer.Form.NFD), "")
            .uppercase(Locale.ROOT)
        val withSpaces = spaces.replace(nonAlnum.replace(ascii, " "), " ").trim()
        val noCountry = country.replace(withSpaces, "")
        return spaces.replace(quality.replace(noCountry, " "), " ").trim()
    }

    fun family(raw: String): Family? {
        val name = clean(raw)
        if (name.isBlank()) return null
        // Broadcast brand families are never sufficient for special film,
        // documentary or children's spin-offs of an otherwise sports brand.
        if (Regex("""^(?:DAZN|ESPN|FOX SPORTS|SKY SPORTS?|BEIN SPORTS?|SPORT TV)\s+(?:MOVIES|CINEMA|KIDS|SERIES|DOCS?|DOCUMENTARY|DRAMA)\b""")
                .containsMatchIn(name)) return null
        // Station-prefix only; e.g. "STAR MOVIES" does not match Star Sports
        // and "SKY CINEMA" does not match Sky Sport.
        return families
            .filter { candidate ->
                val token = clean(candidate.prefix)
                (name == token || name.startsWith("$token ")) &&
                    !name.startsWith("SPORTS DOCUMENTARY")
            }
            .maxByOrNull { clean(it.prefix).length }
    }

    fun isKnownSport(raw: String): Boolean = family(raw) != null

    /**
     * An observed IPTV alias supplied by a customer: "DB Liga" may stand in
     * for "Sky Bundesliga". Keep channel numbers and language distinctions.
     * This is a heuristic station identity, not a licence/rights assertion.
     */
    fun canonicalSportIdentity(raw: String): String {
        // Country/language tags MUST remain part of the identity. "DE: DAZN 1"
        // and "IT: DAZN 1" are not interchangeable even in one playlist.
        val prefix = Regex("""(?i)^\s*(DE|AT|CH|IT|FR|ES|PT|UK|GB|IE|US|CA|BR|AR|MX|RO|PL|TR|NL|BE|RS|HR|GR|AL|MA|SA|AE|AF|IN|PK|CN|JP|KR|AU|NZ|ZA|EG|MY|PH|TH|TZ|CO|NG|KE|GH|MENA|LATAM|AFRICA|ASIA)\s*[:|\-]""")
            .find(raw)?.groupValues?.get(1)?.uppercase(Locale.ROOT).orEmpty()
        var name = clean(raw)
        name = name.replace(Regex("""^(?:SKY SPORT BUNDESLIGA|SKY FUSSBALL BUNDESLIGA|SKY BUNDESLIGA|DB BUNDESLIGA|DB LIGA|DE BUNDESLIGA|BULI)\b"""), "BUNDESLIGA")
        name = name.replace(Regex("""^SKY SPORT CALCIO\b"""), "SKY CALCIO")
        name = name.replace(Regex("""^BEIN SPORT\b"""), "BEIN SPORTS")
        name = name.replace(Regex("""^SUPER SPORT\b"""), "SUPERSPORT")
        return if (prefix.isBlank()) name else prefix + ":" + name
    }
}
