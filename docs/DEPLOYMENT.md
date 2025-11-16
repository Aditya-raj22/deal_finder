# Deployment Guide

## Deployment Architecture

Your Deal Finder app has two components:
1. **Frontend** - Static HTML/CSS/JS files (in `static/` folder)
2. **Backend** - FastAPI server with WebSocket support (`ui_server.py`)

## Recommended Deployment: Railway (All-in-One)

**Railway** is the easiest option - it hosts both frontend and backend together.

### Steps:

1. **Push your code to GitHub**
   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push origin main
   ```

2. **Deploy to Railway**
   - Go to [railway.app](https://railway.app)
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your `deal_finder` repository
   - Railway auto-detects `deploy/railway.json` and deploys
   - Add environment variable: `OPENAI_API_KEY=your-key-here`

3. **Your app is live!**
   - Railway provides a URL like `https://deal-finder.up.railway.app`
   - Users can access the UI and run pipelines

**Cost:** ~$5-10/month (Railway hobby plan)

---

## Alternative: Vercel (Frontend) + Railway (Backend)

If you want to separate frontend and backend:

### Frontend on Vercel (Static Only)

1. **Update `static/app.js`** to point to your Railway backend URL:
   ```javascript
   const API_URL = 'https://your-backend.railway.app';
   ```

2. **Deploy to Vercel**:
   ```bash
   npm i -g vercel
   vercel
   ```
   - Point to project root
   - Vercel reads `deploy/vercel.json` configuration

3. **Backend on Railway** (same as above)

**Cost:** Vercel free tier + Railway $5-10/month

---

## Alternative: Modal (Serverless Backend)

**Note:** Modal is great for compute-heavy tasks but requires architecture changes for WebSocket support.

Current `ui_server.py` uses WebSocket for real-time updates, which doesn't work with Modal's serverless model. You'd need to:
- Remove WebSocket
- Use polling instead (check status every 5 seconds)
- Deploy pipeline execution as Modal functions

**Not recommended** unless you need serverless scaling.

---

## Environment Variables Needed

For any deployment, set these environment variables:

```bash
OPENAI_API_KEY=sk-...your-key...
```

Optional (for premium sources):
```bash
STAT_COOKIE=your-stat-cookie
```

---

## Testing Locally Before Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Run the UI server
python ui_server.py

# Open browser
open http://localhost:8000
```

---

## Quick Links

- **Railway**: https://railway.app
- **Vercel**: https://vercel.com
- **Modal**: https://modal.com

## Recommended: Railway
✅ Easiest setup
✅ Supports WebSocket
✅ Auto-deploys from GitHub
✅ Built-in SSL certificates
✅ Environment variable management
