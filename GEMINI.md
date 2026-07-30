<!-- GSD:project-start source:PROJECT.md -->

## Project

**Prospect Pulse v1**

A unified B2B lead generation and intelligence platform built on Django. It automates web scraping, semantic deduplication, and AI-driven relevance classification of news articles to extract target accounts, leads, and competitor insights matching Ideal Customer Profiles (ICPs).

**Core Value:** Unify campaign configuration, AI-driven article scraping/relevance evaluation, and lead extraction in a single Django ORM-driven application.

### Constraints

- **Database**: SQLite must be used, mapping raw SQL tables to Django ORM.
- **ORM Models**: No raw SQL queries; all database interactions must utilize Django's ORM model interfaces.
- **Asynchronous Execution**: The scraper and LLM pipelines must run asynchronously via Celery workers to avoid blocking the main web request thread.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->

## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.agents/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
