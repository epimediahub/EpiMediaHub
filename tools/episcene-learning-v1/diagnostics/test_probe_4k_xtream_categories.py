#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
import probe_4k_xtream_categories as p

class CategoryTests(unittest.TestCase):
    def test_ambiguous_languages_are_not_de(self):
        self.assertEqual(p.category_label('DE | Serien'),'unambiguous_de_label')
        self.assertEqual(p.category_label('Deutsch Netflix'),'unambiguous_de_label')
        self.assertEqual(p.category_label('DE / IT Serien'),'mixed_language_label')
        self.assertEqual(p.category_label('ITALIAN Series'),'not_explicitly_de')
        self.assertEqual(p.category_label('INTERNATIONAL'),'not_explicitly_de')

    def test_stats_only_exclude_titles_and_urls(self):
        cats=[{'category_id':'17','category_name':'DE | Filme'},
              {'category_id':'22','category_name':'IT | Serie'},
              {'category_id':'23','category_name':'DE / TR Mix'}]
        rows=[{'series_id':'111','name':'PRIVATE SERIES','category_id':'17','stream_url':'secret'},
              {'series_id':'112','name':'PRIVATE SERIES 2','category_id':'22'},
              {'series_id':'113','name':'PRIVATE SERIES 3','category_id':'23'},
              {'series_id':'114','name':'PRIVATE SERIES 4','category_id':'999'}]
        result=p.inspect(cats,rows)
        self.assertEqual(result['series_by_category_evidence']['unambiguous_de_label'],1)
        self.assertEqual(result['series_by_category_evidence']['mixed_language_label'],1)
        self.assertEqual(result['series_by_category_evidence']['missing_or_unknown_id'],1)
        self.assertNotIn('PRIVATE SERIES',str(result))
        self.assertNotIn('secret',str(result))

    def test_ast_only_accepts_provider_api_actions(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'skip_catalogue.py'
            src.write_text(
                'def provider_listing(playlist,busy):\n'
                '  series=provider_api(playlist,"get_series",busy)\n'
                '  categories=provider_api(playlist,"get_series_categories",busy)\n'
                '  return series,categories\n',encoding='utf-8')
            self.assertEqual(set(p.safe_action_names(src)),{'get_series','get_series_categories'})
            src.write_text('def provider_listing(playlist,busy): return provider_api(playlist,"unknown",busy)\n')
            self.assertIsNone(p.safe_action_names(src))

if __name__=='__main__':
    unittest.main()
