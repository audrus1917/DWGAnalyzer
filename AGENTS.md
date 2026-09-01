I have two local projects:

* Old project: `/home/andrus/la_strada/Apps/parsedwg`
* New project: `/home/andrus/la_strada/Apps/DWGAnalyzer`

The old `parsedwg` repository must be treated as READ-ONLY.

All implementation changes must be made only in `DWGAnalyzer`.

Goal: rebuild `DWGAnalyzer` using the useful parts of `parsedwg`, while removing legacy code, simplifying the architecture, translating all user-facing Russian messages to English, and introducing gettext-based internationalization.

## Phase 1 — Analyze first

Do NOT modify any files yet.

Analyze both repositories.

For `parsedwg`:

* inspect the package/module structure;
* identify the main entry points;
* identify DWG/DXF parsing and processing functionality;
* identify file/archive/image processing logic;
* identify CLI/API/user-facing functionality;
* identify configuration;
* identify tests;
* identify external dependencies;
* identify Russian-language strings;
* identify obsolete, duplicated, experimental, tightly coupled, or dead code.

For `DWGAnalyzer`:

* inspect the existing architecture;
* identify functionality that already exists;
* identify architectural decisions that should be preserved;
* identify conflicts with the old implementation.

Then create a migration table with columns similar to:

| parsedwg component | Responsibility | Decision | DWGAnalyzer target | Notes |
| ------------------ | -------------- | -------- | ------------------ | ----- |

Use these decisions:

* KEEP — implementation is already good and can be adapted with minimal changes.
* REWRITE — functionality is useful but implementation should be redesigned.
* SIMPLIFY — functionality is useful but over-engineered or unnecessarily complex.
* REMOVE — functionality should not be migrated.

Also explicitly list:

1. functionality worth preserving;
2. functionality to discard;
3. obsolete dependencies;
4. architectural problems;
5. proposed target package structure;
6. migration stages;
7. risks and unclear areas.

Do not start implementation until this analysis is complete.

## Phase 2 — Target architecture

Prefer a simple architecture with clear responsibilities.

The exact structure should follow the actual requirements you discover, but aim for something conceptually similar to:

```text
dwganalyzer/
    __init__.py

    core/
        ...
        
    models/
        ...

    parsers/
        ...
        
    services/
        ...

    io/
        ...

    i18n/
        __init__.py

    cli/
        ...

tests/

locale/
    ru/
        LC_MESSAGES/
            dwganalyzer.po
```

Do not create directories merely to satisfy this example.

Only introduce a package/layer when there is a real architectural reason for it.

Avoid unnecessary abstractions, factories, managers, registries, base classes, interfaces, and dependency injection unless they solve an actual problem.

## Phase 3 — Migration

After the analysis, migrate functionality incrementally.

Rules:

* `parsedwg` is READ-ONLY.
* Never edit `parsedwg`.
* Never perform a mechanical copy of the whole repository.
* Copy individual implementations only when they are worth preserving.
* Prefer rewriting legacy code when it improves clarity.
* Delete obsolete concepts instead of reproducing them in the new project.
* Backward compatibility with `parsedwg` is not required.
* Do not preserve old APIs merely because they existed before.

For every migrated feature:

1. understand the old behavior;
2. decide whether it should be kept;
3. design its place in the new architecture;
4. migrate or rewrite it;
5. migrate/update relevant tests;
6. remove unnecessary dependencies or abstractions.

## English-first codebase

The new project must use English consistently.

Translate Russian text in:

* identifiers where appropriate;
* user-facing messages;
* CLI output;
* error messages;
* exception messages intended for users;
* warnings;
* documentation;
* docstrings;
* comments;
* configuration descriptions.

Internal implementation identifiers must also use clear English names.

Do not mechanically translate terms when a conventional programming or CAD/DWG term already exists in English.

## gettext / i18n

Introduce GNU gettext support.

English is the canonical source language and default/fallback language.

Use gettext only for text that may need localization.

Example:

```python
from dwganalyzer.i18n import _

raise SomeError(_("Unable to read DWG file: {filename}").format(filename=filename))
```

Do not initialize gettext independently in multiple modules.

Create one small centralized i18n module, for example:

```python
# dwganalyzer/i18n/__init__.py
```

It should expose the translation function `_`.

Application code should import `_` from this module rather than directly configuring gettext.

Requirements:

* source strings are English;
* Russian is implemented as a translation catalog;
* use standard `.po` / `.mo` gettext files;
* provide reasonable fallback behavior when a locale/catalog is missing;
* localization should not affect internal program logic;
* avoid translated strings as dictionary keys, enum values, identifiers, or machine-readable values.

Do NOT translate:

