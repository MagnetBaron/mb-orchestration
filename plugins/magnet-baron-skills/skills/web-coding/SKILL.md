---
name: web-coding
description: Modern web-app coding standards covering project structure, dependencies, testing, security, and review-ready diffs; use when building or changing a web app, site, or HTTP service.
---

# Web app coding

Standards for building and changing web applications so a change is correct, style-matched, and
lands through review on the first pass. Optimize for a small team with one implementer at a time
and a mandatory review gate: **a clean, minimal, well-tested diff is the product.**

## Read before you write

- Read the surrounding files and mirror their patterns (naming, structure, error handling, test
  style) before adding anything. Consistency with the existing code beats your personal preference.
- Check for a `README`, `CONTRIBUTING`, and config (`package.json` scripts, linters, formatters, CI
  workflow) and follow the toolchain that is already there. Do not introduce a second way to do
  something the repo already does one way.
- Reproduce the behavior you are changing (run it, write a failing test) before editing.

## Project structure

- Organize by **feature/domain**, not by technical layer, once past a trivial size (`checkout/`,
  `catalog/` over a giant `controllers/` + `services/` split). Colocate a module's component,
  logic, styles, and tests.
- Keep a clear seam between **UI, business logic, and I/O** (network, storage, third-party SDKs).
  Business logic should be testable without a browser or a live backend.
- One responsibility per module; prefer small pure functions. Push side effects to the edges so the
  core stays deterministic and easy to test.
- Centralize configuration and secrets in environment/config, never inline. **No secrets, tokens, or
  keys in source or in the client bundle** — anything shipped to the browser is public.

## Dependencies

- Prefer the platform and the standard library first. Add a dependency only when it earns its weight
  (maintenance, bundle size, supply-chain surface). A few lines copied beat a transitive tree.
- Pin/lock versions (commit the lockfile). Review what a new dependency pulls in before adding it.
- Do not upgrade or swap libraries as a drive-by inside an unrelated change.

## Types and correctness

- Use static types where the stack supports them (TypeScript, schemas). Type at boundaries — API
  responses, form input, storage — and validate untrusted input at runtime (a schema validator),
  never trust a type assertion for external data.
- Make illegal states unrepresentable: prefer discriminated unions/enums over boolean soup, and
  narrow at the edge so the core never re-checks.
- Handle the error and empty paths explicitly. No silent `catch {}`; surface or log with context.

## Testing

- **Test pyramid:** many fast unit tests on pure logic, fewer integration tests across a real seam
  (route + handler + DB with a test database), a thin layer of end-to-end tests on the critical user
  flows only (sign-in, checkout).
- Write the test with the change, in the repo's existing framework and style. A bug fix starts with
  a test that fails for the stated reason, then the fix makes it pass.
- Test behavior and public contracts, not private internals — tests should survive a refactor that
  preserves behavior. Cover the edge cases: empty, boundary, error, concurrent, unauthorized.
- Keep tests deterministic: no real network, no wall-clock/`sleep` races, fixed seeds, isolated
  state per test. Run the full suite plus the linter before opening a PR.

## Security baseline

- Validate and escape at the boundary; use parameterized queries (never string-built SQL) and the
  framework's output encoding to prevent XSS.
- Authent**icate** then author**ize** on every server route — check the caller *may* do this action,
  server-side, every time. Never rely on the UI hiding a control.
- Enforce HTTPS, set security headers and a CSP, mark cookies `HttpOnly`/`Secure`/`SameSite`, and
  protect state-changing requests against CSRF.
- Keep dependencies patched; run the ecosystem audit in CI. Never log secrets or PII.

## Accessibility and performance

- Semantic HTML first; keyboard operability and visible focus; label every control; meet color
  contrast. Accessibility is a correctness requirement, not a polish pass.
- Measure before optimizing. Ship less JS, split by route, lazy-load below the fold, set explicit
  image dimensions, and cache deliberately. Guard against N+1 queries on the server.

## Safe-change discipline

- **Smallest diff that solves the problem.** No opportunistic refactors, renames, or reformatting
  mixed into a feature or fix — they bury the real change and break review.
- Stay inside the named file scope for the task. If you discover adjacent work, note it; do not do
  it silently.
- Keep changes reversible: additive/backward-compatible first, migrations gated behind a flag or a
  two-step deploy (expand, migrate, contract). Never ship an irreversible data migration casually.
- Preserve the public contract (API shape, URL, event schema) unless the task is to change it; if
  you must, version it and keep the old path working through a deprecation window.

## Review-ready diffs

- One logical change per commit; a clear message stating *what* and *why* (not *how*).
- Update tests, docs, and types in the same change as the code they describe.
- Self-review the diff before requesting review: no debug logging, no commented-out code, no `TODO`
  without an owner, no stray formatting churn. Confirm the tests and linter pass locally.
- In the PR body, state what changed, why, how it was tested, and the risk/rollback. Call out
  anything touching auth, money, data migrations, or third-party integrations so the reviewer raises
  the right bar.
