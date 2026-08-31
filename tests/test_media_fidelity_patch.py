import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import media_fidelity_patch as patch


class MediaFidelityPatchTests(unittest.TestCase):
    def test_twitter_prefers_original_muxed_mp4_without_transcode(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = patch.build_general_ydl_options_fidelity(Path(tmp), "twitter")
        self.assertIn("filesize<46M", opts["format"])
        self.assertIn("filesize_approx<46M", opts["format"])
        self.assertTrue(opts["format"].endswith("best[ext=mp4]/best"))
        self.assertNotIn("postprocessors", opts)
        self.assertNotIn("merge_output_format", opts)
        self.assertNotIn("format_sort", opts)
        self.assertEqual(opts["socket_timeout"], 20)
        self.assertEqual(opts["retries"], 2)

    def test_other_platforms_keep_existing_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = patch.build_general_ydl_options_fidelity(Path(tmp), "instagram")
        self.assertIn("postprocessors", opts)


if __name__ == "__main__":
    unittest.main()
