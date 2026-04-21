#!/usr/bin/env bash
# QUICK IMPLEMENTATION CHECKLIST
# Copy this to your PR description for reviewers

cat << 'EOF'

# ✅ IMPLEMENTATION CHECKLIST — Issue #49 Refactoring

## Pre-Merge Verification

- [ ] **Code Review**: Security team reviewed all `.sh` files
- [ ] **Checksum Validation**: Run `./install.sh verify` passes
- [ ] **Lock File**: `bootstrap-config.lock` contains all artifact hashes
- [ ] **No Live Clones**: Grep confirms no `curl ... | bash` patterns remain
- [ ] **Privilege Audit**: All `sudo` usage is documented and necessary
- [ ] **Secret Handling**: No plaintext master key in command-line (Stage 21)

## Testing (Test Environment)

- [ ] **Stage 00**: `./install.sh 00` completes, Node.js v20+ installed
- [ ] **Stage 20**: `./install.sh 20` succeeds, unifai-operator created, master key at 0600 perms
- [ ] **Stage 21**: `./install.sh 21` seeds API key, verify with `node cli.js list`
- [ ] **Stage 31**: `./install.sh 31` starts containers, `docker-compose ps` works
- [ ] **Stage 50**: `./install.sh 50` installs OpenClaw from pinned release
- [ ] **Full Run**: `./install.sh all` completes without errors
- [ ] **Manifest**: Check `/var/lib/little7/manifests/stage20-supervisor.manifest` generated

## Security Validation

- [ ] **Master Key Permissions**: `ls -la /etc/little7/secretvault_master.key` → `-rw------- root:root`
- [ ] **Secrets Dir**: `ls -la /etc/little7/secrets/` → `d---------` (0700)
- [ ] **Audit Trail**: Check `/var/log/audit/audit.log` for key access logging
- [ ] **No Leaks**: `ps aux | grep openclaw` shows NO plaintext API key
- [ ] **Core Dumps**: Disabled at runtime (`ulimit -c 0` in openclaw-start)

## Documentation

- [ ] **README.BOOTSTRAP**: Reviewed, all sections present (8+ major sections)
- [ ] **.env.example**: Template demonstrates secure secret injection
- [ ] **Inline Comments**: All refactored scripts have clear comments
- [ ] **Lock File**: `bootstrap-config.lock` has audit metadata + version pins

## Compliance

- [ ] **Reproducibility**: Commit `bootstrap-config.lock` alongside refactored scripts
- [ ] **Auditability**: All operations logged to systemd-journald
- [ ] **Least-Privilege**: Service user (unifai-operator) has minimal rights
- [ ] **Zero Trust**: No assumptions about external installer mutability

## Migration Notes

1. **Backup Current**: Before deploying, snapshot current `/etc/little7/` and `/opt/little7/`
2. **No Downtime**: Refactored installer is additive (no breaking changes)
3. **Rollback Plan**: If issues occur, revert to prior commit and redeploy
4. **Validation**: Post-deployment, run `./install.sh verify` to confirm checksums

## Deployment Stages

### Stage 1: Code Merge
- [ ] Merge refactored scripts to `main` branch
- [ ] Tag with `bootstrap-refactor-v1.0.0`

### Stage 2: Staging Deployment (1 week)
- [ ] Deploy to staging environment
- [ ] Run full bootstrap + verify audit logs
- [ ] Confirm no regressions

### Stage 3: Production Rollout (phased)
- [ ] Notify DevOps team of bootstrap changes
- [ ] Run on one prod instance (canary)
- [ ] Monitor logs, audit trail, service health
- [ ] Roll out to remaining prod instances

### Stage 4: Post-Deployment
- [ ] Archive bootstrap logs for 90 days (compliance)
- [ ] Review audit trail: `/var/log/audit/` (30 days)
- [ ] Confirm all services running: `systemctl status lyra-*`

---

## Security Review Summary (for PR Description)

### Vulnerability Closed: Plaintext Master Key in Process Environment
**Before:**
```bash
MASTER_KEY="$(sudo cat ...)"
SECRETVAULT_MASTER_KEY="$MASTER_KEY" node ...  # ❌ Visible in ps aux
```

**After:**
```bash
TEMP_MASTER_KEY_FILE="$(mktemp -t sv_master_key.XXXXXXXXXX)"
chmod 0600 "$TEMP_MASTER_KEY_FILE"
read_master_key_secure > "$TEMP_MASTER_KEY_FILE"
# ✅ Passed via FD, not command-line
exec 3< "$TEMP_MASTER_KEY_FILE"
MASTER_KEY="$(cat <&3)"
trap cleanup_secrets EXIT  # Secure wipe on exit
```

### Vulnerability Closed: Live Clone Mutability (curl | bash)
**Before:**
```bash
curl -fsSL https://openclaw.ai/install.sh | bash  # ❌ No version control
```

**After:**
```bash
OPENCLAW_INSTALLER_SHA256=$(lock_value "OPENCLAW_INSTALLER_SHA256")
verify_download_hash "$URL" "$OPENCLAW_INSTALLER_SHA256" > "$installer"
bash "$installer"  # ✅ Hash-verified, pinned version
```

### Architecture Improvement: Separated Bootstrap from Runtime
**Before:** Installer contained runtime logic (secret injection, service launch)
**After:** Installer ONLY installs; runtime delegated to systemd services

---

## Files to Review (In Order)

1. **install.sh** (80 lines) — orchestrator, checksum verification
2. **stages/00_bigbang.sh** (120 lines) — base bootstrap, Node.js pinning
3. **stages/21_cloud_secrets.sh** (180 lines) — 🔒 CRITICAL: secure secret handling
4. **stages/31_docker_runtime.sh** (130 lines) — privilege reduction
5. **stages/50_openclaw.sh** (200 lines) — artifact pinning
6. **config/bootstrap-config.lock** (120 lines) — comprehensive lock file
7. **.env.example** (140 lines) — secret injection template
8. **README.BOOTSTRAP** (500+ lines) — technical documentation

---

## Questions for Reviewers

- **Security**: Is 5-pass shred sufficient for your security posture? (Alternatives: 7-pass DoD, single-pass generic)
- **Compatibility**: Do you require `bootstrap-config.lock` in VCS or external secret store?
- **Audit**: Should we enable auditd rules for `/etc/little7/secretvault_master.key` by default?
- **Refresh**: How often should we update `bootstrap-config.lock` (monthly, quarterly)?

---

## Contact & Escalations

- **DevSecOps**: For security architecture questions
- **Release Engineering**: For deployment planning
- **Compliance**: For audit trail and retention policies

---

Generated: 2026-04-21 | Issue: #49 | Status: FINAL FOR REVIEW

EOF
