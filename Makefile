.PHONY: lint fix

# Markdown (markdownlint-cli2 via npm) + Python (ruff via uvx, no install needed)
lint:
	npm run -s lint:md
	.claude/hooks/no-emoji.sh
	.claude/hooks/no-hard-wrap.py
	uvx ruff@0.16.10 check .
	uvx ruff@0.16.10 format --check .

fix:
	.claude/hooks/no-hard-wrap.py --fix
	npm run -s fix:md
	uvx ruff@0.16.10 check --fix .
	uvx ruff@0.16.10 format .

.PHONY: site site-build

# Blog dev server with drafts: http://localhost:4321
site:
	cd site && npm run dev

# Production build into site/dist (drafts excluded)
site-build:
	cd site && npm run build
