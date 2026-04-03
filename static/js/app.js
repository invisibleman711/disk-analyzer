/* 磁盘空间整理工具 - 前端交互逻辑 v2 */

let currentPath = "~";
let cachedCaches = [];
let pendingDeletePaths = [];
let loadedAppDetails = {};

// 文件类型颜色/图标映射
const fileTypeConfig = {
  documents: { icon: "doc", color: "#8a6d3b", label: "文档" },
  images: { icon: "img", color: "#4a7fb5", label: "图片" },
  videos: { icon: "vid", color: "#b04a4a", label: "视频" },
  audio: { icon: "aud", color: "#7a5ab0", label: "音频" },
  archives: { icon: "zip", color: "#3a7a4a", label: "压缩包" },
  code: { icon: "code", color: "#2d7a6a", label: "代码" },
  apps: { icon: "app", color: "#a06830", label: "应用" },
  databases: { icon: "db", color: "#5a4a8a", label: "数据库" },
  fonts: { icon: "font", color: "#6a6040", label: "字体" },
  other: { icon: "file", color: "#7a756a", label: "其他" },
  folder: { icon: "dir", color: "#2d8b7a", label: "文件夹" },
};

// ========== Tab 切换 ==========
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    tab.classList.add("active");
    const section = document.getElementById("tab-" + tab.dataset.tab);
    section.classList.add("active");

    const tabName = tab.dataset.tab;
    if (tabName === "overview") loadDisks();
    if (tabName === "files") browsePath(currentPath);
  });
});

// ========== API ==========
async function api(endpoint, options = {}) {
  try {
    const res = await fetch("/api/" + endpoint, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `请求失败: ${res.status}`);
    }
    return await res.json();
  } catch (e) {
    showToast(e.message, "error");
    throw e;
  }
}

// ========== 磁盘概览 ==========
async function loadDisks() {
  const el = document.getElementById("disk-list");
  el.innerHTML = '<div class="loading"><div class="spinner"></div>正在扫描磁盘...</div>';
  try {
    const disks = await api("disks");
    if (!disks.length) { el.innerHTML = '<div class="loading">未检测到磁盘</div>'; return; }
    el.innerHTML = disks.map((d) => {
      const level = d.percent > 90 ? "high" : d.percent > 75 ? "medium" : "low";
      return `
      <div class="disk-card">
        <div class="disk-header">
          <span class="disk-name">${esc(d.mountpoint)}</span>
          <span class="disk-meta">${esc(d.device)} · ${d.fstype}</span>
        </div>
        <div class="disk-cn-name">${esc(d.cn_name)}</div>
        <div class="disk-desc">${esc(d.cn_desc)}</div>
        <div class="disk-bar-bg">
          <div class="disk-bar-fill ${level}" style="width:${d.percent}%"></div>
        </div>
        <div class="disk-stats">
          <span>总容量: <strong>${d.total_str}</strong></span>
          <span>已用: <strong>${d.used_str}</strong></span>
          <span>可用: <strong>${d.free_str}</strong></span>
          <span>使用率: <strong>${d.percent}%</strong></span>
        </div>
      </div>`;
    }).join("");
  } catch { el.innerHTML = '<div class="loading">加载失败，请重试</div>'; }
}

