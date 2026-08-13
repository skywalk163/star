"""
定位器校准器路由（Locator Calibrator Routes）

提供 agent 候选列表、窗口检视（截图+UIA树）、试发测试、配置预览与落盘接口。
与 star_core/locators 基础包解耦：顶层不 import locators，在函数内延迟 import + try/except。
"""

import base64
import io
import os
import re
import shutil
import time
from typing import Any, Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from star_api import state

router = APIRouter()


# ==================== Pydantic 请求模型 ====================

class ProbeRequest(BaseModel):
    """试发测试请求"""
    prompt: str = "calibrator test"
    params: dict[str, Any] = {}


class PreviewRequest(BaseModel):
    """配置预览请求"""
    agent_id: str
    interaction: dict[str, Any]


class ApplyRequest(BaseModel):
    """配置应用请求"""
    agent_id: str
    interaction: dict[str, Any]


# ==================== 辅助函数 ====================

def _get_stars() -> list:
    """获取已发现的星体列表"""
    if state.orbit_engine is None:
        return []
    return state.orbit_engine.star_seeker.scan_skies()


def _find_star(star_id: str):
    """通过 star_id (pid) 查找星体"""
    stars = _get_stars()
    # 先按 PID 字符串匹配
    for s in stars:
        if str(s.pid) == star_id:
            return s
    # 尝试数字转换
    try:
        pid = int(star_id)
        for s in stars:
            if s.pid == pid:
                return s
    except ValueError:
        pass
    return None


def _probe_uia_capability(hwnd: int) -> bool:
    """探测 UIA 能力：能否取到控件树"""
    try:
        import uiautomation as uia
        ctrl = uia.ControlFromHandle(hwnd)
        return ctrl is not None
    except Exception:
        return False


def _probe_visual_capability() -> bool:
    """探测视觉/OCR 能力"""
    try:
        import PaddleOCR  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        from star_core.ocr_gazer import OCRGazer  # noqa: F401
        return True
    except Exception:
        return False


def _probe_cdp_capability(star) -> bool:
    """探测 CDP 能力：agent 配置 category==browser 或 cdptab 存在"""
    try:
        from star_core.config_service import get_config_service
        cs = get_config_service()
        agent_cfg = cs.get_agent(star.star_type)
        if agent_cfg and agent_cfg.get("category") == "browser":
            return True
    except Exception:
        pass
    # 检查 star 是否有 cdptab 属性
    if hasattr(star, "cdptab") and star.cdptab:
        return True
    return False


