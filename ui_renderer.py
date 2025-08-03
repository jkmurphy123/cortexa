from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QMainWindow,
    QGraphicsOpacityEffect,
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QTextOption
from PyQt6.QtCore import Qt, QRect, QRectF, QTimer
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

class SpeechBalloonWidget(QWidget):
    def __init__(self, balloon_spec, parent=None):
        super().__init__(parent)
        self.balloon_spec = balloon_spec
        self.text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.font = QFont("Sans Serif", 14)
        self.padding = 8

        # Opacity effect for fade
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(1.0)
        self._fading = False

    def set_text(self, new_text):
        # Immediately set text (no fade) unless in fade process
        self.text = new_text
        self.effect.setOpacity(1.0)
        self.update()

    def clear(self):
        self.text = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # draw balloon background
        rect = QRect(
            self.balloon_spec.get("x_pos", 100),
            self.balloon_spec.get("y_pos", 50),
            self.balloon_spec.get("width", 400),
            self.balloon_spec.get("height", 250),
        )
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(QColor(50, 50, 50))
        painter.drawRoundedRect(rect, 12, 12)

        # draw text inside with wrapping
        painter.setFont(self.font)
        inner = rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        painter.setPen(QColor(20, 20, 20))
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WordWrap)

        painter.drawText(QRectF(inner), self.text, option)

    def would_overflow(self, candidate_text):
        """Return True if candidate_text would overflow the balloon area."""
        rect = QRect(
            self.balloon_spec.get("x_pos", 100),
            self.balloon_spec.get("y_pos", 50),
            self.balloon_spec.get("width", 400),
            self.balloon_spec.get("height", 250),
        )
        inner = rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        metrics = QFontMetrics(self.font)
        # Use boundingRect with word wrap to measure height
        bounding = metrics.boundingRect(
            QRectF(inner),
            Qt.TextFlag.TextWordWrap,
            candidate_text,
        )
        return bounding.height() > inner.height()

    def fade_out_and_clear(self, pause_before=0, fade_duration=1500, on_finished=None):
        if self._fading:
            return  # already fading
        self._fading = True

        def do_fade():
            anim = QPropertyAnimation(self.effect, b"opacity", self)
            anim.setDuration(fade_duration)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

            def after():
                self.clear()
                self.effect.setOpacity(1.0)
                self._fading = False
                if on_finished:
                    on_finished()

            anim.finished.connect(after)
            anim.start()

        if pause_before > 0:
            QTimer.singleShot(pause_before * 1000, do_fade)
        else:
            do_fade()

class MainWindow(QMainWindow):
    def __init__(self, personality, topic, images_dir=None, on_ready_callback=None):
        super().__init__()
        self.setWindowTitle("Personality Streamer")
        self.personality = personality
        self.topic = topic
        self.on_ready_callback = on_ready_callback
        self.images_dir = Path(images_dir) if images_dir else None

        # Will hold scaled background
        self._background_pixmap = None
        self._raw_avatar_pixmap = None

        # Central widget (empty, painting happens in paintEvent)
        central = QWidget()
        self.setCentralWidget(central)
        self.layout = QVBoxLayout()
        central.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Speech balloon overlay (overlayed via stacking: added after stretch)
        self.balloon_widget = SpeechBalloonWidget(personality.get("speech_balloon", {}), parent=self)
        self.balloon_widget.setFixedSize(1000, 800)  # will be updated if needed
        self.layout.addWidget(self.balloon_widget, stretch=1)

        # Typing indicator (overlayed beneath balloon)
        self.typing_label = QLabel("")
        self.typing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.typing_label.setStyleSheet("color: white; font-size: 16px;")
        self.layout.addWidget(self.typing_label, stretch=0)

        # Load avatar image as background
        self.load_avatar(personality.get("image_file_name"))

        # Fullscreen initial size
        self.resize(1024, 768)
        self.showFullScreen()
        self.balloon_widget.raise_()
        self.typing_label.raise_()

    def load_avatar(self, image_file):
        if not image_file:
            return

        candidates = []
        img_path = Path(image_file)
        if img_path.is_absolute():
            candidates.append(img_path)
        else:
            candidates.append(Path(image_file))
            if self.images_dir:
                candidates.append(self.images_dir / image_file)
            base_dir = Path(__file__).resolve().parent
            if self.images_dir:
                candidates.append(base_dir / self.images_dir / image_file)

        pix = None
        for p in candidates:
            if p.exists():
                pix = QPixmap(str(p))
                break

        if pix and not pix.isNull():
            self._raw_avatar_pixmap = pix
            self._rescale_background()
        else:
            tried = ", ".join(str(p) for p in candidates)
            # fallback: blank background, maybe show missing
            print(f"[warning] Avatar image '{image_file}' not found. Tried: {tried}")

    def resizeEvent(self, event):
        super().resizeEvent(event)        
        # ensure balloon covers window if you want dynamic repositioning
        self.balloon_widget.setFixedSize(self.size())

    def _rescale_background(self):
        if not self._raw_avatar_pixmap:
            return
        # Cover the window: scale preserving aspect, cropping if necessary
        window_size = self.size()
        if window_size.width() <= 0 or window_size.height() <= 0:
            return
        scaled = self._raw_avatar_pixmap.scaled(
            window_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._background_pixmap = scaled

    def paintEvent(self, event):
        # Draw the background image first
        if self._background_pixmap:
            painter = QPainter(self)
            # center-crop logic: draw so the pixmap covers full window
            pix = self._background_pixmap
            w, h = self.width(), self.height()
            pw, ph = pix.width(), pix.height()
            x = (w - pw) // 2
            y = (h - ph) // 2
            painter.drawPixmap(x, y, pix)
        super().paintEvent(event)

    def display_chunk_with_typing(self, chunk, inter_chunk_pause, on_complete=None):
        words = chunk.split()
        displayed = []
        self.typing_label.setText("typing...")
        index = 0

        def step():
            nonlocal index
            if index >= len(words):
                self.typing_label.setText("")
                full_text = " ".join(displayed)
                self.balloon_widget.set_text(full_text)
                if on_complete:
                    on_complete()
                return
            displayed.append(words[index])
            self.balloon_widget.set_text(" ".join(displayed))
            index += 1
            QTimer.singleShot(50, step)

        step()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        elif event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.Control:
            self.close()
        else:
            super().keyPressEvent(event)
