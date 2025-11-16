# Cloud Deployment Guide - Deal Finder Pipeline

Quick comparison and setup for running the pipeline in the cloud.

## 📊 Cost Comparison (10-hour run)

| Option | Cost | Setup Time | Best For |
|--------|------|------------|----------|
| **Modal** | $3-10 | 5 min | Easiest, ML-friendly |
| **AWS Spot** | $0.50-1.50 | 10 min | Cheapest |
| **Railway** | $5-20 | 3 min | Simplest (git-based) |
| **Google Cloud Run Jobs** | $2-8 | 15 min | Good for <9hr runs |
| **Fly.io** | $5-15 | 10 min | Simple, good DX |

---

## 🥇 Option 1: Modal (Recommended)

**Best for:** Easiest setup, ML workloads, pay-per-second billing

### Setup

```bash
# 1. Install Modal
pip install modal

# 2. Create account and authenticate
modal token new

# 3. Create secret for OpenAI key
modal secret create openai-secret OPENAI_API_KEY=sk-your-key-here

# 4. Run pipeline
modal run modal_pipeline.py
```

### Resume from checkpoint

```bash
modal run modal_pipeline.py::resume_pipeline
```

### Monitor

```bash
modal app logs deal-finder
```

### Download outputs

```bash
modal volume get deal-finder-checkpoints output/
```

**Pros:**
- ✅ Handles Selenium/Chrome automatically
- ✅ Built-in secrets management
- ✅ Great for ML (sentence transformers)
- ✅ Pay-per-second billing
- ✅ Easy checkpoint management with volumes

**Cons:**
- ❌ Requires learning Modal CLI (minimal)

---

## 🥈 Option 2: AWS EC2 Spot Instances

**Best for:** Lowest cost, long-running jobs

### Setup

```bash
# 1. Install AWS CLI
pip install awscli
aws configure

# 2. Create key pair (if you don't have one)
aws ec2 create-key-pair --key-name deal-finder-key --query 'KeyMaterial' --output text > ~/.ssh/deal-finder-key.pem
chmod 400 ~/.ssh/deal-finder-key.pem

# 3. Run setup script
bash aws_spot_setup.sh
```

### Connect and run

```bash
# SSH into instance
ssh -i ~/.ssh/deal-finder-key.pem ubuntu@<PUBLIC_IP>

# Copy code to instance
scp -i ~/.ssh/deal-finder-key.pem -r . ubuntu@<PUBLIC_IP>:~/deal_finder

# Run pipeline
cd deal_finder
export OPENAI_API_KEY="sk-your-key-here"
nohup python step2_run_pipeline.py --config config/config.yaml > pipeline.log 2>&1 &

# Monitor
tail -f pipeline.log
```

### Handle spot interruption

Spot instances can be interrupted with 2-minute warning. Your checkpoints handle this gracefully:

```bash
# If interrupted, just restart from checkpoint
python step2_run_pipeline.py --config config/config.yaml --skip-fetch
```

### Download results

```bash
# From your local machine
scp -i ~/.ssh/deal-finder-key.pem -r ubuntu@<PUBLIC_IP>:~/deal_finder/output ./
```

**Pros:**
- ✅ 70-90% cheaper than on-demand
- ✅ Full control over environment
- ✅ No vendor lock-in

**Cons:**
- ❌ Can be interrupted (but checkpoints handle this)
- ❌ More manual setup

---

## 🥉 Option 3: Railway

**Best for:** Git-based deployment, simplicity

### Setup

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login
railway login

# 3. Initialize project
railway init

# 4. Add OpenAI secret
railway variables --set OPENAI_API_KEY=sk-your-key-here

# 5. Deploy
git add .
git commit -m "Deploy to Railway"
railway up
```

### Monitor

```bash
railway logs
```

### Download results

```bash
# Railway provides persistent volumes - check Railway dashboard
```

**Pros:**
- ✅ Dead simple git-based deployment
- ✅ Automatic rebuilds on push
- ✅ Nice web dashboard

**Cons:**
- ❌ More expensive than spot instances
- ❌ May need to configure for long runs

---

## 🎯 Recommended Setup: Modal + Auto-Restart

Create a cron job to auto-restart if interrupted:

```python
# modal_cron_pipeline.py
import modal

app = modal.App("deal-finder-cron")

@app.function(
    schedule=modal.Cron("0 */6 * * *"),  # Every 6 hours
    timeout=21600,  # 6 hour timeout
    secrets=[modal.Secret.from_name("openai-secret")],
)
def run_checkpoint_pipeline():
    """Run pipeline, resuming from last checkpoint."""
    import subprocess
    result = subprocess.run(
        ["python", "step2_run_pipeline.py", "--skip-fetch"],
        capture_output=True
    )
    return result.returncode
```

Deploy:
```bash
modal deploy modal_cron_pipeline.py
```

---

## 💡 Cost Optimization Tips

### 1. Use checkpoints strategically

Your pipeline already has great checkpointing. Use `--skip-*` flags to resume:

```bash
# Skip crawling (use cached URLs)
python step2_run_pipeline.py --skip-crawl

# Skip fetching (use cached articles)
python step2_run_pipeline.py --skip-fetch

# Skip extraction (use cached extractions)
python step2_run_pipeline.py --skip-extraction
```

### 2. Split into smaller jobs

Run each step separately to minimize costs if interrupted:

```bash
# Step 1: Crawl only
python step2_run_pipeline.py --skip-extraction --skip-parsing

# Step 2: Extract only
python step2_run_pipeline.py --skip-crawl --skip-fetch --skip-parsing

# Step 3: Parse only
python step2_run_pipeline.py --skip-crawl --skip-fetch --skip-extraction
```

### 3. Use spot/preemptible instances

- AWS Spot: 70-90% discount
- GCP Preemptible: 80% discount
- Azure Spot: 70-90% discount

Your checkpoints make this safe!

---

## 🚨 Troubleshooting

### Selenium/Chrome issues

If Chrome fails in cloud:

```python
# Update SeleniumWebClient to use headless Chrome
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
```

### Out of memory during embeddings

Reduce batch size in deduplication:

```python
# In openai_extractor.py, line 58
embeddings = model.encode(texts, show_progress_bar=True, batch_size=128)  # Reduced from 256
```

### OpenAI rate limits

Add retry logic is already in place. If still hitting limits:

```python
# In openai_extractor.py, increase backoff
wait_time = (2 ** attempt) * 10.0  # Increased from 5.0
```

---

## 📦 Requirements

Make sure `requirements.txt` includes:

```txt
selenium
beautifulsoup4
lxml
openai
python-dotenv
openpyxl
pandas
pydantic
sentence-transformers
scikit-learn
torch
```

---

## 🎬 Quick Start (Modal)

```bash
# 1. Install
pip install modal

# 2. Auth
modal token new

# 3. Set secret
modal secret create openai-secret OPENAI_API_KEY=sk-...

# 4. Run
modal run modal_pipeline.py

# Done! ✅
```

Total time: **5 minutes**
