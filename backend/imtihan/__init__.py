"""Imtihan (امتحان): MIZAN's AGI test, the base model alone against MIZAN.

Each task goes to both arms through the debug-mode comparison
(``tadbir.muqabala``) and is scored by rule (``scorers``). The report
(``report``) gives pass rates with Wilson intervals, pass^k, calibration,
paraphrase consistency and cost. ``runner`` runs it in the background and
keeps its history. Task sources and licences are in ``tasks/LICENSES.md``.
"""

from .runner import catalog, load_tasks, run_suite

__all__ = ["catalog", "load_tasks", "run_suite"]
