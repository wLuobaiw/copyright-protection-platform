/**
 * 水印鲁棒性测试 - 前端交互
 *
 * 流程：上传图片 → 输入原始水印 → 执行24项攻击测试 → 展示结果表格
 */
document.addEventListener("DOMContentLoaded", () => {
    const uploadZone = document.getElementById("upload-zone");
    const fileInput = document.getElementById("file-input");
    const uploadHint = document.getElementById("upload-hint");
    const stepWatermark = document.getElementById("step-watermark");
    const watermarkInput = document.getElementById("watermark-text");
    const btnTest = document.getElementById("btn-test");
    const loadingArea = document.getElementById("loading-area");
    const resultArea = document.getElementById("result-area");
    const summaryArea = document.getElementById("summary-area");
    const resultTbody = document.getElementById("result-tbody");

    let sessionId = null;
    let selectedFile = null;

    // 上传区域交互
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
        if (fileInput.files.length > 0) {
            handleFile(fileInput.files[0]);
        }
    });

    function handleFile(file) {
        if (!file) return;
        selectedFile = file;
        uploadHint.textContent = "正在上传: " + file.name;

        const formData = new FormData();
        formData.append("file", file);
        formData.append("watermark_text", "");  // 占位，后端需要

        fetch("/robustness/api/robustness/upload", {
            method: "POST",
            body: formData,
        }).then(resp => resp.json()).then(data => {
            if (data.success) {
                sessionId = data.session_id;
                uploadHint.textContent = "已上传: " + data.filename;
                uploadHint.style.color = "#4caf50";
                stepWatermark.style.display = "block";
            } else {
                uploadHint.textContent = "上传失败: " + data.message;
                uploadHint.style.color = "#f44336";
            }
        }).catch(err => {
            uploadHint.textContent = "上传失败: " + err.message;
            uploadHint.style.color = "#f44336";
        });
    }

    // 开启测试按钮状态
    watermarkInput.addEventListener("input", () => {
        btnTest.disabled = !watermarkInput.value.trim();
    });

    // 开始测试
    btnTest.addEventListener("click", async () => {
        if (!sessionId) {
            alert("请先上传图片");
            return;
        }

        btnTest.disabled = true;
        btnTest.textContent = "测试中...";
        resultArea.style.display = "none";
        loadingArea.style.display = "block";

        try {
            const resp = await fetch("/robustness/api/robustness/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessionId,
                    watermark_text: watermarkInput.value.trim(),
                }),
            });
            const data = await resp.json();

            loadingArea.style.display = "none";
            resultArea.style.display = "block";

            if (!data.success) {
                summaryArea.innerHTML = `<p style="color:#f44336;">❌ ${data.message}</p>`;
                return;
            }

            // 渲染总结
            const s = data.summary;
            const scoreColor = s.robustness_score >= 95 ? "#4caf50" :
                               s.robustness_score >= 80 ? "#2e7d32" :
                               s.robustness_score >= 50 ? "#f57c00" : "#f44336";
            summaryArea.innerHTML = `
                <div style="display:flex;gap:2rem;align-items:center;flex-wrap:wrap;">
                    <div style="background:#f5f5f5;padding:1rem 1.5rem;border-radius:8px;text-align:center;">
                        <div style="font-size:0.85rem;color:#888;">鲁棒性评分</div>
                        <div style="font-size:2.5rem;font-weight:700;color:${scoreColor};">${s.robustness_score}%</div>
                    </div>
                    <div style="background:#e8f5e9;padding:1rem 1.5rem;border-radius:8px;text-align:center;">
                        <div style="font-size:0.85rem;color:#888;">✅ 通过</div>
                        <div style="font-size:1.5rem;font-weight:700;color:#4caf50;">${s.success_count}</div>
                    </div>
                    <div style="background:#ffebee;padding:1rem 1.5rem;border-radius:8px;text-align:center;">
                        <div style="font-size:0.85rem;color:#888;">❌ 失败</div>
                        <div style="font-size:1.5rem;font-weight:700;color:#f44336;">${s.fail_count}</div>
                    </div>
                    <div style="padding:1rem 1.5rem;">
                        <div style="font-size:0.85rem;color:#888;">总测试项</div>
                        <div style="font-size:1.5rem;font-weight:700;">${s.total_tests}</div>
                    </div>
                </div>
            `;

            // 渲染结果表格
            resultTbody.innerHTML = data.results.map((r, i) => {
                const rowBg = i % 2 === 0 ? "#fafafa" : "#fff";
                const matchBadge = r.matched
                    ? '<span style="color:#4caf50;font-weight:600;">✅ 通过</span>'
                    : '<span style="color:#f44336;font-weight:600;">❌ 失败</span>';
                const extractedText = r.extracted || (r.error ? `错误: ${r.error}` : "未提取到");
                const extractedStyle = r.matched ? "color:#333;" : "color:#f44336;";
                const similarity = r.similarity != null ? (r.similarity * 100).toFixed(0) + "%" : "-";
                const matchTypeColor = r.match_type === "精确匹配" ? "#4caf50" :
                                       r.match_type === "子串匹配" ? "#2e7d32" :
                                       r.match_type === "相似匹配" ? "#f57c00" : "#999";

                return `
                    <tr style="background:${rowBg};">
                        <td style="padding:0.5rem;border-bottom:1px solid #eee;">${r.attack_type}</td>
                        <td style="padding:0.5rem;border-bottom:1px solid #eee;">${r.parameter}</td>
                        <td style="padding:0.5rem;border-bottom:1px solid #eee;${extractedStyle}max-width:300px;word-break:break-all;">${extractedText}</td>
                        <td style="padding:0.5rem;border-bottom:1px solid #eee;text-align:center;">${matchBadge}</td>
                        <td style="padding:0.5rem;border-bottom:1px solid #eee;text-align:center;color:${matchTypeColor};font-size:0.85rem;">${r.match_type}</td>
                        <td style="padding:0.5rem;border-bottom:1px solid #eee;text-align:right;">${similarity}</td>
                        <td style="padding:0.5rem;border-bottom:1px solid #eee;text-align:right;">${r.confidence}%</td>
                    </tr>
                `;
            }).join("");
        } catch (err) {
            loadingArea.style.display = "none";
            resultArea.style.display = "block";
            summaryArea.innerHTML = `<p style="color:#f44336;">❌ 测试失败: ${err.message}</p>`;
        } finally {
            btnTest.disabled = false;
            btnTest.textContent = "③ 开始鲁棒性测试";
        }
    });
});