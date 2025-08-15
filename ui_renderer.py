from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QMainWindow,
    QGraphicsOpacityEffect,
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QFontMetrics,QGuiApplication
from PyQt5.QtCore import (
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
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.font = QFont("Sans Serif", 14)
        self.padding = 8

        # Text label (fades independently of balloon bg)
        self.text_label = QLabel(self)
        self.text_label.setWordWrap(True)
        self.text_label.setFont(self.font)
        self.text_label.setStyleSheet("color: black; background: transparent;")
        self.text_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.text_label.setText("")

        # Opacity effect for the text only
        self.text_effect = QGraphicsOpacityEffect(self.text_label)
        self.text_label.setGraphicsEffect(self.text_effect)
        self.text_effect.setOpacity(1.0)
        self._fading = False
        self._current_anim = None

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
        painter.setRenderHint(QPainter.Antialiasing)

        # Use widget-local coordinates
        rect = self.rect()  # QRect(0, 0, self.width(), self.height())

        radius = self.balloon_spec.get("border_radius", 12)
        border_w = self.balloon_spec.get("border_width", 1)
        border_color = QColor(self.balloon_spec.get("border_color", "#323232"))
        bg_color = QColor(self.balloon_spec.get("background_color", "#ffffffff"))

        painter.setBrush(bg_color)
        #pen = painter.pen()
        #pen.setColor(border_color)
        #pen.setWidth(border_w)
        #painter.setPen(pen)
        painter.setPen(Qt.NoPen)

        painter.drawRoundedRect(rect, radius, radius)

        self.update_label_geometry()  # keep

    def update_label_geometry(self):
        # Layout text within the widget, not absolute window coords
        inner = self.rect().adjusted(self.padding, self.padding, -self.padding, -self.padding)
        self.text_label.setGeometry(inner)

    def would_overflow(self, candidate_text):
        inner = self.rect().adjusted(self.padding, self.padding, -self.padding, -self.padding)
        metrics = QFontMetrics(self.font)
        bounding = metrics.boundingRect(inner, Qt.TextWordWrap, candidate_text)
        return bounding.height() > inner.height()

    def fade_out_and_clear(self, pause_before=0, fade_duration=1500, on_finished=None):
        if self._fading:
            return
        self._fading = True

        def do_fade():
            anim = QPropertyAnimation(self.text_effect, b"opacity", self)
            self._current_anim = anim
            anim.setDuration(fade_duration)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.InOutQuad)

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
            QTimer.singleShot(int(pause_before * 1000), do_fade)
        else:
            do_fade()


class MainWindow(QMainWindow):
    def __init__(self, personality, topic, images_dir=None,screen_width=1024, screen_height=768, on_ready_callback=None):
        super().__init__()

        self.setFixedSize(screen_width, screen_height)        
        self.setWindowTitle("Personality Streamer")

        # Center the window on screen
        screen = QGuiApplication.primaryScreen().geometry()
        x = (screen.width() - screen_width) // 2
        y = (screen.height() - screen_height) // 2
        self.move(x, y)

        self.personality = personality or {}
        self.topic = topic
        self.on_ready_callback = on_ready_callback
        self.images_dir = Path(images_dir) if images_dir else None
        self.screen_size = QSize(screen_width, screen_height)

        self._background_pixmap = None
        self._raw_avatar_pixmap = None
        self._background_scaled_done = False

        # Central container (we paint bg in window, overlays sit above)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Balloon overlay (we'll parent it to the window, not the layout)
        spec = self.personality.get("speech_balloon", {})
        balloon_w = int(spec.get("width", 400))
        balloon_h = int(spec.get("height", 250))
        x = int(spec.get("x_pos", 100))
        y = int(spec.get("y_pos", 50))

        self.balloon_widget = SpeechBalloonWidget(spec, parent=self)
        self.balloon_widget.setFixedSize(balloon_w, balloon_h)
        self.balloon_widget.move(x, y)
        self.balloon_widget.show()
        self.balloon_widget.raise_()

        # Typing indicator (in layout, centered)
        self.typing_label = QLabel("")
        self.typing_label.setAlignment(Qt.AlignCenter)
        self.typing_label.setStyleSheet("color: black; font-size: 16px;")
        layout.addWidget(self.typing_label, 0)

        # Load avatar (background)
        self.load_avatar(self.personality.get("image_file_name"))

        # Fixed window size from config, then center + show
        self.setFixedSize(self.screen_size)
        self._center_on_screen()
        self.show()  # windowed, not fullscreen

    def _center_on_screen(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._background_scaled_done:
            self._rescale_background()
            self._background_scaled_done = True

    def load_avatar(self, image_file):
        if not image_file:
            return
        candidates = []
        p = Path(image_file)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates.append(Path(image_file))
            if self.images_dir:
                candidates.append(self.images_dir / image_file)
            base_dir = Path(__file__).resolve().parent
            if self.images_dir:
                candidates.append(base_dir / self.images_dir / image_file)

        for c in candidates:
            if c.exists():
                pix = QPixmap(str(c))
                if not pix.isNull():
                    self._raw_avatar_pixmap = pix
                    return
        print(f"[warning] Avatar '{image_file}' not found. Tried: {', '.join(map(str, candidates))}")

    def _rescale_background(self):
        if not self._raw_avatar_pixmap:
            return
        target = self.screen_size
        if target.width() <= 0 or target.height() <= 0:
            return
        self._background_pixmap = self._raw_avatar_pixmap.scaled(
            target,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )

    def paintEvent(self, event):
        if self._background_pixmap:
            painter = QPainter(self)
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
            self.balloon_widget.fade_out_and_clear(
                pause_before=60, fade_duration=1500, on_finished=after_fade
            )
        else:
            proceed_with_chunk(candidate_full)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        elif (event.key() == Qt.Key_Q) and (event.modifiers() & Qt.ControlModifier):
            self.close()
        else:
            super().keyPressEvent(event)
