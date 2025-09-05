# Railway PostgreSQL Setup

## Railway CLI Commands

### 1. Login to Railway (if not already)
```bash
railway login
```

### 2. Link your project (if not already linked)
```bash
railway link
```

### 3. Add PostgreSQL to your Railway project
```bash
railway add postgresql
```

### 4. Deploy the changes
```bash
railway up
```

## Alternative: Railway Dashboard Setup

If you prefer using the Railway dashboard:

1. Go to your Railway project dashboard
2. Click "New" → "Database" → "Add PostgreSQL"
3. Railway will automatically:
   - Create the PostgreSQL instance
   - Add the `DATABASE_URL` environment variable to your service
   - The server will automatically detect and use it

## How it Works

- The server automatically detects if `DATABASE_URL` is set
- If PostgreSQL is available, it will:
  - Create a `pool_summaries` table automatically
  - Store all pool analysis results persistently
  - Survive deployments and restarts
- If PostgreSQL is not available, it falls back to:
  - In-memory storage (lost on restart)
  - File-based storage (lost on Railway deployment)

## Database Schema

The server automatically creates this table:

```sql
CREATE TABLE pool_summaries (
    pool_address VARCHAR(42) PRIMARY KEY,
    tokens VARCHAR(100),
    current_nav NUMERIC(20, 2),
    nav_apr VARCHAR(20),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Verifying the Setup

After deployment, you can verify PostgreSQL is working by:

1. Checking the Railway logs for "Connected to PostgreSQL"
2. Analyzing a pool on the main page
3. Checking the summary page - data should persist after redeployments

## Notes

- The `psycopg2-binary` package is included in requirements.txt
- The server gracefully falls back if PostgreSQL is unavailable
- All existing features continue to work with or without PostgreSQL