// ========== 文件浏览 ==========
async function browsePath(path) {
  currentPath = path;
  document.getElementById("current-path").textContent = path;
  const el = document.getElementById("file-list");
  el.innerHTML = '<div class="loading"><div class="spinner"></div>正在扫描目录...</div>';

  try {
    const data = await api("browse?path=" + encodeURIComponent(path));
    currentPath = data.path;
    document.getElementById("current-path").textContent = data.path;

    const showHidden = document.getElementById("show-hidden").checked;
    const items = showHidden ? data.items : data.items.filter((i) => !i.is_hidden);

    if (!items.length) { el.innerHTML = '<div class="loading">该目录为空</div>'; return; }

    // Build type legend from actual items
    const typesFound = {};
    items.forEach((item) => {
      const ft = item.file_type || "other";
      if (!typesFound[ft]) typesFound[ft] = 0;
      typesFound[ft]++;
    });
    const legendEl = document.getElementById("type-legend");
    legendEl.innerHTML = Object.entries(typesFound)
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => {
        const conf = fileTypeConfig[type] || fileTypeConfig.other;
        return `<span class="type-tag ft-${type}"><span class="type-tag-dot" style="background:${conf.color}"></span>${conf.label} ${count}</span>`;
      })
      .join("");

    const maxSize = Math.max(...items.map((i) => i.size), 1);

    el.innerHTML = `
    <table class="file-table">
      <thead><tr>
        <th>名称</th>
        <th>类型</th>
        <th>大小</th>
        <th style="width:140px">占比</th>
      </tr></thead>
      <tbody>
        ${items.map((item) => {
          const ft = item.file_type || "other";
          const conf = fileTypeConfig[ft] || fileTypeConfig.other;
          const typeInfo = getFileTypeDesc(ft);
          return `
          <tr class="${item.is_dir ? "dir" : ""} ${item.is_hidden ? "hidden-file" : ""}"
              ${item.is_dir ? `onclick="browsePath('${escAttr(item.path)}')"` : ""}
              title="${item.is_dir ? "点击进入目录" : typeInfo}">
            <td>
              <span class="file-icon">${item.is_dir ? "📁" : "📄"}</span>
              ${esc(item.name)}
            </td>
            <td><span class="file-type-badge ft-${ft}">${conf.label}</span></td>
            <td>${item.size_str}</td>
            <td class="size-bar-cell">
              <span class="size-bar-inline" style="width:${Math.max((item.size / maxSize) * 100, 2)}%"></span>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
  } catch { el.innerHTML = '<div class="loading">无法访问该目录</div>'; }
}

function getFileTypeDesc(type) {
  const descs = {
    documents: "办公文档和文本文件",
    images: "照片和图像文件",
    videos: "视频文件，通常占用较大空间",
    audio: "音乐和音频文件",
    archives: "压缩文件，解压后可删除原包",
    code: "程序源代码和配置文件",
    apps: "应用程序包",
    databases: "数据库文件",
    fonts: "字体文件",
    folder: "文件夹",
    other: "其他类型文件",
  };
  return descs[type] || "文件";
}

function browseParent() {
  const parent = currentPath.split("/").slice(0, -1).join("/") || "/";
  browsePath(parent);
}
function refreshBrowse() { browsePath(currentPath); }

// ========== 应用程序 ==========
async function loadApps() {
  const el = document.getElementById("app-list");
  const summary = document.getElementById("app-summary");
  el.innerHTML = '<div class="loading"><div class="spinner"></div>正在扫描应用程序...</div>';
  summary.style.display = "none";
  loadedAppDetails = {};

  try {
    const apps = await api("apps");
    const totalSize = apps.reduce((s, a) => s + a.size, 0);
    const systemApps = apps.filter((a) => a.is_system);
    const userApps = apps.filter((a) => !a.is_system);

    summary.style.display = "flex";
    summary.innerHTML = `
      <div class="summary-item">共 <strong>${apps.length}</strong> 个应用</div>
      <div class="summary-item">系统 <strong>${systemApps.length}</strong></div>
      <div class="summary-item">用户 <strong>${userApps.length}</strong></div>
      <div class="summary-item">总占用 <strong>${fmtSize(totalSize)}</strong></div>
    `;

    el.innerHTML = apps.map((app, i) => `
    <div class="app-item" id="app-${i}">
      <div class="app-item-header" onclick="toggleApp(${i}, '${escAttr(app.path)}')">
        <div class="app-icon-box ${app.is_system ? "system" : "user"}">
          ${app.is_system ? "&#9881;" : "&#9634;"}
        </div>
        <div class="app-info">
          <div class="app-name-row">
            <span class="app-name">${esc(app.name)}</span>
            ${app.version ? `<span class="app-version">v${esc(app.version)}</span>` : ""}
          </div>
          <div class="app-path">${esc(app.path)}</div>
        </div>
        <span class="app-badge ${app.is_system ? "badge-system" : "badge-user"}">${app.is_system ? "系统" : "用户"}</span>
        <div class="app-size">${app.size_str}</div>
        <span class="app-expand-icon">&#9654;</span>
      </div>
      <div class="app-detail" id="app-detail-${i}">
        <div class="app-detail-loading"><div class="spinner" style="width:20px;height:20px;border-width:2px;margin:0 auto 8px"></div>正在分析应用内部结构...</div>
      </div>
    </div>`).join("");
  } catch { el.innerHTML = '<div class="loading">扫描失败，请重试</div>'; }
}

