"""磁盘分析引擎 - 扫描文件、分析应用、识别缓存、生成优化建议"""

import os
import stat
import time
import subprocess
import plistlib
import glob as glob_module
from pathlib import Path

# macOS 常见缓存目录模式
CACHE_PATTERNS = {
    "paths": [
        "~/Library/Caches",
        "~/Library/Logs",
        "~/Library/Application Support/CrashReporter",
        "~/Library/Saved Application State",
        "~/Library/Containers/*/Data/Library/Caches",
        "/private/var/folders",
        "~/.cache",
        "~/.npm/_cacache",
        "~/.yarn/cache",
        "~/Library/Developer/Xcode/DerivedData",
        "~/Library/Developer/Xcode/Archives",
        "~/Library/Developer/CoreSimulator",
        "~/Library/Application Support/Code/Cache",
        "~/Library/Application Support/Code/CachedData",
        "~/Library/Application Support/Code/CachedExtensions",
        "~/Library/Application Support/Google/Chrome/Default/Cache",
        "~/Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage",
        "~/Library/Application Support/Firefox/Profiles/*/cache2",
        "~/Library/Application Support/Slack/Cache",
        "~/Library/Application Support/Slack/Service Worker/CacheStorage",
        "~/Library/Application Support/discord/Cache",
        "~/Library/Group Containers/*.Office/TemporaryItems",
    ],
}

# macOS 磁盘卷宗中文说明
VOLUME_DESCRIPTIONS = {
    "/": {
        "name": "系统主卷宗（Macintosh HD）",
        "desc": "macOS 操作系统的核心分区，存放系统文件、内置应用程序和基础框架。此卷宗为只读挂载，系统完整性保护（SIP）会防止任何修改。不可清理。",
    },
    "/System/Volumes/Data": {
        "name": "数据卷宗（Macintosh HD - Data）",
        "desc": "存放您的所有个人数据、下载文件、安装的应用程序、用户配置和文档。这是日常使用中实际写入数据的分区，也是空间优化的主要目标。大部分可清理空间都在这里。",
    },
    "/System/Volumes/VM": {
        "name": "虚拟内存卷宗",
        "desc": "系统用于虚拟内存交换（swap）的专用分区。当物理内存不足时，系统会将不活跃的内存页面写入此处。大小由系统自动管理，无需手动干预。不可清理。",
    },
    "/System/Volumes/Preboot": {
        "name": "预启动卷宗",
        "desc": "存放电脑启动引导所需的文件，包括 BootKC（启动内核集合）、固件更新和 FileVault 加密恢复密钥等。确保 Mac 能正常开机。不可清理。",
    },
    "/System/Volumes/Update": {
        "name": "系统更新卷宗",
        "desc": "macOS 系统更新过程中的临时暂存区。在安装系统更新时会存放下载的更新包和临时文件，更新完成后通常会自动清理。不建议手动操作。",
    },
    "/System/Volumes/xarts": {
        "name": "安全凭证卷宗（xART）",
        "desc": "存放与 Apple 安全芯片（T2/Apple Silicon）相关的认证凭证和安全令牌，用于硬件级别的安全验证。体积很小，不可清理。",
    },
    "/System/Volumes/iSCPreboot": {
        "name": "iSC 预启动卷宗",
        "desc": "与系统安全启动链（Secure Boot Chain）相关的辅助分区，存放安全启动过程中需要的加密验证数据。体积很小，不可清理。",
    },
    "/System/Volumes/Hardware": {
        "name": "硬件配置卷宗",
        "desc": "存放与具体硬件型号相关的固件配置和设备驱动信息，确保 macOS 正确识别和驱动您的 Mac 硬件。体积极小，不可清理。",
    },
}

