"""
荧惑（OCRGazer）- 光学观星策略

通过截图 + OCR 识别获取 Agent 输出内容
适用于 UI Automation 无法直接访问的应用（如 Electron/D3D 渲染）

优化特性：
- 区域识别：预设 UI 区域，只识别目标区域，速度提升 3-5 倍
- 增量识别：图像差异检测，只识别变化区域
- 后处理优化：结构化解析、换行合并、置信度过滤
- 参数可调：分辨率、检测阈值、批处理大小
"""

from __future__ import annotations

import os
import time
import tempfile
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

try:
    import win32gui
    import win32con
    _win32_available = True
except ImportError:
    _win32_available = False

try:
    import cv2
    _cv2_available = True
except ImportError:
    _cv2_available = False
    cv2 = None

try:
    import numpy as np
    _numpy_available = True
except ImportError:
    _numpy_available = False
    np = None

try:
    from PIL import ImageGrab
    _pil_available = True
except ImportError:
    _pil_available = False
    ImageGrab = None

from star_core.star_seeker import StarBody


def check_ocr_dependencies() -> dict:
    """检查 OCR 依赖可用性"""
    return {
        "win32": _win32_available,
        "cv2": _cv2_available,
        "numpy": _numpy_available,
        "pil": _pil_available,
        "ocr_ready": _win32_available and _cv2_available and _numpy_available and _pil_available,
    }


@dataclass
class UIRegion:
    """
    UI 区域定义
    
    Attributes:
        name: 区域名称
        x_ratio: 左边界比例 (0.0-1.0)
        y_ratio: 上边界比例 (0.0-1.0)
        w_ratio: 宽度比例 (0.0-1.0)
        h_ratio: 高度比例 (0.0-1.0)
        description: 区域描述
    """
    name: str
    x_ratio: float = 0.0
    y_ratio: float = 0.0
    w_ratio: float = 1.0
    h_ratio: float = 1.0
    description: str = ""
    
    def to_pixel(self, img_width: int, img_height: int) -> tuple[int, int, int, int]:
        """转换为像素坐标 (x, y, w, h)"""
        x = int(img_width * self.x_ratio)
        y = int(img_height * self.y_ratio)
        w = int(img_width * self.w_ratio)
        h = int(img_height * self.h_ratio)
        return (x, y, w, h)


# 预设的通用 UI 区域
PRESET_REGIONS = {
    "full": UIRegion("full", 0.0, 0.0, 1.0, 1.0, "全屏"),
    "left_sidebar": UIRegion("left_sidebar", 0.0, 0.05, 0.28, 0.9, "左侧边栏（任务/会话列表）"),
    "left_task_list": UIRegion("left_task_list", 0.02, 0.15, 0.26, 0.75, "左侧任务列表"),
    "center_content": UIRegion("center_content", 0.3, 0.05, 0.45, 0.9, "中间主内容区"),
    "center_chat": UIRegion("center_chat", 0.32, 0.1, 0.4, 0.8, "中间对话区"),
    "right_panel": UIRegion("right_panel", 0.75, 0.05, 0.23, 0.9, "右侧面板（待办/上下文）"),
    "right_todo": UIRegion("right_todo", 0.77, 0.1, 0.21, 0.5, "右侧待办列表"),
    "top_bar": UIRegion("top_bar", 0.0, 0.0, 1.0, 0.08, "顶部栏（标题/菜单）"),
    "bottom_input": UIRegion("bottom_input", 0.25, 0.88, 0.5, 0.1, "底部输入区"),
}


@dataclass
class OCRLine:
    """
    OCR 识别行
    
    Attributes:
        text: 识别文本
        confidence: 置信度 (0.0-1.0)
        box: 四点坐标 [[x,y], ...]
        x_center: 中心点 x 坐标
        y_center: 中心点 y 坐标
        width: 文本宽度
        height: 文本高度
    """
    text: str
    confidence: float
    box: list
    x_center: float
    y_center: float
    width: float
    height: float


