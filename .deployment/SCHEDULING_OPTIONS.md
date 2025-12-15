# Scheduling Options

## Recommended: Prefect Cloud

Serverless, hands-off, observable.

```bash
prefect cloud login
python .deployment/deploy_scheduled.py
```

See [PREFECT_CLOUD_SETUP.md](./PREFECT_CLOUD_SETUP.md).

---

## Alternative: macOS Cron

For local-only execution (requires machine to be on).

### Setup
```bash
crontab -e
```

Add:
```bash
# Weekly on Sunday at 6:00 AM
0 6 * * 0 cd /Volumes/Research/GitHub/internal_research_ops && python -m litintel.cli tier1 >> /tmp/litintel.log 2>&1
```

### Cron Format
```
* * * * *
│ │ │ │ └── Day of week (0=Sun)
│ │ │ └──── Month
│ │ └────── Day
│ └──────── Hour
└────────── Minute
```

---

## Comparison

| Method | Pros | Cons |
|--------|------|------|
| Prefect Cloud | No servers, web UI, alerts | Cloud account |
| Cron | Simple, no dependencies | Manual monitoring |
