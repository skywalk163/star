"""
星体路由（Stars Routes）- 星管理接口

提供星体发现、状态查询等接口
"""

from typing import Optional
from fastapi import APIRouter, HTTPException

from star_api import state


router = APIRouter()


@router.get("/")
async def list_stars():
    """
    列出所有已发现的星体
    
    Returns:
        星体列表
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    stars = state.orbit_engine.star_seeker.scan_skies()
    
    return {
        "stars": [
            {
                "pid": s.pid,
                "star_type": s.star_type,
                "title": s.title,
                "is_shining": s.is_shining,
                "last_activity": s.last_activity,
                "window_count": s.get_window_count(),
                "windows": [w.to_dict() for w in s.windows],
            }
            for s in stars
        ],
        "total": len(stars),
        "shining": len([s for s in stars if s.is_shining]),
        "idle": len([s for s in stars if not s.is_shining])
    }


@router.get("/types")
async def list_star_types():
    """
    列出所有支持的星体类型
    
    Returns:
        星体类型及其描述
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    return state.orbit_engine.star_seeker.list_star_types()


@router.get("/{pid}")
async def get_star(pid: int):
    """
    获取指定星体详情
    
    Args:
        pid: 进程 ID
        
    Returns:
        星体详情
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    star = state.orbit_engine.star_seeker.get_star(pid)
    
    if not star:
        raise HTTPException(status_code=404, detail=f"星体 {pid} 未发现")
    
    return {
        "pid": star.pid,
        "star_type": star.star_type,
        "title": star.title,
        "hwnd": star.hwnd,
        "is_shining": star.is_shining,
        "last_activity": star.last_activity,
        "window_count": star.get_window_count(),
        "windows": [w.to_dict() for w in star.windows],
    }


@router.post("/{pid}/refresh")
async def refresh_star(pid: int):
    """
    刷新星体信息
    
    Args:
        pid: 进程 ID
        
    Returns:
        更新后的星体信息
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    star = state.orbit_engine.star_seeker.refresh_star(pid)
    
    if not star:
        raise HTTPException(status_code=404, detail=f"星体 {pid} 未发现或已熄灭")
    
    return {
        "pid": star.pid,
        "star_type": star.star_type,
        "title": star.title,
        "is_shining": star.is_shining,
        "last_activity": star.last_activity,
        "window_count": star.get_window_count(),
        "windows": [w.to_dict() for w in star.windows],
    }


@router.get("/idle")
async def get_idle_stars(star_type: Optional[str] = None):
    """
    获取空闲星体
    
    Args:
        star_type: 星体类型过滤
        
    Returns:
        空闲星体列表
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    if star_type:
        stars = state.orbit_engine.star_seeker.get_idle_stars(star_type)
    else:
        stars = state.orbit_engine.star_seeker.get_idle_stars()
    
    return {
        "stars": [
            {
                "pid": s.pid,
                "star_type": s.star_type,
                "title": s.title
            }
            for s in stars
        ],
        "total": len(stars)
    }


@router.get("/{pid}/windows")
async def get_star_windows(pid: int):
    """
    获取指定星体的所有窗口
    
    Args:
        pid: 进程 ID
        
    Returns:
        窗口列表
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    star = state.orbit_engine.star_seeker.get_star(pid)
    if not star:
        raise HTTPException(status_code=404, detail=f"星体 {pid} 未发现")
    
    return {
        "pid": pid,
        "window_count": star.get_window_count(),
        "windows": [w.to_dict() for w in star.windows],
    }


