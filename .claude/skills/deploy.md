---
name: deploy
description: Run the full deploy pipeline (pre-checks → SSH deploy → sanity check)
user_invocable: true
---

Run the end-to-end deploy script:

```bash
bash deploy/e2e-deploy.sh
```

This will:
1. **Pre-checks**: Verify clean git state, all commits pushed, tests pass, lint passes
2. **Deploy**: SSH to production and run the deploy script
3. **Sanity check**: Create a game vs AI on kfchess.com, make a move, verify AI responds

If any phase fails, the script stops and reports the error.

Stream the output so the user can see progress. The script may take several minutes (tests + deploy + sanity check).