async function toggleApp(index, appPath) {
  const item = document.getElementById(`app-${index}`);
  const detail = document.getElementById(`app-detail-${index}`);

  if (item.classList.contains("expanded")) {
    item.classList.remove("expanded");
    return;
  }

  item.classList.add("expanded");

  if (loadedAppDetails[index]) return;

  try {
    const data = await api("app-contents?path=" + encodeURIComponent(appPath));
    loadedAppDetails[index] = data;

    if (data.error) {
      detail.innerHTML = `<div class="app-detail-loading">${esc(data.error)}</div>`;
      return;
    }

    // Category summary bar
    let summaryHtml = '';
    if (data.category_summary) {
      const cats = Object.entries(data.category_summary).sort((a, b) => b[1].size - a[1].size);
      summaryHtml = `<div class="app-cat-summary">${cats.map(([key, cat]) =>
        `<span class="app-cat-tag cat-${cat.color}">${esc(cat.label)} ${cat.percent}%</span>`
      ).join("")}</div>`;
    }

    let html = summaryHtml + '<div class="app-content-list">';
    data.contents.forEach((c) => {
      const catColor = getCatColor(c.category);
      html += `
      <div class="app-content-item">
        <span class="app-content-tag cat-${catColor}">${esc(c.category_label)}</span>
        <div class="app-content-name">
          ${esc(c.name)}
          <div class="app-content-desc">${esc(c.description)}</div>
        </div>
        <div class="app-content-bar">
          <div class="app-content-bar-fill bar-${catColor}" style="width:${c.percent}%"></div>
        </div>
        <span class="app-content-percent">${c.percent}%</span>
        <span class="app-content-size">${c.size_str}</span>
      </div>`;
    });
    html += "</div>";

    if (data.cache_items && data.cache_items.length > 0) {
      html += `
      <div class="app-cache-actions">
        <span class="app-cache-info">可清理的缓存/临时文件: <strong>${data.cache_total_str}</strong></span>
        <button class="btn btn-sm btn-danger" onclick="cleanAppCache([${data.cache_items.map(c => "'" + escAttr(c.path) + "'").join(",")}]); event.stopPropagation();">清理缓存</button>
      </div>`;
    }

    detail.innerHTML = html;
  } catch {
    detail.innerHTML = '<div class="app-detail-loading">加载失败</div>';
  }
}

function getCatColor(category) {
  const map = {
    executable: "exec", framework: "fw", resource: "res",
    plugin: "plug", signature: "sig", config: "cfg",
    data: "data", cache: "cache", other: "other",
  };
  return map[category] || "other";
}

async function cleanAppCache(paths) {
  if (!paths.length) return;
  const totalPaths = paths.length;
  if (!confirm(`确定要清理这 ${totalPaths} 个缓存项吗？`)) return;

  try {
    const result = await api("delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths }),
    });
    showToast(`已清理，释放 ${result.total_freed_str} 空间`, "success");
    loadedAppDetails = {};
    loadApps();
  } catch {
    showToast("清理失败", "error");
  }
}

