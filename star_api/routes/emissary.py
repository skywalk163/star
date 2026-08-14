"""
星使路由（Emissary Routes）- 星体交互闭环接口

提供文本注入、输出捕获、对话管理等交互接口
"""

import time
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from star_api import state


router = APIRouter()

# 星使缓存：{star_id: StarEmissary}
_emissary_cache: dict[str, object] = {}


class AskRequest(BaseModel):
    """问答请求"""
    prompt: str
    adapter_name: Optional[str] = None
    timeout: Optional[float] = None


class SendPromptRequest(BaseModel):
    """发送指令请求"""
    prompt: str
    adapter_name: Optional[str] = None


class EmissaryStatusResponse(BaseModel):
    """星使状态响应"""
    star_id: str
    star_type: str
    adapter_name: str
    status: str
    history_count: int
    current_turn: Optional[dict] = None


def _get_emissary(star_id: str, adapter_name: Optional[str] = None):
    """获取或创建星使"""
    from star_core import StarEmissary
    
    if star_id in _emissary_cache:
        em = _emissary_cache[star_id]
        if adapter_name and em.adapter.config.name != adapter_name:
            # 切换适配器
            from star_core import StarAdapter
            em.adapter = StarAdapter.from_name(adapter_name)
        return em
    
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    stars = state.orbit_engine.star_seeker.scan_skies()
    target = None
    for s in stars:
        if str(s.pid) == star_id:
            target = s
            break
    
    if not target:
        # 尝试按 PID 找
        try:
            pid = int(star_id)
            for s in stars:
                if s.pid == pid:
                    target = s
                    break
        except ValueError:
            pass
    
    if not target:
        raise HTTPException(status_code=404, detail=f"星体 {star_id} 未找到")
    
    em = StarEmissary(target, adapter_name=adapter_name)
    _emissary_cache[star_id] = em
    return em


@router.get("/adapters")
async def list_adapters():
    """
    列出所有预设适配器
    
    Returns:
        适配器列表
    """
    from star_core import PRESET_ADAPTERS
    
    return {
        "adapters": [
            {
                "name": name,
                "output_region": cfg.output_region,
                "completion_strategy": cfg.completion_strategy.value,
                "timeout": cfg.timeout,
                "check_interval": cfg.check_interval,
                "ocr_lang": cfg.ocr_lang,
            }
            for name, cfg in PRESET_ADAPTERS.items()
        ],
        "total": len(PRESET_ADAPTERS)
    }


@router.get("/regions")
async def list_regions():
    """
    列出所有预设 OCR 区域
    
    Returns:
        区域列表
    """
    from star_core import OCRGazer
    
    return {
        "regions": OCRGazer.list_preset_regions(),
        "total": len(OCRGazer.list_preset_regions())
    }


@router.get("/{star_id}/status")
async def get_emissary_status(star_id: str):
    """
    获取星使状态
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        星使状态信息
    """
    em = _get_emissary(star_id)
    
    response = {
        "star_id": star_id,
        "star_type": em.star.star_type,
        "adapter_name": em.adapter.config.name,
        "status": em.status.value,
        "history_count": len(em.history),
        "interaction_mode": em.interaction_mode,
        "cdp_available": em.cdp_available,
    }
    
    if em.last_turn:
        response["last_turn"] = {
            "turn_id": em.last_turn.turn_id,
            "prompt": em.last_turn.prompt[:200],
            "response_length": len(em.last_turn.response),
            "status": em.last_turn.status.value,
            "duration": em.last_turn.duration,
            "start_time": em.last_turn.start_time.isoformat(),
            "end_time": em.last_turn.end_time.isoformat() if em.last_turn.end_time else None,
        }
    
    return response


@router.post("/{star_id}/ask")
async def ask_star(star_id: str, request: AskRequest):
    """
    向星体发送一次完整问答（同步阻塞）
    
    Args:
        star_id: 星体 ID 或 PID
        request: 问答请求
        
    Returns:
        响应结果
    """
    em = _get_emissary(star_id, request.adapter_name)
    
    response_text = em.ask(request.prompt, timeout=request.timeout)
    
    turn = em.last_turn
    
    return {
        "star_id": star_id,
        "prompt": request.prompt,
        "response": response_text,
        "turn_id": turn.turn_id if turn else None,
        "status": turn.status.value if turn else "error",
        "duration": turn.duration if turn else 0,
    }


@router.post("/{star_id}/send")
async def send_prompt(star_id: str, request: SendPromptRequest):
    """
    发送指令（不等待结果，异步）
    
    Args:
        star_id: 星体 ID 或 PID
        request: 发送请求
        
    Returns:
        发送结果
    """
    em = _get_emissary(star_id, request.adapter_name)
    
    success = em.send_prompt(request.prompt)
    
    if not success:
        raise HTTPException(status_code=500, detail="指令发送失败")
    
    turn = em.last_turn
    
    return {
        "star_id": star_id,
        "success": True,
        "prompt": request.prompt,
        "turn_id": turn.turn_id if turn else None,
        "status": em.status.value,
    }


