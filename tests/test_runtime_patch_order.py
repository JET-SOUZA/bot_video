import os
import unittest

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import jetbot_v2 as app
import run_v2 as runtime
import telegram_fit_patch as fit
import run_v2_fallback  # noqa: F401 - applies final runtime bindings


class RuntimePatchOrderTests(unittest.TestCase):
    def test_telegram_fit_is_final_download_wrapper(self):
        self.assertIs(app.download_media, fit.download_media_with_telegram_fit)
        self.assertIs(fit._ORIGINAL_DOWNLOAD_MEDIA, runtime.strict_download_media)


if __name__ == "__main__":
    unittest.main()
