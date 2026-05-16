"""
F.R.I.D.A.Y. — PyQt6 Transparent Overlay
Two windows:
  FridayOverlay   — small, draggable, semi-transparent status widget (bottom-right)
  AnnotationOverlay — full-screen transparent draw layer for highlighting regions
"""

import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtCore import (
        Qt, QTimer, QPoint, QRect, QPropertyAnimation,
        QEasingCurve, pyqtSignal, QObject, QThread,
    )
    from PyQt6.QtGui import (
        QColor, QPainter, QPen, QBrush, QFont, QFontMetrics,
        QLinearGradient, QPainterPath,
    )
    from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
    HAS_QT = True
except ImportError:
    HAS_QT = False
    logger.error("PyQt6 not installed — overlay unavailable")


# ── State constants ────────────────────────────────────────────────────────

STATE_IDLE      = "idle"
STATE_LISTENING = "listening"
STATE_THINKING  = "thinking"
STATE_SPEAKING  = "speaking"

_STATE_COLORS = {
    STATE_IDLE:      QColor(60,  120, 220, 180) if HAS_QT else None,   # dim blue
    STATE_LISTENING: QColor(40,  210,  80, 220) if HAS_QT else None,   # bright green
    STATE_THINKING:  QColor(240, 160,  20, 220) if HAS_QT else None,   # amber
    STATE_SPEAKING:  QColor(120,  60, 220, 220) if HAS_QT else None,   # purple
}


