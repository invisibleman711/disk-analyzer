"""磁盘空间整理工具 - Flask Web 应用"""

import os
from flask import Flask, render_template, jsonify, request

from analyzer import (
    get_disk_usage,
    scan_directory,
    get_applications,
    get_app_contents,
    find_cache_files,
    get_optimization_suggestions,
    delete_cache,
    format_size,
    FILE_TYPE_MAP,
)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/disks")
def api_disks():
    return jsonify(get_disk_usage())


@app.route("/api/scan")
def api_scan():
    path = request.args.get("path", "~")
    items = scan_directory(path)
    return jsonify(items)


@app.route("/api/apps")
def api_apps():
    return jsonify(get_applications())


@app.route("/api/app-contents")
def api_app_contents():
    """获取应用程序内部文件结构"""
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "未指定应用路径"}), 400
    return jsonify(get_app_contents(path))


@app.route("/api/caches")
def api_caches():
    return jsonify(find_cache_files())


@app.route("/api/suggestions")
def api_suggestions():
    disks = get_disk_usage()
    apps = get_applications()
    caches = find_cache_files()
    return jsonify(get_optimization_suggestions(disks, apps, caches))


@app.route("/api/analyze")
def api_analyze():
    disks = get_disk_usage()
    apps = get_applications()
    caches = find_cache_files()
    suggestions = get_optimization_suggestions(disks, apps, caches)
    total_cache = sum(c["size"] for c in caches if c["safe_to_delete"])
    return jsonify({
        "disks": disks,
        "apps": apps,
        "caches": caches,
        "suggestions": suggestions,
        "summary": {
            "total_apps": len(apps),
            "system_apps": len([a for a in apps if a["is_system"]]),
            "user_apps": len([a for a in apps if not a["is_system"]]),
            "total_cache_size": total_cache,
            "total_cache_size_str": format_size(total_cache),
            "cache_items": len(caches),
        },
    })


@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json()
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"success": False, "message": "未指定路径"})
    results = []
    total_freed = 0
    for path in paths:
        result = delete_cache(path)
        results.append({"path": path, **result})
        if result["success"]:
            total_freed += result.get("freed", 0)
    return jsonify({
        "results": results,
        "total_freed": total_freed,
        "total_freed_str": format_size(total_freed),
    })


@app.route("/api/browse")
def api_browse():
    path = request.args.get("path", "~")
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return jsonify({"error": "路径不存在"}), 404

    items = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                if is_dir:
                    size = _get_dir_size_fast(entry.path)
                else:
                    size = entry.stat(follow_symlinks=False).st_size
                ext = os.path.splitext(entry.name)[1].lower() if not is_dir else ""
                file_type = "folder" if is_dir else _get_file_type(entry.name)
                items.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_dir": is_dir,
                    "size": size,
                    "size_str": format_size(size),
                    "is_hidden": entry.name.startswith("."),
                    "file_type": file_type,
                    "extension": ext,
                })
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        return jsonify({"error": "无权访问该目录"}), 403

    items.sort(key=lambda x: x["size"], reverse=True)
    return jsonify({
        "path": path,
        "parent": os.path.dirname(path),
        "items": items,
    })


@app.route("/api/file-types")
def api_file_types():
    return jsonify(FILE_TYPE_MAP)


def _get_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    for type_key, type_info in FILE_TYPE_MAP.items():
        if ext in type_info["extensions"]:
            return type_key
    return "other"


def _get_dir_size_fast(path):
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    for sub in os.scandir(entry.path):
                        try:
                            if sub.is_file(follow_symlinks=False):
                                total += sub.stat(follow_symlinks=False).st_size
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total


if __name__ == "__main__":
    import webbrowser
    port = 8765
    print(f"\n{'='*50}")
    print(f"  磁盘空间整理工具")
    print(f"  访问地址: http://127.0.0.1:{port}")
    print(f"{'='*50}\n")
    webbrowser.open(f"http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
