import sys
import os
import shutil
import datetime
from PIL import Image, ExifTags
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QLabel, QFileDialog,
    QPushButton, QScrollArea, QVBoxLayout, QMessageBox,
    QDialog, QHBoxLayout, QRadioButton, QButtonGroup, QGroupBox
)
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtCore import Qt


# --------------------------
# 工具：拼接两张图 (支持横向/纵向)
# --------------------------
def merge_images(img1_path, img2_path, output_path, direction='horizontal'):
    img1 = Image.open(img1_path)
    img2 = Image.open(img2_path)

    if direction == 'horizontal':
        # 对齐高度
        h = min(img1.height, img2.height)
        img1 = img1.resize((int(img1.width * h / img1.height), h))
        img2 = img2.resize((int(img2.width * h / img2.height), h))

        merged = Image.new("RGB", (img1.width + img2.width, h))
        merged.paste(img1, (0, 0))
        merged.paste(img2, (img1.width, 0))
    else:  # vertical
        # 对齐宽度
        w = min(img1.width, img2.width)
        img1 = img1.resize((w, int(img1.height * w / img1.width)))
        img2 = img2.resize((w, int(img2.height * w / img2.width)))

        merged = Image.new("RGB", (w, img1.height + img2.height))
        merged.paste(img1, (0, 0))
        merged.paste(img2, (0, img1.height))

    merged.save(output_path)


