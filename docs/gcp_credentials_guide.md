# GCP Credentials & Authentication Guide -- Litintel

> Last updated: 2026-04-25
>
> This document captures every credential-related issue we have hit and how to
> fix each one. Read this before touching any auth config or migrating projects.

---

## 1. Architecture: Three Separate Credential Types

Litintel uses **three distinct Google authentication mechanisms**. Each serves a
different purpose and they must NOT be mixed.

```
+---------------------------+-------------------------------------+---------------------------+
| Credential Type           | What It Authenticates               | Env Var / File            |
+---------------------------+-------------------------------------+---------------------------+
| Service Account JSON      | Vertex AI (Gemini inference, RAG)   | GOOGLE_APPLICATION_       |
|                           |                                     | CREDENTIALS               |
+---------------------------+-------------------------------------+---------------------------+
| OAuth Client Secret JSON  | Google Drive (personal account)     | GOOGLE_DRIVE_CLIENT_      |
| (Desktop App type)        |                                     | SECRET                    |
+---------------------------+-------------------------------------+---------------------------+
| Cached OAuth Token        | Google Drive (cached after first    | token.json (auto-         |
|                           | browser consent)                    | generated, gitignored)    |
+---------------------------+-------------------------------------+---------------------------+
```

### How the code resolves credentials

**Vertex AI** (`src/litintel/enrich/ai_client.py`):
1. `GOOGLE_APPLICATION_CREDENTIALS` env var (Service Account JSON) -- **highest priority**
2. Application Default Credentials from `gcloud auth application-default login`
3. Metadata server (only on GCP VMs)

**Google Drive** (`src/litintel/storage/drive.py`):
1. Explicit `credentials_path` arg (Service Account) -- checks for `"type": "service_account"`
2. `GOOGLE_DRIVE_CLIENT_SECRET` env var (OAuth Client Secret) -- triggers browser login flow
3. Falls back to `GOOGLE_CLIENT_SECRETS_PATH` (legacy env var name)
4. Application Default Credentials as last resort

> [!IMPORTANT]
> The Service Account used for Vertex AI **cannot** access your personal Google
> Drive. Drive requires either a shared-domain Service Account or an OAuth flow
> with your personal Google account.

---

## 2. Current Setup

### Files on disk

Store all credential files in a **single directory outside the repo** (e.g.,
`~/credentials/` or any secure location). This directory should contain:

```
<credentials-dir>/
  <project>-<hash>.json                   # Service Account key (Vertex AI)
  client_secret_<id>.json                  # OAuth Client Secret (Drive)
  application_default_credentials.json     # ADC -- NOT used by Litintel directly
```

### .env configuration

```bash
# -- Vertex AI --
GCP_PROJECT_ID='<your-personal-project-id>'
GCP_LOCATION='global'
USE_VERTEX_AI=true
GOOGLE_APPLICATION_CREDENTIALS="<credentials-dir>/<service-account-key>.json"

# -- Google Drive --
GOOGLE_DRIVE_CLIENT_SECRET="<credentials-dir>/<client-secret>.json"
GOOGLE_DRIVE_FOLDER_ID="<your-drive-folder-id>"
```

### Why this setup exists

Your `gcloud` CLI may be configured to a **different project** (e.g., a company
project) for day-job work. Without `GOOGLE_APPLICATION_CREDENTIALS`, the Vertex
AI SDK would pick up the company ADC and fail when trying to access your
personal project resources. The Service Account JSON decouples Litintel from
the CLI entirely.

---

## 3. Troubleshooting: Errors We Have Hit

### Error: "Client secrets must be for a web or installed app"

**Cause:** `GOOGLE_DRIVE_CLIENT_SECRET` (or legacy `GOOGLE_CLIENT_SECRETS_PATH`)
is pointing to the wrong file type.

| File Type               | JSON `"type"` field     | Works for Drive OAuth? |
|--------------------------|-------------------------|------------------------|
| Service Account key      | `"service_account"`     | NO                     |
| ADC (from gcloud auth)   | `"authorized_user"`     | NO                     |
| OAuth Client Secret      | has `"installed"` key   | YES                    |