def _capture_screenshot_b64(hwnd: int) -> Optional[str]:
    """截取窗口截图并返回 base64 字符串"""
    # 方式1: OCRGazer.capture_window
    try:
        from star_core.ocr_gazer import OCRGazer
        gazer = OCRGazer.__new__(OCRGazer)
        img_path = gazer.capture_window(hwnd)
        if img_path and os.path.exists(img_path):
            with open(img_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        pass

    # 方式2: PIL ImageGrab 兜底
    try:
        import win32gui
        from PIL import ImageGrab

        rect = win32gui.GetWindowRect(hwnd)
        left, top, right, bottom = rect
        img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        pass

    return None


def _walk_uia_tree(hwnd: int, max_nodes: int = 80) -> tuple[list[dict], bool]:
    """
    遍历 UIA 控件树，返回精简节点列表。
    返回 (nodes, truncated)。
    """
    nodes: list[dict] = []

    try:
        import uiautomation as uia
    except ImportError:
        return [], False

    try:
        root = uia.ControlFromHandle(hwnd)
        if root is None:
            return [], False

        def _extract_node(ctrl, depth: int):
            if len(nodes) >= max_nodes:
                return
            try:
                name = ctrl.Name or ""
                ctrl_type = ctrl.ControlTypeName or ""
                auto_id = ctrl.AutomationId or ""
                rect = ctrl.BoundingRectangle
                # BoundingRectangle 返回 uiautomation.Rect（不可迭代）
                if rect:
                    rect_list = [rect.left, rect.top, rect.right, rect.bottom]
                else:
                    rect_list = [0, 0, 0, 0]

                nodes.append({
                    "name": name,
                    "control_type": ctrl_type,
                    "automation_id": auto_id,
                    "rect": rect_list,
                    "depth": depth,
                })
            except Exception:
                pass

            try:
                children = ctrl.GetChildren()
            except Exception:
                return

            for child in children:
                if len(nodes) >= max_nodes:
                    return
                _extract_node(child, depth + 1)

        _extract_node(root, 0)
        truncated = len(nodes) >= max_nodes
        return nodes, truncated

    except Exception:
        return [], False


def _click_and_inject(hwnd: int, abs_x: int, abs_y: int, text: str) -> tuple[bool, str]:
    """
    在指定坐标点击并注入文本（不回车）。
    使用 pyautogui (SendInput) 替代 win32 mouse_event/keybd_event，
    因为 Electron/Chromium 渲染器不响应 Win32 事件但响应 SendInput。
    返回 (success, error_msg)。
    """
    try:
        import win32con
        import win32gui
        import pyautogui

        # 激活窗口
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.3)

        # 先按 Escape 关闭可能的弹窗/覆盖层
        pyautogui.press('escape')
        time.sleep(0.2)

        # 点击目标坐标（pyautogui 使用 SendInput）
        pyautogui.click(abs_x, abs_y)
        time.sleep(0.6)

        # 清除可能残留的文本
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.1)
        pyautogui.press('delete')
        time.sleep(0.2)

        # 剪贴板注入（支持中文）
        try:
            import pyperclip
            backup = pyperclip.paste()
            try:
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.2)
            finally:
                pyperclip.copy(backup)
        except ImportError:
            # 无 pyperclip 时降级为逐字符输入（仅 ASCII）
            pyautogui.typewrite(text, interval=0.05)
            time.sleep(0.1)

        return True, ""
    except Exception as e:
        return False, str(e)


def _build_locator_target(params: dict[str, Any]):
    """
    根据参数构造临时 LocatorTarget。
    延迟 import locators.base，失败时返回 None。
    """
    try:
        from star_core.locators.base import (
            LocatorTarget, UIAQuery, VisualQuery, RatioQuery, CDPQuery,
        )
    except ImportError:
        return None

    uia_params = params.get("uia") or {}
    visual_params = params.get("visual") or {}
    ratio_params = params.get("ratio") or {}
    cdp_params = params.get("cdp") or {}

    target = LocatorTarget(
        kind=params.get("kind", "input"),
        uia=UIAQuery(
            control_type=uia_params.get("control_type"),
            automation_id=uia_params.get("automation_id"),
            name_regex=uia_params.get("name_regex") or uia_params.get("name_pattern"),
            depth_limit=uia_params.get("depth_limit", 8),
        ) if uia_params else None,
        visual=VisualQuery(
            hint_text=visual_params.get("hint_text"),
            template=visual_params.get("template"),
            region=visual_params.get("region", "full_window"),
            ocr_min_confidence=visual_params.get("ocr_min_confidence", 0.5),
        ) if visual_params else None,
        ratio=RatioQuery(
            x_ratio=ratio_params.get("x", ratio_params.get("x_ratio", 0.5)),
            y_ratio=ratio_params.get("y", ratio_params.get("y_ratio", 0.92)),
        ) if ratio_params else None,
        cdp=CDPQuery(
            selector=cdp_params.get("selector"),
            text_contains=cdp_params.get("text_contains"),
            role=cdp_params.get("role"),
        ) if cdp_params else None,
    )
    return target


