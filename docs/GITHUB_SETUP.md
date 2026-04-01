# GitHub Repository Setup & Branch Protection

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. **Repository name**: `Provenance-Lab2.0`
3. **Owner**: `cheechu`
4. **Description**: "Provenance-tracked CRISPR base-editor design with FastAPI, Prefect, and PostgreSQL JSONB"
5. **Visibility**: Public (or Private, your choice)
6. **Initialize**: ✓ Add .gitignore (Python), ✓ Add README, ✓ Choose license (MIT)
7. Click **Create repository**

## Step 2: Configure Local Git Remote

If you haven't already:

```bash
cd /Users/kavin/Provenance-Lab2.0

# Add the remote (replace with your repo URL)
git remote add origin https://github.com/cheechu/Provenance-Lab2.0.git

# Or update if it exists
git remote set-url origin https://github.com/cheechu/Provenance-Lab2.0.git

# Verify
git remote -v
```

## Step 3: Enable Branch Protection on `main`

1. **Go to repository settings**:
   - Navigate to: https://github.com/cheechu/Provenance-Lab2.0/settings

2. **Click "Branches"** in the left sidebar

3. **Add branch protection rule**:
   - Click **"Add rule"**
   - **Branch name pattern**: `main`
   - **Enable these settings**:
     - ✅ **Require a pull request before merging**
       - Require approvals: `1`
       - ✅ Dismiss stale pull request approvals when new commits are pushed
     - ✅ **Require status checks to pass before merging**
       - Require branches to be up to date before merging
     - ✅ **Require code reviews before merging**
     - ✅ **Restrict who can push to matching branches** (optional)
       - Only allow specified people/teams to push

4. Click **Create** to save the rule

## Step 4: Workflow with Branch Protection

### Creating a Feature Branch

```bash
# Create and checkout a feature branch
git checkout -b Kav--Backend

# Make changes, commit, push
git add .
git commit -m "feat: your changes"
git push origin Kav--Backend
```

### Opening a Pull Request

1. Push your branch to GitHub
2. Go to https://github.com/cheechu/Provenance-Lab2.0
3. You'll see a prompt: **"Compare & pull request"**
4. Click it, fill in description, and **Create Pull Request**

### Merging to Main

1. PR must pass all checks:
   - ✅ At least 1 approval (if configured)
   - ✅ Status checks pass (CI/CD)
   - ✅ Branch up to date with main

2. Once approved, click **"Merge pull request"**
3. Choose merge strategy (Squash, Rebase, or Merge commit)
4. Delete branch after merging (optional)

## Current Status ✅

- **Repository**: Created at cheechu/Provenance-Lab2.0
- **Branch**: `Kav--Backend` - Ready for development
- **Main branch**: Protected with:
  - Require PRs before merging
  - Require 1 approval
  - Require status checks
  - Dismiss stale reviews

## Useful Commands

```bash
# List all branches
git branch -a

# Switch branches
git checkout Kav--Backend
git checkout main

# Sync with remote
git fetch origin
git pull origin Kav--Backend

# Create PR (via GitHub CLI if installed)
gh pr create --base main --head Kav--Backend --title "Your PR title" --body "Description"

# Merge main into your branch to stay updated
git fetch origin
git merge origin/main
```

## Next Steps

1. Configure CI/CD (GitHub Actions) for automated testing
2. Set up codeowners for review requirements
3. Add status check requirements (e.g., all tests must pass)
4. Configure auto-merge if desired

---

**Date Updated**: April 1, 2026  
**Status**: Ready to use
