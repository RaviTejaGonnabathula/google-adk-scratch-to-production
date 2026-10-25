"""Read deployment YAML or perform read-only IAM checks. Never print credentials."""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import yaml

# Import only the shared loader, without importing/instantiating the agent.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app/src/agents"))
from model_settings import resolve_model_settings


def read_config(path, **model_overrides):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping.")
    runtime = data["deployment"]["agentruntime"]
    allowed = {"region", "display_name", "service_account", "agent_engine_id"}
    if not isinstance(runtime, dict) or set(runtime) - allowed:
        raise ValueError("Unknown Agent Runtime configuration fields.")
    values = dict(runtime)
    values.update(resolve_model_settings(path, **model_overrides))
    values["project_id"] = data["google_cloud"]["project_id"]
    values["credentials_file"] = data["deployment"].get("credentials_file")
    if any(value is not None and not isinstance(value, str) for value in values.values()):
        raise ValueError("Settings must be strings or null; quote numeric resource IDs.")
    return values


def runtime_config(model_location, model_name):
    if not isinstance(model_location, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", model_location):
        raise ValueError("A valid model_location is required.")
    # Never put the local credentials or reserved runtime variables into env_vars.
    settings = resolve_model_settings(model_name=model_name, model_location=model_location)
    return {"env_vars": {"ADK_MODEL_LOCATION": settings["model_location"], "ADK_MODEL_NAME": settings["model_name"]}}


def write_runtime_config(model_location, model_name):
    config = runtime_config(model_location, model_name)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", prefix="adk-model-", delete=False, encoding="utf-8") as handle:
        json.dump(config, handle)
        return handle.name


def preflight(project, account, updating):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    checks = [
        (f"https://cloudresourcemanager.googleapis.com/v1/projects/{project}:testIamPermissions",
         ["resourcemanager.projects.get", "serviceusage.services.use",
          "aiplatform.reasoningEngines.update" if updating else "aiplatform.reasoningEngines.create"]),
        (f"https://iam.googleapis.com/v1/projects/-/serviceAccounts/{account}:testIamPermissions",
         ["iam.serviceAccounts.actAs"]),
    ]
    missing = []
    for url, permissions in checks:
        response = session.post(url, json={"permissions": permissions}, timeout=30)
        if not response.ok:
            stage = "runtime-account actAs" if "iam.googleapis.com" in url else "project"
            raise ValueError(f"{stage} IAM verification failed (HTTP {response.status_code}); deployment blocked.")
        granted = response.json().get("permissions", [])
        missing.extend(p for p in permissions if p not in granted)
    if missing:
        raise ValueError("Missing deployment permissions: " + ", ".join(missing))
    print("Core deployer IAM checks passed. Build/service-agent IAM, SDK, billing, APIs, and model availability still require verification.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--project")
    parser.add_argument("--account")
    parser.add_argument("--updating", action="store_true")
    parser.add_argument("--write-runtime-config")
    parser.add_argument("--model-config")
    parser.add_argument("--model-name")
    parser.add_argument("--model-location")
    args = parser.parse_args()
    try:
        if args.write_runtime_config:
            print(write_runtime_config(args.write_runtime_config, args.model_name))
        elif args.model_config:
            print(json.dumps(resolve_model_settings(args.model_config, model_name=args.model_name, model_location=args.model_location)))
        elif args.config:
            print(json.dumps(read_config(args.config, model_name=args.model_name, model_location=args.model_location)))
        else:
            if not args.project or not args.account:
                raise ValueError("Project and runtime account are required.")
            preflight(args.project, args.account, args.updating)
    except (ValueError, KeyError, TypeError):
        # YAML/key parsing errors may contain source text; only expose our safe messages.
        error = sys.exc_info()[1]
        if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError):
            print(str(error), file=sys.stderr)
        else:
            print("Invalid deployment configuration.", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(f"Configuration or authentication check failed ({type(error).__name__}). No deployment was attempted.", file=sys.stderr)
        sys.exit(1)
