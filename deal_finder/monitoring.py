"""Production monitoring and alerting."""

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List

from .models import Deal

logger = logging.getLogger(__name__)


class DataQualityChecker:
    """Check data quality of extracted deals."""

    def __init__(self):
        self.issues = []

    def check_deal(self, deal: Deal) -> List[str]:
        """Check single deal for quality issues."""
        issues = []

        # Required fields
        if not deal.source_url:
            issues.append("Missing source URL")

        if not deal.date_announced:
            issues.append("Missing announcement date")

        if not deal.target or not deal.acquirer:
            issues.append("Missing party information")

        # Data consistency
        if deal.upfront_value_usd and deal.total_deal_value_usd:
            if deal.upfront_value_usd > deal.total_deal_value_usd:
                issues.append("Upfront > Total (data inconsistency)")

        if deal.upfront_pct_total:
            if deal.upfront_pct_total < 0 or deal.upfront_pct_total > 100:
                issues.append(f"Invalid upfront %: {deal.upfront_pct_total}")

        # Evidence completeness
        if not deal.evidence.stage:
            issues.append("No evidence for stage classification")

        if not deal.evidence.deal_type:
            issues.append("No evidence for deal type")

        return issues

    def check_dataset(self, deals: List[Deal]) -> dict:
        """Check entire dataset quality."""
        total_deals = len(deals)
        if total_deals == 0:
            return {"status": "ERROR", "message": "No deals found"}

        stats = {
            "total_deals": total_deals,
            "needs_review_count": sum(1 for d in deals if d.needs_review),
            "needs_review_pct": sum(1 for d in deals if d.needs_review) / total_deals * 100,
            "missing_financials": sum(
                1
                for d in deals
                if not d.upfront_value_usd
                and not d.contingent_payment_usd
                and not d.total_deal_value_usd
            ),
            "missing_geography": sum(1 for d in deals if not d.geography),
            "stage_distribution": Counter(d.stage for d in deals),
            "deal_type_distribution": Counter(d.deal_type_detailed for d in deals),
            "ta_distribution": Counter(d.therapeutic_area for d in deals),
        }

        # Quality thresholds
        issues = []
        if stats["needs_review_pct"] > 80:
            issues.append(
                f"High needs review rate: {stats['needs_review_pct']:.1f}% (threshold: 80%)"
            )

        if stats["missing_financials"] > total_deals * 0.5:
            issues.append(
                f"Over 50% deals missing financial data: {stats['missing_financials']}/{total_deals}"
            )

        stats["quality_issues"] = issues
        stats["status"] = "WARNING" if issues else "OK"

        return stats


class ProductionMonitor:
    """Monitor production runs."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.metrics_file = self.output_dir / "metrics.jsonl"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log_run(
        self,
        run_id: str,
        config: dict,
        stats: dict,
        duration_seconds: float,
        status: str = "SUCCESS",
    ):
        """Log metrics for a pipeline run."""
        metrics = {
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "duration_seconds": duration_seconds,
            "config": {
                "therapeutic_area": config.get("THERAPEUTIC_AREA"),
                "start_date": config.get("START_DATE"),
                "end_date": config.get("END_DATE"),
            },
            "stats": stats,
        }

        with open(self.metrics_file, "a") as f:
            f.write(json.dumps(metrics) + "\n")

        logger.info(f"Logged metrics for run {run_id}")

    def get_recent_runs(self, n: int = 10) -> List[dict]:
        """Get recent run metrics."""
        if not self.metrics_file.exists():
            return []

        with open(self.metrics_file, "r") as f:
            lines = f.readlines()

        return [json.loads(line) for line in lines[-n:]]

    def alert_if_needed(self, stats: dict):
        """Send alerts if quality issues detected."""
        if stats.get("status") == "ERROR":
            self._send_alert(
                level="ERROR", message=f"Pipeline failed: {stats.get('message')}"
            )
        elif stats.get("quality_issues"):
            self._send_alert(
                level="WARNING",
                message=f"Quality issues detected: {', '.join(stats['quality_issues'])}",
            )

    def _send_alert(self, level: str, message: str):
        """Send alert (implement with email/Slack/PagerDuty)."""
        logger.warning(f"ALERT [{level}]: {message}")

        # TODO: Implement actual alerting
        # - Email via SMTP
        # - Slack webhook
        # - PagerDuty API
        # - CloudWatch/Datadog metrics

        # Example Slack webhook:
        # slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        # if slack_webhook:
        #     requests.post(slack_webhook, json={"text": f"[{level}] {message}"})
