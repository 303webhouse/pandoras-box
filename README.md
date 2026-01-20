# 📦 Pandora's Box

Real-time trading signal dashboard with multi-device sync and sub-100ms latency.

## Features

- **Real-time Signal Processing**: TradingView webhooks → validated signals in <100ms
- **Multi-Device Sync**: WebSocket broadcasts to computer, laptop, and phone simultaneously
- **Approved Strategies**: Triple Line Trend Retracement with ADX filtering
- **Bias Filtering**: TICK Range Breadth Model for macro alignment
- **Signal Classification**: APIS CALL, KODIAK CALL, BULLISH TRADE, BEAR CALL
- **Backtesting Ready**: All signals logged to PostgreSQL for analysis
- **Progressive Web App**: Install on phone without app store

## Architecture

```
TradingView Alert → FastAPI → Strategy Validator → Bias Filter → 
Signal Scorer → Redis Cache → PostgreSQL Log → WebSocket Broadcast → All Devices
```

**Target Latency**: <100ms total (webhook → device update)

## Setup Instructions

### Prerequisites

- Python 3.10+
- Redis (local or cloud)
- PostgreSQL (local or cloud)
- Modern web browser

### Backend Setup

1. **Install dependencies**:
```bash
cd backend
pip install -r requirements.txt --break-system-packages
```

2. **Configure environment**:
```bash
cp ../config/.env.example ../config/.env
# Edit .env with your database credentials
```

3. **Initialize database**:
```python
python -c "
from backend.database.postgres_client import init_database
import asyncio
asyncio.run(init_database())
"
```

4. **Start backend**:
```bash
python main.py
```

Backend runs on `http://localhost:8000`

### Frontend Setup

1. **Serve frontend**:
```bash
cd frontend
python -m http.server 3000
```

Frontend runs on `http://localhost:3000`

### Deployment (Free Tier)

**Backend** (Railway or Render):
1. Connect GitHub repo
2. Set environment variables
3. Deploy from `backend/` directory

**Frontend** (Vercel or Netlify):
1. Connect GitHub repo
2. Set build directory to `frontend/`
3. Deploy

**Databases**:
- Redis: Upstash (10k commands/day free)
- PostgreSQL: Supabase (500MB free)

## TradingView Webhook Setup

1. Create alert in TradingView for your strategy
2. Set webhook URL: `https://your-backend-url.com/webhook/tradingview`
3. Set alert message (JSON):
```json
{
  "ticker": "{{ticker}}",
  "strategy": "Triple Line Trend Retracement",
  "direction": "LONG",
  "entry_price": {{close}},
  "stop_loss": {{low}},
  "target_1": {{high}},
  "adx": 32.5,
  "line_separation": 15.2,
  "timeframe": "DAILY"
}
```

## Project Structure

```
trading-hub/
├── docs/                      # Strategy & indicator documentation
│   ├── approved-strategies/
│   ├── approved-bias-indicators/
│   └── architecture/
├── backend/                   # Python FastAPI server
│   ├── main.py               # Entry point
│   ├── webhooks/             # TradingView webhook receiver
│   ├── strategies/           # Strategy validators
│   ├── bias_filters/         # Bias alignment checks
│   ├── scoring/              # Signal classification
│   ├── database/             # Redis + PostgreSQL clients
│   ├── websocket/            # Real-time broadcaster
│   └── api/                  # REST endpoints
├── frontend/                  # HTML/CSS/JS PWA
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── manifest.json
├── config/                    # Environment variables
└── data/                      # Local data storage
```

## Usage

### Viewing Signals

1. Open dashboard on any device
2. Select timeframe (Daily/Weekly/Monthly)
3. View top 10 equity signals + crypto signals
4. Click **SELECT** to move to Open Positions
5. Click **DISMISS** to remove from view

### Adding Strategies

1. Document strategy in `docs/approved-strategies/`
2. Create validator in `backend/strategies/`
3. Register in webhook processor
4. Deploy backend

### Adding Bias Filters

1. Document indicator in `docs/approved-bias-indicators/`
2. Create filter in `backend/bias_filters/`
3. Add to signal processor pipeline
4. Deploy backend

## Performance Targets

- Webhook receipt → validation: <10ms
- Bias filter check: <5ms
- Redis cache write: <2ms
- WebSocket broadcast: <5ms
- **Total latency: <30ms**

## Mobile Installation

### iPhone:
1. Open dashboard in Safari
2. Tap Share → Add to Home Screen
3. App installs like native app

### Android:
1. Open dashboard in Chrome
2. Tap menu → Install app
3. App installs to home screen

## Future Enhancements

- [ ] Custom signal icons (APIS, KODIAK, etc.)
- [ ] Pandora's Box logo design
- [ ] Broker API integrations (when available)
- [ ] Automated trade execution
- [ ] Advanced backtesting interface
- [ ] Black Swan detection integration
- [ ] Alpha Feed social sentiment

## Support

For questions or issues, check the docs in `docs/architecture/` or review the inline code comments.

---

**Built for speed. Designed for multi-device. Ready to scale.**
