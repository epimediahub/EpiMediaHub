package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V118NamesTest {
    @Test fun thePhotographedProviderSuffixIsHidden() {
        assertEquals("Lie To Me S02 E18 Il Sospetto", V118Names.display("Lie To Me S02 E18 Il Sospetto Ita-Eng Webmux Dd5 1"))
        assertEquals("Staffel 2 · Folge 18 · Il Sospetto", V118Names.subtitle("Lie To Me S02 E18 || Il Sospetto Ita-Eng Webmux Dd5 1", "Lie to Me", 2, 18))
    }
    @Test fun technicalTokensAndFileExtensionsCanBeChained() {
        assertEquals("Der Besuch", V118Names.display("Der Besuch [GER-ENG] WEB-DL 1080p H.264 DD5.1.mkv"))
        assertEquals("Il sospetto", V118Names.display("Il sospetto ITA ENG BluRay DTS-HD 7.1.mp4"))
    }
    @Test fun realTitleWordsAndNumbersArePreserved() {
        for (title in listOf("It", "It Takes Two", "Who Is It", "Deutschland 83", "Web of Lies", "The Web", "Engrenages", "The End", "Episode 5 1", "Il sospetto", "À bientôt")) assertEquals(title, V118Names.display(title))
    }
    @Test fun episodeNumbersAreRemovedOnlyWhenTheyMatchTheCurrentEpisode() {
        assertEquals("Il sospetto", V118Names.episode("Lie To Me S02E18 - Il sospetto", "Lie to Me", 2, 18))
        assertEquals("Lie To Me S02E19 - Il sospetto", V118Names.episode("Lie To Me S02E19 - Il sospetto", "Lie to Me", 2, 18))
        assertEquals("It Happened", V118Names.episode("It Happened", "It", 2, 18))
    }
    @Test fun missingEpisodeTitlesDoNotLeaveAnEmptyDivider() {
        assertEquals("Staffel 2 · Folge 18", V118Names.subtitle("Lie To Me S02E18", "Lie to Me", 2, 18))
        assertEquals("Staffel 2 · Folge 18", V118Names.subtitle("Lie to Me", "Lie to Me", 2, 18))
    }
}
