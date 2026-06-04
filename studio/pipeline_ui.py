"""Qt Designer backed widgets for editable rename rule pipelines."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
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
from studio.ui_loader import load_ui


class PipelineNode(QGraphicsRectItem):
    """Movable rule block shown on the pipeline canvas."""

    WIDTH = 150.0
    HEIGHT = 72.0

    def __init__(self, key: str, canvas: PipelineCanvas, pos: QPointF) -> None:
        step = STEP_BY_KEY[key]
        super().__init__(QRectF(0, 0, self.WIDTH, self.HEIGHT))
        self.key = key
        self.canvas = canvas
        self.setPos(pos)
        self.setBrush(QBrush(QColor(32, 36, 48)))
        self.setPen(QPen(QColor(step.accent), 2))
        self.setToolTip(step.description)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

        title = QGraphicsSimpleTextItem(step.title, self)
        title.setBrush(QBrush(QColor("#f5f7ff")))
        title.setPos(14, 12)
        desc = QGraphicsSimpleTextItem(step.description[:28] + ("…" if len(step.description) > 28 else ""), self)
        desc.setBrush(QBrush(QColor("#a8b3cf")))
        desc.setPos(14, 40)

        self.input_socket = QGraphicsEllipseItem(QRectF(-5, self.HEIGHT / 2 - 5, 10, 10), self)
        self.output_socket = QGraphicsEllipseItem(
            QRectF(self.WIDTH - 5, self.HEIGHT / 2 - 5, 10, 10), self
        )
        for socket in (self.input_socket, self.output_socket):
            socket.setBrush(QBrush(QColor(step.accent)))
            socket.setPen(QPen(QColor("#111827"), 1))

    def input_pos(self) -> QPointF:
        return self.mapToScene(0, self.HEIGHT / 2)

    def output_pos(self) -> QPointF:
        return self.mapToScene(self.WIDTH, self.HEIGHT / 2)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.canvas.refresh_cables()
        return super().itemChange(change, value)


class CableItem(QGraphicsPathItem):
    """Right-click removable patch cable between two pipeline nodes."""

    def __init__(self, canvas: PipelineCanvas, src: str, dst: str) -> None:
        super().__init__()
        self.canvas = canvas
        self.src = src
        self.dst = dst
        self.setPen(QPen(QColor("#82aaff"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-10)
        self.setToolTip("Right-click to disconnect")

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.canvas.disconnect(self.src, self.dst)
        event.accept()


class PipelineCanvas(QGraphicsView):
    """Simple VSTHost-style patch canvas for a linear rename pipeline."""

    order_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setMinimumHeight(260)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setObjectName("pipelineCanvas")
        self._nodes: dict[str, PipelineNode] = {}
        self._edges: list[tuple[str, str]] = []
        self._cables: list[CableItem] = []
        self._drag_source: str | None = None
        self._rubber_cable: QGraphicsPathItem | None = None

    def set_order(self, order: list[str]) -> None:
        order = normalise_pipeline_order(order)
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._cables.clear()
        x = 24.0
        for key in order:
            node = PipelineNode(key, self, QPointF(x, 64.0))
            self._nodes[key] = node
            self._scene.addItem(node)
            x += PipelineNode.WIDTH + 70.0
        self._edges = list(zip(order, order[1:], strict=False))
        self.refresh_cables()

    def current_order(self) -> list[str]:
        """Return the connected chain, appending disconnected blocks left-to-right."""
        keys = list(self._nodes)
        outgoing = {src: dst for src, dst in self._edges}
        incoming = {dst for _, dst in self._edges}
        starts = [key for key in keys if key not in incoming]
        starts.sort(key=lambda key: self._nodes[key].pos().x())

        ordered: list[str] = []
        seen: set[str] = set()
        for start in starts:
            key: str | None = start
            while key and key not in seen:
                ordered.append(key)
                seen.add(key)
                key = outgoing.get(key)
        leftovers = [key for key in keys if key not in seen]
        leftovers.sort(key=lambda key: self._nodes[key].pos().x())
        ordered.extend(leftovers)
        return normalise_pipeline_order(ordered)

    def disconnect(self, src: str, dst: str) -> None:
        self._edges = [(a, b) for a, b in self._edges if not (a == src and b == dst)]
        self.refresh_cables()
        self.order_changed.emit(self.current_order())

    def refresh_cables(self) -> None:
        for cable in self._cables:
            self._scene.removeItem(cable)
        self._cables.clear()
        for src, dst in self._edges:
            if src not in self._nodes or dst not in self._nodes:
                continue
            cable = CableItem(self, src, dst)
            cable.setPath(self._cable_path(self._nodes[src].output_pos(), self._nodes[dst].input_pos()))
            self._scene.addItem(cable)
            self._cables.append(cable)
        if self._rubber_cable is not None and self._drag_source in self._nodes:
            self._rubber_cable.setPath(
                self._cable_path(self._nodes[self._drag_source].output_pos(), self.mapToScene(self.mapFromGlobal(self.cursor().pos())))
            )
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-32, -48, 48, 64))

    @staticmethod
    def _cable_path(start: QPointF, end: QPointF) -> QPainterPath:
        path = QPainterPath(start)
        dx = max(40.0, abs(end.x() - start.x()) / 2)
        path.cubicTo(start.x() + dx, start.y(), end.x() - dx, end.y(), end.x(), end.y())
        return path

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = self._socket_hit(event.position().toPoint(), output=True)
        if key:
            self._drag_source = key
            self._rubber_cable = QGraphicsPathItem()
            self._rubber_cable.setPen(QPen(QColor("#c3e88d"), 2, Qt.DashLine))
            self._rubber_cable.setZValue(-5)
            self._scene.addItem(self._rubber_cable)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_source and self._rubber_cable:
            start = self._nodes[self._drag_source].output_pos()
            self._rubber_cable.setPath(self._cable_path(start, self.mapToScene(event.position().toPoint())))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_source:
            dst = self._socket_hit(event.position().toPoint(), output=False)
            src = self._drag_source
            if self._rubber_cable:
                self._scene.removeItem(self._rubber_cable)
            self._drag_source = None
            self._rubber_cable = None
            if dst and dst != src:
                # Keep the graph simple: one output and one input connection per block.
                self._edges = [(a, b) for a, b in self._edges if a != src and b != dst]
                self._edges.append((src, dst))
                self.refresh_cables()
                self.order_changed.emit(self.current_order())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _socket_hit(self, point, *, output: bool) -> str | None:
        scene_point = self.mapToScene(point)
        for key, node in self._nodes.items():
            center = node.output_pos() if output else node.input_pos()
            if (center - scene_point).manhattanLength() <= 14:
                return key
        return None


class PipelineEditor(QWidget):
    """Named reusable pipeline editor loaded from ``gui/pipeline_editor.ui``."""

    order_changed = Signal(list)
    library_changed = Signal(dict, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pipelineEditor")
        self._library = default_pipeline_library()
        self._active_name = DEFAULT_PIPELINE_NAME
        self._updating = False

        self._ui = load_ui("pipeline_editor.ui", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._ui)

        self.pipeline_combo = self._ui.findChild(QComboBox, "pipelineCombo")
        self.save_button = self._ui.findChild(QPushButton, "saveButton")
        self.delete_button = self._ui.findChild(QPushButton, "deleteButton")
        self.step_list = self._ui.findChild(QListWidget, "pipelineStepList")
        placeholder = self._ui.findChild(QGraphicsView, "pipelineCanvas")
        self.canvas = PipelineCanvas()
        splitter = placeholder.parentWidget()
        if not isinstance(splitter, QSplitter):
            raise RuntimeError("pipelineCanvas must live directly inside the pipeline splitter")
        idx = splitter.indexOf(placeholder)
        placeholder.setParent(None)
        splitter.insertWidget(idx, self.canvas)
        placeholder.deleteLater()

        self.pipeline_combo.currentTextChanged.connect(self._select_pipeline)
        self.save_button.clicked.connect(self._save_as)
        self.delete_button.clicked.connect(self._delete_current)
        self.step_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.step_list.setDefaultDropAction(Qt.MoveAction)
        self.step_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.step_list.model().rowsMoved.connect(self._emit_order_changed)
        self.canvas.order_changed.connect(self._canvas_order_changed)
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
        self._load_active()

    def pipeline_library(self) -> dict[str, list[str]]:
        self._library[self._active_name] = self.current_order()
        return {name: list(order) for name, order in self._library.items()}

    def active_pipeline_name(self) -> str:
        return self._active_name

    def current_order(self) -> list[str]:
        return normalise_pipeline_order([self.step_list.item(i).data(Qt.UserRole) for i in range(self.step_list.count())])

    def _refresh_combo(self) -> None:
        self.pipeline_combo.blockSignals(True)
        self.pipeline_combo.clear()
        self.pipeline_combo.addItems(sorted(self._library.keys()))
        self.pipeline_combo.setCurrentText(self._active_name)
        self.pipeline_combo.blockSignals(False)

    def _load_active(self) -> None:
        order = normalise_pipeline_order(self._library.get(self._active_name, []))
        self._set_order_widgets(order)

    def _set_order_widgets(self, order: list[str]) -> None:
        self._updating = True
        self.step_list.clear()
        for key in order:
            step = STEP_BY_KEY[key]
            item = QListWidgetItem(step.title)
            item.setData(Qt.UserRole, key)
            item.setToolTip(step.description)
            self.step_list.addItem(item)
        self.canvas.set_order(order)
        self._updating = False

    def _select_pipeline(self, name: str) -> None:
        if not name or name == self._active_name:
            return
        self._library[self._active_name] = self.current_order()
        self._active_name = name
        self._load_active()
        self.order_changed.emit(self.current_order())
        self.library_changed.emit(self.pipeline_library(), self._active_name)

    def _emit_order_changed(self, *_args) -> None:
        if self._updating:
            return
        order = self.current_order()
        self._library[self._active_name] = order
        self.canvas.set_order(order)
        self.order_changed.emit(order)
        self.library_changed.emit(self.pipeline_library(), self._active_name)

    def _canvas_order_changed(self, order: list[str]) -> None:
        if self._updating:
            return
        self._library[self._active_name] = order
        self._set_order_widgets(order)
        self.order_changed.emit(order)
        self.library_changed.emit(self.pipeline_library(), self._active_name)

    def _save_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Pipeline", "Pipeline name:", text=self._active_name)
        name = name.strip()
        if not ok or not name:
            return
        self._library[name] = self.current_order()
        self._active_name = name
        self._refresh_combo()
        self.library_changed.emit(self.pipeline_library(), self._active_name)

    def _delete_current(self) -> None:
        if self._active_name == DEFAULT_PIPELINE_NAME:
            QMessageBox.information(self, "Pipeline", "The factory pipeline cannot be deleted.")
            return
        del self._library[self._active_name]
        self._active_name = DEFAULT_PIPELINE_NAME
        self._refresh_combo()
        self._load_active()
        self.library_changed.emit(self.pipeline_library(), self._active_name)
        self.order_changed.emit(self.current_order())
