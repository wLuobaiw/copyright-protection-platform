/**
 * 作品展示画廊 - B 负责完善
 *
 * 页面加载时从 /api/gallery/works 获取作品列表并渲染。
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
    if (works.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🖼</div>
                <p>暂无作品，请前往"作品管理"页面上传。</p>
            </div>`;
        return;
    }

    container.innerHTML = works.map(w => `
        <div class="gallery-item">
            <img src="${w.image}" alt="${w.original_name}" loading="lazy">
            <div class="gallery-info">
                <div class="copyright">${escapeHtml(w.watermark)}</div>
                <div class="meta">${w.original_name}</div>
                <div class="meta">发布: ${w.published_at}</div>
            </div>
        </div>
    `).join("");
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
