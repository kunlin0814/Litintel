# Prefect Cloud Setup

## Quick Start (5 minutes)

### 1. Create Prefect Cloud Account (Free)
Visit https://app.prefect.cloud and sign up.

### 2. Login from Terminal
```bash
cd /Volumes/Research/GitHub/internal_research_ops
prefect cloud login
```

### 3. Deploy
```bash
python .deployment/deploy_scheduled.py
```

### 4. Done!
Your pipeline is deployed:
- **Schedule**: Biweekly on Monday at 7:00 AM EST.
- **Serverless**: Runs in Prefect Cloud (no local machine needed).

---

## Monitoring

- **View Runs**: https://app.prefect.cloud -> Flows.
- **Logs**: Click any run for details.
- **Alerts**: Configure Slack/Email in Prefect Cloud settings.

---

## Management

| Action | Command |
|--------|---------|
| Trigger Now | `prefect deployment run 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'` |
| Pause | `prefect deployment pause 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'` |
| Resume | `prefect deployment resume 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'` |
| List | `prefect deployment ls` |

---

## Changing Schedule

Edit `.deployment/deploy_scheduled.py`:
```python
rrule="DTSTART:20251215T070000\nFREQ=WEEKLY;INTERVAL=2;BYDAY=MO"
```

Examples:
- Weekly: `FREQ=WEEKLY;INTERVAL=1`
- Monthly: `FREQ=MONTHLY;BYDAY=1MO`

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Run not triggering | Check `prefect deployment ls` and Work Pool status. |
| Missing env vars in Cloud | Set `NOTION_TOKEN`, `OPENAI_API_KEY` in Prefect Blocks or Variables. |

---

## Cost

Prefect Cloud Free Tier:
- 20,000 runs/month.
- Biweekly = ~2 runs/month. **Free.**
