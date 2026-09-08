#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/sniper-deals
set -a
source .env
set +a

python3 -m unittest discover -s tests -v
python3 sniper_deals.py

# Publica o dashboard em uma worktree limpa para preservar o estado da VPS.
PUBLISH_DIR=/home/ubuntu/sniper-deals-publish
GIT_SSH_COMMAND="ssh -i /home/ubuntu/.ssh/github_deploy -o StrictHostKeyChecking=accept-new" \
  git fetch origin main
if [ ! -e "$PUBLISH_DIR/.git" ]; then
  rm -rf "$PUBLISH_DIR"
  git worktree add --detach "$PUBLISH_DIR" origin/main
else
  git -C "$PUBLISH_DIR" reset --hard origin/main
fi
cp docs/history.json docs/index.html "$PUBLISH_DIR/docs/"
git -C "$PUBLISH_DIR" add docs/history.json docs/index.html
if ! git -C "$PUBLISH_DIR" diff --cached --quiet; then
  git -C "$PUBLISH_DIR" config user.name "SniperDeals VPS"
  git -C "$PUBLISH_DIR" config user.email "bot@sniperdeals.local"
  git -C "$PUBLISH_DIR" commit -m "chore: atualizar dashboard"
  GIT_SSH_COMMAND="ssh -i /home/ubuntu/.ssh/github_deploy -o StrictHostKeyChecking=accept-new" \
    git -C "$PUBLISH_DIR" push origin HEAD:main
fi
