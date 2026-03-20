## Summary

- What changed?
- Why was it needed?

## Checks

- [ ] `./scripts/test.sh all`
- [ ] `uv run --group dev ruff check apps/api apps/bot common scripts`
- [ ] `uv run --group dev ruff format --check apps/api apps/bot common scripts`
- [ ] `npm run lint` in `apps/web`
- [ ] `npm run test` in `apps/web`
- [ ] `npm run test:e2e` in `apps/web` if web auth/browser flow changed
- [ ] `npm run typecheck` in `apps/web`
- [ ] `npm run build` in `apps/web`
- [ ] `npm run lint` in `apps/admin`
- [ ] `npm run test` in `apps/admin`
- [ ] `npm run test:e2e` in `apps/admin` if admin UI or auth/browser flow changed
- [ ] `npm run typecheck` in `apps/admin`
- [ ] `npm run build` in `apps/admin`

## Impact

- [ ] Database migrations
- [ ] New or changed environment variables
- [ ] API or frontend contract changes
- [ ] Docs updated if behavior changed

## UI Review

- [ ] No UI changes
- [ ] Screenshots attached
- [ ] Manual smoke completed for affected flow

## Release

- [ ] Not a `dev -> main` release PR
- [ ] For `dev -> main`: draft release note prepared
- [ ] For `dev -> main`: planned tag `v0.x.y` recorded
