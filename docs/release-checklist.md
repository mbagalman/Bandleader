# Bandleader Release Checklist

## Version and Changelog

1. Confirm target release version.
2. Update version in `pyproject.toml` (`[project].version`) and `bandleader/__init__.py` (`__version__`) — they must match.
3. Update [CHANGELOG.md](../CHANGELOG.md):
   - move items from `Unreleased` to a dated release section
   - include major fixes, behavior changes, and migration notes

## Quality Gate

1. Run tests:
```bash
python3 -m pytest -q
```
2. Run quick CLI smoke checks:
```bash
python3 -m bandleader --help
python3 -m bandleader.stem_cleaner --help
python3 -m bandleader.bass_generator --help
python3 -m bandleader.arp_generator --help
```
3. Validate docs examples still match current CLI flags and config schema.

## Packaging and Tagging

1. Commit release changes.
2. Delete stale build artifacts so old versions cannot be uploaded by accident:
```bash
rm -rf dist/ build/ *.egg-info/
```
3. Build fresh distributions and confirm `dist/` contains only the target version:
```bash
python3 -m build --sdist --wheel
ls dist/
```
4. Create tag:
```bash
git tag vX.Y.Z
```
5. Push branch and tag:
```bash
git push origin <branch>
git push origin vX.Y.Z
```

## Post-Release

1. Create next `Unreleased` section in `CHANGELOG.md`.
2. Record any hotfix candidates from issues/feedback as GitHub issues.
