import json
from pathlib import Path


def test_vercel_crons_cover_patrol_and_monitor_checks():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    crons = {item["path"]: item["schedule"] for item in config["crons"]}

    assert crons["/api/cron/patrol"] == "0 4 * * *"
    assert crons["/api/cron/check-monitors"] == "*/5 * * * *"