@router.get("/{star_id}/response")
async def get_response(star_id: str):
    """
    获取当前响应（用于轮询模式）
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        当前响应状态和内容
    """
    em = _get_emissary(star_id)
    
    if not em._current_turn and not em.last_turn:
        return {
            "status": em.status.value,
            "response": "",
            "turn_id": None,
        }
    
    # 如果正在等待，实时读取一次
    if em.status.value == "waiting":
        from star_core.ocr_gazer import OCRResult
        region = em.adapter.get_output_region_name()
        try:
            result = em.ocr.gaze_region(em.star, region)
            current_text = result.text
        except Exception:
            current_text = ""
    else:
        current_text = em.last_turn.response if em.last_turn else ""
    
    turn = em._current_turn or em.last_turn
    
    return {
        "status": em.status.value,
        "response": current_text,
        "turn_id": turn.turn_id if turn else None,
        "duration": turn.duration if turn else 0,
    }


@router.post("/{star_id}/wait")
async def wait_for_response(star_id: str, timeout: Optional[float] = None):
    """
    等待当前指令完成
    
    Args:
        star_id: 星体 ID 或 PID
        timeout: 超时时间（秒）
        
    Returns:
        最终响应
    """
    em = _get_emissary(star_id)
    
    if em.status.value != "waiting" and em.status.value != "sending":
        # 没有正在进行的任务
        return {
            "status": em.status.value,
            "response": em.last_turn.response if em.last_turn else "",
            "turn_id": em.last_turn.turn_id if em.last_turn else None,
            "duration": em.last_turn.duration if em.last_turn else 0,
        }
    
    response_text = em.wait_for_response(timeout=timeout)
    turn = em.last_turn
    
    return {
        "status": turn.status.value if turn else "error",
        "response": response_text,
        "turn_id": turn.turn_id if turn else None,
        "duration": turn.duration if turn else 0,
    }


@router.get("/{star_id}/history")
async def get_history(star_id: str, limit: int = 20):
    """
    获取对话历史
    
    Args:
        star_id: 星体 ID 或 PID
        limit: 返回条数
        
    Returns:
        历史对话列表
    """
    em = _get_emissary(star_id)
    
    history = em.history[-limit:] if limit > 0 else em.history
    
    return {
        "star_id": star_id,
        "history": [
            {
                "turn_id": t.turn_id,
                "prompt": t.prompt[:300],
                "response_length": len(t.response),
                "response_preview": t.response[:200],
                "status": t.status.value,
                "duration": t.duration,
                "start_time": t.start_time.isoformat(),
                "end_time": t.end_time.isoformat() if t.end_time else None,
            }
            for t in reversed(history)
        ],
        "total": len(em.history),
    }


@router.get("/{star_id}/history/{turn_id}")
async def get_turn_detail(star_id: str, turn_id: str):
    """
    获取指定轮次的详细信息
    
    Args:
        star_id: 星体 ID 或 PID
        turn_id: 轮次 ID
        
    Returns:
        轮次详情
    """
    em = _get_emissary(star_id)
    
    for turn in em.history:
        if turn.turn_id == turn_id:
            return {
                "turn_id": turn.turn_id,
                "prompt": turn.prompt,
                "response": turn.response,
                "status": turn.status.value,
                "duration": turn.duration,
                "start_time": turn.start_time.isoformat(),
                "end_time": turn.end_time.isoformat() if turn.end_time else None,
                "metadata": turn.metadata,
            }
    
    raise HTTPException(status_code=404, detail="轮次未找到")


@router.delete("/{star_id}/history")
async def clear_history(star_id: str):
    """
    清空对话历史
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        操作结果
    """
    em = _get_emissary(star_id)
    em.clear_history()
    
    return {"success": True, "message": "历史已清空"}


@router.get("/{star_id}/tasks")
async def get_task_list(star_id: str):
    """
    获取任务列表（OCR 识别）
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        任务列表
    """
    em = _get_emissary(star_id)
    
    start = time.time()
    tasks = em.get_task_list()
    elapsed = time.time() - start
    
    return {
        "star_id": star_id,
        "tasks": [
            {
                "title": t.title,
                "status": t.status,
                "is_active": t.is_active,
                "y": t.y,
            }
            for t in tasks
        ],
        "count": len(tasks),
        "recognize_time": elapsed,
    }


@router.get("/{star_id}/todos")
async def get_todo_list(star_id: str):
    """
    获取待办列表（OCR 识别）
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        待办列表
    """
    em = _get_emissary(star_id)
    
    start = time.time()
    todos = em.get_todo_list()
    elapsed = time.time() - start
    
    return {
        "star_id": star_id,
        "todos": [
            {
                "title": t.title,
                "status": t.status,
                "y": t.y,
            }
            for t in todos
        ],
        "count": len(todos),
        "recognize_time": elapsed,
    }


@router.get("/{star_id}/ocr-status")
async def get_ocr_status(star_id: str):
    """
    获取当前 OCR 识别的状态信息
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        状态信息
    """
    em = _get_emissary(star_id)
    
    status = em.get_current_status()
    
    return {
        "star_id": star_id,
        **status,
    }


