# Secondary Sync Instructions

Follow these instructions on the secondary machine/laptop to synchronize with the primary machine's baseline:

## Scenario A: First Checkout
```bash
# 1. Fetch all remote branches and metadata
git fetch --all --prune

# 2. Checkout and track the new sync branch
git switch -c agent-hub-sync-2026-07-08 --track origin/agent-hub-sync-2026-07-08
```

## Scenario B: If Branch Already Exists Locally
```bash
# 1. Switch to the sync branch
git switch agent-hub-sync-2026-07-08

# 2. Pull the latest commits from remote
git pull --ff-only
```
