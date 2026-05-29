/**
 * 作品管理（后台上传 + 水印嵌入）
 *
 * 流程：选择文件 → 填写版权信息 → 嵌入水印 → 发布到展示页
 */
(function () {
    // 获取所有 DOM 元素，缺失时抛出明确错误
    function getEl(id) {
        const el = document.getElementById(id);
        if (!el) {
            throw new Error(`页面缺少元素 #${id}，请清除浏览器缓存后刷新 (Ctrl+Shift+R)`);
        }
        return el;
    }

    const uploadZone = getEl("upload-zone");
    const fileInput = getEl("file-input");
    const watermarkInput = getEl("watermark-text");
    const btnEmbed = getEl("btn-embed");
    const btnPublish = getEl("btn-publish");
    const resultArea = getEl("result-area");
    const resultContent = getEl("result-content");
    const uploadHint = getEl("upload-hint");
    const worksContainer = getEl("works-list");

    let currentResult = null;
    let selectedFile = null;

    // --- 上传区域交互 ---
    uploadZone.addEventListener("click", () => fileInput.click());
    uploadZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadZone.classList.add("drag-over");
    });
    uploadZone.addEventListener("dragleave", () => {
        uploadZone.classList.remove("drag-over");
    });
    uploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadZone.classList.remove("drag-over");
        handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
    });

    function handleFile(file) {
        if (!file || !file.type.startsWith("image/")) {
            alert("请选择图片文件");
            return;
        }
        selectedFile = file;
        uploadHint.textContent = `已选择: ${file.name}`;
        checkEmbedReady();
    }

    watermarkInput.addEventListener("input", checkEmbedReady);
    function checkEmbedReady() {
        btnEmbed.disabled = !(selectedFile && watermarkInput.value.trim());
    }

    // --- 嵌入水印 ---
    btnEmbed.addEventListener("click", async () => {
        if (!selectedFile) return;

        btnEmbed.disabled = true;
        btnEmbed.textContent = "正在嵌入水印...";

        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("watermark", watermarkInput.value.trim());

        try {
            const resp = await fetch("/admin/api/admin/upload", {
                method: "POST",
                body: formData,
            });
            // 响应非 JSON 时给出明确提示
            const text = await resp.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch (_) {
                throw new Error("服务器返回了非JSON响应，状态码 " + resp.status + "。请检查 Flask 是否正常运行。");
            }

            resultArea.style.display = "block";
            if (data.success) {
                resultContent.innerHTML = `
                    <p>✅ 嵌入状态: <span class="status-badge success">成功</span></p>
                    <p>📊 PSNR: <strong>${data.psnr} dB</strong></p>
                    <p>🔍 水印提取验证: <strong>${data.watermark_verified || "无"}</strong></p>
                `;
                currentResult = data;
                btnPublish.style.display = "inline-block";
            } else {
                resultContent.innerHTML = `
                    <p>❌ 嵌入失败: ${escapeHtml(data.error || data.message || "未知错误")}</p>
                `;
                currentResult = null;
                btnPublish.style.display = "none";
            }
        } catch (err) {
            resultContent.innerHTML = `<p>❌ 请求失败: ${err.message}</p>`;
        } finally {
            btnEmbed.disabled = false;
            btnEmbed.textContent = "③ 开始嵌入水印";
        }
    });

    // --- 发布到展示页 ---
    btnPublish.addEventListener("click", async () => {
        if (!currentResult) return;

        btnPublish.disabled = true;
        btnPublish.textContent = "正在发布...";

        try {
            const resp = await fetch("/admin/api/admin/publish", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    work_id: currentResult.work_id,
                    watermark_text: watermarkInput.value.trim(),
                    original_name: selectedFile.name,
                    watermarked_filename: currentResult.watermarked_url.split("/").pop(),
                }),
            });
            const data = await resp.json();

            if (data.success) {
                alert("发布成功！前往作品展示页查看。");
                btnPublish.textContent = "✅ 已发布";
                btnPublish.disabled = true;
                loadWorksList();
            } else {
                alert("发布失败: " + data.message);
                btnPublish.disabled = false;
                btnPublish.textContent = "发布到展示页";
            }
        } catch (err) {
            alert("请求失败: " + err.message);
            btnPublish.disabled = false;
            btnPublish.textContent = "发布到展示页";
        }
    });

    // --- 加载已发布列表 ---
    loadWorksList();

    async function loadWorksList() {
        try {
            const resp = await fetch("/admin/api/admin/works");
            const data = await resp.json();

            if (!data.works || data.works.length === 0) {
                worksContainer.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">📭</div>
                        <p>暂无已发布作品</p>
                    </div>`;
                return;
            }

            worksContainer.innerHTML = data.works.map(w => `
                <div style="display:flex;align-items:center;gap:1rem;padding:0.75rem 0;border-bottom:1px solid #eee;">
                    <img src="${w.image}" style="width:60px;height:60px;object-fit:cover;border-radius:6px;flex-shrink:0;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(w.original_name)}</div>
                        <div style="font-size:0.8rem;color:#059669;margin-top:0.15rem;">🔏 ${escapeHtml(w.watermark)}</div>
                        <div style="font-size:0.8rem;color:#999;margin-top:0.1rem;">${w.published_at}</div>
                    </div>
                    <button class="btn-danger" onclick="deleteWork('${w.id}', this)" title="删除此作品">
                        🗑 删除
                    </button>
                </div>
            `).join("");
        } catch (err) {
            console.error("加载作品列表失败:", err);
        }
    }

    // --- 删除 ---
    window.deleteWork = async function (workId, btn) {
        if (!confirm("确定要删除该作品吗？此操作不可撤销。")) return;
        btn.disabled = true;
        btn.textContent = "删除中...";
        try {
            const resp = await fetch(`/admin/api/admin/works/${workId}`, { method: "DELETE" });
            const data = await resp.json();
            if (data.success) {
                loadWorksList();
            } else {
                alert("删除失败: " + data.message);
                btn.disabled = false;
                btn.textContent = "🗑 删除";
            }
        } catch (err) {
            alert("请求失败: " + err.message);
            btn.disabled = false;
            btn.textContent = "🗑 删除";
        }
    };

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
})();
