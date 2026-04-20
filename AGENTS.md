# Project guidelines

These rules apply to any change in this repo — human or AI. They exist so that code review is spent on substance, not style, and so that strictness isn't quietly eroded.

## Linting and formatting

`ruff` is the single source of truth for style, lint, and import ordering. The configuration in `pyproject.toml` is deliberately strict (ANN, D, S, TRY, FBT, PTH, ERA, and many others).

**Do not circumvent lint failures.** The fix for a ruff violation is to fix the code, not to silence the rule.

Forbidden anywhere in source, tests, and scripts:

- `# noqa` (with or without a rule code)
- `# type: ignore`
- `# fmt: off` / `# fmt: on`
- `# ruff: noqa`

`tests/test_no_noqa_policy.py` enforces this and will fail CI if any forbidden comment appears.

If a rule genuinely shouldn't apply project-wide, adjust the `ignore = [...]` list in `pyproject.toml` and leave an inline comment explaining why. For structural exceptions (e.g., `assert` in tests), use `tool.ruff.lint.per-file-ignores`. Never silence at the call site.

Run locally:

```bash
uv run ruff check .
uv run ruff format --check .
```

Auto-fix safe issues:

```bash
uv run ruff check --fix .
uv run ruff format .
```

## Docstrings

Every public module, class, function, and method has a Google-style docstring:

1. One-line imperative summary (`Return ...`, not `Returns ...`).
2. Blank line, then extended description if non-obvious.
3. `Args:`, `Returns:`, `Raises:` sections as applicable.

**Never repeat type information that is already in the signature.** The annotation is canonical; the docstring explains intent and edge cases. Write `word: The surface form to look up.` — not `word (str): ...`.

Private helpers (leading underscore) get a short docstring only when behavior is non-obvious.

## Tests

- `pytest` runs the test suite. Unit tests live under `tests/unit/`, integration under `tests/integration/`, browser end-to-end under `tests/e2e/`.
- Every new module gets a matching test file.
- Tests must not reach the network by default. Network-dependent tests are marked `@pytest.mark.network` and opted in with `--run-network`.

## Dependencies

Managed with `uv`. To add a dependency:

```bash
uv add <package>
uv add --group dev <package>   # for dev-only tools
```

Commit `pyproject.toml` and `uv.lock`.

## Supported languages

The core set is defined in `src/ebook_langlearner/languages.py`. Adding a language means adding it there, verifying wordfreq and simplemma both support it, and adding a fixture-level test.
