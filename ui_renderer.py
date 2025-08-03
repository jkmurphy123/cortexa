from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QMainWindow,
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QTextOption
from PyQt6.QtCore import Qt, QRect, QRectF, QTimer

class SpeechBalloonWidget(QWidget):
    def __init__(self, balloon_spec, parent=None):
        super().__init__(parent)
        self.balloon_spec = balloon_spec
        self.text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.font = QFont("Sans Serif", 14)
        self.padding = 8

    def set_text(self, new_text):
        self.text = new_text
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


class MainWindow(QMainWindow):
    def __init__(self, personality, topic, images_dir=None, on_ready_callback=None):
        super().__init__()
        self.setWindowTitle("Personality Streamer")
        self.personality = personality
        self.topic = topic
        self.on_ready_callback = on_ready_callback
        self.images_dir = Path(images_dir) if images_dir else None

        central = QWidget()
        self.setCentralWidget(central)
        self.layout = QVBoxLayout()
        central.setLayout(self.layout)

        # Avatar image
        self.avatar_label = QLabel()
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.avatar_label, stretch=0)

        # Speech balloon overlay
        self.balloon_widget = SpeechBalloonWidget(personality.get("speech_balloon", {}), parent=self)
        self.balloon_widget.setFixedSize(1000, 800)
        self.layout.addWidget(self.balloon_widget, stretch=1)

        # Typing indicator
        self.typing_label = QLabel("")
        self.typing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.typing_label, stretch=0)

        # Load avatar image
        self.load_avatar(personality.get("image_file_name"))

        # Window sizing
        self.resize(800, 600)
        self.balloon_widget.raise_()

    def load_avatar(self, image_file):
        if not image_file:
            self.avatar_label.setText("[No avatar specified]")
            return

        candidates = []
        img_path = Path(image_file)
        # Absolute path priority
        if img_path.is_absolute():
            candidates.append(img_path)
        else:
            # raw relative
            candidates.append(Path(image_file))
            # from configured images_dir (relative to cwd)
            if self.images_dir:
                candidates.append(self.images_dir / image_file)
            # from images_dir relative to this module file (in case config path is relative to code)
            base_dir = Path(__file__).resolve().parent
            if self.images_dir:
                candidates.append(base_dir / self.images_dir / image_file)

        pix = None
        found_path = None
        for p in candidates:
            if p.exists():
                pix = QPixmap(str(p))
                found_path = p
                break

        if pix and not pix.isNull():
            scaled = pix.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.avatar_label.setPixmap(scaled)
        else:
            tried = ", ".join(str(p) for p in candidates)
            self.avatar_label.setText(f"[Avatar missing: {image_file}]\nTried: {tried}")

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
