import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))
from autopa.alps_serial import AlpsLineParser, AlpsSample, _is_legacy_version


class AlpsLineParserTest(unittest.TestCase):
    def test_new_firmware_combined_line(self):
        parser = AlpsLineParser()
        self.assertEqual(
            parser.parse("a=-123,b=456", 100),
            AlpsSample(100, -123, 456))

    def test_legacy_pair_uses_raw_arrival_timestamp(self):
        parser = AlpsLineParser()
        self.assertIsNone(parser.parse("a=100", 200))
        self.assertEqual(
            parser.parse("b=90", 220),
            AlpsSample(200, 100, 90))

    def test_filtered_only_line_is_preserved(self):
        parser = AlpsLineParser()
        self.assertEqual(
            parser.parse("b=-9", 300),
            AlpsSample(300, None, -9))

    def test_noise_is_ignored(self):
        parser = AlpsLineParser()
        self.assertIsNone(parser.parse("version:2.0.0", 1))
        self.assertIsNone(parser.parse("SAMPLE_THRESHOLD=123", 2))

    def test_version_command_style(self):
        self.assertTrue(_is_legacy_version("1.0"))
        self.assertTrue(_is_legacy_version("1.0.0"))
        self.assertFalse(_is_legacy_version("1.0.5"))
        self.assertFalse(_is_legacy_version("2.0.0"))


if __name__ == "__main__":
    unittest.main()
