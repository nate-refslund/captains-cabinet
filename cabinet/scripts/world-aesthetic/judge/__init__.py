"""VISION JUDGE — pairwise LLM-judge protocol for Cabinet World frames.

The mechanical gates (../gates/) catch recorded failure classes
deterministically; this package carries the JUDGMENT half: protocol in code,
judgment via agents at call time (the cabinet pattern). `judge_protocol.py
build` emits a blinded pairwise task list JSON for an LLM runner;
`judge_protocol.py ingest` computes calibration-gated verdicts from the
filled results. `goldens.py` pins Captain-approved frames as regression
goldens and appends Captain verdicts to the calibration corpus.

IMPORT CONTRACT: loaded via ../_loader.py as the unique module name
"world_aesthetic_judge" (mirror of the gates contract — never importable
under a generic name). The CLI modules re-anchor themselves onto this
package when executed directly (PEP 366), so
`python3.12 .../judge/judge_protocol.py` works without sys.path mutation.
"""

from . import _corpus  # noqa: F401
from . import calibration  # noqa: F401
from . import goldens  # noqa: F401
from . import judge_protocol  # noqa: F401

TASKS_SCHEMA = "cabinet.world.judge-tasks/v1"
KEY_SCHEMA = "cabinet.world.judge-key/v1"
RUN_SCHEMA = "cabinet.world.judge-run/v1"
RESULTS_SCHEMA = "cabinet.world.judge-results/v1"
VERDICTS_SCHEMA = "cabinet.world.judge-verdicts/v1"
GOLDENS_SCHEMA = "cabinet.world.goldens/v1"
GOLDEN_DIFF_SCHEMA = "cabinet.world.golden-diff/v1"
