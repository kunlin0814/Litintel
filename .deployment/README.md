# Admin/Deployment Configuration

## For Regular Users - Ignore This!

This directory is for **automated Prefect Cloud deployment**. Use **`python -m litintel.cli tier1`** locally.

See [README.md](../README.md) for usage.

---

## For Admins/Maintainers

**Deployment**: `tier1-pca-gold-standard`
**Flow**: `PCa-Tier1-GoldStandard-Pipeline`
**Schedule**: Biweekly, Monday 7:00 AM EST (Serverless).

### Quick Commands

```bash
# Deploy/update
python .deployment/deploy_scheduled.py

# Trigger manually
prefect deployment run 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'

# Pause
prefect deployment pause 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'

# Resume
prefect deployment resume 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'
```

See [PREFECT_CLOUD_SETUP.md](./PREFECT_CLOUD_SETUP.md) for initial setup.