def _try_locate(target, hwnd: int, star) -> Optional[dict]:
    """
    尝试用 locators 链定位目标元素。
    返回 {"source": str, "box": {...}} 或 None。
    """
    try:
        from star_core.locators.base import WindowContext
        from star_core.locators import default_registry

        ctx = WindowContext(hwnd=hwnd, star=star, min_confidence=0.3)
        registry = default_registry()

        # 按 params 中出现的 locator 顺序尝试
        order = []
        for name in ("uia", "visual", "ratio", "cdp"):
            if getattr(target, name) is not None and name in registry:
                order.append(name)

        for name in order:
            locator = registry[name]
            try:
                box = locator.find(target, ctx)
                if box and box.confidence >= ctx.min_confidence:
                    return {
                        "source": box.source,
                        "box": {
                            "x": box.x,
                            "y": box.y,
                            "width": box.width,
                            "height": box.height,
                            "confidence": box.confidence,
                            "meta": box.meta,
                        },
                    }
            except Exception:
                continue
    except ImportError:
        pass
    return None


def _ratio_fallback_click(ratio_params: dict, hwnd: int) -> Optional[dict]:
    """当 locators 不可用时，用 ratio 参数兜底计算点击坐标"""
    try:
        import win32gui
        rect = win32gui.GetWindowRect(hwnd)
        left, top, right, bottom = rect
        w, h = right - left, bottom - top
        # 兼容 yaml 的 x/y 和 dataclass 的 x_ratio/y_ratio 两种写法
        x_ratio = ratio_params.get("x", ratio_params.get("x_ratio", 0.5))
        y_ratio = ratio_params.get("y", ratio_params.get("y_ratio", 0.92))
        abs_x = int(left + w * x_ratio)
        abs_y = int(top + h * y_ratio)
        return {
            "source": "ratio",
            "box": {
                "x": abs_x,
                "y": abs_y,
                "width": 0,
                "height": 0,
                "confidence": 0.3,
                "meta": {"x_ratio": x_ratio, "y_ratio": y_ratio},
            },
        }
    except Exception:
        return None


# ==================== 路由 ====================

@router.get("/candidates")
async def list_candidates():
    """
    列出当前已发现的 agent 及其可用定位能力。
    capabilities 探测：uia=有 hwnd 且能取到控件树；visual=OCR 可用；cdp=browser 配置或 cdptab 存在。
    """
    try:
        stars = _get_stars()
        candidates = []
        for s in stars:
            hwnd = s.hwnd if hasattr(s, "hwnd") else 0
            caps = {
                "uia": _probe_uia_capability(hwnd) if hwnd else False,
                "visual": _probe_visual_capability(),
                "cdp": _probe_cdp_capability(s),
            }
            candidates.append({
                "star_id": str(s.pid),
                "star_type": s.star_type,
                "title": s.title,
                "pid": s.pid,
                "capabilities": caps,
            })
        return {"candidates": candidates}
    except Exception as e:
        return {"ok": False, "error": str(e), "candidates": []}


@router.get("/{star_id}/inspect")
async def inspect_star(star_id: str):
    """
    返回窗口截图 base64 + 精简 UIA 控件树。
    最多返回 80 个节点，超出截断并标注 truncated。
    """
    star = _find_star(star_id)
    if star is None:
        raise HTTPException(status_code=404, detail=f"star {star_id} not found")

    hwnd = star.hwnd if hasattr(star, "hwnd") else 0
    if not hwnd:
        raise HTTPException(status_code=400, detail="star has no hwnd")

    try:
        screenshot_b64 = _capture_screenshot_b64(hwnd)
        if not screenshot_b64:
            return {"ok": False, "error": "screenshot capture failed",
                    "screenshot_b64": "", "uia_tree": [], "truncated": False}

        uia_tree, truncated = _walk_uia_tree(hwnd, max_nodes=80)

        return {
            "ok": True,
            "screenshot_b64": screenshot_b64,
            "uia_tree": uia_tree,
            "truncated": truncated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e),
                "screenshot_b64": "", "uia_tree": [], "truncated": False}