// ========== 缓存管理 ==========
async function loadCaches() {
  const el = document.getElementById("cache-list");
  const summary = document.getElementById("cache-summary");
  const btnClean = document.getElementById("btn-clean");
  el.innerHTML = '<div class="loading"><div class="spinner"></div>正在扫描缓存文件...</div>';
  summary.style.display = "none";
  btnClean.style.display = "none";

  try {
    cachedCaches = await api("caches");

    const totalSize = cachedCaches.reduce((s, c) => s + c.size, 0);
    const safeSize = cachedCaches.filter((c) => c.safe_to_delete).reduce((s, c) => s + c.size, 0);

    summary.style.display = "flex";
    summary.innerHTML = `
      <div class="summary-item">发现 <strong>${cachedCaches.length}</strong> 个缓存项</div>
      <div class="summary-item">总缓存 <strong>${fmtSize(totalSize)}</strong></div>
      <div class="summary-item">可安全清理 <strong>${fmtSize(safeSize)}</strong></div>
    `;

    if (cachedCaches.some((c) => c.safe_to_delete)) {
      btnClean.style.display = "inline-flex";
      document.getElementById("cache-select-all").style.display = "flex";
      updateCacheSelectedInfo();
    }

    el.innerHTML = cachedCaches.map((c, i) => {
      const rec = c.recommendation || {};
      const recClass = rec.action === "clean" ? "rec-clean" : rec.action === "keep" ? "rec-keep" : "rec-optional";
      const recIcon = rec.action === "clean" ? "&#10003;" : rec.action === "keep" ? "&#10007;" : "&#8776;";

      return `
      <div class="cache-item ${c.safe_to_delete ? "" : "cache-unsafe"}">
        ${c.safe_to_delete
          ? `<input type="checkbox" data-index="${i}" ${rec.action === "clean" ? "checked" : ""}>`
          : `<input type="checkbox" disabled title="不建议删除">`}
        <div class="cache-info">
          <div class="cache-name">
            ${esc(c.parent || c.name)}
            <span class="cache-category">${esc(c.category)}</span>
          </div>
          <div class="cache-path" title="${escAttr(c.path)}">${esc(c.path)}</div>
          <div class="cache-desc">${esc(c.description)}</div>
          <div class="cache-recommendation ${recClass}">${recIcon} ${esc(rec.label || "")}</div>
          <div class="cache-rec-reason">${esc(rec.reason || "")}</div>
        </div>
        <div class="cache-right">
          <div class="cache-size">${c.size_str}</div>
        </div>
      </div>`;
    }).join("");
  } catch { el.innerHTML = '<div class="loading">扫描失败，请重试</div>'; }
}

function cleanSelected() {
  const cbs = document.querySelectorAll('#cache-list input[type="checkbox"]:checked:not(:disabled)');
  const paths = [];
  const items = [];
  cbs.forEach((cb) => {
    const idx = parseInt(cb.dataset.index);
    const cache = cachedCaches[idx];
    if (cache) {
      paths.push(cache.path);
      items.push(`${cache.parent || cache.name} — ${cache.size_str}`);
    }
  });
  if (!paths.length) { showToast("请至少选择一个缓存项", "error"); return; }

  pendingDeletePaths = paths;
  const total = paths.reduce((s, p) => {
    const c = cachedCaches.find((x) => x.path === p);
    return s + (c ? c.size : 0);
  }, 0);

  document.getElementById("confirm-message").textContent =
    `确定要删除以下 ${paths.length} 个缓存项吗？预计释放 ${fmtSize(total)} 空间。`;
  document.getElementById("confirm-items").innerHTML = items.map((i) => `<div>${esc(i)}</div>`).join("");
  document.getElementById("confirm-dialog").style.display = "flex";
}

function toggleAllCaches(checked) {
  const cbs = document.querySelectorAll('#cache-list input[type="checkbox"]:not(:disabled)');
  cbs.forEach((cb) => { cb.checked = checked; });
  updateCacheSelectedInfo();
}

