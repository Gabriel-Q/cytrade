# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-03-06

### Added
- Added open-source readiness files: `.gitignore`, `.env.example`, `CONTRIBUTING.md`, `SECURITY.md`, `RELEASE_CHECKLIST.md`.
- Added regression tests for main app wiring, data subscription recovery, web cancel route, settings environment overrides, and `xt_order_id` persistence/migration.
- Added `终审.md` as the final review summary.

### Changed
- Improved `README.md` for public/open-source usage.
- Moved settings toward environment-variable-first configuration.
- Unified `xt_order_id` persistence to integer storage and added migration handling for legacy SQLite schemas.
- Cleaned up duplicate `resubscribe_all()` implementation in data subscription manager.
- Fixed reconnect callback registration in the main entry wiring.
- Updated project docs to remove sensitive examples and align review/test baseline.

### Verified
- Full test suite passes: `50 passed`.
