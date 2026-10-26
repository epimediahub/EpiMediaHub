package de.epimediahub.app.ui

import android.content.Context
import android.graphics.BitmapFactory
import de.epimediahub.app.data.PrefsRepository
import de.epimediahub.app.data.ThemeRepository
import de.epimediahub.app.MainViewModel
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V131SkinCatalogueTest {
    @Test fun everySportTeamHasTwoCompletePortraitVariantsWithItsOriginalBadgeAndScene() {
        val app = RuntimeEnvironment.getApplication()
        val repo = ThemeRepository(app); val catalog = repo.load()
        val teams = V131SkinArtwork.load(app)
        assertEquals(134, teams.size)
        assertEquals(30, catalog.groups.first { it.id == "nba" }.themes.size)
        assertEquals(32, catalog.groups.first { it.id == "nfl" }.themes.size)
        assertEquals(20, catalog.groups.first { it.id == "national_teams" }.themes.size)
        assertEquals(11, catalog.groups.first { it.id == "formula_1" }.themes.size)
        val originalTeams = catalog.groups.filter { it.id != "cars" }.flatMap { it.themes }
        assertEquals(134, originalTeams.toSet().size)
        val assets = mutableSetOf<String>()
        for ((base, variants) in teams) {
            assertEquals(listOf(base, base + "__players", base + "__legends"), variants.map { it.id })
            assertTrue("Original badge: $base", repo.officialMarkRes(base) != 0)
            val original = catalog.themes.getValue(base)
            assertTrue(original.family)
            assertTrue(variants.first().portraits.isEmpty())
            for (variant in variants.drop(1)) {
                assertEquals("Pair: ${variant.id}", 2, variant.portraits.size)
                assertEquals(2, variant.portraits.map { it.name }.toSet().size)
                val theme = catalog.themes.getValue(variant.id)
                assertTrue(theme.family); assertEquals(original.group, theme.group); assertEquals(original.accent, theme.accent)
                assertEquals(repo.officialMarkRes(base), repo.officialMarkRes(variant.id))
                assertEquals(repo.backgroundRes(base), repo.backgroundRes(variant.id))
                assertEquals(V097SkinWorldFor(base, original.label, original.group), V097SkinWorldFor(variant.id, theme.label, theme.group))
                variant.portraits.forEach { assertTrue(it.name.isNotBlank()); assets.add(it.asset) }
                if (variant.pairAsset.isNotBlank()) assets.add(variant.pairAsset)
            }
        }
        assets.forEach { name ->
            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            app.assets.open(name).use { BitmapFactory.decodeStream(it, null, options) }
            assertTrue("Decodable $name", options.outWidth >= 96 && options.outHeight >= 96)
        }
        assertTrue(V131SkinArtwork.variants(app, "ferrari").isEmpty())
        assertTrue(V131SkinArtwork.variants(app, "default").isEmpty())
    }
    @Test fun selectedVariantSurvivesReloadAndPrivateLockStillProtectsIt() {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().commit()
        val prefs = PrefsRepository(app); prefs.setFamilySkinsUnlocked(true)
        val vm = MainViewModel(app); vm.selectTheme("nba_los_angeles_lakers__legends")
        assertEquals("nba_los_angeles_lakers__legends", MainViewModel(app).ui.value.themeId)
        vm.lockPrivateSkins(); assertEquals("default", vm.ui.value.themeId)
        vm.selectTheme("f1_ferrari__players"); assertEquals("default", vm.ui.value.themeId)
    }
}
