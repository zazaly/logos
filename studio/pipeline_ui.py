"""Qt widgets for named, drag-reorderable rename pipelines."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGraphicsDropShadowEffect,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from studio.pipeline import (
    DEFAULT_PIPELINE_NAME,
    STEP_BY_KEY,
    default_pipeline_library,
    normalise_pipeline_order,
)


class PipelineCanvas(QGraphicsView):
    """Small patch-cable-style graph preview for a pipeline order."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setMinimumHeight(220)
        self.setRenderHints(self.renderHints())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("pipelineCanvas")

    def set_order(self, order: list[str]) -> None:
        self._scene.clear()
        x = 12.0
        y = 42.0
        width = 138.0
        height = 68.0
        gap = 64.0
        sockets: list[tuple[QPointF, QPointF]] = []

        for index, key in enumerate(normalise_pipeline_order(order)):
            step = STEP_BY_KEY[key]
            rect = QGraphicsRectItem(QRectF(x, y, width, height))
            rect.setBrush(QBrush(QColor(32, 36, 48)))
            rect.setPen(QPen(QColor(step.accent), 2))
            rect.setToolTip(step.description)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(16)
            shadow.setOffset(0, 4)
            rect.setGraphicsEffect(shadow)
            self._scene.addItem(rect)

            title = QGraphicsSimpleTextItem(f"{index + 1}. {step.title}")
            title.setBrush(QBrush(QColor("#f5f7ff")))
            title.setPos(x + 12, y + 12)
            self._scene.addItem(title)

            desc = QGraphicsSimpleTextItem(step.description[:25] + ("…" if len(step.description) > 25 else ""))
            desc.setBrush(QBrush(QColor("#a8b3cf")))
            desc.setPos(x + 12, y + 38)
            self._scene.addItem(desc)

            inlet = QPointF(x, y + height / 2)
            outlet = QPointF(x + width, y + height / 2)
            sockets.append((inlet, outlet))
            for point in (inlet, outlet):
                socket = QGraphicsRectItem(QRectF(point.x() - 4, point.y() - 4, 8, 8))
                socket.setBrush(QBrush(QColor(step.accent)))
                socket.setPen(QPen(QColor("#111827"), 1))
                self._scene.addItem(socket)

            x += width + gap

        for left, right in zip(sockets, sockets[1:], strict=False):
            start = left[1]
            end = right[0]
            path = self._scene.addPath(
                self._cable_path(start, end),
                QPen(QColor("#82aaff"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin),
            )
            path.setZValue(-1)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-16, -24, 24, 32))

    @staticmethod
    def _cable_path(start: QPointF, end: QPointF):
        from PySide6.QtGui import QPainterPath

        path = QPainterPath(start)
        dx = max(40.0, (end.x() - start.x()) / 2)
        path.cubicTo(start.x() + dx, start.y() - 42, end.x() - dx, end.y() + 42, end.x(), end.y())
        return path


class PipelineEditor(QGroupBox):
    """Named reusable pipeline editor with drag/drop ordering."""

    order_changed = Signal(list)
    library_changed = Signal(dict, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🎛  RULE PIPELINE", parent)
        self.setObjectName("pipelineEditor")
        self._library = default_pipeline_library()
        self._active_name = DEFAULT_PIPELINE_NAME

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 18, 8, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        self.pipeline_combo = QComboBox()
        self.pipeline_combo.setObjectName("pipelineCombo")
        self.pipeline_combo.currentTextChanged.connect(self._select_pipeline)
        top.addWidget(self.pipeline_combo, stretch=1)

        self.save_button = QPushButton("Save As…")
        self.save_button.clicked.connect(self._save_as)
        top.addWidget(self.save_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_current)
        top.addWidget(self.delete_button)
        root.addLayout(top)

        split = QSplitter(Qt.Vertical)
        self.step_list = QListWidget()
        self.step_list.setObjectName("pipelineStepList")
        self.step_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.step_list.setDefaultDropAction(Qt.MoveAction)
        self.step_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.step_list.model().rowsMoved.connect(self._emit_order_changed)
        split.addWidget(self.step_list)

        self.canvas = PipelineCanvas()
        split.addWidget(self.canvas)
        split.setSizes([260, 240])
        root.addWidget(split)

        self.set_library(self._library, self._active_name)

    def set_library(self, library: dict[str, list[str]] | None, active_name: str | None) -> None:
        merged = default_pipeline_library()
        for name, order in (library or {}).items():
            clean_name = str(name).strip()
            if clean_name:
                merged[clean_name] = normalise_pipeline_order(order)
        self._library = merged
        self._active_name = active_name if active_name in merged else DEFAULT_PIPELINE_NAME
        self._refresh_combo()
        self._load_order(self._library[self._active_name])

    def current_order(self) -> list[str]:
        return [self.step_list.item(row).data(Qt.UserRole) for row in range(self.step_list.count())]

    def pipeline_library(self) -> dict[str, list[str]]:
        self._library[self._active_name] = self.current_order()
        return {name: normalise_pipeline_order(order) for name, order in self._library.items()}

    def active_pipeline_name(self) -> str:
        return self._active_name

    def _refresh_combo(self) -> None:
        self.pipeline_combo.blockSignals(True)
        self.pipeline_combo.clear()
        self.pipeline_combo.addItems(sorted(self._library))
        self.pipeline_combo.setCurrentText(self._active_name)
        self.pipeline_combo.blockSignals(False)
        self.delete_button.setEnabled(self._active_name != DEFAULT_PIPELINE_NAME)

    def _load_order(self, order: list[str]) -> None:
        self.step_list.blockSignals(True)
        self.step_list.clear()
        for key in normalise_pipeline_order(order):
            step = STEP_BY_KEY[key]
            item = QListWidgetItem(f"{step.title}  —  {step.description}")
            item.setData(Qt.UserRole, key)
            item.setToolTip("Drag to rewire this rule group in the deterministic pipeline.")
            self.step_list.addItem(item)
        self.step_list.blockSignals(False)
        self.canvas.set_order(self.current_order())
        self.order_changed.emit(self.current_order())

    def _select_pipeline(self, name: str) -> None:
        if not name or name not in self._library:
            return
        self._library[self._active_name] = self.current_order()
        self._active_name = name
        self.delete_button.setEnabled(name != DEFAULT_PIPELINE_NAME)
        self._load_order(self._library[name])
        self.library_changed.emit(self.pipeline_library(), self._active_name)

    def _emit_order_changed(self, *_args) -> None:
        self._library[self._active_name] = self.current_order()
        self.canvas.set_order(self.current_order())
        self.order_changed.emit(self.current_order())
        self.library_changed.emit(self.pipeline_library(), self._active_name)

    def _save_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Pipeline", "Pipeline name:", text=self._active_name)
        clean_name = name.strip()
        if not ok or not clean_name:
            return
        self._library[clean_name] = self.current_order()
        self._active_name = clean_name
        self._refresh_combo()
        self.library_changed.emit(self.pipeline_library(), self._active_name)

    def _delete_current(self) -> None:
        if self._active_name == DEFAULT_PIPELINE_NAME:
            return
        if QMessageBox.question(self, "Delete Pipeline", f"Delete pipeline '{self._active_name}'?") != QMessageBox.Yes:
            return
        self._library.pop(self._active_name, None)
        self._active_name = DEFAULT_PIPELINE_NAME
        self._refresh_combo()
        self._load_order(self._library[self._active_name])
        self.library_changed.emit(self.pipeline_library(), self._active_name)
