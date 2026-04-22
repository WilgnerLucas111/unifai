#!/bin/bash

##############################################################################
# UnifAI Native Installation Sequence (VM-as-a-Department)
#
# Architecture: Bare-metal/OpenStack - NO Docker, NO nested virtualization
# Target: Ubuntu 22.04 LTS / Debian 12
#
# Execution Order (CRITICAL):
#   1. supervisor-secretvault
#   2. keyman + supervisor
#   3. OpenClaw (native)
#   4. Configure global environment (LLM local, etc)
##############################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

# Global Configuration
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/unifai}"
PYTHON_VERSION="3.10"
NODE_VERSION="18"
LOG_FILE="/tmp/unifai-install.log"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use: sudo $0)"
    fi
}

check_os() {
    if ! grep -E "(Ubuntu|Debian)" /etc/os-release > /dev/null; then
        log_error "This script is designed for Ubuntu/Debian. Detected: $(lsb_release -ds)"
    fi
    log_success "OS Check: $(lsb_release -ds)"
}

##############################################################################
# PHASE 0: System Dependencies
##############################################################################

phase_0_system_deps() {
    log_info "=== PHASE 0: System Dependencies ==="

    apt-get update
    apt-get install -y \
        build-essential \
        curl \
        wget \
        git \
        jq \
        ca-certificates \
        apt-transport-https \
        software-properties-common \
        systemd \
        openssh-server

    log_success "Phase 0: System dependencies installed"
}

##############################################################################
# PHASE 1: supervisor-secretvault (Secret Governance Foundation)
##############################################################################

phase_1_supervisor_secretvault() {
    log_info "=== PHASE 1: supervisor-secretvault Installation ==="

    # Create installation directory
    mkdir -p "${INSTALL_PREFIX}/supervisor-secretvault"
    cd "${INSTALL_PREFIX}/supervisor-secretvault"

    # Clone repo (adjust URL as needed)
    if [[ ! -d ".git" ]]; then
        git clone https://github.com/joustonhuang/supervisor-secretvault.git .
    else
        git pull origin main
    fi

    log_info "Installing Node.js dependencies..."
    npm install

    # Create systemd service for secretvault
    cat > /etc/systemd/system/unifai-secretvault.service << 'EOF'
[Unit]
Description=UnifAI Secret Vault Service
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=unifai
WorkingDirectory=/opt/unifai/supervisor-secretvault
ExecStart=/usr/bin/node cli.js
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_success "Phase 1: supervisor-secretvault installed and service registered"
}

##############################################################################
# PHASE 2: Python Environment (for Keyman + OpenClaw)
##############################################################################

phase_2_python_env() {
    log_info "=== PHASE 2: Python Environment Setup ==="

    # Add deadsnakes PPA for latest Python
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update
    apt-get install -y \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-venv \
        python${PYTHON_VERSION}-dev \
        python3-pip

    # Create global venv
    mkdir -p "${INSTALL_PREFIX}/venv"
    python${PYTHON_VERSION} -m venv "${INSTALL_PREFIX}/venv"

    # Upgrade pip
    source "${INSTALL_PREFIX}/venv/bin/activate"
    pip install --upgrade pip setuptools wheel

    log_success "Phase 2: Python environment ready at ${INSTALL_PREFIX}/venv"
}

##############################################################################
# PHASE 3: Keyman (Authorization & Permission System)
##############################################################################

phase_3_keyman() {
    log_info "=== PHASE 3: Keyman Installation ==="

    source "${INSTALL_PREFIX}/venv/bin/activate"

    mkdir -p "${INSTALL_PREFIX}/keyman"
    cd "${INSTALL_PREFIX}/keyman"

    # Clone keyman repo (adjust URL as needed)
    if [[ ! -d ".git" ]]; then
        git clone https://github.com/joustonhuang/keyman.git .
    else
        git pull origin main
    fi

    # Install Python dependencies
    pip install -r requirements.txt

    # Create systemd service for Keyman
    cat > /etc/systemd/system/unifai-keyman.service << EOF
[Unit]
Description=UnifAI Keyman Service (Authorization)
After=network.target unifai-secretvault.service
Wants=network-online.target

[Service]
Type=simple
User=unifai
WorkingDirectory=${INSTALL_PREFIX}/keyman
Environment="PATH=${INSTALL_PREFIX}/venv/bin"
ExecStart=${INSTALL_PREFIX}/venv/bin/python -m keyman.cli
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_success "Phase 3: Keyman installed and service registered"
}

##############################################################################
# PHASE 4: Supervisor (Agent Management & Orchestration)
##############################################################################

phase_4_supervisor() {
    log_info "=== PHASE 4: Supervisor Installation ==="

    source "${INSTALL_PREFIX}/venv/bin/activate"

    mkdir -p "${INSTALL_PREFIX}/supervisor"
    cd "${INSTALL_PREFIX}/supervisor"

    # Clone supervisor repo (adjust URL as needed)
    if [[ ! -d ".git" ]]; then
        git clone https://github.com/joustonhuang/supervisor.git .
    else
        git pull origin main
    fi

    pip install -r requirements.txt

    # Create systemd service for Supervisor
    cat > /etc/systemd/system/unifai-supervisor.service << EOF
[Unit]
Description=UnifAI Supervisor Service (Agent Orchestration)
After=network.target unifai-keyman.service unifai-secretvault.service
Wants=network-online.target

[Service]
Type=simple
User=unifai
WorkingDirectory=${INSTALL_PREFIX}/supervisor
Environment="PATH=${INSTALL_PREFIX}/venv/bin"
ExecStart=${INSTALL_PREFIX}/venv/bin/python -m supervisor.cli
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_success "Phase 4: Supervisor installed and service registered"
}

