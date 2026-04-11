# Project Status

Quick orientation — show the current state of the repo, recent work, and any pending changes.

## Steps

1. **Git status** — Run `git status` (never use `-uall`). Show branch name, whether it's ahead/behind remote, and list modified/untracked files.

2. **Recent commits** — Run `git log --oneline -10` to show the last 10 commits. This helps understand what was done recently.

3. **Uncommitted changes** — If there are unstaged changes, run `git diff --stat HEAD` to show which files changed and how many lines.

4. **Services running** — Check if anything is running on ports 8000 (backend), 5173 (frontend), 5432 (postgres) using `lsof -i :PORT`. Report which are up.

5. **Quick summary** — In 3-5 bullet points, summarize:
   - Current branch and whether there's uncommitted work
   - What the last few commits were about (feature? fix? docs?)
   - Which services are running
   - Any obvious next steps based on what you see
