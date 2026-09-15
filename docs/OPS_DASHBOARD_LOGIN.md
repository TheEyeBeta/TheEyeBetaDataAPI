# One-time: save an official ops dashboard client secret (PowerShell)

Run **once**. Prints the durable client secret for `admin-tool-production`.
Store it in your password manager, then use **Sign in** on the ops dashboard
(Client ID + secret). Do **not** re-run this every visit.

```powershell
ssh macmini @'
set -euo pipefail
cd /home/the-eye-beta/TheEyeBeta2025/TheEyeBetaDataAPI
set -a
. ./.env
set +a
LIVE="${DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
LIVE="${LIVE/postgresql+psycopg2:\/\//postgresql:\/\/}"
CLIENT_ID="admin-tool-production"
# api_key is the secret; secret_prefix is for operators — print secret only
psql "$LIVE" -Atc "SELECT api_key FROM iam.issue_service_api_key('${CLIENT_ID}', 'ops-dashboard-stable', NULL);" | head -1
'@
```

Then open:

- `https://dataapiprod.theeyebeta.store/api/v1/admin/dashboard`
- or `http://127.0.0.1:7000/api/v1/admin/dashboard` (with `ssh -N -L 7000:127.0.0.1:7000 macmini`)

Sign in with:

- Client ID: `admin-tool-production`
- Client secret: *(value from the command above)*
