import tempfile
import unittest
from pathlib import Path
from incident_store import IncidentStore
from monitor_rules import Alert


class IncidentStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'incidents.db'
        self.store = IncidentStore(self.path)
        self.alert = Alert('analysis_stalled:8', 'analysis_stalled', 'critical', '8',
                           'Analyse-Lane ohne Fortschritt')

    def test_deduplicates_and_notifies_once(self):
        self.assertEqual([self.alert.key], self.store.observe([self.alert], 100))
        self.assertEqual([], self.store.observe([self.alert], 110))
        row = self.store.get(self.alert.key)
        self.assertEqual(2, row['occurrences'])
        self.assertEqual(100, row['first_seen_epoch'])
        self.assertEqual(110, row['last_seen_epoch'])
        self.assertEqual('open', row['state'])

    def test_acknowledgement_is_not_new_alert(self):
        self.store.observe([self.alert], 100)
        self.assertTrue(self.store.acknowledge(self.alert.key, 105))
        self.assertEqual([], self.store.observe([self.alert], 110))
        self.assertEqual('acknowledged', self.store.get(self.alert.key)['state'])

    def test_verified_resolve_and_reopen(self):
        self.store.observe([self.alert], 100)
        self.assertTrue(self.store.resolve(self.alert.key, 150))
        self.assertEqual('resolved', self.store.get(self.alert.key)['state'])
        self.assertEqual([self.alert.key], self.store.observe([self.alert], 200))
        row = self.store.get(self.alert.key)
        self.assertEqual('open', row['state'])
        self.assertEqual(200, row['first_seen_epoch'])
        self.assertIsNone(row['resolved_epoch'])
        self.assertEqual(1, row['occurrences'])

    def test_missing_observation_does_not_resolve(self):
        self.store.observe([self.alert], 100)
        self.store.observe([], 200)
        self.assertEqual('open', self.store.get(self.alert.key)['state'])

    def test_no_unknown_acknowledge_or_resolve(self):
        self.assertFalse(self.store.acknowledge('missing', 30))
        self.assertFalse(self.store.resolve('missing', 30))

    def test_database_file_is_private(self):
        self.assertEqual(0, self.path.stat().st_mode & 0o077)

    def test_rejects_accessible_database(self):
        self.path.chmod(0o644)
        with self.assertRaises(PermissionError):
            IncidentStore(self.path)

    def test_persistence_across_instances(self):
        self.store.observe([self.alert], 10)
        self.assertEqual('open', IncidentStore(self.path).get(self.alert.key)['state'])

    def test_multiple_alerts_and_ordering(self):
        later = Alert('build_failed:12', 'build_failed', 'warning', '12',
                      'Build fehlgeschlagen')
        self.store.observe([self.alert], 100)
        self.store.observe([later], 200)
        self.assertEqual([later.key, self.alert.key],
                         [x['alert_key'] for x in self.store.open_incidents()])

    def test_same_key_after_resolution_notifies_again(self):
        self.store.observe([self.alert], 100)
        self.store.resolve(self.alert.key, 101)
        self.store.observe([self.alert], 102)
        self.assertEqual('open', self.store.get(self.alert.key)['state'])


if __name__ == '__main__':
    unittest.main()