@router.get("/{star_id}/screenshot")
async def get_screenshot(star_id: str):
    """
    获取当前截图（Base64）
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        截图信息
    """
    em = _get_emissary(star_id)
    
    import base64
    import tempfile
    import os
    
    temp_path = os.path.join(tempfile.gettempdir(), f"star_snap_{star_id}.png")
    success = em.ocr.capture_and_save(em.star, temp_path)
    
    if not success:
        raise HTTPException(status_code=500, detail="截图失败")
    
    with open(temp_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()
    
    return {
        "star_id": star_id,
        "image_base64": img_data,
        "format": "png",
    }


@router.delete("/{star_id}")
async def destroy_emissary(star_id: str):
    """
    销毁星使（释放资源）
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        操作结果
    """
    if star_id in _emissary_cache:
        del _emissary_cache[star_id]
        return {"success": True, "message": f"星使 {star_id} 已销毁"}
    
    return {"success": True, "message": "星使不存在"}


# ==================== 日志读取接口 ====================

from star_core.log_reader import get_reader, LOG_PATTERNS


@router.get("/{star_id}/logs")
async def get_log_info(star_id: str):
    """
    获取星体的日志信息（查找日志文件）
    
    Args:
        star_id: 星体 ID 或 PID
        
    Returns:
        日志文件信息列表
    """
    em = _get_emissary(star_id)
    reader = get_reader()
    
    log_files = reader.find_logs_for_star(em.star)
    
    files_info = []
    for f in log_files:
        try:
            stat = os.stat(f)
            files_info.append({
                "path": f,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        except Exception:
            files_info.append({"path": f, "error": "无法访问"})
    
    return {
        "star_id": star_id,
        "files": files_info,
        "count": len(files_info),
        "log_supported": len(files_info) > 0,
    }


@router.get("/{star_id}/logs/recent")
async def get_log_recent(star_id: str, max_lines: int = 50):
    """
    读取星体的最近日志内容（毫秒级）
    
    Args:
        star_id: 星体 ID 或 PID
        max_lines: 最大行数
        
    Returns:
        日志内容 + 解析出的 AI 响应
    """
    em = _get_emissary(star_id)
    reader = get_reader()
    
    log_files = reader.find_logs_for_star(em.star)
    result = reader.read_recent(log_files, max_lines=max_lines)
    
    return {
        "star_id": star_id,
        "files_scanned": result.source_files,
        "lines_read": len(result.entries),
        "elapsed_ms": round(result.elapsed_ms, 2),
        "ai_responses": result.ai_responses,
        "latest_text": result.latest_text,
        "raw_lines": [e.content for e in result.entries[-20:]],  # 最近 20 行
        "error": result.error,
    }


@router.get("/logs/discover")
async def discover_logs():
    """
    发现系统上所有支持的 AI Agent 日志
    
    Returns:
        各 Agent 的日志发现结果
    """
    reader = get_reader()
    return {
        "agents": reader.get_supported_types(),
        "total_loggable": sum(1 for a in reader.get_supported_types() if a["has_logs"]),
    }


@router.get("/{star_id}/cdp")
async def get_cdp_info(star_id: str):
    """
    获取 CDP 连接信息（用于 Trae 等 Electron 应用）

    返回 CDP 端口状态、可用 targets、交互模式等。

    Args:
        star_id: 星体 ID 或 PID

    Returns:
        CDP 连接信息
    """
    em = _get_emissary(star_id)

    if not hasattr(em, "_trae_cdp") or em._trae_cdp is None:
        return {
            "star_id": star_id,
            "cdp_available": False,
            "reason": "no_cdp_config",
            "message": "该 Agent 未配置 CDP。请在 ai-agents.yaml 中添加 cdp 段。",
        }

    bridge = em._trae_cdp
    alive = bridge.is_alive()

    result = {
        "star_id": star_id,
        "cdp_available": alive,
        "interaction_mode": em.interaction_mode,
        "port": bridge.port,
    }

    if alive:
        # 列出 targets
        target = bridge.find_chat_target()
        if target:
            result["target"] = {
                "id": target.get("id", "")[:40],
                "title": target.get("title", "")[:60],
                "url": target.get("url", "")[:80],
            }
        else:
            result["target"] = None
            result["target_message"] = "未找到匹配的 target"

    return result


@router.post("/{star_id}/cdp/probe")
async def probe_cdp_globals(star_id: str):
    """
    探测 Trae 渲染器中的全局对象（用于发现内部 IPC 接口）

    Args:
        star_id: 星体 ID 或 PID

    Returns:
        全局对象探测结果
    """
    em = _get_emissary(star_id)

    if not hasattr(em, "_trae_cdp") or em._trae_cdp is None:
        raise HTTPException(status_code=400, detail="该 Agent 未配置 CDP")

    bridge = em._trae_cdp
    if not bridge.is_alive():
        raise HTTPException(status_code=503, detail="CDP 端口不可达")

    result = bridge.probe_globals()
    return {
        "star_id": star_id,
        "globals": result,
    }