# 文件类型分类和说明
FILE_TYPE_MAP = {
    "documents": {
        "label": "文档",
        "icon": "doc",
        "extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".pages", ".numbers", ".key", ".csv", ".md", ".odt", ".ods"],
        "desc": "办公文档和文本文件，包括 PDF、Word、Excel 等格式",
    },
    "images": {
        "label": "图片",
        "icon": "img",
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif", ".ico", ".heic", ".heif", ".raw", ".psd", ".ai"],
        "desc": "照片和图像文件，包含相机照片、截图、设计稿等",
    },
    "videos": {
        "label": "视频",
        "icon": "vid",
        "extensions": [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".webm", ".mpg", ".mpeg", ".3gp"],
        "desc": "视频文件通常占用大量空间，检查是否有不再需要的视频",
    },
    "audio": {
        "label": "音频",
        "icon": "aud",
        "extensions": [".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg", ".wma", ".aiff", ".alac"],
        "desc": "音乐和音频文件",
    },
    "archives": {
        "label": "压缩包",
        "icon": "zip",
        "extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".dmg", ".iso", ".pkg"],
        "desc": "压缩文件和磁盘映像，解压后的压缩包通常可以删除",
    },
    "code": {
        "label": "代码",
        "icon": "code",
        "extensions": [".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".java", ".c", ".cpp", ".h", ".swift", ".go", ".rs", ".rb", ".php", ".sh", ".json", ".xml", ".yaml", ".yml", ".toml"],
        "desc": "程序源代码和配置文件",
    },
    "apps": {
        "label": "应用程序",
        "icon": "app",
        "extensions": [".app", ".dmg", ".pkg", ".ipa"],
        "desc": "应用程序包和安装文件",
    },
    "databases": {
        "label": "数据库",
        "icon": "db",
        "extensions": [".db", ".sqlite", ".sqlite3", ".sql", ".mdb"],
        "desc": "数据库文件，通常是应用程序存储数据使用",
    },
    "fonts": {
        "label": "字体",
        "icon": "font",
        "extensions": [".ttf", ".otf", ".woff", ".woff2", ".eot"],
        "desc": "字体文件",
    },
    "other": {
        "label": "其他",
        "icon": "other",
        "extensions": [],
        "desc": "未分类的文件类型",
    },
}


def format_size(size_bytes):
    """将字节数转换为人类可读的格式"""
    if size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def get_dir_size(path):
    """递归获取目录大小"""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(entry.path)
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total


def get_file_type(filename):
    """根据文件扩展名判断文件类型"""
    ext = os.path.splitext(filename)[1].lower()
    for type_key, type_info in FILE_TYPE_MAP.items():
        if ext in type_info["extensions"]:
            return type_key
    return "other"


def get_file_type_info(type_key):
    """获取文件类型信息"""
    return FILE_TYPE_MAP.get(type_key, FILE_TYPE_MAP["other"])


def scan_directory(path, max_depth=2, current_depth=0):
    """扫描目录，返回文件列表（按大小排序）"""
    items = []
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return items

    try:
        entries = list(os.scandir(path))
    except (PermissionError, OSError):
        return items

    for entry in entries:
        try:
            info = _get_file_info(entry)
            if info:
                info["depth"] = current_depth
                items.append(info)
        except (PermissionError, OSError):
            continue

    items.sort(key=lambda x: x["size"], reverse=True)
    return items


def _get_file_info(entry):
    """获取 os.DirEntry 的信息"""
    try:
        st = entry.stat(follow_symlinks=False)
        is_dir = entry.is_dir(follow_symlinks=False)
        if is_dir:
            size = get_dir_size(entry.path)
        else:
            size = st.st_size
        file_type = "folder" if is_dir else get_file_type(entry.name)
        return {
            "path": entry.path,
            "name": entry.name,
            "size": size,
            "size_str": format_size(size),
            "is_dir": is_dir,
            "is_hidden": entry.name.startswith('.'),
            "file_type": file_type,
            "modified": st.st_mtime,
            "modified_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
        }
    except (PermissionError, OSError):
        return None


def get_disk_usage():
    """获取所有挂载磁盘的使用情况"""
    import psutil
    disks = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            mp = partition.mountpoint
            vol_info = VOLUME_DESCRIPTIONS.get(mp, {
                "name": mp,
                "desc": "外接存储设备或第三方分区",
            })
            disks.append({
                "device": partition.device,
                "mountpoint": mp,
                "fstype": partition.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
                "total_str": format_size(usage.total),
                "used_str": format_size(usage.used),
                "free_str": format_size(usage.free),
                "cn_name": vol_info["name"],
                "cn_desc": vol_info["desc"],
            })
        except (PermissionError, OSError):
            continue
    return disks


def get_applications():
    """分析 /Applications 目录下的所有应用程序"""
    apps = []
    app_dirs = ["/Applications", os.path.expanduser("~/Applications")]

    for app_dir in app_dirs:
        if not os.path.exists(app_dir):
            continue
        try:
            for entry in os.scandir(app_dir):
                if entry.name.endswith(".app"):
                    size = get_dir_size(entry.path)
                    app_info = _get_app_metadata(entry.path)
                    apps.append({
                        "name": entry.name.replace(".app", ""),
                        "path": entry.path,
                        "size": size,
                        "size_str": format_size(size),
                        "is_system": _is_system_app(entry.path),
                        "bundle_id": app_info.get("bundle_id", ""),
                        "version": app_info.get("version", ""),
                        "location": app_dir,
                    })
        except (PermissionError, OSError):
            continue

    utils_dir = "/Applications/Utilities"
    if os.path.exists(utils_dir):
        try:
            for entry in os.scandir(utils_dir):
                if entry.name.endswith(".app"):
                    size = get_dir_size(entry.path)
                    app_info = _get_app_metadata(entry.path)
                    apps.append({
                        "name": entry.name.replace(".app", ""),
                        "path": entry.path,
                        "size": size,
                        "size_str": format_size(size),
                        "is_system": True,
                        "bundle_id": app_info.get("bundle_id", ""),
                        "version": app_info.get("version", ""),
                        "location": utils_dir,
                    })
        except (PermissionError, OSError):
            pass

    apps.sort(key=lambda x: x["size"], reverse=True)
    return apps


def get_app_contents(app_path):
    """获取应用内部文件结构和大小占比"""
    app_path = os.path.expanduser(app_path)
    if not os.path.exists(app_path):
        return {"error": "应用不存在"}

    total_size = get_dir_size(app_path)

    # 确定扫描目录：优先扫描 Contents/
    scan_dir = app_path
    if app_path.endswith(".app"):
        contents_dir = os.path.join(app_path, "Contents")
        if os.path.exists(contents_dir):
            scan_dir = contents_dir

    contents = []
    try:
        for entry in os.scandir(scan_dir):
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                size = get_dir_size(entry.path) if is_dir else entry.stat(follow_symlinks=False).st_size
                percent = round(size / total_size * 100, 1) if total_size > 0 else 0
                classification = _classify_app_content(entry.name, entry.path)
                item = {
                    "name": entry.name,
                    "path": entry.path,
                    "size": size,
                    "size_str": format_size(size),
                    "is_dir": is_dir,
                    "percent": percent,
                    "category": classification["category"],
                    "category_label": classification["label"],
                    "description": classification["desc"],
                    "can_delete": classification["can_delete"],
                }
                contents.append(item)
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    contents.sort(key=lambda x: x["size"], reverse=True)
    cache_items = [c for c in contents if c["can_delete"] and c["size"] > 0]

    # 按分类汇总
    category_summary = {}
    for c in contents:
        cat = c["category"]
        if cat not in category_summary:
            meta = APP_CATEGORY_META.get(cat, {"label": cat, "color": "other"})
            category_summary[cat] = {"label": meta["label"], "color": meta["color"], "size": 0, "count": 0}
        category_summary[cat]["size"] += c["size"]
        category_summary[cat]["count"] += 1
    for k in category_summary:
        category_summary[k]["size_str"] = format_size(category_summary[k]["size"])
        category_summary[k]["percent"] = round(category_summary[k]["size"] / total_size * 100, 1) if total_size > 0 else 0

    return {
        "total_size": total_size,
        "total_size_str": format_size(total_size),
        "contents": contents,
        "cache_items": cache_items,
        "cache_total": sum(c["size"] for c in cache_items),
        "cache_total_str": format_size(sum(c["size"] for c in cache_items)),
        "category_summary": category_summary,
    }


# 应用内部文件分类体系
# category: executable=可执行程序, framework=框架/库, resource=资源文件,
#           plugin=插件/扩展, signature=签名/安全, config=配置文件,
#           data=应用数据, cache=缓存/临时文件, other=其他
APP_CONTENT_CLASSIFICATION = {
    # 可执行程序 — 应用核心
    "MacOS":           {"category": "executable", "label": "可执行程序", "desc": "应用的核心二进制文件，是应用启动时实际运行的程序代码", "can_delete": False},
    "Helpers":         {"category": "executable", "label": "辅助程序",   "desc": "应用附带的辅助进程（如渲染进程、网络进程等），应用运行时会调用", "can_delete": False},
    "XPCServices":     {"category": "executable", "label": "XPC 服务",  "desc": "macOS 进程间通信服务，用于应用的后台任务和权限隔离", "can_delete": False},
    "LoginItems":      {"category": "executable", "label": "登录项",    "desc": "开机自启动组件，控制应用是否在登录时自动运行", "can_delete": False},

    # 框架和库
    "Frameworks":      {"category": "framework",  "label": "依赖框架",   "desc": "应用依赖的动态库和框架，包含第三方 SDK 和运行时库", "can_delete": False},
    "SharedFrameworks": {"category": "framework", "label": "共享框架",   "desc": "多个组件共用的框架库，通常占用空间较大（如 Electron 框架）", "can_delete": False},
    "Libraries":       {"category": "framework",  "label": "库文件",     "desc": "应用依赖的链接库文件", "can_delete": False},
    "SystemFrameworks": {"category": "framework", "label": "系统框架副本", "desc": "应用自带的系统框架副本，确保在不同 macOS 版本上兼容运行", "can_delete": False},

    # 资源文件
    "Resources":       {"category": "resource",   "label": "资源文件",   "desc": "图标、图片、音效、界面布局、多语言翻译包等非代码资源，应用界面显示依赖这些文件", "can_delete": False},
    "SharedSupport":   {"category": "resource",   "label": "共享资源",   "desc": "应用附带的额外数据，如文档模板、示例文件、帮助文档等", "can_delete": False},
    "Assets.car":      {"category": "resource",   "label": "资源目录",   "desc": "编译后的图片资源包（Asset Catalog），包含各分辨率的图标和图片", "can_delete": False},

    # 插件和扩展
    "PlugIns":         {"category": "plugin",     "label": "插件",      "desc": "应用的扩展功能模块，如文件格式支持、Quick Look 预览等", "can_delete": False},
    "Plugins":         {"category": "plugin",     "label": "插件",      "desc": "应用的扩展功能模块", "can_delete": False},
    "Extensions":      {"category": "plugin",     "label": "系统扩展",   "desc": "macOS 系统级扩展，如分享扩展、Today Widget 等", "can_delete": False},

    # 签名和安全
    "_CodeSignature":  {"category": "signature",  "label": "代码签名",   "desc": "Apple 代码签名数据，macOS 用此验证应用未被篡改，Gatekeeper 要求必须存在", "can_delete": False},
    "CodeResources":   {"category": "signature",  "label": "签名资源清单", "desc": "列出所有受代码签名保护的文件哈希值，用于完整性校验", "can_delete": False},
    "_MASReceipt":     {"category": "signature",  "label": "购买凭证",   "desc": "Mac App Store 的购买/下载凭证，证明应用的合法来源", "can_delete": False},
    "embedded.provisionprofile": {"category": "signature", "label": "配置描述文件", "desc": "开发者签名和权限配置文件，定义应用被允许使用的系统功能", "can_delete": False},

    # 配置文件
    "Info.plist":      {"category": "config",     "label": "应用清单",   "desc": "应用的元数据配置（名称、版本、权限声明、支持的文件类型等），macOS 依此识别应用", "can_delete": False},
    "PkgInfo":         {"category": "config",     "label": "包类型标识", "desc": "标识这是一个应用程序包（APPL），仅 8 字节的标记文件", "can_delete": False},

    # 应用数据（混合目录）
    "Library":         {"category": "data",       "label": "应用数据",   "desc": "包含应用的偏好设置、数据库和缓存的混合目录，可能有可清理的子目录", "can_delete": False},
    "Developer":       {"category": "data",       "label": "开发者数据", "desc": "开发工具链、SDK、编译器等开发相关数据", "can_delete": False},

    # 缓存和临时文件 — 可清理
    "Caches":          {"category": "cache",      "label": "缓存",      "desc": "应用运行中生成的临时缓存数据，清理后应用会自动重建", "can_delete": True},
    "Cache":           {"category": "cache",      "label": "缓存",      "desc": "缓存数据，清理后会自动重建", "can_delete": True},
    "GPUCache":        {"category": "cache",      "label": "GPU 缓存",  "desc": "图形处理器渲染缓存，加速界面显示，清理后自动重建", "can_delete": True},
    "ShaderCache":     {"category": "cache",      "label": "着色器缓存", "desc": "GPU 着色器编译结果缓存，清理后首次渲染会略慢", "can_delete": True},
    "DawnCache":       {"category": "cache",      "label": "Dawn 缓存", "desc": "WebGPU 图形引擎缓存", "can_delete": True},
    "WebKit":          {"category": "cache",      "label": "WebKit 缓存", "desc": "内嵌网页引擎的渲染缓存和数据", "can_delete": True},
    "Logs":            {"category": "cache",      "label": "日志",      "desc": "应用运行日志记录，通常只对排查问题有用", "can_delete": True},
    "logs":            {"category": "cache",      "label": "日志",      "desc": "应用运行日志", "can_delete": True},
    "CrashReporter":   {"category": "cache",      "label": "崩溃报告",  "desc": "应用崩溃时生成的诊断报告", "can_delete": True},
    "blob_storage":    {"category": "cache",      "label": "Blob 存储", "desc": "网页应用的二进制大对象存储（Electron 应用常见）", "can_delete": True},
    "IndexedDB":       {"category": "cache",      "label": "IndexedDB", "desc": "网页应用的本地数据库存储", "can_delete": True},
    "Local Storage":   {"category": "cache",      "label": "本地存储",  "desc": "网页应用的 LocalStorage 数据", "can_delete": True},
    "Session Storage":  {"category": "cache",     "label": "会话存储",  "desc": "网页应用的会话临时数据", "can_delete": True},
    "Service Worker":  {"category": "cache",      "label": "Service Worker", "desc": "网页后台脚本及其缓存的离线资源", "can_delete": True},
    "Code Cache":      {"category": "cache",      "label": "代码缓存",  "desc": "JavaScript V8 引擎编译缓存", "can_delete": True},
    "tmp":             {"category": "cache",      "label": "临时文件",  "desc": "临时文件目录，可安全清理", "can_delete": True},
    "temp":            {"category": "cache",      "label": "临时文件",  "desc": "临时文件目录，可安全清理", "can_delete": True},
}

# 分类中文名和颜色（前端配合使用）
APP_CATEGORY_META = {
    "executable": {"label": "可执行程序", "color": "exec"},
    "framework":  {"label": "框架/库",   "color": "fw"},
    "resource":   {"label": "资源文件",   "color": "res"},
    "plugin":     {"label": "插件/扩展",  "color": "plug"},
    "signature":  {"label": "签名/安全",  "color": "sig"},
    "config":     {"label": "配置文件",   "color": "cfg"},
    "data":       {"label": "应用数据",   "color": "data"},
    "cache":      {"label": "缓存/临时",  "color": "cache"},
    "other":      {"label": "其他",      "color": "other"},
}


def _classify_app_content(name, path):
    """对应用内部文件进行精确分类"""
    # 精确匹配
    if name in APP_CONTENT_CLASSIFICATION:
        info = APP_CONTENT_CLASSIFICATION[name]
        return {
            "category": info["category"],
            "label": info["label"],
            "desc": info["desc"],
            "can_delete": info["can_delete"],
        }

    # 模式匹配
    name_lower = name.lower()
    if "cache" in name_lower:
        return {"category": "cache", "label": "缓存", "desc": "缓存数据，可安全清理", "can_delete": True}
    if "log" in name_lower:
        return {"category": "cache", "label": "日志", "desc": "日志文件，可安全清理", "can_delete": True}
    if "tmp" in name_lower or "temp" in name_lower:
        return {"category": "cache", "label": "临时文件", "desc": "临时文件，可安全清理", "can_delete": True}
    if name.endswith(".dylib") or name.endswith(".so"):
        return {"category": "framework", "label": "动态库", "desc": "动态链接库文件，应用运行时加载", "can_delete": False}
    if name.endswith(".plist"):
        return {"category": "config", "label": "配置文件", "desc": "属性列表配置文件", "can_delete": False}
    if name.endswith((".strings", ".lproj", ".nib", ".storyboardc")):
        return {"category": "resource", "label": "资源文件", "desc": "界面或本地化资源", "can_delete": False}
    if name.endswith((".car", ".icns", ".png", ".jpg", ".tiff", ".pdf")):
        return {"category": "resource", "label": "图片资源", "desc": "图标或图片资源文件", "can_delete": False}
    if name.endswith(".entitlements"):
        return {"category": "signature", "label": "权限声明", "desc": "应用的系统权限声明文件", "can_delete": False}

    # 默认归类
    if os.path.isdir(path):
        return {"category": "other", "label": "其他目录", "desc": "应用附属目录", "can_delete": False}
    return {"category": "other", "label": "其他文件", "desc": "应用附属文件", "can_delete": False}


def _get_app_metadata(app_path):
    """读取 .app 的 Info.plist 获取元数据"""
    info = {"bundle_id": "", "version": ""}
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    if not os.path.exists(plist_path):
        return info
    try:
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
            info["bundle_id"] = plist.get("CFBundleIdentifier", "")
            info["version"] = plist.get("CFBundleShortVersionString", "")
    except Exception:
        pass
    return info


def _is_system_app(app_path):
    """判断是否为系统应用"""
    system_apps = {
        "Safari", "Mail", "Messages", "FaceTime", "Photos",
        "Music", "TV", "Podcasts", "News", "Stocks", "Books",
        "Calendar", "Contacts", "Reminders", "Notes", "Maps",
        "Weather", "Clock", "Calculator", "Preview", "TextEdit",
        "Font Book", "Chess", "Stickies", "Dictionary", "Grapher",
        "Digital Color Meter", "System Preferences", "System Settings",
        "App Store", "Finder", "Siri", "Photo Booth", "QuickTime Player",
        "Automator", "Script Editor", "Terminal", "Activity Monitor",
        "Console", "Disk Utility", "Keychain Access", "Migration Assistant",
        "System Information", "Bluetooth File Exchange", "Boot Camp Assistant",
    }
    app_name = os.path.basename(app_path).replace(".app", "")
    if app_name in system_apps:
        return True
    bundle_id = _get_app_metadata(app_path).get("bundle_id", "")
    if bundle_id.startswith("com.apple."):
        return True
    return False


def find_cache_files():
    """查找所有缓存文件和目录"""
    caches = []

    for pattern in CACHE_PATTERNS["paths"]:
        expanded = os.path.expanduser(pattern)
        if "*" in expanded:
            matches = glob_module.glob(expanded)
        else:
            matches = [expanded]

        for match_path in matches:
            if os.path.exists(match_path):
                size = get_dir_size(match_path) if os.path.isdir(match_path) else os.path.getsize(match_path)
                if size > 0:
                    category = _categorize_cache(match_path)
                    safe = _is_safe_to_delete(match_path)
                    caches.append({
                        "path": match_path,
                        "name": os.path.basename(match_path),
                        "parent": _get_friendly_parent(match_path),
                        "size": size,
                        "size_str": format_size(size),
                        "category": category,
                        "safe_to_delete": safe,
                        "description": _get_cache_description_detailed(match_path),
                        "recommendation": _get_cache_recommendation(match_path, size, safe),
                    })

    caches.sort(key=lambda x: x["size"], reverse=True)
    return caches


def _categorize_cache(path):
    """对缓存进行分类"""
    path_lower = path.lower()
    if "xcode" in path_lower or "deriveddata" in path_lower:
        return "开发工具缓存"
    elif "chrome" in path_lower or "firefox" in path_lower or "safari" in path_lower:
        return "浏览器缓存"
    elif "npm" in path_lower or "yarn" in path_lower or "pip" in path_lower:
        return "包管理器缓存"
    elif "slack" in path_lower or "discord" in path_lower or "telegram" in path_lower:
        return "通讯应用缓存"
    elif "vscode" in path_lower or "code" in path_lower:
        return "编辑器缓存"
    elif "log" in path_lower:
        return "日志文件"
    elif "crash" in path_lower:
        return "崩溃报告"
    elif "saved application state" in path_lower:
        return "应用状态缓存"
    elif "simulator" in path_lower:
        return "模拟器数据"
    elif "office" in path_lower:
        return "办公软件缓存"
    else:
        return "系统缓存"


def _get_friendly_parent(path):
    """获取缓存的友好名称"""
    path_lower = path.lower()
    if "google/chrome" in path_lower:
        return "Google Chrome"
    elif "firefox" in path_lower:
        return "Firefox"
    elif "slack" in path_lower:
        return "Slack"
    elif "discord" in path_lower:
        return "Discord"
    elif "code" in path_lower and ("vscode" in path_lower or "Code" in path):
        return "VS Code"
    elif "xcode" in path_lower:
        return "Xcode"
    elif "npm" in path_lower:
        return "npm"
    elif "yarn" in path_lower:
        return "Yarn"
    elif "office" in path_lower:
        return "Microsoft Office"
    else:
        return os.path.basename(os.path.dirname(path))


def _is_safe_to_delete(path):
    """判断是否可以安全删除"""
    unsafe_patterns = ["/private/var", "/System", "/usr"]
    for pattern in unsafe_patterns:
        if path.startswith(pattern):
            return False
    return True


def _get_cache_description_detailed(path):
    """获取缓存的详细描述"""
    path_lower = path.lower()
    if "deriveddata" in path_lower:
        return "Xcode 编译产物和索引缓存。每次编译项目时 Xcode 会在此目录生成中间编译文件、构建日志和代码索引数据。占用空间通常随项目数量线性增长。删除后 Xcode 会在下次打开项目时自动重新生成，但首次编译会变慢。"
    elif "coresimulator" in path_lower:
        return "iOS/watchOS/tvOS 模拟器运行时数据，包含模拟器系统镜像、已安装的测试应用和模拟器用户数据。如果您不做 iOS 开发或已经很久没用模拟器，可以安全清理。删除后需在 Xcode 中重新下载模拟器运行时。"
    elif "archives" in path_lower and "xcode" in path_lower:
        return "Xcode 应用归档文件（.xcarchive），是已经打包好的应用副本。用于提交到 App Store 或导出 IPA 文件。已成功提交的旧版本归档可以安全删除。如果您需要对旧版本进行符号化崩溃日志，则建议保留。"
    elif "chrome" in path_lower and "service worker" in path_lower:
        return "Chrome 浏览器 Service Worker 缓存，用于离线网页应用和推送通知。包含各网站注册的后台脚本及其缓存的资源数据。删除后网页应用在下次访问时会重新缓存，不影响浏览记录和密码。"
    elif "chrome" in path_lower and "cache" in path_lower:
        return "Chrome 浏览器页面缓存，存储已访问网页的图片、CSS、JavaScript 等静态资源。缓存的目的是加快重复访问同一网页的速度。删除后不影响书签、密码和浏览历史，但短期内浏览网页速度可能略慢。"
    elif "firefox" in path_lower and "cache" in path_lower:
        return "Firefox 浏览器页面缓存。作用与 Chrome 缓存类似，存储网页静态资源用于加速重复访问。删除后 Firefox 会在浏览时自动重建缓存，不影响书签、密码和历史记录。"
    elif "npm" in path_lower:
        return "npm 全局包下载缓存。当您使用 npm install 安装包时，下载的包文件会被缓存在此处，以便未来相同版本的安装可以直接从本地缓存读取。删除后不影响已安装的项目依赖，但下次安装时需要重新从网络下载。"
    elif "yarn" in path_lower:
        return "Yarn 包管理器缓存目录。功能与 npm 缓存类似，存储下载过的 JavaScript 包文件。如果使用 Yarn 2+ (Berry) 版本，缓存机制略有不同。删除后下次安装依赖时会重新下载。"
    elif path_lower.endswith("/logs") or path_lower.endswith("/library/logs"):
        return "应用程序运行日志，记录软件运行过程中的状态信息、错误信息和调试数据。通常只对开发者排查问题有用。长时间积累的日志文件可能占用可观空间，可以安全清理。"
    elif "crashreporter" in path_lower:
        return "应用崩溃报告文件。当应用程序意外退出时，系统会在此保存崩溃堆栈信息。这些报告会被 Apple 收集用于改善软件质量。如果您已经提交过反馈或不需要排查崩溃原因，可以安全删除。"
    elif "saved application state" in path_lower:
        return "各应用程序的窗口状态快照。macOS 用于实现「恢复」功能，即重新打开应用时恢复到上次关闭时的窗口位置和状态。删除后影响较小，只是应用再次打开时不会记住上次的窗口布局。"
    elif "slack" in path_lower:
        return "Slack 即时通讯应用的本地缓存，包含聊天中的图片预览、文件缩略图和 Electron 引擎的网页资源缓存。删除后 Slack 会在下次启动时重新加载这些数据，不影响聊天记录（存在服务器端）。"
    elif "discord" in path_lower:
        return "Discord 语音社交应用的本地缓存，与 Slack 类似包含媒体预览和 Electron 引擎缓存。删除后 Discord 会自动重建，不影响账号数据和聊天历史。"
    elif path_lower.endswith("/library/caches"):
        return "系统级应用缓存总目录。包含各种应用程序的缓存数据，如 Safari 缓存、系统字体缓存、Spotlight 索引缓存等。是所有应用缓存的汇总位置。可以安全清理，但删除后短期内系统响应可能略慢。"
    elif ".cache" in path_lower and path_lower.endswith("/.cache"):
        return "用户级通用缓存目录（XDG 规范）。许多命令行工具和开源软件将缓存数据存放在此处，如 pip、Homebrew、各种 CLI 工具等。可以安全清理。"
    elif "code/cache" in path_lower or "code/cacheddata" in path_lower:
        return "VS Code 编辑器的运行缓存和已编译的扩展数据。包含编辑器界面渲染缓存、扩展编译产物和工作区索引。删除后 VS Code 会在下次启动时重新生成，可能首次打开稍慢。"
    elif "cachedextensions" in path_lower:
        return "VS Code 已下载的扩展缓存。当扩展更新或重新安装时使用的本地缓存副本。删除后不影响已安装的扩展，但下次更新扩展时需要重新下载。"
    elif "containers" in path_lower and "caches" in path_lower:
        return "沙盒应用的缓存数据。macOS 中从 App Store 下载的应用在独立容器中运行，各自的缓存存放在此。可以安全清理，应用会在需要时自动重建。"
    elif "/private/var/folders" in path_lower:
        return "系统级临时文件和缓存目录。macOS 为每个用户维护的底层临时存储区，存放系统级缓存、临时文件和进程间通信数据。由系统自动管理，不建议手动删除，可能影响正在运行的程序。"
    elif "office" in path_lower:
        return "Microsoft Office 应用的临时文件和自动恢复数据。包含 Word、Excel、PowerPoint 等办公软件的编辑临时文件。正常情况下可以清理，但如果有未保存的文档，清理后可能无法恢复。"
    else:
        return "缓存数据文件。系统或应用程序为提升性能而生成的临时数据。删除后相关功能通常会在下次使用时自动重新生成缓存。"


def _get_cache_recommendation(path, size, safe):
    """获取清理建议"""
    path_lower = path.lower()
    size_gb = size / (1024 * 1024 * 1024)

    if not safe:
        return {
            "action": "keep",
            "label": "不建议清理",
            "reason": "此路径属于系统关键目录，删除可能导致系统不稳定或应用异常。请让系统自动管理。",
        }

    if "deriveddata" in path_lower:
        if size_gb > 5:
            return {
                "action": "clean",
                "label": "建议清理",
                "reason": f"DerivedData 已占用 {format_size(size)}，明显偏大。清理后 Xcode 会自动重建当前项目的编译缓存。",
            }
        return {
            "action": "optional",
            "label": "可选清理",
            "reason": "如果近期不需要频繁编译，可以清理释放空间。否则保留可加速编译。",
        }

    if "coresimulator" in path_lower:
        return {
            "action": "clean",
            "label": "建议清理",
            "reason": "模拟器数据通常占用很大空间。如果不做 iOS 开发，建议清理。需要时可在 Xcode 中重新下载。",
        }

    if "chrome" in path_lower or "firefox" in path_lower:
        if size_gb > 1:
            return {
                "action": "clean",
                "label": "建议清理",
                "reason": f"浏览器缓存已达 {format_size(size)}。清理不影响书签和密码，浏览器会自动重建缓存。",
            }
        return {
            "action": "optional",
            "label": "可选清理",
            "reason": "缓存大小正常。清理可释放空间但会短暂影响网页加载速度。",
        }

    if "npm" in path_lower or "yarn" in path_lower:
        if size_gb > 0.5:
            return {
                "action": "clean",
                "label": "建议清理",
                "reason": f"包管理器缓存占用 {format_size(size)}。清理不影响已安装的项目依赖，只是下次安装新包时需要重新下载。",
            }
        return {
            "action": "optional",
            "label": "可选清理",
            "reason": "缓存保留可加速未来的包安装。空间不紧张时可以保留。",
        }

    if "slack" in path_lower or "discord" in path_lower:
        return {
            "action": "clean",
            "label": "建议清理",
            "reason": "通讯应用的缓存数据（图片预览等）会持续增长。清理不影响聊天记录，应用会自动重建。",
        }

    if "log" in path_lower or "crashreporter" in path_lower:
        return {
            "action": "clean",
            "label": "建议清理",
            "reason": "日志和崩溃报告积累后会占用空间，且对普通用户没有实际用途。可以安全清理。",
        }

    if "saved application state" in path_lower:
        return {
            "action": "optional",
            "label": "可选清理",
            "reason": "删除后应用不会记住上次的窗口位置，影响很小。空间紧张时可清理。",
        }

    if "code" in path_lower:
        if size_gb > 1:
            return {
                "action": "clean",
                "label": "建议清理",
                "reason": f"VS Code 缓存达 {format_size(size)}，偏大。清理后编辑器会自动重建，不影响设置和扩展。",
            }
        return {
            "action": "optional",
            "label": "可选清理",
            "reason": "VS Code 缓存保留可加速编辑器启动。",
        }

    if path_lower.endswith("/library/caches") or path_lower.endswith("/.cache"):
        if size_gb > 2:
            return {
                "action": "clean",
                "label": "建议清理",
                "reason": f"缓存目录已达 {format_size(size)}，清理可显著释放空间。各应用会在需要时自动重建缓存。",
            }
        return {
            "action": "optional",
            "label": "可选清理",
            "reason": "通用缓存目录，清理后短期内部分操作可能略慢。",
        }

    if size_gb > 1:
        return {
            "action": "clean",
            "label": "建议清理",
            "reason": f"占用 {format_size(size)} 空间较大，建议清理释放空间。",
        }

    return {
        "action": "optional",
        "label": "可选清理",
        "reason": "可以安全删除，删除后相关应用会自动重建缓存。",
    }


def get_optimization_suggestions(disks, apps, caches):
    """基于分析结果生成详细的优化建议"""
    suggestions = []

    # 1. 磁盘空间综合评估
    data_disk = next((d for d in disks if d["mountpoint"] == "/System/Volumes/Data"), None)
    if data_disk:
        if data_disk["percent"] > 90:
            suggestions.append({
                "level": "critical",
                "icon": "!!",
                "title": "数据卷空间严重不足，需要立即清理",
                "detail": f"数据卷已使用 {data_disk['percent']}%，仅剩 {data_disk['free_str']}。macOS 在剩余空间不足 10% 时会出现性能下降、应用闪退、无法更新系统等问题。强烈建议立即释放至少 20GB 空间。",
                "items": [
                    {"text": "优先清理浏览器缓存和开发工具缓存（通常可释放数 GB）", "can_clean": True},
                    {"text": "检查\"下载\"文件夹中不再需要的大文件（如 .dmg 安装包）", "can_clean": True},
                    {"text": "清空废纸篓（Finder → 清倒废纸篓）", "can_clean": True},
                    {"text": "检查是否有不再使用的大型应用程序可以卸载", "can_clean": True},
                ],
            })
        elif data_disk["percent"] > 75:
            suggestions.append({
                "level": "warning",
                "icon": "!",
                "title": "数据卷空间偏紧，建议定期清理",
                "detail": f"数据卷已使用 {data_disk['percent']}%，剩余 {data_disk['free_str']}。虽然暂时不会影响使用，但建议保持至少 15-20% 的可用空间，以确保系统稳定运行和 Time Machine 备份正常。",
                "items": [
                    {"text": "定期清理浏览器缓存（切换到\"缓存管理\"页面操作）", "can_clean": True},
                    {"text": "检查大型文件：视频、下载的安装包等", "can_clean": True},
                    {"text": "系统文件和应用程序文件不要删除", "can_clean": False},
                ],
            })
        else:
            suggestions.append({
                "level": "success",
                "icon": "ok",
                "title": "数据卷空间充足",
                "detail": f"数据卷使用率 {data_disk['percent']}%，剩余 {data_disk['free_str']}。当前空间状况良好，无需紧急清理。建议养成定期检查的习惯。",
                "items": [],
            })

    # 2. 可清理缓存详细建议
    safe_caches = [c for c in caches if c["safe_to_delete"]]
    total_safe = sum(c["size"] for c in safe_caches)
    recommend_clean = [c for c in caches if c.get("recommendation", {}).get("action") == "clean"]
    total_recommend = sum(c["size"] for c in recommend_clean)

    if recommend_clean:
        items = []
        for c in recommend_clean[:8]:
            items.append({
                "text": f"{c['parent']}（{c['size_str']}）— {c.get('recommendation', {}).get('reason', '')}",
                "can_clean": True,
            })
        suggestions.append({
            "level": "warning",
            "icon": "clean",
            "title": f"建议清理 {len(recommend_clean)} 项缓存，可释放约 {format_size(total_recommend)}",
            "detail": "以下缓存项占用空间较大且清理风险低。删除后不会影响应用的核心功能，相关应用会在需要时自动重建缓存数据。",
            "items": items,
        })

    optional_caches = [c for c in caches if c.get("recommendation", {}).get("action") == "optional"]
    if optional_caches:
        total_optional = sum(c["size"] for c in optional_caches)
        items = []
        for c in optional_caches[:5]:
            items.append({
                "text": f"{c['parent']}（{c['size_str']}）— {c.get('recommendation', {}).get('reason', '')}",
                "can_clean": True,
            })
        suggestions.append({
            "level": "info",
            "icon": "opt",
            "title": f"可选清理 {len(optional_caches)} 项，合计 {format_size(total_optional)}",
            "detail": "以下缓存项可以安全删除，但保留它们有助于加速相关应用的运行。如果空间充足，可以选择保留。",
            "items": items,
        })

    # 3. 不可清理项说明
    unsafe_caches = [c for c in caches if not c["safe_to_delete"]]
    if unsafe_caches:
        items = []
        for c in unsafe_caches:
            items.append({
                "text": f"{c['parent']}（{c['size_str']}）— 系统关键路径，由 macOS 自动管理，手动删除可能导致系统不稳定",
                "can_clean": False,
            })
        suggestions.append({
            "level": "info",
            "icon": "lock",
            "title": f"以下 {len(unsafe_caches)} 项不建议清理",
            "detail": "这些位于系统保护路径下的文件由 macOS 自动管理。即使占用空间较大，也不应手动删除。系统会在适当时候自动清理。",
            "items": items,
        })

    # 4. 大型应用建议
    large_user_apps = [a for a in apps if a["size"] > 1024 * 1024 * 1024 and not a["is_system"]]
    if large_user_apps:
        items = []
        for a in large_user_apps:
            items.append({
                "text": f"{a['name']}（{a['size_str']}）— 用户安装的应用，如果不再使用可以卸载释放空间",
                "can_clean": True,
            })
        suggestions.append({
            "level": "info",
            "icon": "app",
            "title": f"{len(large_user_apps)} 个大型用户应用（每个 > 1GB）",
            "detail": "这些应用占用空间较大。请检查是否所有应用都在日常使用中。不再需要的应用可以通过 Finder 或 Launchpad 卸载。注意：系统应用（如 Xcode 等 Apple 开发工具）的卸载需要谨慎。",
            "items": items,
        })

    system_apps_large = [a for a in apps if a["size"] > 1024 * 1024 * 1024 and a["is_system"]]
    if system_apps_large:
        items = []
        for a in system_apps_large:
            items.append({
                "text": f"{a['name']}（{a['size_str']}）— macOS 系统应用，不可删除",
                "can_clean": False,
            })
        suggestions.append({
            "level": "info",
            "icon": "sys",
            "title": f"{len(system_apps_large)} 个大型系统应用",
            "detail": "这些是 macOS 系统自带的应用，受系统完整性保护（SIP），不可也不应删除。它们是系统正常运行的组成部分。",
            "items": items,
        })

    # 5. 实用清理技巧
    suggestions.append({
        "level": "info",
        "icon": "tip",
        "title": "日常存储管理小贴士",
        "detail": "养成良好的存储管理习惯，可以长期保持磁盘空间充足。",
        "items": [
            {"text": "定期清空废纸篓 — 删除的文件在清空废纸篓前仍占用磁盘空间", "can_clean": True},
            {"text": "下载的 .dmg 安装包在安装完应用后可以删除", "can_clean": True},
            {"text": "大型视频文件考虑转存到外接硬盘或云存储", "can_clean": True},
            {"text": "不活跃的开发项目中的 node_modules 可以删除，需要时 npm install 即可恢复", "can_clean": True},
            {"text": "系统的 /System、/usr、/bin 目录绝对不要碰", "can_clean": False},
            {"text": "不确定的文件先压缩备份再删除，避免误删", "can_clean": False},
        ],
    })

    return suggestions


def delete_cache(path):
    """安全删除缓存文件/目录"""
    import shutil
    path = os.path.expanduser(path)

    if not os.path.exists(path):
        return {"success": False, "message": "路径不存在"}

    if not _is_safe_to_delete(path):
        return {"success": False, "message": "该路径不允许删除（系统关键路径）"}

    home = os.path.expanduser("~")
    if path in ("/", home, "/Applications", "/System", "/Library"):
        return {"success": False, "message": "不允许删除根级别目录"}

    try:
        size_before = get_dir_size(path) if os.path.isdir(path) else os.path.getsize(path)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return {
            "success": True,
            "message": f"已成功删除，释放 {format_size(size_before)} 空间",
            "freed": size_before,
            "freed_str": format_size(size_before),
        }
    except PermissionError:
        return {"success": False, "message": "权限不足，无法删除"}
    except Exception as e:
        return {"success": False, "message": f"删除失败: {str(e)}"}