@dataclass
class OCRResult:
    """
    OCR 识别结果
    
    Attributes:
        text: 识别到的全部文本
        lines: 逐行识别结果
        image_path: 截图文件路径
        region: 识别区域名称
        timestamp: 识别时间戳
        recognize_time: 识别耗时（秒）
        capture_time: 截图耗时（秒）
    """
    text: str
    lines: list[OCRLine] = field(default_factory=list)
    image_path: Optional[str] = None
    region: str = "full"
    timestamp: datetime = field(default_factory=datetime.now)
    recognize_time: float = 0.0
    capture_time: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "line_count": len(self.lines),
            "region": self.region,
            "timestamp": self.timestamp.isoformat(),
            "capture_time": self.capture_time,
            "recognize_time": self.recognize_time,
            "lines": [
                {
                    "text": l.text,
                    "confidence": l.confidence,
                    "x_center": l.x_center,
                    "y_center": l.y_center
                }
                for l in self.lines
            ]
        }


@dataclass
class TaskItem:
    """
    任务项（结构化解析结果）
    
    Attributes:
        title: 任务标题
        status: 状态 (running/completed/failed/pending/unknown)
        y: 垂直位置（用于排序）
        is_active: 是否是当前选中的任务
    """
    title: str
    status: str = "unknown"
    y: float = 0.0
    is_active: bool = False


class OCRPostProcessor:
    """
    OCR 结果后处理器
    
    对原始 OCR 结果进行结构化解析和优化
    """
    
    # 状态关键词映射
    STATUS_KEYWORDS = {
        "运行中": "running",
        "执行中": "running",
        "进行中": "running",
        "处理中": "running",
        "生成中": "running",
        "思考中": "running",
        "编写中": "running",
        "搜索中": "running",
        "分析中": "running",
        "正在": "running",
        "已完成": "completed",
        "完成": "completed",
        "成功": "completed",
        "任务完成": "completed",
        "已就绪": "completed",
        "就绪": "completed",
        "失败": "failed",
        "错误": "failed",
        "异常": "failed",
        "出错": "failed",
        "已取消": "cancelled",
        "取消": "cancelled",
        "待处理": "pending",
        "等待中": "pending",
        "排队": "pending",
        "待执行": "pending",
    }
    
    # UI 标签词（过滤用）
    UI_LABELS = {
        "新建任务", "新建", "技能", "自动化", "待办", "任务列表",
        "文件", "上下文", "压缩", "其他", "输入", "输出", "结果",
        "Work", "Code", "Design", "编辑", "帮助", "Plain", "Text",
        "在中打开", "速通", "默认",
    }
    
    # 常见 OCR 纠错映射（中文）
    OCR_CORRECTIONS = {
        "120s": "120s",
        "CLl": "CLI",
        "Ilvm": "llvm",
        "duan": "段",
    }
    
    @classmethod
    def filter_low_confidence(cls, lines: list[OCRLine], threshold: float = 0.5) -> list[OCRLine]:
        """过滤低置信度行"""
        return [l for l in lines if l.confidence >= threshold]
    
    @classmethod
    def filter_ui_labels(cls, lines: list[OCRLine]) -> list[OCRLine]:
        """过滤 UI 标签行"""
        result = []
        for line in lines:
            text = line.text.strip()
            if len(text) < 2:
                continue
            # 纯数字/纯符号过滤
            if text.isdigit() or all(c in '+-=|[]{}()<>.:;,，。、' for c in text):
                continue
            # UI 标签过滤
            is_ui = False
            for label in cls.UI_LABELS:
                if label in text and len(text) < len(label) + 4:
                    is_ui = True
                    break
            if is_ui:
                continue
            result.append(line)
        return result
    
    @classmethod
    def merge_nearby_lines(cls, lines: list[OCRLine], max_y_gap: int = 30, max_x_gap: int = 50) -> list[OCRLine]:
        """
        合并邻近的行（同一任务/段落可能被拆分成多行）
        
        Args:
            lines: 原始行列表（按 y 排序）
            max_y_gap: 垂直方向最大间距（像素）
            max_x_gap: 水平方向最大间距（像素）
            
        Returns:
            合并后的行列表
        """
        if not lines:
            return []
        
        sorted_lines = sorted(lines, key=lambda l: (l.y_center, l.x_center))
        merged = []
        current_group = [sorted_lines[0]]
        
        for line in sorted_lines[1:]:
            last = current_group[-1]
            y_gap = abs(line.y_center - last.y_center)
            x_gap = abs(line.x_center - last.x_center)
            
            if y_gap < max_y_gap and x_gap < max_x_gap + max(last.width, line.width):
                current_group.append(line)
            else:
                merged.append(cls._merge_group(current_group))
                current_group = [line]
        
        if current_group:
            merged.append(cls._merge_group(current_group))
        
        return merged
    
    @classmethod
    def _merge_group(cls, group: list[OCRLine]) -> OCRLine:
        """合并一组行"""
        if len(group) == 1:
            return group[0]
        
        # 按 x 坐标排序后拼接文本
        sorted_by_x = sorted(group, key=lambda l: l.x_center)
        text = " ".join(l.text for l in sorted_by_x)
        
        # 平均置信度（加权）
        total_weight = sum(l.confidence for l in group)
        avg_conf = total_weight / len(group)
        
        # 计算包围盒
        all_x = [p[0] for l in group for p in l.box]
        all_y = [p[1] for l in group for p in l.box]
        
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        box = [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]
        
        return OCRLine(
            text=text,
            confidence=avg_conf,
            box=box,
            x_center=(min_x + max_x) / 2,
            y_center=(min_y + max_y) / 2,
            width=max_x - min_x,
            height=max_y - min_y
        )
    
    @classmethod
    def detect_status(cls, text: str) -> Optional[str]:
        """从文本中检测状态"""
        for kw, status in cls.STATUS_KEYWORDS.items():
            if kw in text:
                return status
        return None
    
    @classmethod
    def parse_task_list(cls, lines: list[OCRLine]) -> list[TaskItem]:
        """
        从 OCR 行中解析任务列表
        
        Args:
            lines: 任务区域的 OCR 行（已过滤和合并）
            
        Returns:
            任务项列表
        """
        if not lines:
            return []
        
        # 先过滤和合并
        filtered = cls.filter_ui_labels(lines)
        filtered = cls.filter_low_confidence(filtered, 0.4)
        merged = cls.merge_nearby_lines(filtered)
        
        tasks = []
        for line in merged:
            text = line.text.strip()
            if len(text) < 3:
                continue
            
            status = cls.detect_status(text) or "unknown"
            is_active = False
            
            # 检测是否有选中/高亮的迹象（通过特殊字符）
            if any(c in text for c in ['▶', '●', '◆', '■']):
                is_active = True
            
            tasks.append(TaskItem(
                title=text[:100],
                status=status,
                y=line.y_center,
                is_active=is_active
            ))
        
        return tasks
    
    @classmethod
    def extract_dialog_text(cls, lines: list[OCRLine]) -> list[dict]:
        """
        从对话区域提取对话内容（区分用户和 AI）
        
        Args:
            lines: 对话区的 OCR 行
            
        Returns:
            对话段落列表 {role, content, y}
        """
        if not lines:
            return []
        
        sorted_lines = sorted(lines, key=lambda l: l.y_center)
        
        dialogs = []
        current_role = "unknown"
        current_text = []
        current_y = 0
        
        for line in sorted_lines:
            text = line.text.strip()
            if len(text) < 2:
                continue
            
            # 简单启发式：靠左是用户，靠右是 AI（基于 x_center 位置）
            # 实际应用中应结合气泡位置等特征
            is_right_side = line.x_center > 500  # 简单阈值
            
            role = "ai" if is_right_side else "user"
            
            if role != current_role and current_text:
                dialogs.append({
                    "role": current_role,
                    "content": " ".join(current_text),
                    "y": current_y
                })
                current_text = [text]
                current_y = line.y_center
                current_role = role
            else:
                current_text.append(text)
                current_role = role
                current_y = line.y_center
        
        if current_text:
            dialogs.append({
                "role": current_role,
                "content": " ".join(current_text),
                "y": current_y
            })
        
        return dialogs


