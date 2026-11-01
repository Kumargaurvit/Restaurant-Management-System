"""Guards the project rules that are easy to forget: settings are documented, deps agree."""

import json
import re
from pathlib import Path

from restaurant_management_system.config import Settings

ROOT = Path(__file__).resolve().parent.parent


def test_every_setting_is_in_env_example_and_the_readme() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    undocumented_env = [
        name.upper()
        for name in Settings.model_fields
        if not re.search(rf"^#?\s*{name.upper()}=", env_example, re.M)
    ]
    undocumented_readme = [name.upper() for name in Settings.model_fields if f"`{name.upper()}`" not in readme]

    assert undocumented_env == [], f"add to .env.example: {undocumented_env}"
    assert undocumented_readme == [], f"add to the README configuration table: {undocumented_readme}"


def test_env_example_only_names_real_settings() -> None:
    known = {name.upper() for name in Settings.model_fields} | {"BACKEND_PORT"}  # docker-compose only
    names = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", (ROOT / ".env.example").read_text(encoding="utf-8"), re.M))

    assert names - known == set(), f"not a setting: {sorted(names - known)}"


def test_every_frontend_package_is_listed_in_requirements_frontend() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    listed = (ROOT / "requirements-frontend.txt").read_text(encoding="utf-8")

    missing = [name for name in {**package["dependencies"], **package["devDependencies"]} if name not in listed]

    assert missing == [], f"add to requirements-frontend.txt: {missing}"


def test_backend_dependencies_agree_between_pyproject_and_requirements() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    requirements = (ROOT / "requirements-backend.txt").read_text(encoding="utf-8").lower()

    pins = set(re.findall(r'"([a-z0-9_.-]+==[0-9][^"]*)"', pyproject))
    missing = [pin for pin in pins if pin not in requirements]

    assert missing == [], f"version differs or missing in requirements-backend.txt: {missing}"


def test_there_is_a_single_migration_head() -> None:
    revisions: dict[str, str | None] = {}
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        revision = re.search(r"^revision(?::[^=]+)? = '([^']+)'", text, re.M)
        parent = re.search(r"^down_revision(?::[^=]+)? = (?:'([^']+)'|None)", text, re.M)
        assert revision, path.name
        revisions[revision.group(1)] = parent.group(1) if parent else None

    parents = {parent for parent in revisions.values() if parent}
    heads = [rev for rev in revisions if rev not in parents]

    assert len(heads) == 1, f"migrations have {len(heads)} heads: {heads}"
