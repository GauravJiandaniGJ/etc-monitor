#!/bin/bash
# Test runner script for ETC Monitor application
# 
# Usage:
#   ./scripts/run_tests.sh           # Run all tests with coverage
#   ./scripts/run_tests.sh unit      # Run only unit tests
#   ./scripts/run_tests.sh integration  # Run only integration tests

set -e

# Change to project root
cd "$(dirname "$0")/.."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Running ETC Monitor Test Suite${NC}"
echo "========================================"

# Determine which tests to run
TEST_PATH="tests/"
if [ "$1" == "unit" ]; then
    TEST_PATH="tests/unit/ tests/parsers/"
    echo "Running UNIT tests only..."
elif [ "$1" == "integration" ]; then
    TEST_PATH="tests/integration/"
    echo "Running INTEGRATION tests only..."
else
    echo "Running ALL tests..."
fi

# Run pytest with coverage
python -m pytest $TEST_PATH \
    -v \
    --tb=short \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=html:htmlcov

echo ""
echo -e "${GREEN}✓ Tests complete!${NC}"
echo "Coverage report: htmlcov/index.html"
