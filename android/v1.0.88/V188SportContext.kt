package de.epimediahub.app.ui

/**
 * Sports recognition is completely independent from frame-rate detection.
 * Never infer "sports" from 25 fps, resolution or the existence of a 50 fps
 * sibling. In particular, a general entertainment/movie channel must not
 * show automatic Sportmodus prompts merely because it has quality variants.
 */
internal object V188SportContext {
    enum class Confidence { NONE, PROBABLE, CONFIRMED }

    private val sportsEvent = Regex(
        """(?i)(?:\b(?:football|soccer|fussball|fußball|fútbol|futbol|calcio|bundesliga|serie\s+[ab]|"""+
        """premier\s+league|champions\s+league|europa\s+league|conference\s+league|"""+
        """coppa\s+italia|fa\s+cup|world\s+cup|weltmeisterschaft|european\s+championship|"""+
        """tennis|atp|wta|wimbledon|roland\s+garros|formula\s*1|formel\s*1|"""+
        """formula\s+uno|grand\s+prix|motogp|nascar|basketball|nba|euroleague|nfl|"""+
        """american\s+football|rugby|hockey|eishockey|handball|volleyball|"""+
        """cycling|radrennen|radsport|olympics|olympia|olimpiadi|boxing|boxen)\b)"""
    )
    // A sports brand airing documentaries, news or entertainment is not an
    // automatic "live sport" match when the current EPG explicitly says so.
    private val notLiveEvent = Regex(
        """(?i)\b(?:film|movie|cinema|serie(?!\s+[ab]\b)|series|documentary|documentario|"""+
        """documentazione|dokumentation|doku|recap|highlights|magazine|talkshow|"""+
        """talk\s+show|news|nachrichten|notizie|tg\s+sport|replay|replica)\b"""
    )
    private val sportsBrand = Regex(
        """(?i)(?:\b(?:dazn|eurosport|sportitalia|sport1|sport\s*tv|sky\s*(?:sport|calcio)|"""+
        """espn|bein\s*sports?|tnt\s*sports?|supersport|nfl\s+network|nba\s+tv|"""+
        """f1\s*tv|formula\s*1\s*tv|canal\+?\s+sport)\b)"""
    )
    private val sportsCategory = Regex(
        """(?i)\b(?:sport|sports|calcio|football|soccer|fussball|fußball|"""+
        """bundesliga|motorsport|formula\s*1|formel\s*1|tennis|basketball|"""+
        """rugby|racing|f1|eventi\s+sportivi)\b"""
    )

    fun confidence(
        channelName: String, categoryName: String,
        currentEpgTitle: String, currentEpgDescription: String = ""
    ): Confidence {
        val epgText = (currentEpgTitle + " " + currentEpgDescription).trim()
        // A concrete live match on a general broadcaster is relevant too.
        // An explicit movie/news/documentary classification always suppresses.
        if (epgText.isNotBlank()) {
            if (notLiveEvent.containsMatchIn(currentEpgTitle)) return Confidence.NONE
            if (sportsEvent.containsMatchIn(currentEpgTitle) ||
                (currentEpgTitle.isNotBlank() &&
                 sportsEvent.containsMatchIn(currentEpgDescription) &&
                 !notLiveEvent.containsMatchIn(currentEpgDescription)))
                return Confidence.CONFIRMED
            // The program title may be generic ("Live", "Event", provider EPG
            // placeholder). Known dedicated sports networks still count as
            // probable unless the current programme is explicitly non-sport.
            return if (V188WorldwideSportChannels.isKnownSport(channelName) ||
                sportsBrand.containsMatchIn(channelName))
                Confidence.PROBABLE else Confidence.NONE
        }
        // Without a programme guide, use the well-known dedicated sport
        // channel brand OR a conjunction of sport station and sport category.
        val knownSportStation =
            V188WorldwideSportChannels.isKnownSport(channelName) ||
                sportsBrand.containsMatchIn(channelName)
        val namedSportStation = sportsCategory.containsMatchIn(channelName)
        val sportsGroup = sportsCategory.containsMatchIn(categoryName)
        return if (knownSportStation || (namedSportStation && sportsGroup))
            Confidence.PROBABLE else Confidence.NONE
    }

    fun automaticOfferAllowed(
        channelName: String, categoryName: String,
        currentEpgTitle: String, currentEpgDescription: String,
        confirmedCurrentFps: Int, hasVerified50Alternative: Boolean
    ): Boolean =
        confirmedCurrentFps == 25 && hasVerified50Alternative &&
            confidence(channelName, categoryName, currentEpgTitle, currentEpgDescription) != Confidence.NONE
}
