#!/usr/bin/env python3
"""群星项目环境引导脚本。

在系统 Python 3.14 缺少部分依赖时，自动将 .pylibs 加入 sys.path。
使用方法：将此脚本作为 sitecustomize 放置，或在启动脚本中 import。

也可直接运行验证环境：
    python scripts/bootstrap_env.py
"""

import sys
import os
from pathlib import Path

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PYLIBS = _PROJECT_ROOT / ".pylibs"

# 将 .pylibs 加入 sys.path（如果存在）
if _PYLIBS.is_dir():
    _str = str(_PYLIBS)
    if _str not in sys.path:
        sys.path.insert(0, _str)

# 同时确保项目根目录在 path 中
_str_root = str(_PROJECT_ROOT)
if _str_root not in sys.path:
    sys.path.insert(0, _str_root)


if __name__ == "__main__":
    # 验证环境
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version}")
    print(f"Project root: {_PROJECT_ROOT}")
    print(f".pylibs: {_PYLIBS} ({'exists' if _PYLIBS.is_dir() else 'missing'})")
    print()

    # 测试关键导入
    tests = [
        ("star_core.trae_cdp_bridge", "TraeCDPBridge"),
        ("star_core.cdp_bridge", "CDPBridge"),
        ("star_core.star_emissary", "StarEmissary"),
        ("loguru", "logger"),
        ("pyperclip", "copy"),
    ]

    all_ok = True
    for module, attr in tests:
        try:
            mod = __import__(module, fromlist=[attr])
            if hasattr(mod, attr):
                print(f"  [OK] {module}.{attr}")
            else:
                print(f"  [WARN] {module} imported but {attr} not found")
        except ImportError as e:
            print(f"  [FAIL] {module}: {e}")
            all_ok = False

    print()
    if all_ok:
        print("环境检查通过!")
    else:
        print("部分依赖缺失，请运行: pip install --target .pylibs <package>")
