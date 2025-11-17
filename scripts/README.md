# Article Crawl & Embed Scripts

This folder contains the main scripts for the two-stage crawl & embed pipeline.

## Scripts

### `crawl.py` - Stage 1: Fetch Article Content
Discovers URLs and fetches article content (no embeddings).

```bash
# Full crawl from 2021
python scripts/crawl.py --start-date 2021-01-01

# Recent articles
python scripts/crawl.py --start-date 2025-01-01

# Custom workers and checkpointing
python scripts/crawl.py --workers 50 --checkpoint-every 500
```

### `embed.py` - Stage 2: Generate Embeddings
Processes pending articles and generates embeddings for ChromaDB.

```bash
# Embed all pending articles
python scripts/embed.py

# Embed with custom batch size
python scripts/embed.py --batch-size 250

# Retry failed articles
python scripts/embed.py --retry-failed
```

### `update.py` - Incremental Update (Crawl + Embed)
Combines both stages for daily/weekly updates.

```bash
# Daily update (yesterday to today)
python scripts/update.py

# Weekly update
python scripts/update.py --start-date 2025-01-09

# Custom date range
python scripts/update.py --start-date 2025-01-01 --end-date 2025-01-15
```

## Quick Start

**First-time setup:**
```bash
# 1. Clear old URL index
rm output/url_index.json

# 2. Crawl articles
nohup python scripts/crawl.py --start-date 2021-01-01 > logs/crawl.log 2>&1 &

# 3. When crawl finishes, embed
nohup python scripts/embed.py > logs/embed.log 2>&1 &
```

**Daily updates:**
```bash
# Set up cron job
0 2 * * * cd /path/to/deal_finder && python scripts/update.py >> logs/daily_update.log 2>&1
```

## Documentation

See **[docs/CRAWL_EMBED_WORKFLOW.md](../docs/CRAWL_EMBED_WORKFLOW.md)** for complete documentation.
