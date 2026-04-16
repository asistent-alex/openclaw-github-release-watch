# GitHub Release Watch Workflows

## Daily release digest

1. Load configured repos
2. Check latest stable published releases
3. Enrich results with semver, notes excerpt, stars/forks, and advisory signals
4. Generate digest payload
5. Render HTML digest
6. Send email via IMM-Romania when needed

## Status review

1. Read saved checker state
2. Review tracked repos
3. Inspect updates/failures
4. Inspect momentum and advisory context
5. Decide whether to send or refine the digest
