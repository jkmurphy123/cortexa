from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QMainWindow,
    QGraphicsOpacityEffect,
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QTextOption, QFontMetrics
from PyQt6.QtCore import (
    Qt,
    QRect,
    QRectF,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
)


class SpeechBalloonWidget(QWidget):
    def __init__(self, balloon_spec, parent=None):
        super().__init__(parent)
        self.balloon_spec = balloon_spec or {}
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.font = QFont("Sans Serif", 14)
        self.padding = 8

        # Text label overlayed inside the balloon
        self.text_label = QLabel(self)
        self.text_label.setWordWrap(True)
        self.text_label.setFont(self.font)
        self.text_label.setStyleSheet("color: black; background: transparent;")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_label.setText("")  # start empty

        # Opacity effect for text (only the text fades)
        self.text_effect = QGraphicsOpacityEffect(self.text_label)
        self.text_label.setGraphicsEffect(self.text_effect)
        self.text_effect.setOpacity(1.0)
        self._fading = False
        self._current_anim = None  # keep reference so it isn't garbage-collected

    @property
    def text(self):
        return self.text_label.text()

    def set_text(self, new_text):
        self.text_label.setText(new_text)
        self.text_effect.setOpacity(1.0)
        self.update_label_geometry()
        self.update()

    def clear(self):
        self.text_label.setText("")
        self.text_effect.setOpacity(1.0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw balloon background
        rect = QRect(
            self.balloon_spec.get("x_pos", 100),
            self.balloon_spec.get("y_pos", 50),
            self.balloon_spec.get("width", 400),
            self.balloon_spec.get("height", 250),
        )
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(QColor(50, 50, 50))
        painter.drawRoundedRect(rect, 12, 12)

        # Ensure label is positioned correctly inside balloon
        self.update_label_geometry()

    def update_label_geometry(self):
        rect = QRect(
            self.balloon_spec.get("x_pos", 100),
            self.balloon_spec.get("y_pos", 50),
            self.balloon_spec.get("width", 400),
            self.balloon_spec.get("height", 250),
        )
        inner = rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        # QLabel expects QRect for geometry
        self.text_label.setGeometry(inner)

    def would_overflow(self, candidate_text):
        rect = QRect(
            self.balloon_spec.get("x_pos", 100),
            self.balloon_spec.get("y_pos", 50),
            self.balloon_spec.get("width", 400),
            self.balloon_spec.get("height", 250),
        )
        inner = rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        metrics = QFontMetrics(self.font)
        # Use boundingRect with word-wrap flag to get required height
        flags = int(Qt.TextFlag.TextWordWrap)
        bounding = metrics.boundingRect(inner, flags, candidate_text)
        return bounding.height() > inner.height()

    def fade_out_and_clear(self, pause_before=0, fade_duration=1500, on_finished=None):
        if self._fading:
            return
        self._fading = True

        def do_fade():
            anim = QPropertyAnimation(self.text_effect, b"opacity", self)
            self._current_anim = anim  # hold reference
            anim.setDuration(fade_duration)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

            def after():
                self.clear()
                self.text_effect.setOpacity(1.0)
                self._fading = False
                self._current_anim = None
                if on_finished:
                    on_finished()

            anim.finished.connect(after)
            anim.start()

        if pause_before > 0:
            QTimer.singleShot(pause_before * 1000, do_fade)
        else:
            do_fade()

class MainWindow(QMainWindow):
    def __init__(self, personality, topic, images_dir=None, screen_width=1024, screen_height=768, on_ready_callback=None):
        super().__init__()
        self.setWindowTitle("Personality Streamer")
        self.personality = personality or {}
        self.topic = topic
        self.on_ready_callback = on_ready_callback
        self.images_dir = Path(images_dir) if images_dir else None
        self.screen_size = QSize(screen_width, screen_height)

        self._background_pixmap = None
        self._raw_avatar_pixmap = None
        self._background_scaled_done = False

        # Central setup
        central = QWidget()
        self.setCentralWidget(central)
        self.layout = QVBoxLayout()
        central.setLayout(self.layout)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Speech balloon widget (fixed size from spec)
        spec = self.personality.get("speech_balloon", {})
        balloon_w = spec.get("width", 400)
        balloon_h = spec.get("height", 250)
        self.balloon_widget = SpeechBalloonWidget(spec, parent=self)
        self.balloon_widget.setFixedSize(balloon_w * 2, balloon_h * 2)  #temp
        self.balloon_widget.setStyleSheet("border: 2px solid red;")  #temp
        self.layout.addWidget(self.balloon_widget, stretch=1)

        # Typing indicator
        self.typing_label = QLabel("")
        self.typing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.typing_label.setStyleSheet("color: white; font-size: 16px;")
        self.layout.addWidget(self.typing_label, stretch=0)

        # Load avatar image (background)
        self.load_avatar(self.personality.get("image_file_name"))

        # Initial window size from config before going fullscreen
        self.resize(self.screen_size)
        self.showFullScreen()
        self.balloon_widget.raise_()
        self.typing_label.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._background_scaled_done:
            self._rescale_background()
            self._background_scaled_done = True

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

        for p in candidates:
            if p.exists():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    self._raw_avatar_pixmap = pix
                    return
        tried = ", ".join(str(p) for p in candidates)
        print(f"[warning] Avatar image '{image_file}' not found. Tried: {tried}")

    def _rescale_background(self):
        if not self._raw_avatar_pixmap:
            return
        # Scale once to the configured screen size (not dynamic resizing)
        target = self.screen_size
        if target.width() <= 0 or target.height() <= 0:
            return
        scaled = self._raw_avatar_pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._background_pixmap = scaled

    def paintEvent(self, event):
        if self._background_pixmap:
            painter = QPainter(self)
            painter.setPen(QColor(0, 0, 0))  # pure black
            pix = self._background_pixmap
            w, h = self.width(), self.height()
            pw, ph = pix.width(), pix.height()
            x = (w - pw) // 2
            y = (h - ph) // 2
            painter.drawPixmap(x, y, pix)
        super().paintEvent(event)

    def display_chunk_with_typing(self, chunk, inter_chunk_pause, on_complete=None):
        existing = self.balloon_widget.text.strip()
        candidate_full = (existing + " " + chunk).strip() if existing else chunk.strip()

        def proceed_with_chunk(text_to_show):
            words = text_to_show.split()
            displayed = []
            self.typing_label.setText("typing...")
            index = 0

            def step():
                nonlocal index
                if index >= len(words):
                    self.typing_label.setText("")
                    full_text = " ".join(displayed)
                    self.balloon_widget.set_text(full_text)
                    self.balloon_widget.raise_()
                    self.balloon_widget.update()
                    if on_complete:
                        on_complete()
                    return
                displayed.append(words[index])
                self.balloon_widget.set_text(" ".join(displayed))
                index += 1
                QTimer.singleShot(50, step)

            step()

        if self.balloon_widget.would_overflow(candidate_full):
            def after_fade():
                proceed_with_chunk(chunk)

            self.balloon_widget.fade_out_and_clear(pause_before=60, fade_duration=1500, on_finished=after_fade)
        else:
            proceed_with_chunk(candidate_full)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        elif event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.Control:
            self.close()
        else:
            super().keyPressEvent(event)