# --------------------------
# 大图预览窗口
# --------------------------
class ImagePreviewDialog(QDialog):
    def __init__(self, img_path=None, parent=None, pixmap=None, is_selected=False):
        super().__init__(parent)
        self.setWindowTitle("图片预览")
        self.img_path = img_path
        self.is_selected = is_selected
        self.deselect_mode = False

        vbox = QVBoxLayout(self)

        if pixmap:
            pix = pixmap
        elif img_path:
            pix = QPixmap(img_path)
        else:
            pix = QPixmap()

        pix = pix.scaled(
            600, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        label = QLabel()
        label.setPixmap(pix)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(label)

        # 底部按钮
        hbox = QHBoxLayout()
        
        if pixmap:
            # 批量预览模式
            btn_ok = QPushButton("确定")
            btn_cancel = QPushButton("关闭")
            btn_ok.clicked.connect(self.accept)
            btn_cancel.clicked.connect(self.reject)
            hbox.addWidget(btn_ok)
            hbox.addWidget(btn_cancel)
        else:
            # 手动预览模式
            if self.is_selected:
                # 已选中的图片：显示"取消选择"和"选择这张"
                btn_deselect = QPushButton("取消选择")
                btn_select = QPushButton("选择这张")
                
                btn_deselect.clicked.connect(self.deselect_and_close)
                btn_select.clicked.connect(self.accept)
                
                btn_select.setDefault(True)  # 默认选中"选择这张"
                
                hbox.addWidget(btn_deselect)
                hbox.addWidget(btn_select)
            else:
                # 未选中的图片
                btn_ok = QPushButton("选择这张")
                btn_cancel = QPushButton("取消")
                
                btn_ok.clicked.connect(self.accept)
                btn_cancel.clicked.connect(self.reject)
                
                hbox.addWidget(btn_ok)
                hbox.addWidget(btn_cancel)
        
        vbox.addLayout(hbox)

        self.setFixedSize(650, 720)
    
    def deselect_and_close(self):
        """取消选择并关闭对话框"""
        self.deselect_mode = True
        self.reject()


# --------------------------
# 批量处理窗口
# --------------------------
class BatchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量拼接设置")
        
        # Set size to 80% of screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.8), int(screen.height() * 0.8))
        
        self.parent_win = parent
        self.preview_labels = []

        layout = QVBoxLayout(self)

        # 1. 排序设置
        group_sort = QGroupBox("1. 图片排序方式")
        layout_sort = QHBoxLayout()
        self.rb_time = QRadioButton("按拍摄时间 (默认)")
        self.rb_name = QRadioButton("按文件名")
        self.rb_time.setChecked(True)
        layout_sort.addWidget(self.rb_time)
        layout_sort.addWidget(self.rb_name)
        group_sort.setLayout(layout_sort)
        layout.addWidget(group_sort)

        # 2. 拼接方向
        group_dir = QGroupBox("2. 拼接方向")
        layout_dir = QHBoxLayout()
        self.rb_h_batch = QRadioButton("左右拼接")
        self.rb_v_batch = QRadioButton("上下拼接")
        self.rb_h_batch.setChecked(True)
        layout_dir.addWidget(self.rb_h_batch)
        layout_dir.addWidget(self.rb_v_batch)
        group_dir.setLayout(layout_dir)
        layout.addWidget(group_dir)

        # 3. 预览区域
        group_preview = QGroupBox("3. 预览 (前3组)")
        self.layout_preview = QGridLayout()
        group_preview.setLayout(self.layout_preview)
        layout.addWidget(group_preview)

        # 按钮区
        hbox_btn = QHBoxLayout()
        btn_preview = QPushButton("生成预览")
        self.btn_start = QPushButton("开始批量拼接")
        btn_preview.clicked.connect(self.generate_preview)
        self.btn_start.clicked.connect(self.start_batch)
        hbox_btn.addWidget(btn_preview)
        hbox_btn.addWidget(self.btn_start)
        layout.addLayout(hbox_btn)

        self.pairs_to_process = []

    def get_sorted_files(self):
        # 复用主窗口的加载逻辑，但只获取文件列表
        exts = (".jpg", ".jpeg", ".png")
        files = [
            f for f in os.listdir(self.parent_win.folder)
            if f.lower().endswith(exts)
            and f not in os.listdir(self.parent_win.processed_folder)
            and f not in os.listdir(self.parent_win.result_folder)
        ]

        if self.rb_time.isChecked():
            files.sort(key=lambda f: self.parent_win.get_capture_time(f))
        else:
            files.sort() # 按文件名

        return files

    def generate_preview(self):
        # 清空旧预览
        for i in reversed(range(self.layout_preview.count())):
            self.layout_preview.itemAt(i).widget().deleteLater()

        files = self.get_sorted_files()
        if len(files) < 2:
            QMessageBox.warning(self, "提示", "图片数量不足 2 张，无法拼接")
            return

        # 生成配对
        self.pairs_to_process = []
        for i in range(0, len(files) - 1, 2):
            self.pairs_to_process.append((files[i], files[i+1]))

        # 只预览前3组
        preview_pairs = self.pairs_to_process[:3]
        direction = 'vertical' if self.rb_v_batch.isChecked() else 'horizontal'

        row = 0
        for p1, p2 in preview_pairs:
            path1 = os.path.join(self.parent_win.folder, p1)
            path2 = os.path.join(self.parent_win.folder, p2)
            
            # 临时生成预览图 (不保存到磁盘，直接转 QPixmap)
            try:
                # 使用 PIL 在内存中拼接
                img1 = Image.open(path1)
                img2 = Image.open(path2)
                
                if direction == 'horizontal':
                    h = min(img1.height, img2.height)
                    img1 = img1.resize((int(img1.width * h / img1.height), h))
                    img2 = img2.resize((int(img2.width * h / img2.height), h))
                    merged = Image.new("RGB", (img1.width + img2.width, h))
                    merged.paste(img1, (0, 0))
                    merged.paste(img2, (img1.width, 0))
                else:
                    w = min(img1.width, img2.width)
                    img1 = img1.resize((w, int(img1.height * w / img1.width)))
                    img2 = img2.resize((w, int(img2.height * w / img2.width)))
                    merged = Image.new("RGB", (w, img1.height + img2.height))
                    merged.paste(img1, (0, 0))
                    merged.paste(img2, (0, img1.height))

                # PIL Image -> QPixmap
                # 先转为 Qt 兼容格式
                merged = merged.convert("RGBA")
                data = merged.tobytes("raw", "RGBA")
                qim = QPixmap.fromImage(
                    QImage(data, merged.width, merged.height, QImage.Format.Format_RGBA8888)
                )
                
                # 显示
                lbl_name = QLabel(f"组 {row+1}: {p1} + {p2}")
                lbl_img = QLabel()
                # Increased size from 300, 150 to 500, 300
                lbl_img.setPixmap(qim.scaled(500, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                lbl_img.setStyleSheet("border: 1px solid gray")
                
                # 点击查看大图
                # 注意：这里需要用默认参数绑定 qim，否则闭包会出问题
                lbl_img.mousePressEvent = lambda e, pm=qim: self.open_large_preview(pm)

                self.layout_preview.addWidget(lbl_name, row, 0)
                self.layout_preview.addWidget(lbl_img, row, 1)
                row += 1

            except Exception as e:
                print(f"Preview error: {e}")
        
        # 视觉引导：生成预览后，焦点给到“开始批量拼接”按钮，并设为默认
        if self.pairs_to_process:
            self.btn_start.setFocus()
            self.btn_start.setDefault(True)

    def open_large_preview(self, pixmap):
        dlg = ImagePreviewDialog(parent=self, pixmap=pixmap)
        dlg.exec()

    def start_batch(self):
        if not self.pairs_to_process:
            QMessageBox.warning(self, "提示", "请先生成预览以确认配对")
            return

        direction = 'vertical' if self.rb_v_batch.isChecked() else 'horizontal'
        count = 0
        
        for p1, p2 in self.pairs_to_process:
            path1 = os.path.join(self.parent_win.folder, p1)
            path2 = os.path.join(self.parent_win.folder, p2)
            
            base1 = os.path.splitext(p1)[0]
            base2 = os.path.splitext(p2)[0]
            output_name = f"{base1}_{base2}.jpg"
            output_path = os.path.join(self.parent_win.result_folder, output_name)

            try:
                merge_images(path1, path2, output_path, direction)
                
                # 移动源文件
                shutil.move(path1, os.path.join(self.parent_win.processed_folder, p1))
                shutil.move(path2, os.path.join(self.parent_win.processed_folder, p2))
                count += 1
            except Exception as e:
                print(f"Error merging {p1} and {p2}: {e}")

        QMessageBox.information(self, "完成", f"批量处理完成，共生成 {count} 张图片。")
        self.accept()
        self.parent_win.load_images() # 刷新主界面


# --------------------------
# 主窗口
# --------------------------
class ImageSelector(QWidget):
    def __init__(self):
        super().__init__()

        self.folder = ""
        self.processed_folder = ""
        self.result_folder = ""
        self.image_paths = []
        self.selected = []
        self.labels = []
        self.exif_cache = {}  # 缓存EXIF时间数据

        self.initUI()

    def initUI(self):
        self.setWindowTitle("2PicMerge - 双图拼接工具")
        self.setGeometry(200, 100, 1000, 700)

        layout = QVBoxLayout(self)

        # 顶部控制区
        top_layout = QHBoxLayout()
        
        # 选择计数器
        self.lbl_selection_count = QLabel("已选择: 0/2")
        self.lbl_selection_count.setStyleSheet("font-weight: bold; color: #6750A4;")
        top_layout.addWidget(self.lbl_selection_count)
        
        btn_choose = QPushButton("选择图片文件夹")
        btn_choose.clicked.connect(self.choose_folder)
        top_layout.addWidget(btn_choose)

        # 手动拼接方向选择
        self.group_dir = QButtonGroup(self)
        self.rb_h = QRadioButton("左右拼接")
        self.rb_v = QRadioButton("上下拼接")
        self.rb_h.setChecked(True)
        self.group_dir.addButton(self.rb_h)
        self.group_dir.addButton(self.rb_v)
        
        top_layout.addWidget(QLabel("手动模式:"))
        top_layout.addWidget(self.rb_h)
        top_layout.addWidget(self.rb_v)
        
        top_layout.addStretch()

        # 批量按钮
        btn_batch = QPushButton("批量拼接...")
        btn_batch.clicked.connect(self.open_batch_dialog)
        top_layout.addWidget(btn_batch)

        layout.addLayout(top_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.scroll.setWidget(self.grid_widget)

    # --------------------------
    # 选择图片文件夹
    # --------------------------
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if not folder:
            return

        self.folder = folder

        # processed 文件夹
        self.processed_folder = os.path.join(folder, "processed")
        os.makedirs(self.processed_folder, exist_ok=True)

        # result 文件夹
        self.result_folder = os.path.join(folder, "result")
        os.makedirs(self.result_folder, exist_ok=True)

        self.load_images()

    # --------------------------
    # 打开批量窗口
    # --------------------------
    def open_batch_dialog(self):
        if not self.folder:
            QMessageBox.warning(self, "提示", "请先选择图片文件夹")
            return
            
        dlg = BatchDialog(self)
        dlg.exec()

    # --------------------------
    # 获取图片拍摄时间（EXIF → mtime）
    # --------------------------
    def get_capture_time(self, filename):
        # 检查缓存
        if filename in self.exif_cache:
            return self.exif_cache[filename]
        
        full_path = os.path.join(self.folder, filename)

        try:
            img = Image.open(full_path)
            exif = img._getexif()
            if exif:
                # 映射 EXIF tag ID → 文本名称
                exif_data = {
                    ExifTags.TAGS.get(k, k): v
                    for k, v in exif.items()
                }
                # 尝试多个关键字段
                for key in ["DateTimeOriginal", "CreateDate", "DateTimeDigitized"]:
                    if key in exif_data:
                        dt_str = exif_data[key]
                        try:
                            result = datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                            self.exif_cache[filename] = result
                            return result
                        except:
                            pass
        except:
            pass

        # 无 EXIF → 文件修改时间
        result = datetime.datetime.fromtimestamp(os.path.getmtime(full_path))
        self.exif_cache[filename] = result
        return result

    # --------------------------
    # 加载 + 排序 + 显示图片缩略图
    # --------------------------
    def load_images(self):
        self.selected = []
        self.update_selection_count()
        self.exif_cache.clear()  # 清空EXIF缓存

        # 清空 UI 网格
        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # 文件过滤
        exts = (".jpg", ".jpeg", ".png")
        if not self.folder:
            return
            
        files = [
            f for f in os.listdir(self.folder)
            if f.lower().endswith(exts)
            and f not in os.listdir(self.processed_folder)
            and f not in os.listdir(self.result_folder)
        ]

        # 按拍摄时间排序（核心）
        files.sort(key=lambda f: self.get_capture_time(f))

        # 生成完整路径
        self.image_paths = [os.path.join(self.folder, f) for f in files]
        self.labels = []

        # 绘制缩略图
        row = col = 0
        for img_path in self.image_paths:
            label = QLabel()
            label.setFixedSize(180, 180)
            label.setStyleSheet("border: 2px solid transparent;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            pix = QPixmap(img_path).scaled(
                160,
                160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            label.setPixmap(pix)

            label.mousePressEvent = lambda e, path=img_path, lab=label: self.open_preview(path, lab)

            self.grid.addWidget(label, row, col)
            self.labels.append(label)

            col += 1
            if col == 5:
                col = 0
                row += 1

    # --------------------------
    # 弹出大图预览
    # --------------------------
    def open_preview(self, path, label):
        # 检查该图片是否已选中
        is_selected = any(p == path for p, _ in self.selected)
        
        if is_selected:
            # 已选中的图片：可以取消选择或重新确认
            preview = ImagePreviewDialog(path, self, is_selected=True)
            result = preview.exec()
            
            if preview.deselect_mode:
                # 取消选择
                self.deselect_image(path, label)
            elif result == QDialog.DialogCode.Accepted:
                # 重新确认选择（保持选中状态）
                pass
        else:
            # 未选中的图片：正常预览和选择
            preview = ImagePreviewDialog(path, self, is_selected=False)
            if preview.exec() == QDialog.DialogCode.Accepted:
                self.select_image(path, label)

    # --------------------------
    # 确认选择一张
    # --------------------------
    def select_image(self, path, label):
        if len(self.selected) == 2:
            self.clear_selection()

        self.selected.append((path, label))
        label.setStyleSheet("border: 3px solid red;")
        self.update_selection_count()

        if len(self.selected) == 2:
            self.merge_selected()
    
    def deselect_image(self, path, label):
        """取消选择某张图片"""
        self.selected = [(p, l) for p, l in self.selected if p != path]
        label.setStyleSheet("border: 2px solid transparent;")
        self.update_selection_count()
    
    def update_selection_count(self):
        """更新选择计数器"""
        count = len(self.selected)
        self.lbl_selection_count.setText(f"已选择: {count}/2")

    def clear_selection(self):
        for _, label in self.selected:
            label.setStyleSheet("border: 2px solid transparent;")
        self.selected = []
        self.update_selection_count()

    # --------------------------
    # 拼接 + 移动源图 + 刷新界面
    # --------------------------
    # --------------------------
    # 拼接 + 移动源图 + 刷新界面
    # --------------------------
    def merge_selected(self):
        img1, lab1 = self.selected[0]
        img2, lab2 = self.selected[1]

        base1 = os.path.splitext(os.path.basename(img1))[0]
        base2 = os.path.splitext(os.path.basename(img2))[0]
        output_name = f"{base1}_{base2}.jpg"

        output_path = os.path.join(self.result_folder, output_name)
        
        # 获取当前选择的方向
        direction = 'vertical' if self.rb_v.isChecked() else 'horizontal'

        try:
            merge_images(img1, img2, output_path, direction)

            # 移动源图片到 processed/
            shutil.move(img1, os.path.join(self.processed_folder, os.path.basename(img1)))
            shutil.move(img2, os.path.join(self.processed_folder, os.path.basename(img2)))

            QMessageBox.information(
                self,
                "完成",
                f"拼接完成 ({'上下' if direction == 'vertical' else '左右'}) → result/{output_name}\n\n两张原图已移动到 processed/ 文件夹。"
            )
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

        # 状态清空并刷新
        self.clear_selection()
        self.load_images()


# --------------------------
# 主程序入口
# --------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置应用图标
    icon_path = os.path.join(os.path.dirname(__file__), "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Material Design 3 (Pixel-like) Stylesheet
    # Colors:
    # Primary: #6750A4 (Purple) -> Buttons
    # On Primary: #FFFFFF
    # Primary Container: #EADDFF (Light Purple) -> Selected items
    # Background: #FFFBFE (Very light pinkish white)
    # Surface: #FFFBFE
    # Outline: #79747E (Gray)
    
    style_sheet = """
    QWidget {
        background-color: #FFFBFE;
        color: #1C1B1F;
        font-family: "Segoe UI", "Roboto", "Helvetica Neue", sans-serif;
        font-size: 14px;
    }

    /* Buttons (Filled - Primary) */
    QPushButton {
        background-color: #6750A4;
        color: #FFFFFF;
        border: none;
        border-radius: 20px; /* Pill shape */
        padding: 10px 24px;
        font-weight: bold;
        font-size: 14px;
    }
    QPushButton:hover {
        background-color: #7F67BE; /* Lighter purple */
    }
    QPushButton:pressed {
        background-color: #4F378B; /* Darker purple */
    }
    QPushButton:disabled {
        background-color: #E7E0EC;
        color: #1C1B1F;
        opacity: 0.5;
    }

    /* Radio Buttons */
    QRadioButton {
        spacing: 8px;
        font-size: 14px;
    }
    QRadioButton::indicator {
        width: 18px;
        height: 18px;
        border-radius: 10px;
        border: 2px solid #6750A4;
    }
    QRadioButton::indicator:checked {
        background-color: #6750A4;
        border: 2px solid #6750A4;
        image: none; /* Custom dot handled by background */
    }
    QRadioButton::indicator:unchecked {
        background-color: transparent;
    }

    /* GroupBox */
    QGroupBox {
        border: 1px solid #CAC4D0;
        border-radius: 12px;
        margin-top: 12px; /* Leave space for title */
        padding-top: 24px;
        font-weight: bold;
        color: #6750A4;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
        left: 12px;
        background-color: #FFFBFE; /* Mask border behind title */
    }

    /* Scroll Area */
    QScrollArea {
        border: none;
        background-color: #FFFBFE;
    }
    
    /* Labels */
    QLabel {
        color: #1C1B1F;
    }
    
    /* Dialogs */
    QDialog {
        background-color: #FFFBFE;
    }
    
    /* Message Box */
    QMessageBox {
        background-color: #FFFBFE;
    }
    QMessageBox QPushButton {
        min-width: 80px;
    }
    """
    app.setStyleSheet(style_sheet)

    win = ImageSelector()
    win.show()
    sys.exit(app.exec())
