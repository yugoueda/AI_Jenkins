#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
env_file="${project_root}/.env"
job_script="${project_root}/jenkins/init.groovy.d/create-ai-review-jobs.groovy"
jenkins_url="${JENKINS_URL:-http://127.0.0.1:8080}"

if [ ! -f "${env_file}" ]; then
  echo "error: ${env_file} does not exist" >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "${env_file}" | tail -n 1
}

jenkins_user="$(read_env_value JENKINS_USER)"
jenkins_token="$(read_env_value JENKINS_TOKEN)"

if [ -z "${jenkins_user}" ] || [ -z "${jenkins_token}" ]; then
  echo "error: set JENKINS_USER and JENKINS_TOKEN in ${env_file}" >&2
  exit 1
fi

curl --fail --silent --show-error \
  --user "${jenkins_user}:${jenkins_token}" \
  --data-urlencode "script@${job_script}" \
  "${jenkins_url}/scriptText"

echo
echo "Jenkins job definitions refreshed."
