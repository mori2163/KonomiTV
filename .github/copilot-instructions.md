# GitHub Copilot Instructions

This repository has comprehensive development instructions documented in the root-level `AGENTS.md` file.

**Please read the [AGENTS.md](../AGENTS.md) file at the repository root for complete instructions including:**

- Project-specific considerations
- Technology stack details
- Directory structure
- Coding conventions for Python and TypeScript/Vue.js

## Quick Reference

### Key Points

- This is a client-server architecture web application (PWA) that runs locally on user machines
- Must support both Windows and Linux
- Commands must be run in the appropriate directory:
  - Client commands: Run in `client/` directory
  - Server commands: Run in `server/` directory
- Always use `poetry run` for Python commands in the server

### Package Managers

- **Client**: yarn v1 (run in `client/` directory)
- **Server**: Poetry (run in `server/` directory with `poetry run`)

### Linting

- **Client**: ESLint (TypeScript/Vue)
- **Server**: `poetry run task lint` (Ruff + Pyright)

### Tech Stack Summary

**Client (`client/`)**:
- TypeScript, Vite, Vue.js 3.x, Vuetify 3.x, Pinia

**Server (`server/`)**:
- Python 3.11, Poetry, Uvicorn, FastAPI, Pydantic v2, Tortoise ORM, SQLite

For complete details, coding conventions, and architecture information, refer to [AGENTS.md](../AGENTS.md).
