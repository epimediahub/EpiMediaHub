package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.roundToLong

class V122FrameRateEstimatorTest {
    private fun samples(rate: Double, quantizedMs: Boolean = false): List<Float> {
        val estimator = V122FrameRateEstimator()
        return (0..(rate * 10).toInt()).mapNotNull { frame ->
            val pts = frame * 1_000_000.0 / rate
            estimator.sample(if (quantizedMs) (pts / 1000).roundToLong() * 1000 else pts.roundToLong())
        }
    }

    @Test fun distinguishesFractionalAndIntegerRatesAtAllCommonTvCadences() {
        for (rate in listOf(24000.0 / 1001, 24.0, 25.0, 30000.0 / 1001, 30.0,
            48000.0 / 1001, 48.0, 50.0, 60000.0 / 1001, 60.0, 100.0, 120000.0 / 1001, 120.0)) {
            val result = samples(rate)
            assertTrue("No estimate for $rate", result.isNotEmpty())
            result.forEach { assertEquals(rate, it.toDouble(), .001) }
        }
    }

    @Test fun averagesMillisecondContainerTimestampsWithoutRoundingFilmTo24() {
        for (rate in listOf(24000.0 / 1001, 24.0, 30000.0 / 1001, 30.0, 50.0, 60000.0 / 1001, 60.0)) {
            val result = samples(rate, quantizedMs = true)
            assertTrue(result.isNotEmpty())
            result.forEach { assertEquals(rate, it.toDouble(), .001) }
        }
    }

    @Test fun aShortWindowCannotTriggerAModeSwitch() {
        val estimator = V122FrameRateEstimator()
        repeat(72) { assertNull(estimator.sample(it * 1_000_000L / 24)) }
    }

    @Test fun repeatedMissingFramesDoNotInventALowerCadence() {
        val estimator = V122FrameRateEstimator()
        var pts = 0L
        repeat(500) { frame ->
            pts += if (frame % 20 == 0) 80_000L else 40_000L
            assertNull(estimator.sample(pts))
        }
    }

    @Test fun variableCadenceIsNotRoundedToAStandardRate() {
        val estimator = V122FrameRateEstimator()
        var pts = 0L
        repeat(500) { frame ->
            pts += if (frame % 2 == 0) 33_333L else 41_667L
            assertNull(estimator.sample(pts))
        }
        assertTrue(samples(27.0).isEmpty())
    }

    @Test fun seekAndDiscontinuityRequireAFreshStableWindow() {
        val estimator = V122FrameRateEstimator()
        repeat(60) { assertNull(estimator.sample(it * 40_000L)) }
        assertNull(estimator.sample(500_000L)) // backwards seek
        repeat(74) { assertNull(estimator.sample(540_000L + it * 40_000L)) }
        assertEquals(25f, estimator.sample(3_500_000L)!!, .001f)
        assertNull(estimator.sample(9_000_000L)) // large forwards jump
        repeat(140) { assertNull(estimator.sample(9_020_000L + it * 20_000L)) }
        estimator.reset()
        assertNull(estimator.sample(0L))
    }

    @Test fun knownMetadataIsNeverReplacedWithHalfOrDoubleRate() {
        assertEquals(50f, V122FrameRateEstimator.contentRate(50f, 25f), 0f)
        assertEquals(25f, V122FrameRateEstimator.contentRate(25f, 50f), 0f)
        assertEquals(24000f / 1001, V122FrameRateEstimator.contentRate(24f, 24000f / 1001), 0f)
    }

    @Test fun absentOrInvalidMetadataUsesOnlyAValidMeasuredCadence() {
        assertEquals(25f, V122FrameRateEstimator.contentRate(-1f, 25f), 0f)
        assertEquals(0f, V122FrameRateEstimator.contentRate(Float.NaN, 0f), 0f)
        assertEquals(0f, V122FrameRateEstimator.contentRate(-1f, Float.POSITIVE_INFINITY), 0f)
    }
}
