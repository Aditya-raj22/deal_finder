# Production Deployment Guide

Complete guide to deploying Deal Finder in production.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [API Keys & Access](#api-keys--access)
3. [Docker Deployment](#docker-deployment)
4. [Scheduling & Automation](#scheduling--automation)
5. [Monitoring & Alerts](#monitoring--alerts)
6. [Scaling & Performance](#scaling--performance)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 20.04+) or macOS
- **Docker**: 20.10+ with Docker Compose
- **Resources**: 2 CPU cores, 4GB RAM minimum
- **Storage**: 10GB+ for data and cache

### Required API Keys

**Minimum (for basic operation):**
- OpenAI API key (`OPENAI_API_KEY`) - For TA vocab generation (one-time, ~$0.01)

**Recommended (for production):**
- At least ONE of:
  - [NewsAPI.org](https://newsapi.org/pricing) - $449/month Pro plan
  - [PR Newswire](https://www.prnewswire.com/contact-us/) - Contact for pricing
  - [Business Wire](https://www.businesswire.com/portal/site/home/) - Contact for pricing

**Optional:**
- Slack Webhook URL (`SLACK_WEBHOOK_URL`) - For alerts

---

## API Keys & Access

### 1. NewsAPI.org (Recommended for MVP)

**Signup:**
```bash
# Get API key from https://newsapi.org/register
export NEWSAPI_ORG_KEY="your_key_here"
```

**Pricing:**
- Free tier: NOT suitable (only 100 requests/day, 1-month history)
- **Pro plan**: $449/month (unlimited requests, full archive)

**Pros:**
- Easy to integrate
- Aggregates multiple news sources
- Good for biotech/pharma coverage

**Cons:**
- Can be expensive
- May have some gaps in early-stage deal coverage

### 2. PR Newswire API

**Contact**: Enterprise sales required
**Pricing**: ~$1,000-5,000/month depending on volume

**Pros:**
- Official press release source
- High quality, comprehensive coverage
- Best for M&A/partnership announcements

**Cons:**
- Expensive
- Requires enterprise contract

### 3. Business Wire API

**Contact**: Enterprise sales required
**Pricing**: Similar to PR Newswire

**Pros:**
- Another major press release distributor
- Good coverage

**Cons:**
- Expensive
- Requires enterprise contract

### 4. Alternative: Web Scraping (Development Only)

The tool includes web scraping fallback, but:
- ⚠️ **NOT recommended for production**
- Blocked by most news sites
- Unreliable, fragile
- May violate ToS

---

## Docker Deployment

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/yourorg/deal_finder.git
cd deal_finder

# 2. Set up environment variables
cp .env.example .env
nano .env  # Add your API keys

# 3. Build and run
docker-compose up --build

# 4. Check output
ls -l output/
```

### Production Deployment

**1. Create `.env` file:**
```bash
# .env
OPENAI_API_KEY=sk-...
NEWSAPI_ORG_KEY=your_newsapi_key
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

**2. Configure for your therapeutic area:**
```bash
# Edit config/production.yaml
nano config/production.yaml

# Change THERAPEUTIC_AREA to your target
THERAPEUTIC_AREA: "oncology"  # or "neurology", "cardiology", etc.
```

**3. Deploy with Docker Compose:**
```bash
# Build and run in detached mode
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**4. Persist data with volumes:**
```yaml
# docker-compose.yml already includes:
volumes:
  - ./output:/app/output      # Excel & JSONL files
  - ./logs:/app/logs          # Application logs
  - ./.cache:/app/.cache      # Translation cache
```

---

## Scheduling & Automation

### Option 1: Cron (Simple)

**1. Set up cron job (monthly run):**
```bash
# Install crontab
crontab -e

# Add line (runs 1st of each month at 2am)
0 2 1 * * /opt/deal_finder/deploy/schedule.sh >> /var/log/deal_finder_cron.log 2>&1
```

**2. Make script executable:**
```bash
chmod +x deploy/schedule.sh
```

**3. Test manually:**
```bash
./deploy/schedule.sh
```

### Option 2: Airflow (Advanced)

**1. Create Airflow DAG:**
```python
# dags/deal_finder_dag.py
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email': ['alerts@yourcompany.com'],
    'email_on_failure': True,
    'retries': 2,
    'retry_delay': timedelta(hours=1),
}

dag = DAG(
    'deal_finder_pipeline',
    default_args=default_args,
    description='Monthly biotech deals pipeline',
    schedule_interval='0 2 1 * *',  # Monthly, 1st at 2am
    catchup=False,
)

run_pipeline = BashOperator(
    task_id='run_deal_finder',
    bash_command='cd /opt/deal_finder && docker-compose up --abort-on-container-exit',
    dag=dag,
)
```

### Option 3: GitHub Actions (Cloud)

**1. Create workflow:**
```yaml
# .github/workflows/monthly.yml
name: Monthly Deal Finder Run

on:
  schedule:
    - cron: '0 2 1 * *'  # Monthly, 1st at 2am UTC
  workflow_dispatch:  # Manual trigger

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up environment
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          NEWSAPI_ORG_KEY: ${{ secrets.NEWSAPI_ORG_KEY }}
        run: |
          echo "OPENAI_API_KEY=$OPENAI_API_KEY" >> .env
          echo "NEWSAPI_ORG_KEY=$NEWSAPI_ORG_KEY" >> .env

      - name: Run pipeline
        run: docker-compose up --abort-on-container-exit

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: deals-output
          path: output/
```

---

## Monitoring & Alerts

### Built-in Monitoring

The pipeline automatically logs metrics to `output/metrics.jsonl`:

```json
{
  "run_id": "abc123",
  "timestamp": "2025-01-15T02:00:00Z",
  "status": "SUCCESS",
  "duration_seconds": 1823.5,
  "stats": {
    "total_deals": 45,
    "needs_review_count": 12,
    "needs_review_pct": 26.7,
    "quality_issues": []
  }
}
```

### Slack Alerts

**1. Create Slack webhook:**
- Go to https://api.slack.com/apps
- Create app → Incoming Webhooks
- Copy webhook URL

**2. Add to `.env`:**
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**3. Enable in config:**
```yaml
# config/production.yaml
ENABLE_ALERTS: true
```

**Alerts sent for:**
- ❌ Pipeline failures
- ⚠️ Quality issues (>80% needs review)
- ⚠️ Missing data (>50% no financials)

### CloudWatch / Datadog Integration

**TODO**: Extend `monitoring.py` to push metrics:

```python
# deal_finder/monitoring.py
def _send_metrics_to_cloudwatch(self, metrics):
    import boto3
    cloudwatch = boto3.client('cloudwatch')
    cloudwatch.put_metric_data(
        Namespace='DealFinder',
        MetricData=[
            {
                'MetricName': 'DealsFound',
                'Value': metrics['total_deals'],
                'Unit': 'Count'
            }
        ]
    )
```

---

## Scaling & Performance

### Horizontal Scaling

**Run multiple therapeutic areas in parallel:**

```bash
# docker-compose-parallel.yml
version: '3.8'
services:
  immunology:
    build: .
    environment:
      - THERAPEUTIC_AREA=immunology_inflammation
    volumes:
      - ./output/immunology:/app/output

  neurology:
    build: .
    environment:
      - THERAPEUTIC_AREA=neurology
    volumes:
      - ./output/neurology:/app/output

  oncology:
    build: .
    environment:
      - THERAPEUTIC_AREA=oncology
    volumes:
      - ./output/oncology:/app/output
```

```bash
docker-compose -f docker-compose-parallel.yml up
```

### Performance Tuning

**1. Increase discovery speed:**
```yaml
# config/production.yaml
REQUEST_RATE_LIMIT_PER_DOMAIN_PER_MIN: 60  # Faster (if API allows)
MAX_RESULTS_PER_CYCLE: 500  # More aggressive
DRY_RUNS_TO_CONVERGE: 2  # Fewer cycles
```

**2. Resource allocation:**
```yaml
# docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '4'  # More CPUs
      memory: 8G  # More RAM
```

**3. Enable translation caching:**
```yaml
# Already enabled by default
LANGUAGE_POLICY:
  CACHE_TRANSLATIONS: true
```

---

## Troubleshooting

### No deals found

**Check:**
1. API keys are valid: `echo $NEWSAPI_ORG_KEY`
2. TA vocabulary is correct: `cat config/ta_vocab/yourta.json`
3. Date range is reasonable: `START_DATE: "2021-01-01"`
4. Check logs: `docker-compose logs | grep "Discovered"`

### High "needs review" rate (>80%)

**Normal causes:**
- Ambiguous stage mentions (phase 1/2)
- No explicit TA match in text
- Missing financial amounts

**Not a bug** - this is by design (false negative prevention)

**Solution:**
- Manually review flagged items
- Update TA vocab to be more specific
- Add more synonyms to improve matching

### API rate limits

**NewsAPI.org limits:**
- Free: 100 req/day (NOT suitable)
- Pro: Unlimited

**Solution:**
- Upgrade to paid tier
- Use multiple API sources
- Reduce `REQUEST_RATE_LIMIT_PER_DOMAIN_PER_MIN`

### Translation failures

**Check:**
- Internet connectivity
- Translation cache: `ls .cache/translations/`
- Provider availability (Google Translate API)

**Fallback:**
- Returns original text if translation fails
- Pipeline continues (no critical failure)

### Docker build fails

```bash
# Clear cache and rebuild
docker-compose down
docker system prune -a
docker-compose build --no-cache
docker-compose up
```

---

## Cost Breakdown (Production)

### Monthly Costs

| Service | Cost | Required? |
|---------|------|-----------|
| NewsAPI.org Pro | $449/month | Recommended |
| OpenAI (TA vocab) | $0.01 one-time | Required |
| Translation (cached) | $0/month | Included |
| AWS EC2 t3.medium | ~$30/month | If cloud hosting |
| S3 storage (10GB) | ~$0.23/month | Optional |
| **Total (with NewsAPI)** | **~$479/month** | |
| **Total (with scraping)** | **~$30/month** | Dev only |

### Enterprise Alternative

**PR Newswire + Business Wire APIs:**
- Cost: $2,000-10,000/month
- Better coverage, more reliable
- Worth it for serious biotech deal tracking

---

## Next Steps

1. ✅ Set up API keys
2. ✅ Configure therapeutic area
3. ✅ Test locally: `docker-compose up`
4. ✅ Deploy to production server
5. ✅ Set up cron/Airflow scheduling
6. ✅ Configure Slack alerts
7. ✅ Run first monthly update
8. ✅ Review results and iterate

**Support**: File issues at https://github.com/yourorg/deal_finder/issues