function updateCacheSelectedInfo() {
  const cbs = document.querySelectorAll('#cache-list input[type="checkbox"]:not(:disabled)');
  const checkedCbs = document.querySelectorAll('#cache-list input[type="checkbox"]:checked:not(:disabled)');
  let totalSize = 0;
  checkedCbs.forEach((cb) => {
    const idx = parseInt(cb.dataset.index);
    if (cachedCaches[idx]) totalSize += cachedCaches[idx].size;
  });
  const infoEl = document.getElementById("cache-selected-info");
  infoEl.innerHTML = `已选 <strong>${checkedCbs.length}</strong> / ${cbs.length} 项，共 <strong>${fmtSize(totalSize)}</strong>`;

  // Sync select-all checkbox state
  const allCb = document.getElementById("cache-check-all");
  if (allCb) {
    allCb.checked = cbs.length > 0 && checkedCbs.length === cbs.length;
    allCb.indeterminate = checkedCbs.length > 0 && checkedCbs.length < cbs.length;
  }
}

// Delegate change events on cache checkboxes to update info
document.addEventListener("change", (e) => {
  if (e.target.matches('#cache-list input[type="checkbox"]')) {
    updateCacheSelectedInfo();
  }
});

function closeDialog() {
  document.getElementById("confirm-dialog").style.display = "none";
  pendingDeletePaths = [];
}

async function confirmClean() {
  const pathsToDelete = [...pendingDeletePaths];
  closeDialog();
  const el = document.getElementById("cache-list");
  el.innerHTML = '<div class="loading"><div class="spinner"></div>正在清理缓存...</div>';
  try {
    const result = await api("delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths: pathsToDelete }),
    });
    const ok = result.results.filter((r) => r.success).length;
    const fail = result.results.filter((r) => !r.success).length;
    let msg = `成功清理 ${ok} 项，释放 ${result.total_freed_str}`;
    if (fail > 0) msg += `，${fail} 项清理失败`;
    showToast(msg, fail > 0 ? "error" : "success");
    loadCaches();
  } catch { showToast("清理失败", "error"); loadCaches(); }
}

// ========== 优化建议 ==========
async function loadSuggestions() {
  const el = document.getElementById("suggestion-list");
  el.innerHTML = '<div class="loading"><div class="spinner"></div>正在进行全面分析...</div>';

  try {
    const suggestions = await api("suggestions");
    el.innerHTML = suggestions.map((s) => {
      const iconMap = {
        "!!": "icon-critical", "!": "icon-warning",
        "clean": "icon-warning", "opt": "icon-info",
        "lock": "icon-info", "app": "icon-info",
        "sys": "icon-info", "tip": "icon-info",
        "ok": "icon-success",
      };
      const iconClass = iconMap[s.icon] || "icon-info";
      const iconText = s.icon === "!!" ? "!!" : s.icon === "!" ? "!" : s.icon === "ok" ? "OK" : s.icon === "clean" ? "~" : s.icon === "lock" ? "#" : s.icon === "tip" ? "i" : "*";

      let itemsHtml = "";
      if (s.items && s.items.length) {
        itemsHtml = `<div class="suggestion-items">${s.items.map((item) => `
          <div class="suggestion-item ${item.can_clean ? "can-clean" : "no-clean"}">
            <span class="suggestion-item-icon">${item.can_clean ? "&#10003;" : "&#10007;"}</span>
            <span class="suggestion-item-text">${esc(item.text)}</span>
          </div>
        `).join("")}</div>`;
      }

      return `
      <div class="suggestion-card ${s.level}">
        <div class="suggestion-header">
          <span class="suggestion-icon ${iconClass}">${iconText}</span>
          <span class="suggestion-title">${esc(s.title)}</span>
        </div>
        <div class="suggestion-detail">${esc(s.detail)}</div>
        ${itemsHtml}
      </div>`;
    }).join("");
  } catch { el.innerHTML = '<div class="loading">分析失败，请重试</div>'; }
}

// ========== 工具函数 ==========
function esc(str) {
  if (str == null) return "";
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}
function escAttr(str) {
  return String(str).replace(/'/g, "\\'").replace(/"/g, "&quot;");
}
function fmtSize(bytes) {
  if (bytes < 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return size.toFixed(2) + " " + units[i];
}
function showToast(msg, type = "success") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast " + type;
  t.style.display = "block";
  setTimeout(() => { t.style.display = "none"; }, 4000);
}

// ========== 初始加载 ==========
loadDisks();
