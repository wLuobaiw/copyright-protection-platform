/**
 * 作品展示画廊
 *
 * 仅展示最新发布的一张作品图片。
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

    // 过滤掉无效条目（缺少 image 的脏数据），只保留有效作品
    const valid = works.filter(w => w && typeof w === "object" && w.image);
    if (valid.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🖼</div>
                <p>暂无作品，请前往"作品管理"页面上传。</p>
            </div>`;
        return;
    }

    // 只展示最新发布的一张
    const latest = valid[valid.length - 1];

    container.innerHTML = `
        <div class="featured-image">
            <img src="${latest.image}" alt="${escapeHtml(latest.original_name || '')}" loading="lazy">
        </div>`;
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
