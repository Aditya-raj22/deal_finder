#!/bin/bash
# Cron job to run deal finder monthly

set -euo pipefail

# Configuration
PROJECT_DIR="/opt/deal_finder"
LOG_DIR="${PROJECT_DIR}/logs"
RUN_ID="$(date +%Y%m%d_%H%M%S)"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Change to project directory
cd "${PROJECT_DIR}"

# Log start
echo "[${RUN_ID}] Starting deal finder pipeline" | tee -a "${LOG_DIR}/cron.log"

# Run with Docker Compose
docker-compose up --build --abort-on-container-exit

# Check exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[${RUN_ID}] Pipeline completed successfully" | tee -a "${LOG_DIR}/cron.log"

    # Optional: Upload results to S3/GCS
    # aws s3 cp output/deals.xlsx s3://my-bucket/deals_${RUN_ID}.xlsx
    # aws s3 cp output/evidence.jsonl s3://my-bucket/evidence_${RUN_ID}.jsonl
else
    echo "[${RUN_ID}] Pipeline failed with exit code ${EXIT_CODE}" | tee -a "${LOG_DIR}/cron.log"

    # Optional: Send alert
    # curl -X POST "$SLACK_WEBHOOK_URL" \
    #   -H 'Content-Type: application/json' \
    #   -d "{\"text\":\"Deal Finder pipeline failed: ${RUN_ID}\"}"
fi

# Cleanup old logs (keep last 30 days)
find "${LOG_DIR}" -name "*.log" -mtime +30 -delete

exit $EXIT_CODE
