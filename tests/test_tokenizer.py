import unittest
from reader.furigana_manager import analyze_tokens

class TestTokenizer(unittest.TestCase):
    def test_simple_word(self):
        tokens = analyze_tokens('そこ')
        self.assertTrue(any(t['orig'] == 'そこ' for t in tokens))

    def test_word_with_punctuation(self):
        tokens = analyze_tokens('そこ。')
        self.assertTrue(any(t['orig'] == 'そこ' for t in tokens))

    def test_word_with_quotes(self):
        tokens = analyze_tokens('“から”')
        self.assertTrue(any(t['orig'] == 'から' for t in tokens))

    def test_word_with_spaces(self):
        tokens = analyze_tokens('  から  ')
        self.assertTrue(any(t['orig'] == 'から' for t in tokens))

if __name__ == '__main__':
    unittest.main()