if HAS_QT:
    class _AnimationTimer(QObject):
        """Drives the pulsing/spinning animation tick."""
        tick = pyqtSignal()

        def __init__(self, interval_ms: int = 50):
            super().__init__()
            self._timer = QTimer()
            self._timer.setInterval(interval_ms)
            self._timer.timeout.connect(self.tick)

        def start(self):
            self._timer.start()

        def stop(self):
            self._timer.stop()


    # ── Main overlay widget ────────────────────────────────────────────────

    class FridayOverlay(QWidget):
        """
        Small, semi-transparent, always-on-top pill widget.
        Shows the current state and last transcript line.
        Draggable anywhere on screen.
        Signals: state_changed(str), text_update(str)
        """

        state_changed = pyqtSignal(str)
        text_update   = pyqtSignal(str)

        _W = 280
        _H = 80

        def __init__(self):
            super().__init__()
            self._state      = STATE_IDLE
            self._transcript = "F.R.I.D.A.Y. ready"
            self._anim_phase = 0.0
            self._drag_pos   = QPoint()

            self._setup_window()
            self._position_window()
            self._start_animation()

            # Connect own signals
            self.state_changed.connect(self._on_state_changed)
            self.text_update.connect(self._on_text_update)

        # ── Setup ──────────────────────────────────────────────────────────

        def _setup_window(self):
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.setFixedSize(self._W, self._H)
            self.setWindowTitle("F.R.I.D.A.Y.")
            opacity = getattr(config, "OVERLAY_OPACITY", 0.92)
            self.setWindowOpacity(opacity)

        def _position_window(self):
            screen = QApplication.primaryScreen().geometry()
            pos    = getattr(config, "OVERLAY_POSITION", "bottom-right")
            margin = 24
            if pos == "bottom-right":
                x = screen.right()  - self._W - margin
                y = screen.bottom() - self._H - margin - 48
            elif pos == "bottom-left":
                x = screen.left() + margin
                y = screen.bottom() - self._H - margin - 48
            elif pos == "top-right":
                x = screen.right() - self._W - margin
                y = screen.top() + margin + 48
            else:  # top-left
                x = screen.left() + margin
                y = screen.top() + margin + 48
            self.move(x, y)
            self.raise_()

        def _start_animation(self):
            self._anim_timer = QTimer()
            self._anim_timer.setInterval(40)   # 25 fps
            self._anim_timer.timeout.connect(self._advance_animation)
            self._anim_timer.start()

        def _advance_animation(self):
            speed = {
                STATE_IDLE:      0.015,
                STATE_LISTENING: 0.06,
                STATE_THINKING:  0.08,
                STATE_SPEAKING:  0.05,
            }.get(self._state, 0.02)
            self._anim_phase = (self._anim_phase + speed) % 1.0
            self.update()

        # ── Painting ───────────────────────────────────────────────────────

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            color = _STATE_COLORS.get(self._state, _STATE_COLORS[STATE_IDLE])

            # Background pill
            bg = QColor(12, 14, 20, 240)
            p.setBrush(QBrush(bg))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, self._W, self._H, 16, 16)

            # Border glow
            border_color = QColor(color)
            border_color.setAlpha(int(120 + 100 * abs(__import__('math').sin(self._anim_phase * 3.14159))))
            pen = QPen(border_color, 1.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, self._W - 2, self._H - 2, 15, 15)

            # State indicator circle (left side)
            cx, cy, cr = 28, self._H // 2, 10
            import math
            pulse = 0.5 + 0.5 * math.sin(self._anim_phase * 2 * math.pi)
            if self._state == STATE_THINKING:
                # spinning arc
                p.setPen(QPen(color, 2.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                start_angle = int(self._anim_phase * 360 * 16)
                p.drawArc(cx - cr, cy - cr, cr * 2, cr * 2, start_angle, 270 * 16)
            elif self._state == STATE_SPEAKING:
                # waveform bars
                bar_color = QColor(color)
                bar_color.setAlpha(200)
                p.setBrush(QBrush(bar_color))
                p.setPen(Qt.PenStyle.NoPen)
                for i in range(5):
                    bar_h = int(4 + 12 * abs(math.sin((self._anim_phase * 2 * math.pi) + i * 0.8)))
                    bx = cx - 10 + i * 5
                    p.drawRect(bx, cy - bar_h // 2, 3, bar_h)
            else:
                # pulsing filled circle
                ring_color = QColor(color)
                ring_color.setAlpha(int(80 + 140 * pulse))
                p.setBrush(QBrush(ring_color))
                p.setPen(Qt.PenStyle.NoPen)
                radius = int(cr * (0.8 + 0.2 * pulse))
                p.drawEllipse(QPoint(cx, cy), radius, radius)

            # State label
            state_font = QFont("Segoe UI", 7)
            state_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
            p.setFont(state_font)
            state_text = {
                STATE_IDLE:      "STANDBY",
                STATE_LISTENING: "LISTENING",
                STATE_THINKING:  "PROCESSING",
                STATE_SPEAKING:  "SPEAKING",
            }.get(self._state, "")
            label_color = QColor(color)
            label_color.setAlpha(200)
            p.setPen(label_color)
            p.drawText(48, 22, state_text)

            # Transcript text
            text_font = QFont("Segoe UI", 8)
            p.setFont(text_font)
            p.setPen(QColor(210, 215, 230, 210))
            # Clip text to fit
            fm      = QFontMetrics(text_font)
            max_w   = self._W - 56
            clipped = fm.elidedText(
                self._transcript, Qt.TextElideMode.ElideRight, max_w
            )
            p.drawText(48, 52, clipped)

            # FRIDAY label (top right, small)
            brand_font = QFont("Segoe UI", 6)
            brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
            p.setFont(brand_font)
            p.setPen(QColor(80, 100, 160, 140))
            p.drawText(self._W - 72, 14, "F.R.I.D.A.Y.")

            p.end()

        # ── Signals / Slots ────────────────────────────────────────────────

        def _on_state_changed(self, state: str):
            self._state = state
            self.update()

        def _on_text_update(self, text: str):
            self._transcript = text
            self.update()

        def set_state(self, state: str):
            """Thread-safe state update via signal."""
            self.state_changed.emit(state)

        def set_text(self, text: str):
            """Thread-safe transcript update via signal."""
            self.text_update.emit(text)

        # ── Drag ──────────────────────────────────────────────────────────

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

        def mouseMoveEvent(self, event):
            if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
                self.move(event.globalPosition().toPoint() - self._drag_pos)


    # ── Annotation overlay ─────────────────────────────────────────────────

    class AnnotationOverlay(QWidget):
        """
        Full-screen transparent always-on-top window.
        Used to highlight regions Friday is "looking at" or pointing to.
        Click-through (WA_TransparentForMouseEvents).
        """

        def __init__(self):
            super().__init__()
            self._annotations: list[dict] = []
            self._setup_window()

        def _setup_window(self):
            screen = QApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        def highlight_region(
            self,
            x: int, y: int, w: int, h: int,
            label: str = "",
            color: tuple = (80, 160, 255),
            duration_ms: int = 4000,
        ):
            """Draw a labeled bounding box on the screen for duration_ms milliseconds."""
            ann = {
                "type":  "rect",
                "x": x, "y": y, "w": w, "h": h,
                "label": label,
                "color": QColor(*color, 180),
            }
            self._annotations.append(ann)
            self.update()
            QTimer.singleShot(duration_ms, lambda: self._remove_annotation(ann))

        def draw_arrow(
            self,
            x1: int, y1: int, x2: int, y2: int,
            color: tuple = (255, 200, 40),
            duration_ms: int = 4000,
        ):
            """Draw an arrow between two screen points."""
            ann = {
                "type":  "arrow",
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "color": QColor(*color, 200),
            }
            self._annotations.append(ann)
            self.update()
            QTimer.singleShot(duration_ms, lambda: self._remove_annotation(ann))

        def clear(self):
            self._annotations.clear()
            self.update()

        def _remove_annotation(self, ann: dict):
            try:
                self._annotations.remove(ann)
            except ValueError:
                pass
            self.update()

        def paintEvent(self, event):
            if not self._annotations:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            for ann in self._annotations:
                c = ann["color"]
                if ann["type"] == "rect":
                    # filled rect with semi-transparent fill + solid border
                    fill = QColor(c)
                    fill.setAlpha(30)
                    p.setBrush(QBrush(fill))
                    pen = QPen(c, 2.5)
                    p.setPen(pen)
                    p.drawRoundedRect(ann["x"], ann["y"], ann["w"], ann["h"], 4, 4)
                    if ann.get("label"):
                        label_font = QFont("Segoe UI", 9)
                        label_font.setBold(True)
                        p.setFont(label_font)
                        p.setPen(c)
                        p.drawText(ann["x"] + 4, ann["y"] - 6, ann["label"])

                elif ann["type"] == "arrow":
                    import math
                    pen = QPen(ann["color"], 3)
                    p.setPen(pen)
                    p.setBrush(QBrush(ann["color"]))
                    p.drawLine(ann["x1"], ann["y1"], ann["x2"], ann["y2"])
                    # Arrowhead
                    angle = math.atan2(ann["y2"] - ann["y1"], ann["x2"] - ann["x1"])
                    ah = 12
                    aa = math.pi / 6
                    pts = [
                        QPoint(ann["x2"], ann["y2"]),
                        QPoint(
                            int(ann["x2"] - ah * math.cos(angle - aa)),
                            int(ann["y2"] - ah * math.sin(angle - aa)),
                        ),
                        QPoint(
                            int(ann["x2"] - ah * math.cos(angle + aa)),
                            int(ann["y2"] - ah * math.sin(angle + aa)),
                        ),
                    ]
                    from PyQt6.QtGui import QPolygon
                    p.drawPolygon(QPolygon(pts))

            p.end()

else:
    # Stubs when PyQt6 is unavailable
    class FridayOverlay:
        def __init__(self): pass
        def show(self): pass
        def set_state(self, s): pass
        def set_text(self, t): pass

    class AnnotationOverlay:
        def __init__(self): pass
        def show(self): pass
        def highlight_region(self, *a, **k): pass
        def draw_arrow(self, *a, **k): pass
        def clear(self): pass
