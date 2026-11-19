"""Validate and stage the three explicitly allowed application packages."""
import argparse
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

PACKAGE_NAMES = ("agents", "tools", "composition")
CACHE_DIRS = {"__pycache__", ".adk", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def check_sources(repository, credentials_file=None):
    repository = Path(repository).resolve()
    roots = [repository / name for name in PACKAGE_NAMES]
    credentials = [Path(value).resolve() for value in (
        credentials_file, os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        os.environ.get("CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"),
    ) if value]
    for root in roots:
        if not root.is_dir() or root.is_symlink() or root.is_junction():
            raise ValueError(f"Missing or linked upload package: {root.name}")
        if any(credential.is_relative_to(root.resolve()) for credential in credentials):
            raise ValueError("Credentials must be outside every uploaded package.")
        for path in root.rglob("*"):
            if path.is_symlink() or path.is_junction():
                raise ValueError(f"Linked paths are not allowed in upload package {root.name}.")
            if any(part in CACHE_DIRS for part in path.relative_to(root).parts):
                continue
            if path.name == ".env" or path.name.startswith(".env."):
                raise ValueError(f"Environment files are not allowed in upload package {root.name}.")
            if path.is_dir():
                continue
            relative = path.relative_to(root).as_posix()
            allowed = path.suffix == ".py" or (
                root.name == "agents" and relative in {"capabilities.yaml", "requirements.txt"}
            )
            if not allowed:
                raise ValueError(f"Unexpected file in upload package {root.name}: {relative}")
    if not (roots[0] / "agent.py").is_file():
        raise ValueError("The agents/agent.py entry point is missing.")
    if not (roots[0] / "requirements.txt").is_file():
        raise ValueError("Export locked dependencies to agents/requirements.txt first.")
    return roots


def prepare_sources(repository, destination, credentials_file=None):
    """Copy only validated sources; never let SDK copying include local caches."""
    roots = check_sources(repository, credentials_file)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Staging destination must be a new directory.")
    if any(destination.is_relative_to(root) for root in roots):
        raise ValueError("Staging destination must be outside upload packages.")
    destination.mkdir(parents=True)
    try:
        for root in roots:
            shutil.copytree(root, destination / root.name, ignore=shutil.ignore_patterns(*CACHE_DIRS))
    except Exception:
        # This exact absolute destination was absent above and created here.
        # Never delete an existing directory supplied by a caller.
        shutil.rmtree(destination)
        raise
    return {"root": str(destination), **{name: str(destination / name) for name in PACKAGE_NAMES}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--credentials-file")
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    try:
        if args.prepare:
            # Only create a staging folder after all validation passes.
            check_sources(args.repository, args.credentials_file)
            destination = Path(tempfile.gettempdir()) / f"adk-sources-{uuid.uuid4().hex}-packages"
            result = prepare_sources(args.repository, destination, args.credentials_file)
            print(json.dumps(result))
        else:
            check_sources(args.repository, args.credentials_file)
            print("Application upload roots validated.")
    except ValueError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
