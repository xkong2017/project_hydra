#!/bin/bash
# Run HydraCode-6 tests in Docker containers
# Usage: ./run_tests_docker.sh [test_type]
#   test_type: unit, integration, e2e, smoke, all (default: all)

set -euo pipefail

TEST_TYPE="${1:-all}"
IMAGE_NAME="hydra-code-test"
CONTAINER_NAME="hydra-code-test-$$"

echo "=== HydraCode-6 Docker Test Runner ==="
echo "Test type: ${TEST_TYPE}"
echo ""

# Build Docker image
echo "Building Docker image..."
docker build -f Dockerfile.test -t "${IMAGE_NAME}" .

# Clean up any existing container with the same name
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

# Run tests based on type
case "${TEST_TYPE}" in
  unit)
    echo "Running unit tests..."
    docker run --rm --name "${CONTAINER_NAME}" \
      "${IMAGE_NAME}" pytest tests/unit/ -v --tb=short -m unit
    ;;
  integration)
    echo "Running integration tests (with git fixtures)..."
    # Only run tests that use git_repo fixture - skip tests that assume CWD is a git repo
    docker run --rm --name "${CONTAINER_NAME}" \
      "${IMAGE_NAME}" pytest tests/integration/ -v --tb=short -k "git_repo or worktree or extract_patch or cleanup"
    ;;
  e2e)
    echo "Running E2E tests (mocked)..."
    docker run --rm --name "${CONTAINER_NAME}" \
      "${IMAGE_NAME}" pytest tests/e2e/ -v --tb=short -m "e2e and not smoke"
    ;;
  smoke)
    echo "Running smoke tests (requires real LLM)..."
    if [ "${HYDRA_SMOKE:-0}" != "1" ]; then
      echo "Skipping smoke tests - set HYDRA_SMOKE=1 to enable"
      exit 0
    fi
    docker run --rm --name "${CONTAINER_NAME}" \
      -e HYDRA_SMOKE=1 \
      -e CLAUDE_BIN="${CLAUDE_BIN:-claude}" \
      "${IMAGE_NAME}" pytest tests/e2e/test_smoke.py -v --tb=short -m smoke
    ;;
  all)
    echo "Running all tests (except integration and smoke)..."
    docker run --rm --name "${CONTAINER_NAME}" \
      "${IMAGE_NAME}" pytest tests/ -v --tb=short -m "not integration and not smoke"
    ;;
  *)
    echo "Unknown test type: ${TEST_TYPE}"
    echo "Available: unit, integration, e2e, smoke, all"
    exit 1
    ;;
esac

EXIT_CODE=$?
echo ""
echo "Test run completed with exit code: ${EXIT_CODE}"
exit ${EXIT_CODE}