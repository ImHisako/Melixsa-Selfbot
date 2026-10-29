import unittest

from Cogs.core import lyrics_tools as lyrics


class LocalLyricsTests(unittest.TestCase):
    def test_timestamps_repeated_lines_fraction_and_metadata(self):
        lines = lyrics.parse_lrc(
            "[ar:Artista di prova]\n[00:10.50][00:20.500]Riga A\n"
            "[00:05]Riga B\n[00:30.5]Riga C\nTesto senza tempo\n"
        )
        self.assertEqual(lines, [(5.0, "Riga B"), (10.5, "Riga A"), (20.5, "Riga A"), (30.5, "Riga C")])

    def test_offset_and_word_timing(self):
        self.assertEqual(lyrics.parse_lrc("[offset:500]\n[00:02.50]<00:02.50>Riga <00:03.00>uno"), [(2.0, "Riga uno")])

    def test_blank_lines_stop_previous_verse_and_no_backlog_after_seek(self):
        lines = lyrics.parse_lrc("[00:01]Riga uno\n[00:03]\n[00:10]Riga due")
        self.assertIsNone(lyrics.current_line(lines, 0))
        self.assertEqual(lyrics.current_line(lines, 1), (0, "Riga uno"))
        self.assertIsNone(lyrics.current_line(lines, 3))
        self.assertEqual(lyrics.current_line(lines, 11), (2, "Riga due"))
        self.assertIsNone(lyrics.current_line(lines, 20))

    def test_missing_timing_and_oversized_line(self):
        self.assertEqual(lyrics.parse_lrc("[ar:Artista]\nRiga senza tempo"), [])
        self.assertIsNone(lyrics.current_line([], 10))
        with self.assertRaises(lyrics.LyricsError):
            lyrics.parse_lrc("[00:01]" + "🎶" * 1501)


if __name__ == "__main__":
    unittest.main()
