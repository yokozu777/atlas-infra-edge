#!/usr/bin/env bash
# Standalone runner for atlas-infra-edge.
#
# Usage:
#   cp inventory-example.yml inventory.yml   # edit hosts
#   # edit group_vars/all/atlas-infra-edge.yml (replace CHANGEME secrets; enable feature gates)
#   ansible-galaxy collection install -r requirements.yml
#   ./run.sh                                 # full infra platform (per gates)
#   ./run.sh --tags 00_ensure_workspace
#   ./run.sh --tags 01_install_docker_engine
#   ./run.sh --tags 03_deploy_bind_compose
#   ./run.sh --check -v
#
# Env overrides:
#   INVENTORY                     inventory path (default: ./inventory.yml or inventory-example.yml)
#   PLAYBOOK                      playbook path (default: playbooks/infra_hosts.yaml)
#   EXTRA_VARS_FILE               optional ansible -e @file (e.g. vaulted secrets)
#   SSH_KEY / ANSIBLE_PRIVATE_KEY_FILE
#   CLUSTER_WORKSPACE_ID          workspace dir name under parent (overrides group_vars)
#   CLUSTER_WORKSPACE_PARENT      parent dir for workspaces (default: ./workspace)
#   CLUSTER_WORKSPACE_ROOT        full workspace path (overrides ID/parent-based default)
#   ANSIBLE_CONFIG                default: ./ansible.cfg
#   ANSIBLE_CACHE_PLUGIN_CONNECTION  fact cache dir (default: <workspace>/.ansible_facts_cache)
#
# Vars: group_vars/all/atlas-infra-edge.yml + optional host_vars/<host>.yml
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export ANSIBLE_CONFIG="${ANSIBLE_CONFIG:-${ROOT}/ansible.cfg}"
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o StrictHostKeyChecking=no}"

if [[ -n "${SSH_KEY:-}" ]]; then
  export ANSIBLE_PRIVATE_KEY_FILE="${ANSIBLE_PRIVATE_KEY_FILE:-${SSH_KEY}}"
elif [[ -z "${ANSIBLE_PRIVATE_KEY_FILE:-}" ]]; then
  for candidate in "${HOME}/.ssh/id_ed25519" "${HOME}/.ssh/id_rsa"; do
    if [[ -f "${candidate}" ]]; then
      export ANSIBLE_PRIVATE_KEY_FILE="${candidate}"
      break
    fi
  done
fi

if [[ -n "${INVENTORY:-}" ]]; then
  :
elif [[ -f "${ROOT}/inventory.yml" ]]; then
  INVENTORY="${ROOT}/inventory.yml"
else
  INVENTORY="${ROOT}/inventory-example.yml"
fi

PLAYBOOK="${PLAYBOOK:-${ROOT}/playbooks/infra_hosts.yaml}"

CLUSTER_WORKSPACE_ID="${CLUSTER_WORKSPACE_ID:-infra.example.com}"
CLUSTER_WORKSPACE_PARENT="${CLUSTER_WORKSPACE_PARENT:-${ROOT}/workspace}"
# Resolve relative parent/root against repo root so Ansible localhost tasks land in-tree.
if [[ "${CLUSTER_WORKSPACE_PARENT}" != /* ]]; then
  CLUSTER_WORKSPACE_PARENT="${ROOT}/${CLUSTER_WORKSPACE_PARENT#./}"
fi
export CLUSTER_WORKSPACE_ID
export CLUSTER_WORKSPACE_PARENT
if [[ -n "${CLUSTER_WORKSPACE_ROOT:-}" && "${CLUSTER_WORKSPACE_ROOT}" != /* ]]; then
  CLUSTER_WORKSPACE_ROOT="${ROOT}/${CLUSTER_WORKSPACE_ROOT#./}"
fi
export CLUSTER_WORKSPACE_ROOT="${CLUSTER_WORKSPACE_ROOT:-${CLUSTER_WORKSPACE_PARENT}/${CLUSTER_WORKSPACE_ID}}"
mkdir -p "${CLUSTER_WORKSPACE_ROOT}" "${CLUSTER_WORKSPACE_ROOT}/.ansible_facts_cache"
# Persist cacheable set_fact across split --tags runs (deferred pkg-repo warm, etc.).
export ANSIBLE_CACHE_PLUGIN_CONNECTION="${ANSIBLE_CACHE_PLUGIN_CONNECTION:-${CLUSTER_WORKSPACE_ROOT}/.ansible_facts_cache}"

if [[ ! -f "${INVENTORY}" ]]; then
  echo "error: inventory not found: ${INVENTORY}" >&2
  echo "hint: cp inventory-example.yml inventory.yml && edit hosts" >&2
  exit 1
fi

if [[ ! -f "${PLAYBOOK}" ]]; then
  echo "error: playbook not found: ${PLAYBOOK}" >&2
  exit 1
fi

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "error: ansible-playbook not found in PATH" >&2
  exit 1
fi

EXTRA_VARS=()
if [[ -n "${EXTRA_VARS_FILE:-}" ]]; then
  if [[ ! -f "${EXTRA_VARS_FILE}" ]]; then
    echo "error: EXTRA_VARS_FILE not found: ${EXTRA_VARS_FILE}" >&2
    exit 1
  fi
  EXTRA_VARS+=(-e "@${EXTRA_VARS_FILE}")
fi

echo "inventory: ${INVENTORY}"
echo "playbook:  ${PLAYBOOK}"
echo "ssh key:   ${ANSIBLE_PRIVATE_KEY_FILE:-<(none — password/agent auth)>}"
echo "workspace: ${CLUSTER_WORKSPACE_ROOT}"
echo "fact cache: ${ANSIBLE_CACHE_PLUGIN_CONNECTION}"
if [[ -n "${EXTRA_VARS_FILE:-}" ]]; then
  echo "extra:     @${EXTRA_VARS_FILE}"
fi

exec ansible-playbook \
  -i "${INVENTORY}" \
  "${PLAYBOOK}" \
  "${EXTRA_VARS[@]}" \
  "$@"
