import unittest

import yaml

from core.tools import ToolPolicy


class VoucherSubmitPolicyTests(unittest.TestCase):
    def load_policy(self):
        with open("config.yaml", encoding="utf-8") as source:
            config = yaml.safe_load(source)
        return ToolPolicy(config["tool_policy"])

    def test_voucher_submit_requires_platform_confirmation(self):
        policy = self.load_policy()
        decision = policy.check(
            "bash",
            {
                "command": (
                    "python skills/dingtalk-kingdee-voucher-sync/scripts/command.py "
                    "submit --plan skills/dingtalk-kingdee-voucher-sync/runtime/plans/latest.json "
                    "--confirm-submit"
                )
            },
        )
        self.assertEqual(decision.action, "confirm")

    def test_form_argument_does_not_look_like_rm(self):
        decision = self.load_policy().check(
            "bash",
            {"command": "python skills/dingtalk-kingdee-voucher-sync/scripts/sync.py list --form all"},
        )
        self.assertEqual(decision.action, "allow")

    def test_real_rm_still_requires_confirmation(self):
        decision = self.load_policy().check("bash", {"command": "cd workspace && rm report.json"})
        self.assertEqual(decision.action, "confirm")


if __name__ == "__main__":
    unittest.main()
