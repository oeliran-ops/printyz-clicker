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
    history_changed = Signal(bool, bool)   # can_undo, can_redo
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
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._start_build)
        # undo history: a snapshot is committed once edits pause (a slider drag = one step)
        self._undo: list[Project] = []
        self._redo: list[Project] = []
        self._stable = copy.deepcopy(self.project)
        self._hist_timer = QTimer(self)
        self._hist_timer.setSingleShot(True)
        self._hist_timer.setInterval(600)
        self._hist_timer.timeout.connect(self._commit_history)

    # ---- edits ---------------------------------------------------------------
    def set_text(self, text: str) -> None:
        self.last_sync = sync_keys_from_text(self.project, text)
        self.touch()

    def touch(self, record: bool = True) -> None:
        """Call after any change to self.project."""
        self.changed.emit()
        self._dirty = True
        self._timer.start()
        if record:
            self._hist_timer.start()

    # ---- undo / redo -----------------------------------------------------------
    def _commit_history(self) -> None:
        if self._stable.to_dict() == self.project.to_dict():
            return
        self._undo.append(self._stable)
        del self._undo[:-100]
        self._redo.clear()
        self._stable = copy.deepcopy(self.project)
        self.history_changed.emit(True, False)

    def reset_history(self) -> None:
        """Start the undo history at the current project (after loading / initial setup)."""
        self._hist_timer.stop()
        self._undo.clear()
        self._redo.clear()
        self._stable = copy.deepcopy(self.project)
        self.history_changed.emit(False, False)

    def _restore(self, snap: Project) -> None:
        self.project = copy.deepcopy(snap)
        self._stable = copy.deepcopy(snap)
        self.last_sync = SyncResult(total_keys=len(self.project.keys))
        self.touch(record=False)
        self.history_changed.emit(bool(self._undo), bool(self._redo))

    def undo(self) -> None:
        self._commit_history()          # an edit still pending becomes undoable first
        if self._undo:
            self._redo.append(copy.deepcopy(self.project))
            self._restore(self._undo.pop())

    def redo(self) -> None:
        if self._redo:
            self._undo.append(copy.deepcopy(self.project))
            self._restore(self._redo.pop())

    def replace_project(self, project: Project) -> None:
        self.project = project
        self.last_sync = sync_keys_from_text(project, project.text) if not project.keys else SyncResult(
            total_keys=len(project.keys))
        self.touch(record=False)
        self.reset_history()

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