@router.get("/{pid}/windows/{hwnd}")
async def get_window_detail(pid: int, hwnd: int):
    """
    获取指定窗口的详细信息（含 OCR 任务信息）
    
    Args:
        pid: 进程 ID
        hwnd: 窗口句柄
        
    Returns:
        窗口详情（上下文 + OCR 结果）
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    star = state.orbit_engine.star_seeker.get_star(pid)
    if not star:
        raise HTTPException(status_code=404, detail=f"星体 {pid} 未发现")
    
    target_window = None
    for w in star.windows:
        if w.hwnd == hwnd:
            target_window = w
            break
    
    if not target_window:
        raise HTTPException(status_code=404, detail=f"窗口 {hwnd} 未在星体 {pid} 中找到")
    
    ctx = target_window.parse_context(star.star_type)
    
    result = {
        "pid": pid,
        "hwnd": hwnd,
        "title": target_window.title,
        "context": ctx.to_dict(),
        "rect": list(target_window.rect) if target_window.rect else [],
        "class_name": target_window.class_name,
        "is_visible": target_window.is_visible,
    }
    
    return result


@router.post("/{pid}/windows/{hwnd}/ocr")
async def capture_window_ocr(pid: int, hwnd: int, region: Optional[str] = None):
    """
    对指定窗口执行 OCR 识别
    
    Args:
        pid: 进程 ID
        hwnd: 窗口句柄
        region: 识别区域（可选，如 left_task_list, center_chat 等）
        
    Returns:
        OCR 识别结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    star = state.orbit_engine.star_seeker.get_star(pid)
    if not star:
        raise HTTPException(status_code=404, detail=f"星体 {pid} 未发现")
    
    found = any(w.hwnd == hwnd for w in star.windows)
    if not found:
        raise HTTPException(status_code=404, detail=f"窗口 {hwnd} 未在星体 {pid} 中找到")
    
    try:
        from star_core.ocr_gazer import OCRGazer
        gazer = OCRGazer()
        img_path = gazer.capture_window(hwnd)
        if not img_path:
            raise HTTPException(status_code=500, detail="窗口截图失败")
        
        ocr_result = gazer.recognize_text(img_path, region=region)
        
        avg_conf = 0.0
        if ocr_result.lines:
            confs = [l.confidence for l in ocr_result.lines if hasattr(l, 'confidence') and l.confidence > 0]
            avg_conf = sum(confs) / len(confs) if confs else 0.0
        
        return {
            "pid": pid,
            "hwnd": hwnd,
            "region": region or "full",
            "text": ocr_result.text,
            "lines": [
                {
                    "text": line.text,
                    "confidence": getattr(line, 'confidence', 0.0),
                    "bbox": list(line.bbox) if hasattr(line, 'bbox') and line.bbox else [],
                }
                for line in ocr_result.lines
            ],
            "total_lines": len(ocr_result.lines),
            "confidence_avg": avg_conf,
            "recognize_time": ocr_result.recognize_time,
            "capture_time": ocr_result.capture_time,
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="OCR 模块未安装")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR 识别失败: {str(e)}")


@router.post("/{pid}/windows/{hwnd}/tasks")
async def get_window_tasks(pid: int, hwnd: int):
    """
    获取指定窗口的任务列表（OCR 识别左侧任务区）
    
    Args:
        pid: 进程 ID
        hwnd: 窗口句柄
        
    Returns:
        任务列表
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    star = state.orbit_engine.star_seeker.get_star(pid)
    if not star:
        raise HTTPException(status_code=404, detail=f"星体 {pid} 未发现")
    
    found = any(w.hwnd == hwnd for w in star.windows)
    if not found:
        raise HTTPException(status_code=404, detail=f"窗口 {hwnd} 未在星体 {pid} 中找到")
    
    try:
        from star_core.ocr_gazer import OCRGazer, OCRPostProcessor
        gazer = OCRGazer()
        img_path = gazer.capture_window(hwnd)
        if not img_path:
            raise HTTPException(status_code=500, detail="窗口截图失败")
        
        ocr_result = gazer.recognize_text(img_path, region="left_task_list")
        tasks = OCRPostProcessor.parse_task_list(ocr_result.lines)
        
        return {
            "pid": pid,
            "hwnd": hwnd,
            "tasks": [
                {
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "confidence": t.confidence,
                }
                for t in tasks
            ],
            "total": len(tasks),
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="OCR 模块未安装")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务列表获取失败: {str(e)}")
