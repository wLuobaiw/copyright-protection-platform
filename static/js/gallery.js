/**
 * 作品展示画廊
 *
 * 以网格列表展示所有已发布作品，每项显示缩略图、文件名和发布时间。
 */
document.addEventListener("DOMContentLoaded", () => {
    loadGallery();
});

async function loadGallery() {
    try {
        const resp = await fetch("/api/gallery/works");
        const data = await resp.json();
        renderGallery(data.works || []);
    } catch (err) {
        console.error("加载画廊失败:", err);
    }
}

function renderGallery(works) {
    const container = document.getElementById("gallery-container");

    // 过滤掉无效条目（缺 image 的脏数据），按发布时间降序排列
    const valid = works
        .filter(w => w && typeof w === "object" && w.image)
        .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));

    if (valid.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🖼</div>
                <p>暂无作品，请前往"作品管理"页面上传。</p>
            </div>`;
        return;
    }

    container.innerHTML = valid.map(w => `
        <div class="gallery-item">
            <img src="${w.image}" alt="${escapeHtml(w.original_name || '')}" loading="lazy">
            <div class="gallery-info">
                <div class="gallery-filename">${escapeHtml(w.original_name || '未知文件')}</div>
                <div class="gallery-time">${escapeHtml(w.published_at || '')}</div>
            </div>
        </div>
    `).join("");
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
