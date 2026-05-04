<# 
Input: current workspace after Package 2.
Output: restored tracked paths via git restore.
Side effects: reverts Package 2 workspace changes for migration paths.
#>

param(
    [switch]$DryRun
)

$paths = @(
    "apps/reference/domains/decision_making",
    "tests/domains/decision_making/test_layered_boundaries.py",
    "tools/migrations/dm_split"
)

foreach ($path in $paths) {
    if ($DryRun) {
        Write-Output "git restore --source=HEAD -- $path"
    } else {
        git restore --source=HEAD -- $path
    }
}
