# Outlook Email Processing Automation AI MVP — DeepSeek-compatible version

This project is a lightweight agentic workflow for fund operations email automation. It monitors a designated Outlook folder, classifies emails into operational task types, extracts structured action items, generates draft replies, and updates a local tracker. The system is intentionally human-in-the-loop: it creates drafts but does not automatically send emails.

It is coded during my internship at Pacific Synergy Group @ HK.

General Workflow:
```text
Outlook / Exchange folder: AI Intake
        ↓
Microsoft Graph API reads emails
        ↓
DeepSeek/OpenAI-compatible API classifies/extracts/drafts
        ↓
Creates Outlook reply drafts only, never sends
        ↓
Writes ops_email_tracker.csv
```
---

## 1. First-time Microsoft setup

### 1.1 Create an Outlook folder

In Outlook Web or Outlook desktop, create a top-level mail folder:

```text
AI Intake
```

For testing, copy or move 2-5 non-sensitive emails into this folder.

### 1.2 Register a Microsoft Entra app

Go to Microsoft Entra admin center / Azure portal:

```text
Microsoft Entra ID → App registrations → New registration
```

Recommended settings:

```text
Name: Outlook Ops AI Local Test
Supported account types: Accounts in this organizational directory only
Redirect URI: leave empty for device-code MVP
```

After creating the app, copy:

```text
Application (client) ID → MS_CLIENT_ID
Directory (tenant) ID → MS_TENANT_ID
```

### 1.3 Enable public client flow

In the app registration:

```text
Authentication → Advanced settings → Allow public client flows → Yes
```

This is needed for the local device-code login flow.

### 1.4 Add delegated Graph permissions

In the app registration:

```text
API permissions → Add a permission → Microsoft Graph → Delegated permissions
```

Add:

```text
User.Read
Mail.ReadWrite
```

Do **not** add `Mail.Send` for v1. This MVP creates drafts only and never sends emails.

Depending on tenant policy, user consent may be blocked. If login fails with consent/admin errors, ask IT/admin to grant delegated consent for `User.Read` and `Mail.ReadWrite` to this test app.

---

## 2. Local install

```bash
cd outlook_ops_ai_mvp_deepseek
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```text
MS_TENANT_ID=your-tenant-id
MS_CLIENT_ID=your-client-id

AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=your-deepseek-api-key
AI_MODEL=deepseek-v4-flash

MAIL_FOLDER=AI Intake
MAX_MESSAGES=5
DRY_RUN=true
```

For the first run, keep:

```text
DRY_RUN=true
```

This will classify and update the local tracker, but will not create Outlook drafts/categories.

---

## 3. Run

```bash
python run.py
```

First run will show a Microsoft device-code login message like:

```text
To sign in, use a web browser to open https://microsoft.com/devicelogin and enter code XXXXXXXX
```

After login, the script will:

1. Find the Outlook folder `AI Intake`.
2. Read recent messages.
3. Classify each message into an operational task.
4. Append one row per message to `ops_email_tracker.csv`.
5. If `DRY_RUN=false`, create Outlook reply drafts and add categories.


## 5. Safety policy

This MVP intentionally does not support automatic sending.

It only creates drafts. A human must review and click Send in Outlook.

High-risk items are always flagged for human review:

- wire transfer
- payment confirmation
- legal document
- investor-facing email
- ODD response
- subscription document
- NAV/fee/calculation-dependent answers