@router.post("/{star_id}/probe")
async def probe_star(star_id: str, request: ProbeRequest):
    """
    按临时定位参数实测定位 + 若命中则真实点击并注入测试文本。
    不回车发送，只聚焦+注入，避免污染对话。
    """
    star = _find_star(star_id)
    if star is None:
        raise HTTPException(status_code=404, detail=f"star {star_id} not found")

    hwnd = star.hwnd if hasattr(star, "hwnd") else 0
    if not hwnd:
        raise HTTPException(status_code=400, detail="star has no hwnd")

    try:
        # 尝试用 locators 链定位
        target = _build_locator_target(request.params)
        loc_result = None

        if target is not None:
            loc_result = _try_locate(target, hwnd, star)

        # locators 不可用时用 ratio 兜底
        if loc_result is None and request.params.get("ratio"):
            loc_result = _ratio_fallback_click(request.params["ratio"], hwnd)

        if loc_result is None:
            return {"hit": False, "source": "", "box": {},
                    "error": "no locator hit (locators package may not be ready)"}

        box = loc_result["box"]
        abs_x = box["x"]
        abs_y = box["y"]

        # 点击并注入
        ok, err = _click_and_inject(hwnd, abs_x, abs_y, request.prompt)
        if not ok:
            return {"hit": False, "source": loc_result["source"],
                    "box": box, "error": f"inject failed: {err}"}

        return {
            "hit": True,
            "source": loc_result["source"],
            "box": box,
            "error": "",
        }
    except Exception as e:
        return {"hit": False, "source": "", "box": {}, "error": str(e)}


@router.post("/preview")
async def preview_config(request: PreviewRequest):
    """
    输入定位参数 -> 返回将要写入 yaml 的 interaction 片段（YAML 文本）与文件路径。
    """
    try:
        fragment = {request.agent_id: {"interaction": request.interaction}}
        yaml_text = yaml.dump(
            fragment,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            indent=2,
        )

        config_path = os.path.join(
            state.project_root or os.getcwd(), "config", "ai-agents.yaml"
        )

        return {
            "ok": True,
            "yaml": yaml_text,
            "path": config_path,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "yaml": "", "path": ""}


@router.post("/apply")
async def apply_config(request: ApplyRequest):
    """
    将配置写回 config/ai-agents.yaml（备份原文件）-> 热生效。
    注意：PyYAML 重写会丢失注释，已在响应中提示已备份。
    """
    try:
        config_path = os.path.join(
            state.project_root or os.getcwd(), "config", "ai-agents.yaml"
        )

        if not os.path.exists(config_path):
            return {"ok": False, "error": f"config file not found: {config_path}"}

        # 备份
        bak_path = config_path + ".bak"
        shutil.copy2(config_path, bak_path)

        # 尝试用 ruamel 保留注释
        used_ruamel = False
        data = None

        try:
            from ruamel.yaml import YAML
            ry = YAML()
            ry.preserve_quotes = True
            ry.indent(mapping=2, sequence=4, offset=2)
            with open(config_path, "r", encoding="utf-8") as f:
                data = ry.load(f)
            used_ruamel = True
        except ImportError:
            pass

        if data is None:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

        if not data or "agents" not in data:
            return {"ok": False, "error": "invalid config: no agents section"}

        # 找到 agent 条目并写入 interaction
        agent_found = False
        for agent in data.get("agents", []):
            if agent.get("id") == request.agent_id:
                agent["interaction"] = request.interaction
                agent_found = True
                break

        if not agent_found:
            return {"ok": False,
                    "error": f"agent '{request.agent_id}' not found in config"}

        # 写回
        if used_ruamel:
            from ruamel.yaml import YAML
            ry = YAML()
            ry.preserve_quotes = True
            ry.indent(mapping=2, sequence=4, offset=2)
            ry.default_flow_style = False
            with open(config_path, "w", encoding="utf-8") as f:
                ry.dump(data, f)
        else:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data, f,
                    sort_keys=False,
                    allow_unicode=True,
                    default_flow_style=False,
                    indent=2,
                )

        # 重载 config_service
        try:
            from star_core.config_service import get_config_service
            get_config_service().load()
        except Exception:
            pass

        return {
            "ok": True,
            "path": config_path,
            "backup": bak_path,
            "comments_preserved": used_ruamel,
            "note": "" if used_ruamel else "PyYAML rewrite: comments lost, backup saved as .bak",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