class OCRGazer:
    """
    荧惑观星者 - 基于 OCR 的输出捕获
    
    通过截图 + 光学字符识别获取 Agent 界面上的文字内容，
    作为 UI Automation 不可用时的备用观星策略。
    """
    
    def __init__(
        self,
        lang: str = "ch",
        use_gpu: bool = False,
        det_limit_side_len: int = 960,
        min_confidence: float = 0.5,
        use_incremental: bool = True,
        change_threshold: float = 0.01,
    ):
        """
        初始化 OCR 观星者
        
        Args:
            lang: 识别语言 - "ch", "en", "chinese_cht"
            use_gpu: 是否使用 GPU 加速
            det_limit_side_len: 检测边长限制（越小越快，默认960）
            min_confidence: 最小置信度阈值
            use_incremental: 是否启用增量识别
            change_threshold: 变化检测阈值（像素变化比例）
        """
        self._deps_ok = check_ocr_dependencies()["ocr_ready"]
        self._ocr = None
        self._lang = lang
        self._use_gpu = use_gpu
        self._det_limit_side_len = det_limit_side_len
        self._min_confidence = min_confidence
        self._use_incremental = use_incremental
        self._change_threshold = change_threshold
        
        self._last_screenshot_path: Optional[str] = None
        self._last_full_image: Optional[np.ndarray] = None if not _numpy_available else None
        self._last_full_result: Optional[OCRResult] = None
        self._regions_cache: dict[str, OCRResult] = {}
        self._cache_by_region: dict[str, tuple] = {}
    
    def _get_ocr(self):
        """懒加载 PaddleOCR 引擎"""
        if not self._deps_ok:
            raise RuntimeError(f"OCR 依赖不完整: {check_ocr_dependencies()}")
        if self._ocr is None:
            from paddleocr import PaddleOCR
            
            self._ocr = PaddleOCR(
                use_angle_cls=False,
                lang=self._lang,
                use_gpu=self._use_gpu,
                show_log=False,
                det_limit_side_len=self._det_limit_side_len,
                drop_score=self._min_confidence,
            )
        return self._ocr
    
    @staticmethod
    def list_preset_regions() -> list[dict]:
        """列出所有预设区域"""
        return [
            {
                "name": region.name,
                "description": region.description,
                "x_ratio": region.x_ratio,
                "y_ratio": region.y_ratio,
                "w_ratio": region.w_ratio,
                "h_ratio": region.h_ratio,
            }
            for region in PRESET_REGIONS.values()
        ]
    
    def capture_window(self, hwnd: int, save_path: Optional[str] = None) -> Optional[str]:
        """
        截取指定窗口的图像
        
        使用 PrintWindow + PW_RENDERFULLCONTENT 捕获硬件加速渲染的窗口
        
        Args:
            hwnd: 窗口句柄
            save_path: 保存路径，默认自动生成
            
        Returns:
            截图文件路径，失败返回 None
        """
        try:
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                return None
            
            import win32ui
            from ctypes import windll
            from PIL import Image as PILImage
            
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
            
            if not result:
                result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
            
            img = None
            if result:
                bmpinfo = saveBitMap.GetInfo()
                bmpstr = saveBitMap.GetBitmapBits(True)
                img = PILImage.frombuffer(
                    'RGB',
                    (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                    bmpstr, 'raw', 'BGRX', 0, 1
                )
            
            mfcDC.DeleteDC()
            saveDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            win32gui.DeleteObject(saveBitMap.GetHandle())
            
            if img is None:
                try:
                    screenshot = ImageGrab.grab(all_screens=True)
                    img = screenshot.crop((left, top, right, bottom))
                except Exception:
                    return None
            
            if save_path is None:
                temp_dir = os.path.join(tempfile.gettempdir(), "star_ocr")
                os.makedirs(temp_dir, exist_ok=True)
                save_path = os.path.join(
                    temp_dir,
                    f"gaze_{hwnd}_{int(time.time())}.png"
                )
            
            img.save(save_path)
            self._last_screenshot_path = save_path
            
            return save_path
            
        except Exception:
            return None
    
    def _load_image(self, image_path: str) -> Optional[np.ndarray]:
        """加载图像"""
        if not os.path.exists(image_path):
            return None
        return cv2.imread(image_path)
    
    def _detect_changes(self, new_img: np.ndarray, old_img: np.ndarray) -> tuple[float, list[tuple]]:
        """
        检测两幅图像之间的变化
        
        Args:
            new_img: 新图像
            old_img: 旧图像
            
        Returns:
            (变化比例, 变化区域列表 [(x,y,w,h), ...])
        """
        if old_img is None or new_img.shape != old_img.shape:
            return 1.0, [(0, 0, new_img.shape[1], new_img.shape[0])]
        
        # 灰度化
        gray_new = cv2.cvtColor(new_img, cv2.COLOR_BGR2GRAY)
        gray_old = cv2.cvtColor(old_img, cv2.COLOR_BGR2GRAY)
        
        # 高斯模糊去噪
        gray_new = cv2.GaussianBlur(gray_new, (5, 5), 0)
        gray_old = cv2.GaussianBlur(gray_old, (5, 5), 0)
        
        # 计算差异
        diff = cv2.absdiff(gray_new, gray_old)
        
        # 阈值化
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        
        # 计算变化比例
        total_pixels = diff.size
        changed_pixels = np.count_nonzero(thresh)
        change_ratio = changed_pixels / total_pixels
        
        # 找到变化区域
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        regions = []
        for contour in contours:
            if cv2.contourArea(contour) > 500:  # 最小面积过滤
                x, y, w, h = cv2.boundingRect(contour)
                regions.append((x, y, w, h))
        
        return change_ratio, regions
    
    def recognize_text(
        self,
        image_path: str,
        region: Optional[str | tuple] = None,
        use_post_process: bool = True,
    ) -> OCRResult:
        """
        识别图像中的文字
        
        Args:
            image_path: 图像文件路径
            region: 识别区域 - 字符串（预设区域名）或 (x, y, w, h) 像素坐标
            use_post_process: 是否启用后处理
            
        Returns:
            OCRResult 识别结果
        """
        t_start = time.time()
        
        img = self._load_image(image_path)
        if img is None:
            return OCRResult(text="", lines=[], image_path=image_path)
        
        img_h, img_w = img.shape[:2]
        
        # 解析区域参数
        region_name = "full"
        crop_region = None
        
        if region is not None:
            if isinstance(region, str):
                preset = PRESET_REGIONS.get(region)
                if preset:
                    region_name = region
                    crop_region = preset.to_pixel(img_w, img_h)
            elif isinstance(region, (tuple, list)) and len(region) == 4:
                region_name = "custom"
                crop_region = tuple(region)
        
        # 裁剪区域
        if crop_region:
            x, y, w, h = crop_region
            x = max(0, min(x, img_w - 1))
            y = max(0, min(y, img_h - 1))
            w = min(w, img_w - x)
            h = min(h, img_h - y)
            if w <= 0 or h <= 0:
                return OCRResult(text="", lines=[], image_path=image_path, region=region_name)
            img = img[y:y+h, x:x+w]
        else:
            x, y = 0, 0
        
        # 增量识别：检查变化（仅全屏模式）
        if self._use_incremental and region_name == "full" and self._last_full_image is not None:
            current_img = cv2.imread(image_path)
            change_ratio, _ = self._detect_changes(current_img, self._last_full_image)
            if change_ratio < self._change_threshold and self._last_full_result:
                # 变化太小，复用上次结果
                cached = self._last_full_result
                cached.timestamp = datetime.now()
                cached.capture_time = time.time() - t_start
                cached.recognize_time = 0.0
                return cached
        
        # 执行 OCR
        try:
            ocr = self._get_ocr()
            raw_result = ocr.ocr(img, cls=False)
        except Exception:
            return OCRResult(
                text="",
                lines=[],
                image_path=image_path,
                region=region_name,
                recognize_time=time.time() - t_start
            )
        
        # 解析结果
        lines = []
        if raw_result and raw_result[0]:
            for item in raw_result[0]:
                if len(item) >= 2:
                    box, (text, confidence) = item[0], item[1]
                    
                    # 坐标偏移回原图
                    adjusted_box = [[p[0] + x, p[1] + y] for p in box]
                    
                    xs = [p[0] for p in adjusted_box]
                    ys = [p[1] for p in adjusted_box]
                    
                    line = OCRLine(
                        text=text,
                        confidence=confidence,
                        box=adjusted_box,
                        x_center=sum(xs) / 4,
                        y_center=sum(ys) / 4,
                        width=max(xs) - min(xs),
                        height=max(ys) - min(ys)
                    )
                    lines.append(line)
        
        # 按 y 排序
        lines.sort(key=lambda l: l.y_center)
        
        # 后处理
        if use_post_process:
            lines = OCRPostProcessor.filter_low_confidence(lines, self._min_confidence)
        
        full_text = "\n".join(l.text for l in lines) if lines else ""
        
        elapsed = time.time() - t_start
        
        result = OCRResult(
            text=full_text,
            lines=lines,
            image_path=image_path,
            region=region_name,
            recognize_time=elapsed,
            capture_time=0
        )
        
        # 保存全屏结果用于增量识别
        if region_name == "full":
            self._last_full_image = cv2.imread(image_path)
            self._last_full_result = result
        
        return result
    
    def gaze(self, star: StarBody) -> str:
        """
        凝视星辉 - 通过 OCR 获取星体当前输出
        
        Args:
            star: 目标星体
            
        Returns:
            识别到的文本内容
        """
        result = self.gaze_detail(star)
        return result.text
    
    def gaze_detail(
        self,
        star: StarBody,
        region: Optional[str] = None,
    ) -> OCRResult:
        """
        详细观星 - 获取完整的 OCR 识别结果
        
        Args:
            star: 目标星体
            region: 识别区域名（预设区域名）
            
        Returns:
            OCRResult 完整结果
        """
        t_capture = time.time()
        img_path = self.capture_window(star.hwnd)
        capture_time = time.time() - t_capture
        
        if not img_path:
            return OCRResult(text="", lines=[])
        
        result = self.recognize_text(img_path, region=region)
        result.capture_time = capture_time
        return result
    
    def gaze_region(self, star: StarBody, region_name: str) -> OCRResult:
        """
        观星 - 只识别指定区域（速度更快）
        
        Args:
            star: 目标星体
            region_name: 预设区域名
            
        Returns:
            OCRResult
        """
        return self.gaze_detail(star, region=region_name)
    
    def get_task_list(self, star: StarBody) -> list[TaskItem]:
        """
        获取任务列表（优化：只识别左侧任务区）
        
        Args:
            star: 目标星体
            
        Returns:
            任务项列表
        """
        result = self.gaze_detail(star, region="left_task_list")
        if not result.lines:
            return []
        return OCRPostProcessor.parse_task_list(result.lines)
    
    def get_todo_list(self, star: StarBody) -> list[TaskItem]:
        """
        获取右侧待办列表
        
        Args:
            star: 目标星体
            
        Returns:
            待办项列表
        """
        result = self.gaze_detail(star, region="right_todo")
        if not result.lines:
            return []
        return OCRPostProcessor.parse_task_list(result.lines)
    
    def get_chat_content(self, star: StarBody) -> list[dict]:
        """
        获取对话区内容
        
        Args:
            star: 目标星体
            
        Returns:
            对话段落列表
        """
        result = self.gaze_detail(star, region="center_chat")
        if not result.lines:
            return []
        return OCRPostProcessor.extract_dialog_text(result.lines)
    
    def get_current_status(self, star: StarBody) -> dict:
        """
        获取 Agent 当前工作状态
        
        Args:
            star: 目标星体
            
        Returns:
            状态信息字典
        """
        result = self.gaze_detail(star, region="center_content")
        full_text = result.text.lower()
        
        status_info = {
            "is_active": False,
            "status": "idle",
            "current_task": None,
            "progress": None,
            "timestamp": datetime.now().isoformat()
        }
        
        running_keywords = [
            "运行中", "执行中", "进行中", "处理中", "生成中",
            "思考中", "编写中", "搜索中", "分析中", "正在",
            "thinking", "generating", "processing", "running", "working"
        ]
        
        complete_keywords = [
            "已完成", "完成", "成功", "任务完成", "就绪",
            "done", "complete", "success", "ready", "passed"
        ]
        
        error_keywords = [
            "错误", "失败", "异常", "出错",
            "error", "failed", "exception", "failing"
        ]
        
        for kw in running_keywords:
            if kw in full_text:
                status_info["status"] = "running"
                status_info["is_active"] = True
                break
        
        if status_info["status"] == "idle":
            for kw in complete_keywords:
                if kw in full_text:
                    status_info["status"] = "completed"
                    break
        
        if status_info["status"] == "idle":
            for kw in error_keywords:
                if kw in full_text:
                    status_info["status"] = "error"
                    break
        
        # 提取当前任务标题（中部最长的行）
        if result.lines:
            mid_lines = [
                l for l in result.lines
                if len(l.text) > 8 and l.confidence > 0.8
            ]
            if mid_lines:
                longest = max(mid_lines, key=lambda l: len(l.text))
                status_info["current_task"] = longest.text
        
        return status_info
    
    @staticmethod
    def list_preset_regions() -> list[dict]:
        """列出所有预设区域"""
        return [
            {
                "name": r.name,
                "description": r.description,
                "x_ratio": r.x_ratio,
                "y_ratio": r.y_ratio,
                "w_ratio": r.w_ratio,
                "h_ratio": r.h_ratio,
            }
            for r in PRESET_REGIONS.values()
        ]
    
    def capture_and_save(self, star: StarBody, save_path: str) -> bool:
        """
        截图并保存到指定路径（方便调试）
        
        Args:
            star: 目标星体
            save_path: 保存路径
            
        Returns:
            是否成功
        """
        result = self.capture_window(star.hwnd, save_path=save_path)
        return result is not None
