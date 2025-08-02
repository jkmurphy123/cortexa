import sys
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QWidget,
    QVBoxLayout,
    QMainWindow,
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QTextOption
from PyQt6.QtCore import Qt, QRect, QTimer

class SpeechBalloonWidget(QWidget):
    def __init__(self, balloon_spec, parent=None):
        super().__init__(parent)
        self.balloon_spec = balloon_spec
        self.text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.font = QFont("Sans Serif", 12)
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
        # draw semi-transparent rounded rect
        rect = QRect(
            self.balloon_spec["x_pos"],
            self.balloon_spec["y_pos"],
            self.balloon_spec["width"],
            self.balloon_spec["height"],
        )
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(QColor(50, 50, 50))
        painter.drawRoundedRect(rect, 12, 12)

        # draw text inside
        painter.setFont(self.font)
        inner = rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        painter.setPen(QColor(20, 20, 20))
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WordWrap)

        # convert to QRectF so the overload with QTextOption is used
        painter.drawText(QRectF(inner), self.text, option)


class MainWindow(QMainWindow):
    def __init__(self, personality, topic, on_ready_callback=None):
        super().__init__()
        self.setWindowTitle("Personality Streamer")
        self.personality = personality
        self.topic = topic
        self.on_ready_callback = on_ready_callback

        central = QWidget()
        self.setCentralWidget(central)
        self.layout = QVBoxLayout()
        central.setLayout(self.layout)

        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.avatar_label, stretch=0)

        # Transparent overlay for speech balloon
        self.balloon_widget = SpeechBalloonWidget(personality["speech_balloon"], parent=self)
        self.balloon_widget.setFixedSize(self.size())
        self.layout.addWidget(self.balloon_widget)

        # Typing indicator
        self.typing_label = QLabel("")
        self.typing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.typing_label, stretch=0)

        # Load avatar
        self.load_avatar(personality.get("image_file_name"))

        # Resize behavior
        self.resize(800, 600)
        self.balloon_widget.raise_()

    def load_avatar(self, image_file):
        if image_file:
            pix = QPixmap(image_file)
            if pix and not pix.isNull():
                # scale to width proportionally
                scaled = pix.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.avatar_label.setPixmap(scaled)
            else:
                self.avatar_label.setText(f"[Avatar missing: {image_file}]")
        else:
            self.avatar_label.setText("[No avatar specified]")

    def display_chunk_with_typing(self, chunk, inter_chunk_pause, on_complete=None):
        # Simulate a simple typing effect: reveal word by word
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
            QTimer.singleShot(50, step)  # 50ms per word; tweak for speed

        step()
