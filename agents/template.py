"""
Template agent module for bug-finding.

Copy this file to create a new agent. Implement setup() and run()
following the interface below, then set CRS_AGENT=<your_module_name>.
"""

from pathlib import Path


def setup(source_dir: Path, config: dict) -> None:
    """One-time agent configuration.

    Called once at startup with the source directory and an agent-specific
    config dict (for example: API URL/key, model token, or agent home dir).
    """
    raise NotImplementedError("Implement setup() for your agent")


def run(
    source_dir: Path,
    build_dir: Path,
    pov_dir: Path,
    diff_dir: Path,
    seed_dir: Path,
    bug_candidate_dir: Path,
    harness: str,
    work_dir: Path,
    *,
    language: str = "c",
    sanitizer: str = "address",
) -> bool:
    """Run the agent autonomously for vulnerability discovery.

    The agent should:
    1. Analyze source code and available evidence (diffs, seeds, bug-candidates)
    2. Identify potential vulnerabilities reachable through the harness
    3. Craft inputs that trigger crashes (POVs)
    4. Verify each POV via `libCRS run-pov`
    5. Write verified POVs to pov_dir/ (auto-submitted by libCRS daemon)

    Returns True if the agent believes it found vulnerabilities.
    """
    raise NotImplementedError("Implement run() for your agent")
