```markdown
# mizan Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the core development patterns and conventions used in the `mizan` Python codebase. You'll learn about file naming, import/export styles, commit message conventions, and how to write and run tests. This guide helps maintain consistency and efficiency when contributing to `mizan`.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `myModule.py`, `dataProcessor.py`

### Import Style
- Use **relative imports** within the codebase.
  - Example:
    ```python
    from .utils import helperFunction
    ```

### Export Style
- Use **named exports** (explicitly define what is exported).
  - Example:
    ```python
    __all__ = ['mainFunction', 'helperFunction']
    ```

### Commit Messages
- Follow **conventional commit** patterns.
- Use prefixes such as `docs` for documentation and `feat` for new features.
  - Example:
    ```
    feat: add data normalization to processor
    docs: update usage instructions in README
    ```

## Workflows

### Adding a New Feature
**Trigger:** When implementing new functionality.
**Command:** `/add-feature`

1. Create a new Python file using camelCase naming.
2. Implement the feature using relative imports as needed.
3. Export key functions or classes using `__all__`.
4. Write a test file named `featureName.test.py`.
5. Commit your changes with a `feat:` prefix.
    - Example: `feat: implement user authentication`
6. Push your branch and open a pull request.

### Updating Documentation
**Trigger:** When updating or adding documentation.
**Command:** `/update-docs`

1. Edit or create documentation files as needed.
2. Commit changes with a `docs:` prefix.
    - Example: `docs: add API usage examples`
3. Push your branch and open a pull request.

## Testing Patterns

- Test files follow the pattern `*.test.*` (e.g., `myModule.test.py`).
- The testing framework is **unknown**, so check existing test files for structure.
- Place tests alongside the modules they test or in a dedicated test directory.
- Example test file:
    ```python
    # myModule.test.py
    from .myModule import mainFunction

    def test_mainFunction():
        assert mainFunction(2, 2) == 4
    ```

## Commands
| Command         | Purpose                                 |
|-----------------|-----------------------------------------|
| /add-feature    | Start the workflow for adding a feature |
| /update-docs    | Start the workflow for documentation    |
```
