# Plant Monitor agent bootstrap

Use this file as the tracked repository entrypoint for agent development.

When the current assignment/WorkId says Plant Monitor is Switchstand-managed, Switchstand owns the development process and authority/currentness rules; this repository owns the technical truth about Plant Monitor. Do not import another repository's workflow into this one.

Before substantive work:
- read `README.md`, `docs/roadmap.md`, and `docs/internals.md`;
- for Raspberry Pi or sensor work, also read `docs/sensor-ingest.md`;
- verify the exact repository/ref you are changing.

Validation:
- `make test` is the normal full backend + Pi + JavaScript validation;
- `make test-pi` is the focused Pi validation route;
- `make test-e2e` is separate browser evidence and is not implied by `make test`;
- report NOT_RUN/UNKNOWN honestly when a required boundary cannot be exercised.

Live effects are separate from code changes. Raspberry Pi deployment, service restart, database migration, and other live-system actions require explicit current authority and live-state readback. Do not infer live users, paths, services, or device state from documentation alone.

A local ignored `CLAUDE.md` / `.claude` may exist. Do not overwrite it or treat it as durable repository truth until it has been inspected and reconciled.

Keep implementation on a task branch/PR. The current Switchstand WorkId or direct Marco assignment defines scope; repository files and tool availability do not grant additional authority.
