#!/usr/bin/env bash
# Preview or apply the repository settings that enforce this project's rebase-only workflow.
set -euo pipefail

apply=false
include_admins=false
maintainer=""

usage() {
  echo "usage: $0 [--dry-run|--apply] [--include-admins] [--maintainer LOGIN]"
}

while (($#)); do
  case "$1" in
    --dry-run) apply=false ;;
    --apply) apply=true ;;
    --include-admins) include_admins=true ;;
    --maintainer)
      shift
      [[ $# -gt 0 ]] || { usage; exit 2; }
      maintainer="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

command -v gh >/dev/null || { echo "error: gh is required" >&2; exit 1; }
repo="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
maintainer="${maintainer:-$(gh api user --jq .login)}"
maintainer_id="$(gh api "users/$maintainer" --jq .id)"

apply_json() {
  local label="$1" method="$2" endpoint="$3" body="$4"
  echo "$label"
  echo "  $method $endpoint"
  if [[ "$apply" == true ]]; then
    printf '%s\n' "$body" | gh api --method "$method" "$endpoint" --input - >/dev/null
    echo "  applied"
  else
    echo "  dry-run (use --apply to execute)"
  fi
}

repo_settings='{
  "allow_merge_commit": false,
  "allow_squash_merge": false,
  "allow_rebase_merge": true,
  "delete_branch_on_merge": true
}'

branch_rules="$(cat <<JSON
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["history", "test", "consistency"]
  },
  "enforce_admins": $include_admins,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
)"

environment="$(cat <<JSON
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "reviewers": [{"type": "User", "id": $maintainer_id}]
}
JSON
)"

echo "repository=$repo maintainer=$maintainer include_admins=$include_admins mode=$([[ "$apply" == true ]] && echo apply || echo dry-run)"
apply_json "Enable rebase-only merging and delete merged branches" PATCH "repos/$repo" "$repo_settings"
apply_json "Protect main with PRs, required CI and linear history" PUT "repos/$repo/branches/main/protection" "$branch_rules"
apply_json "Create/update npm environment with required reviewer $maintainer" PUT "repos/$repo/environments/npm" "$environment"

echo "done"
