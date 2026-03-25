# supervisor-secretvault.unifai

This directory is the first ownership boundary for supervisor-managed secrets.

Layout:

- `secrets/` — encrypted secret material intended to install into `/etc/little7/secrets`
- `grants/` — explicit grant artifacts
- `audit/` — lightweight audit records
- `config/` — secretvault-local configuration
- `tmp/` — temporary working files

Notes:

- Keep secret files encrypted at rest in `secrets/`.
- Do not place plaintext credentials here.
- `.auth` files belong under `grants/` only.
- The bootstrap installer writes `config/default.json` with `keyman.command` pointing to `config/keyman_authorize.py`, so the boundary does not depend on PATH resolution.
- Keyman responses must preserve `request_id` for audit correlation.
- The runtime installer still deploys secrets into `/etc/little7/secrets` so existing consumers such as `supervisor/bin/get-secret` continue to work.
- `install.sh` installs the current secret set into `/etc/little7/secrets`.
- `uninstall.sh` removes `/etc/little7/secrets` to provide a clean rollback path for this boundary.
