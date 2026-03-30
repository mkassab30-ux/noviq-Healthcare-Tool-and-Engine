#!/bin/bash
# NOVIQ Engine — GitHub Setup Script
# Run ONCE after cloning or unzipping

set -e
echo "🚀 NOVIQ Engine — GitHub Setup"
echo "================================"

git init
git branch -M main

# Placeholder files to preserve folder structure
find . -type d -empty -not -path "./.git/*" -exec touch {}/.gitkeep \;

# Python init files
touch src/__init__.py
touch src/connector/__init__.py
touch src/ingestion/__init__.py
touch src/rag/__init__.py
touch src/intelligence-layer/__init__.py
touch src/scoring/__init__.py
touch src/output/__init__.py
touch tests/__init__.py
touch tests/type1/__init__.py
touch tests/type2/__init__.py
touch tests/type3/__init__.py

# Copy env template
cp .env.template .env
echo "⚠️  .env created — add your ANTHROPIC_API_KEY before running"

# Initial commit
git add .
git commit -m "feat: Phase 0 complete — NOVIQ Engine foundation

- Full repository structure
- ACS 0001/0002 Scoring Engine (Python)
- Keyword Dictionary: Lap Cholecystectomy (first procedure)
- Procedure documentation template
- Architecture documented in README"

echo ""
echo "✅ Done! Now run:"
echo ""
echo "  git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git"
echo "  git push -u origin main"
echo ""
echo "Phase 0 complete. Next step: Phase 1 — Type 1 procedures."
