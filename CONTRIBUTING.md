# Contributing guide

Thank you for your interest in contributing to this project!

Here are a few tips for getting started.

## Quickstart

The project workflow is managed using shell scripts stored in `scripts/`.

First, install dependencies:

```
scripts/install
```

To run the test suite, use:

```
scripts/test
```

To run code formatting:

```
scripts/lint
```

To run code checks alone:

```
scripts/check
```

## Releasing

_Notes to maintainers._

- Create a release PR with the following:
  - Bump the version in `__version__.py`.
  - Update `CHANGELOG.md` with PRs since the last release. PRs that do not alter behavior (such as docs updates, refactors, tooling updates, etc) should not be included.
- Once the release PR is reviewed and merged, create a new release on the GitHub UI, including:
  - Tag version, like `2.1.0`.
  - Release title, `Version 2.1.0`.
  - Description copied from the changelog.
- Once created, the release tag will trigger a 'deploy' job on CI, automatically pushing the new version to PyPI.
