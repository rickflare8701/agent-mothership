# 💾 Session Persistence

> Never lose your progress. Sync your session across environments.

## How It Works

Every time you save, the system:
1. Collects all project file states (hashes, sizes, timestamps)
2. Records your git branch and commit
3. Saves to a local `.session/` directory
4. Pushes a snapshot to GitHub (branch: `sessions`)

When you start in a fresh environment, you restore from the GitHub snapshot.

## Usage

```bash
# Save your session manually
npm run sync
# or
node session-persistence/sync.js

# Auto-save every 5 minutes
node session-persistence/sync.js --auto

# Restore from the last saved session
node session-persistence/sync.js --restore
# or
./scripts/restore.sh
```

## Best Practices

1. **Run `npm run sync` before leaving** any environment
2. **Run `./scripts/restore.sh` when starting** a new environment
3. **Use `--auto` mode** during long sessions to never lose work
4. The last 10 backups are kept locally in `.session/backups/`

## Data Saved

- File structure and hashes
- Git branch and commit
- Timestamp and platform info
- Git status (unstaged changes)