##############################################################################
# PHASE 5: OpenClaw (Native Installation)
##############################################################################

phase_5_openclaw() {
    log_info "=== PHASE 5: OpenClaw Native Installation ==="

    # Install Node.js if not present
    if ! command -v node &> /dev/null; then
        log_info "Installing Node.js v${NODE_VERSION}..."
        curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash -
        apt-get install -y nodejs
    fi

    mkdir -p "${INSTALL_PREFIX}/openclaw"
    cd "${INSTALL_PREFIX}/openclaw"

    # Clone OpenClaw repo (adjust URL as needed)
    if [[ ! -d ".git" ]]; then
        git clone https://github.com/openclaw/openclaw.git .
    else
        git pull origin main
    fi

    npm install

    # Create systemd service for OpenClaw
    cat > /etc/systemd/system/unifai-openclaw.service << EOF
[Unit]
Description=UnifAI OpenClaw Service
After=network.target unifai-supervisor.service
Wants=network-online.target

[Service]
Type=simple
User=unifai
WorkingDirectory=${INSTALL_PREFIX}/openclaw
ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_success "Phase 5: OpenClaw installed and service registered"
}

##############################################################################
# PHASE 6: LLM Local Integration (LM Studio)
##############################################################################

phase_6_llm_local() {
    log_info "=== PHASE 6: LLM Local Integration Setup ==="

    # Create environment configuration file
    cat > "${INSTALL_PREFIX}/.env" << 'EOF'
# UnifAI Global Environment Configuration
# Generated by installer.sh

# LLM Configuration (Local - LM Studio)
OPENAI_BASE_URL="http://localhost:1234/v1"
OPENAI_API_KEY="lm-studio"
OPENAI_MODEL="local-model"

# Service Ports
OPENCLAW_PORT=3000
SUPERVISOR_PORT=5000
KEYMAN_PORT=5001
SECRETVAULT_PORT=5002

# Installation Paths
INSTALL_PREFIX="/opt/unifai"
PYTHON_VENV="${INSTALL_PREFIX}/venv"

# Logging
LOG_LEVEL="INFO"
LOG_DIR="/var/log/unifai"

# Security (Governance)
SECRET_VAULT_MODE="supervised"
PERMISSION_ENFORCEMENT="strict"
AUDIT_LOGGING="enabled"
EOF

    mkdir -p /var/log/unifai
    chown unifai:unifai /var/log/unifai

    log_success "Phase 6: LLM local integration configured"
}

##############################################################################
# PHASE 7: Create UnifAI User & Permissions
##############################################################################

phase_7_user_setup() {
    log_info "=== PHASE 7: UnifAI User & Permissions ==="

    # Create unifai user if not exists
    if ! id -u unifai &> /dev/null; then
        useradd -m -s /bin/bash -G sudo unifai 2>/dev/null || true
        log_success "Created user: unifai"
    fi

    # Verify user created
    if id -u unifai &> /dev/null; then
        log_success "User unifai verified"
    else
        log_error "Failed to create unifai user"
    fi

    # Set proper ownership
    chown -R unifai:unifai "${INSTALL_PREFIX}"
    chmod -R 755 "${INSTALL_PREFIX}"

    log_success "Phase 7: User setup complete"
}

##############################################################################
# PHASE 8: Validation & Summary
##############################################################################

phase_8_validation() {
    log_info "=== PHASE 8: Installation Validation ==="

    echo ""
    log_info "Checking installed components..."

    # Check Node.js
    if command -v node &> /dev/null; then
        log_success "Node.js: $(node --version)"
    else
        log_warn "Node.js: NOT FOUND"
    fi

    # Check Python
    if command -v python${PYTHON_VERSION} &> /dev/null; then
        log_success "Python: $(python${PYTHON_VERSION} --version)"
    else
        log_warn "Python ${PYTHON_VERSION}: NOT FOUND"
    fi

    # Check services
    log_info "Registered systemd services:"
    systemctl list-unit-files | grep unifai- | while read line; do
        log_success "  $line"
    done

    echo ""
    log_info "=== INSTALLATION COMPLETE ==="
    echo ""
    log_info "Next steps:"
    echo "  1. Start services: sudo systemctl start unifai-secretvault unifai-keyman unifai-supervisor unifai-openclaw"
    echo "  2. Enable auto-start: sudo systemctl enable unifai-*"
    echo "  3. Check status: sudo systemctl status unifai-*"
    echo "  4. View logs: sudo journalctl -u unifai-openclaw -f"
    echo ""
    log_info "Configuration file: ${INSTALL_PREFIX}/.env"
    log_info "Installation log: ${LOG_FILE}"
}

##############################################################################
# Main Execution Flow
##############################################################################

main() {
    log_info "Starting UnifAI Native Installation Sequence"
    log_info "Installation prefix: ${INSTALL_PREFIX}"
    log_info "Python version: ${PYTHON_VERSION}"
    log_info "Node version: ${NODE_VERSION}"

    check_root
    check_os

    phase_0_system_deps
    phase_1_supervisor_secretvault
    phase_2_python_env
    phase_3_keyman
    phase_4_supervisor
    phase_5_openclaw
    phase_6_llm_local
    phase_7_user_setup
    phase_8_validation

    log_success "All phases completed successfully!"
}

main "$@"
