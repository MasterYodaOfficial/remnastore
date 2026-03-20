## Summary

- What changed?
- Why was it needed?

## Checks

- [ ] `./scripts/test.sh all`
- [ ] `uv run --group dev ruff check apps/api apps/bot common scripts`
- [ ] `npm run lint` in `apps/web`
- [ ] `npm run test` in `apps/web`
- [ ] `npm run typecheck` in `apps/web`
- [ ] `npm run build` in `apps/web`
- [ ] `npm run lint` in `apps/admin`
- [ ] `npm run test` in `apps/admin`
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
