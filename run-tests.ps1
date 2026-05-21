# Run Oskar integration + unit tests inside the dev container
$result = docker exec `
    -e PYTHONUNBUFFERED=1 `
    oskar-app-dev `
    python -m pytest tests/ --tb=short -q --cov=src --cov-fail-under=80 2>&1

Write-Output $result
