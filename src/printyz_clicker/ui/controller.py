"""ProjectController: owns the single Project, debounces edits and rebuilds geometry
in a background thread. The viewer and the exporter both consume its BuildResult."""

from __future__ import annotations

import copy
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from ..fonts.registry import FontRegistry
from ..geometry.builder import BuildResult, build_project
from ..model.project import Project
from ..text.engine import SyncResult, sync_keys_from_text
from ..validation.checks import ValidationReport, validate


class _Signals(QObject):
    done = Signal(int, object, object)    # generation, BuildResult, ValidationReport
    failed = Signal(int, str)


class _BuildJob(QRunnable):
    def __init__(self, gen: int, project: Project, fonts: FontRegistry):
        super().__init__()
        self.gen, self.project, self.fonts = gen, project, fonts
        self.signals = _Signals()

    def run(self) -> None:
        try:
            res = build_project(self.project, self.fonts)
            rep = validate(res, mesh_checks=False)
            self.signals.done.emit(self.gen, res, rep)
        except Exception as e:  # noqa: BLE001 - surfaced to the user, never hidden
            self.signals.failed.emit(self.gen, f"{e}\n{traceback.format_exc(limit=3)}")


class ProjectController(QObject):
    changed = Signal()                     # project data changed (UI refresh)
    building = Signal()
    built = Signal(object, object)         # BuildResult, ValidationReport
    build_failed = Signal(str)

    def __init__(self, fonts: FontRegistry, project: Project | None = None):
        super().__init__()
        self.fonts = fonts
        self.project = project or Project(name="PRINTYZ")
        self.developer_mode = True
        self.last_sync = SyncResult()
        self.result: BuildResult | None = None
        self.report: ValidationReport | None = None
        self._gen = 0
        self._running = False
        self._dirty = False
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)   # OCC is driven from one worker thread only
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._start_build)

    # ---- edits ---------------------------------------------------------------
    def set_text(self, text: str) -> None:
        self.last_sync = sync_keys_from_text(self.project, text)
        self.touch()

    def touch(self) -> None:
        """Call after any change to self.project."""
        self.changed.emit()
        self._dirty = True
        self._timer.start()

    def replace_project(self, project: Project) -> None:
        self.project = project
        self.last_sync = sync_keys_from_text(project, project.text) if not project.keys else SyncResult(
            total_keys=len(project.keys))
        self.touch()

    # ---- building ------------------------------------------------------------
    def _start_build(self) -> None:
        if self._running:
            return  # picked up again when the running job finishes
        self._dirty = False
        self._running = True
        self._gen += 1
        job = _BuildJob(self._gen, copy.deepcopy(self.project), self.fonts)
        job.signals.done.connect(self._on_done)
        job.signals.failed.connect(self._on_failed)
        self.building.emit()
        self._pool.start(job)

    def _finish(self) -> bool:
        self._running = False
        if self._dirty:
            self._timer.start(10)
            return False
        return True

    def _on_done(self, gen: int, res: BuildResult, rep: ValidationReport) -> None:
        if not self._finish():
            return
        self.result, self.report = res, rep
        self.built.emit(res, rep)

    def _on_failed(self, gen: int, msg: str) -> None:
        if not self._finish():
            return
        self.build_failed.emit(msg)

    def wait_idle(self, timeout_ms: int = 120000) -> None:
        """Test helper: block until the pending build finished."""
        from PySide6.QtCore import QCoreApplication, QElapsedTimer

        t = QElapsedTimer()
        t.start()
        while (self._timer.isActive() or self._running) and t.elapsed() < timeout_ms:
            QCoreApplication.processEvents()
            self._pool.waitForDone(50)
        QCoreApplication.processEvents()
