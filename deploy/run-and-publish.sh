#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sniper-deals
set -a
source .env
set +a

GIT_SSH_COMMAND="ssh -i /home/ubuntu/.ssh/github_deploy -o StrictHostKeyChecking=accept-new" \
  git fetch origin main
GIT_SSH_COMMAND="ssh -i /home/ubuntu/.ssh/github_deploy -o StrictHostKeyChecking=accept-new" \
  git checkout origin/main -- sniper_deals.py history.py tests .github README.md

python3 -m unittest discover -s tests -v
python3 sniper_deals.py

# Publica apenas dashboard; estado operacional fica na VPS/backups.
git add docs/history.json docs/index.html
git diff --cached --quiet || git commit -m "chore: atualizar dashboard"
if ! git diff --cached --quiet || [ "$(git rev-list --count origin/main..HEAD)" -gt 0 ]; then
  GIT_SSH_COMMAND="ssh -i /home/ubuntu/.ssh/github_deploy -o StrictHostKeyChecking=accept-new" \
    git push origin HEAD:main
fi
