"""Only synthetic aggregate fixtures; no production source or provider access."""
import unittest
import visual_cause_summary as summary

def gap():
    return {
        "mode":"EPISCENE_RELEASE_GAP_READ_ONLY",
        "production_db_modified":False,
        "window_to_pending_marker_gap":{
           "8":{"NO_VISUAL_WINDOWS_FOR_ASSET_AND_KIND":100,
                "VISUAL_WINDOWS_BUT_FEWER_THAN_3_EPISODES":40},
           "10":{"WINDOWS_BUT_NO_MATCHING_ASSET_REVISION":200,
                "THREE_PLUS_EPISODES_HAVE_WINDOWS_CHECK_CONSENSUS_ENGINE":60}},
        "pending_stage_by_playlist":{"8":{"AWAITING_VISUAL_CONSENSUS":140},
                                     "10":{"VISUAL_REVIEW":260}},
        "failed_jobs":{"8":{"failed_reason_classes":{"TIME_OR_DEADLINE":10}},
                       "10":{"failed_reason_classes":{"MEDIA_DECODING":2}}},
        "gap_by_segment_type":{"8":{"intro":{"NO_VISUAL_WINDOWS_FOR_ASSET_AND_KIND":100}},
                               "10":{"outro":{"WINDOWS_BUT_NO_MATCHING_ASSET_REVISION":200}}},
        "visual_windows_by_playlist":{"8":{"all":3},"10":{"all":300}}
    }

def runtime():
    return {
      "mode":"EPISCENE_READ_ONLY_RUNTIME_TRIAGE",
      "production_db_modified":False,
      "systemd":{"epimediahub-analysis-worker.service":{"state":"active"}},
      "time_budget_suspected":True,
      "jobs":{"8":{"recent_partial":4,"running_over_15m":0,"status_counts":{"review":12}},
              "10":{"recent_partial":2,"running_over_15m":0,"status_counts":{"partial":3}}}
    }

class VisualCauseTests(unittest.TestCase):
    def test_rank_and_types_without_leaking_metadata(self):
        x=summary.condense(gap(),runtime())
        self.assertEqual(x["bewertung"]["8"]["groesster_nachpruefbarer_engpass"],
                         "KEINE_GESPEICHERTEN_BILDFENSTER")
        self.assertEqual(x["bewertung"]["10"]["groesster_nachpruefbarer_engpass"],
                         "BILDFENSTER_ALTE_ODER_FALSCHE_VERSION")
        self.assertEqual(x["bewertung"]["8"]["betroffene_pending_markereintraege_im_bildpruefpfad"],140)
        self.assertTrue(x["keine_freigaben"])
        self.assertTrue(x["keine_datenbank_aenderung"])
        self.assertTrue(x["keine_anbieter_streams"])

    def test_wrong_report_mode_rejected(self):
        a=gap();a["mode"]="UNKNOWN"
        with self.assertRaises(ValueError):
            summary.condense(a,runtime())

    def test_bad_count_ignored(self):
        a=gap();a["window_to_pending_marker_gap"]["8"]["NO_VISUAL_WINDOWS_FOR_ASSET_AND_KIND"]=-2
        x=summary.condense(a,runtime())
        self.assertEqual(x["bewertung"]["8"]["betroffene_pending_markereintraege_im_bildpruefpfad"],40)

if __name__=="__main__":
    unittest.main(verbosity=2)
