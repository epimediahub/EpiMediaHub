#!/usr/bin/env python3
import unittest
import language_policy as policy

class PlaylistLanguagePolicyTests(unittest.TestCase):
    def test_4k_requires_explicit_german_evidence(self):
        for value in ('["de"]','["it", "de"]',['deu'],['de-at']):
            with self.subTest(value=value):
                ok,reason=policy.eligible(8,codes=value)
                self.assertTrue(ok)
                self.assertEqual(reason,'explicit_language_code')

    def test_4k_rejects_italian_unknown_or_ambiguous(self):
        for value in ('["it"]','["tr"]','[]','invalid-json',[],None):
            with self.subTest(value=value):
                ok,reason=policy.eligible(8,codes=value)
                self.assertFalse(ok)
                self.assertEqual(reason,'german_source_not_verified')

    def test_category_requires_explicit_id_approval(self):
        self.assertEqual(policy.eligible(8,category_id=17,category_label='DE | Serien')[0],False)
        self.assertEqual(policy.eligible(8,category_id=17,category_label='DE | Serien',
                                         approved_category_ids=[17])[0],True)
        self.assertEqual(policy.eligible(8,category_id=17,category_label='IT | Serie',
                                         approved_category_ids=[17])[0],False)
        self.assertEqual(policy.eligible(8,category_id=17,category_label='DEVICE Movies',
                                         approved_category_ids=[17])[0],False)

    def test_it_curation_is_allowed_without_ranking(self):
        ok,reason=policy.eligible(10,codes='[]')
        self.assertTrue(ok)
        self.assertEqual(reason,'curated_italian_playlist')
        self.assertFalse(policy.eligible(9,codes=['it'])[0])

if __name__ == '__main__':
    unittest.main()
