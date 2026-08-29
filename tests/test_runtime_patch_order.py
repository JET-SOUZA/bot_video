import os
import unittest

os.environ.setdefault("TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import jetbot_v2 as app
import telegram_fit_patch as fit
import run_v2_fallback as entry


class RuntimePatchOrderTests(unittest.TestCase):
    def test_importing_policy_module_does_not_apply_final_runtime(self):
        self.assertFalse(entry._RUNTIME_APPLIED)

    def test_telegram_fit_is_final_download_wrapper_after_explicit_apply(self):
        entry.apply_runtime_policy()
        self.assertTrue(entry._RUNTIME_APPLIED)
        self.assertIs(app.download_media, fit.download_media_with_telegram_fit)
        self.assertIs(fit._ORIGINAL_DOWNLOAD_MEDIA, entry.download_media_with_shopee_policy)


if __name__ == "__main__":
    unittest.main()