**Fix:** Download a new OAuth Client Secret:
1. [GCP Console -> APIs & Services -> Credentials](https://console.cloud.google.com/apis/credentials) (select your project)
2. Click **+ Create Credentials -> OAuth client ID**
3. Application type: **Desktop app**
4. Download JSON -> save to your credentials directory (outside the repo)
5. Update `GOOGLE_DRIVE_CLIENT_SECRET` in `.env`

**How to verify file type:**
```bash
python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
if 'installed' in d: print('OAuth Client Secret (Desktop) -- CORRECT for Drive')
elif d.get('type') == 'service_account': print('Service Account -- WRONG for Drive')
elif d.get('type') == 'authorized_user': print('ADC -- WRONG for Drive')
else: print('Unknown:', list(d.keys())[:5])
" /path/to/your/file.json
```

---

### Error: "Access blocked: Litintel has not completed the Google verification process" (403)

**Cause:** The OAuth Consent Screen is in **"Testing"** mode, and your email
is not in the Test Users list. Google blocks all non-listed users.

**Fix (recommended -- publish the app):**
1. Go to [OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent) (select your project)
2. Under **Publishing status**, click **PUBLISH APP**
3. Confirm the popup

This removes the Test Users restriction entirely. Since you are the only user,
you do not need to submit for Google verification. You will see an "Unverified
app" warning on first login -- click **Advanced -> Go to Litintel (unsafe)**.

**Alternative fix (add test user):**
1. Same page, scroll to **Test users** section
2. Click **+ ADD USERS** -> enter your email -> **SAVE**

> [!WARNING]
> "PUBLISH APP" is simpler and permanent. The Test Users approach is fragile:
> sometimes Google takes minutes to propagate, and users report the list
> silently failing.

---

### Error: "Your active project does not match the quota project in your local ADC file"

**Cause:** You ran `gcloud auth application-default login` while on one project
and then switched your CLI to a different project. The CLI notices the mismatch
and warns you.

**Fix:** This warning is harmless for Litintel because we use
`GOOGLE_APPLICATION_CREDENTIALS` (Service Account), which bypasses ADC entirely.
If the warning bothers you for your company work:
```bash
gcloud auth application-default set-quota-project <your-company-project-id>
```

---

### Error: Vertex AI returns 403 / "Permission Denied" after switching gcloud projects

**Cause:** Without `GOOGLE_APPLICATION_CREDENTIALS`, the Vertex AI SDK reads
`~/.config/gcloud/application_default_credentials.json`, which is tied to
whatever project you last ran `gcloud auth application-default login` on.

**Fix:** Set `GOOGLE_APPLICATION_CREDENTIALS` in `.env` to a Service Account
JSON that belongs to your personal project. This completely decouples Litintel
from the CLI.

---

### Stale token.json causing repeated auth failures

**Cause:** After changing credential files, the cached `token.json` in the
project root may hold an expired or wrong-project token.

**Fix:**
```bash
rm token.json   # from the project root
# Then re-run the pipeline -- a fresh browser login will be triggered
```

---

## 4. Multi-Project CLI Coexistence

### The Problem

Your `gcloud` CLI serves your company project. Litintel needs your personal
project. If both share the same ADC, switching the CLI breaks the pipeline.

### The Solution: Service Account Isolation

```
gcloud CLI (company project)          Litintel (personal project)
  |                                       |
  v                                       v
~/.config/gcloud/                   GOOGLE_APPLICATION_CREDENTIALS
application_default_credentials.json   (Service Account JSON)
  |                                       |
  v                                       v
<company-project-id>                 <personal-project-id>
```

**Rules:**
1. Never run `gcloud auth application-default login` expecting Litintel to use it
2. Always keep `GOOGLE_APPLICATION_CREDENTIALS` set in `.env`
3. The CLI project setting (`gcloud config set project`) has zero effect on Litintel

---

## 5. Security Checklist

- [x] `.env` is in `.gitignore`
- [x] `token.json` is in `.gitignore`
- [x] `client_secret.json` is in `.gitignore`
- [x] Credential JSON files live outside the repo (in a secure directory)
- [ ] Service Account key rotated every 90 days (set a calendar reminder)
- [ ] OAuth Consent Screen set to minimum scopes (`drive.file` only)

> [!CAUTION]
> **Never commit credential files to git.** Service Account keys are permanent
> until manually rotated. If leaked, an attacker gets full access to your
> Vertex AI quota and any Drive folders shared with the service account.

---

## 6. Migration Checklist: Moving to Company GCP Project

When you are ready to migrate Litintel from your personal project to a company
project, follow these steps:

### Pre-Migration

- [ ] Confirm which APIs are enabled on the company project:
  - Vertex AI API
  - Google Drive API (if Drive sync will run from company infra)
  - Cloud Resource Manager API (for RAG corpus)
- [ ] Confirm IAM permissions: your account or a new Service Account needs
  `Vertex AI User` (minimum) or `Vertex AI Admin` (if managing RAG corpora)
- [ ] Decide: will Google Drive sync still use your personal Drive, or move to
  a Shared Drive owned by the company?

### Migration Steps

1. **Create a new Service Account** in the company project
   - IAM role: `Vertex AI User`
   - Download JSON key
   - Store in a secure credentials directory (company-approved location)

2. **Update `.env`**
   ```bash
   GCP_PROJECT_ID='<company-project-id>'
   GOOGLE_APPLICATION_CREDENTIALS="/path/to/company_service_account.json"
   ```

3. **Re-create RAG Corpus** (corpus IDs are project-scoped)
   ```bash
   python scripts/create_rag_corpus.py
   # Update VERTEX_RAG_CORPUS_NAME in .env with the new value
   ```

4. **Google Drive decision:**
   - **Keep personal Drive:** No change needed. OAuth Client Secret stays the same.
   - **Move to company Shared Drive:** Create a new OAuth Client Secret under
     the company project, or use a company Service Account with domain-wide
     delegation. Share the Shared Drive folder with the service account email.

5. **Test end-to-end**
   ```bash
   python scripts/test_drive_sync.py 41972735
   python scripts/run_pipeline.py
   ```

### Post-Migration

- [ ] Revoke the old personal Service Account key (GCP Console -> IAM -> Service Accounts)
- [ ] Update `VERTEX_RAG_CORPUS_NAME` (old corpus in personal project is now orphaned)
- [ ] Verify billing: company project should absorb all Vertex AI costs
- [ ] If using company Shared Drive: verify folder permissions and Drive API quotas

---

## 7. Quick Reference: Credential File Identification

```bash
# Run this to identify any GCP JSON file:
python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
if 'installed' in d:
    print(f'OAuth Client Secret (Desktop App)')
    print(f'  Project: {d[\"installed\"].get(\"project_id\", \"unknown\")}')
elif 'web' in d:
    print(f'OAuth Client Secret (Web App)')
elif d.get('type') == 'service_account':
    print(f'Service Account Key')
    print(f'  Project: {d.get(\"project_id\", \"unknown\")}')
    print(f'  Email:   {d.get(\"client_email\", \"unknown\")}')
elif d.get('type') == 'authorized_user':
    print(f'Application Default Credentials (ADC)')
    print(f'  Quota Project: {d.get(\"quota_project_id\", \"unknown\")}')
else:
    print(f'Unknown type. Keys: {list(d.keys())[:5]}')
" /path/to/file.json
```

---

## 8. Test Scripts

### Test Drive sync only
```bash
python scripts/test_drive_sync.py 41972735
```

### Verify which credentials Litintel will use
```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
sa = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '(not set)')
ds = os.environ.get('GOOGLE_DRIVE_CLIENT_SECRET', '(not set)')
pj = os.environ.get('GCP_PROJECT_ID', '(not set)')
print(f'Vertex AI Service Account: {sa}')
print(f'Drive Client Secret:       {ds}')
print(f'Target Project:            {pj}')
import pathlib
for label, path in [('SA', sa), ('Drive', ds)]:
    p = pathlib.Path(path)
    if p.exists():
        print(f'  {label}: file exists, {p.stat().st_size} bytes')
    elif path != '(not set)':
        print(f'  {label}: FILE NOT FOUND!')
"
```