* debug-only messages;
* internal structured logging fields;
* protocol values;
* API field names;
* database identifiers;
* DWG/DXF entity names;
* enum/internal constants.

Unless those strings are explicitly intended for an end user.

## Russian translation

Search the old repository for existing Russian messages.

For each useful Russian user-facing message:

1. determine its actual meaning in context;
2. write a natural English source message;
3. add the Russian equivalent to the gettext catalog.

Do not use awkward word-for-word translations.

The resulting code should contain English strings such as:

```python
_("Drawing contains no supported entities")
```

and the Russian translation should live in the `.po` file rather than in Python code.

## Python quality

While migrating:

* use modern Python supported by the project;
* add accurate type hints;
* prefer `pathlib.Path` over manual path manipulation where appropriate;
* use dataclasses/Pydantic only when they provide clear value;
* keep functions reasonably small;
* keep modules focused;
* avoid global mutable state;
* make errors explicit;
* define domain-specific exceptions where useful;
* avoid broad `except Exception` unless there is a concrete boundary reason.

Docstrings must be written in English.

Use Google-style docstrings for public functions/classes where documentation is useful.

Do not add redundant docstrings that merely restate the function signature.

## DWG/DXF domain

Pay particular attention to domain concepts.

Do not mix:

* file discovery;
* archive extraction;
* DWG/DXF parsing;
* entity interpretation;
* drawing analysis;
* reporting/output;
* localization.

These should remain separable responsibilities where practical.

Avoid exposing parser/library-specific objects throughout the entire application.

If the old project leaks third-party DWG/DXF library objects everywhere, consider introducing small domain representations at appropriate boundaries.

However, do not build a large domain model unless the project actually needs it.

## Dependencies

Audit dependencies from `parsedwg`.

For each dependency determine whether it is still necessary.

Do not migrate dependencies merely because the old project used them.

Prefer the Python standard library when it provides a clean solution.

Keep the final dependency set minimal.

## Tests

Reuse useful old tests conceptually, but do not blindly copy tests that encode obsolete architecture.

During migration:

* run focused tests related to the code being changed;
* do not run the entire suite after every tiny change;
* run the broader relevant suite at meaningful checkpoints.

Add tests for:

* important drawing-processing behavior;
* important error paths;
* migrated functionality;
* gettext initialization;
* English fallback;
* Russian translation where practical.

Tests must not depend on the developer machine locale.

## Logging

Keep machine-readable/internal logs in English.

Do not gettext-wrap every logging statement.

Only localize logging output if it is intentionally presented directly to the end user.

Prefer structured logging-friendly messages where appropriate.

## Documentation

Update the project documentation as migration progresses.

At minimum document:

* project purpose;
* architecture;
* supported inputs;
* basic usage;
* development setup;
* testing;
* localization;
* how to extract/update gettext messages;
* how to compile translations;
* how to add another language.

All documentation must be in English.

## Git/change discipline

Make changes in small coherent steps.

Before making a significant architectural change, inspect all usages first.

Do not perform unrelated formatting/refactoring across the repository.

Avoid huge mechanical rewrites unless they are actually necessary.

After each significant migration stage, summarize:

* what was migrated;
* what was rewritten;
* what was removed;
* what remains;
* tests executed;
* important decisions made.

## Important constraints

Do not:

* modify the old `parsedwg` repository;
* blindly reproduce its directory structure;
* preserve obsolete abstractions for compatibility;
* add unnecessary dependencies;
* over-engineer the new project;
* gettext-wrap technical constants or machine-readable strings;
* leave Russian user-facing strings hardcoded in Python;
* translate Python identifiers mechanically without understanding their meaning.

When uncertain whether old functionality is still useful, prefer to flag it in the migration plan rather than automatically migrating it.

Start now with Phase 1 only: inspect both projects and produce the detailed migration analysis and proposed target architecture. Do not modify any files yet.

### Abstract classes and protocols

Use abstract base classes (`ABC`) and `Protocol` sparingly.

Prefer simple concrete classes and functions by default.

Introduce an `ABC` or `Protocol` only when there is a clear architectural benefit, for example:

* multiple interchangeable implementations already exist or are very likely to exist;
* dependency boundaries need to be explicit;
* testability materially improves from the abstraction;
* the abstraction represents a stable domain contract.

Do not create an abstract class or protocol merely to anticipate hypothetical future implementations.

Prefer `Protocol` when structural typing is sufficient and inheritance is not required.

Prefer `ABC` when implementations should share a deliberate inheritance hierarchy, common behavior, or enforced lifecycle.

Before introducing a new abstraction, consider whether a simple concrete type, function, or callable would be clearer.
