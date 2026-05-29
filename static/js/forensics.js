/**
 * 侵权取证与鉴定 - C + D 负责完善
 *
 * 流程：上传嫌疑文件 → 填写元信息 → 执行鉴定 → 打包证据ZIP
 */
document.addEventListener("DOMContentLoaded", () => {
    const uploadZone = document.getElementById("forensics-upload-zone");
    const fileInput = document.getElementById("forensics-file-input");
    const uploadHint = document.getElementById("forensics-upload-hint");
    const uploadStatus = document.getElementById("upload-status");
    const stepMetadata = document.getElementById("step-metadata");
    const stepIdentify = document.getElementById("step-identify");
    const stepPackage = document.getElementById("step-package");
    const btnIdentify = document.getElementById("btn-identify");
    const btnPackage = document.getElementById("btn-package");
    const logPanel = document.getElementById("log-panel");
    const logArea = document.getElementById("log-area");
    const conclusionArea = document.getElementById("conclusion-area");
    const packageResult = document.getElementById("package-result");
    const fileList = document.getElementById("file-list");
    const packageHash = document.getElementById("package-hash");
    const btnDownload = document.getElementById("btn-download");
    const btnCopyHash = document.getElementById("btn-copy-hash");

    let sessionId = null;
    let currentConclusion = null;

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
        handleSuspectFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            handleSuspectFile(fileInput.files[0]);
        }
    });

    async function handleSuspectFile(file) {
        if (!file) return;
        uploadHint.textContent = "正在上传...";

        const formData = new FormData();
        formData.append("file", file);

        try {
            const resp = await fetch("/forensics/api/forensics/upload", {
                method: "POST",
                body: formData,
            });
            const data = await resp.json();

            if (data.success) {
                sessionId = data.session_id;
                uploadHint.textContent = `已上传: ${data.filename}`;
                uploadStatus.innerHTML = `<span class="status-badge success">✅ 上传成功</span>`;
                stepMetadata.style.display = "block";
                stepIdentify.style.display = "block";
            } else {
                uploadStatus.innerHTML = `<span class="status-badge error">❌ ${data.message}</span>`;
            }
        } catch (err) {
            uploadStatus.innerHTML = `<span class="status-badge error">❌ 上传失败: ${err.message}</span>`;
        }
    }

    // --- 第3步：执行鉴定 ---
    btnIdentify.addEventListener("click", async () => {
        if (!sessionId) {
            alert("请先上传文件");
            return;
        }

        btnIdentify.disabled = true;
        btnIdentify.textContent = "鉴定中...";
        logArea.style.display = "block";
        logPanel.innerHTML = "";
        conclusionArea.style.display = "none";
        stepPackage.style.display = "none";

        const formData = new FormData();
        formData.append("session_id", sessionId);
        formData.append("source_url", document.getElementById("source-url").value);
        formData.append("capture_time", document.getElementById("capture-time").value);
        formData.append("publisher", document.getElementById("publisher").value);
        formData.append("notes", document.getElementById("forensics-notes").value);
        formData.append("officer", document.getElementById("officer-name").value);
        formData.append("expected_watermark", document.getElementById("expected-watermark").value);

        try {
            const resp = await fetch("/forensics/api/forensics/identify", {
                method: "POST",
                body: formData,
            });
            const data = await resp.json();

            // 渲染日志
            if (data.log) {
                data.log.forEach(entry => {
                    const cls = entry.status === "fail" ? "fail" :
                                entry.status === "ok" ? "ok" : "info";
                    logPanel.innerHTML += `
                        <div class="log-entry ${cls}">
                            [${entry.timestamp}] ${entry.step}: ${entry.detail}
                        </div>`;
                });
                logPanel.scrollTop = logPanel.scrollHeight;
            }

            // 渲染结论
            if (data.conclusion) {
                currentConclusion = data.conclusion;
                conclusionArea.style.display = "block";
                conclusionArea.innerHTML = `
                    <h3 style="margin-top:1rem;">鉴定结论</h3>
                    <div class="conclusion-panel">
                        <div class="conclusion-row">
                            <span>文件SHA-256</span>
                            <span class="hash-text">${data.conclusion.file_sha256 || "N/A"}</span>
                        </div>
                        <div class="conclusion-row">
                            <span>ELA检测</span>
                            <span class="${data.conclusion.ela_result && !data.conclusion.ela_result.includes('篡改') ? 'pass' : 'fail'}">
                                ${data.conclusion.ela_result || "N/A"}
                            </span>
                        </div>
                        <div class="conclusion-row">
                            <span>水印提取</span>
                            <span>${data.conclusion.watermark_extracted || "未检测到"}</span>
                        </div>
                        <div class="conclusion-row">
                            <span>权属比对</span>
                            <span class="${data.conclusion.watermark_match ? 'pass' : 'fail'}">
                                ${data.conclusion.watermark_match ? '✅ 匹配' : '❌ 不匹配'}
                            </span>
                        </div>
                        <div class="conclusion-row">
                            <span>最终结论</span>
                            <span>${data.conclusion.final_judgment || "N/A"}</span>
                        </div>
                    </div>
                `;
            }

            // 显示第4步
            stepPackage.style.display = "block";

        } catch (err) {
            logPanel.innerHTML += `<div class="log-entry fail">鉴定失败: ${err.message}</div>`;
        } finally {
            btnIdentify.disabled = false;
            btnIdentify.textContent = "开始鉴定";
        }
    });

    // --- 第4步：打包证据 ---
    btnPackage.addEventListener("click", async () => {
        if (!sessionId) {
            alert("请先完成鉴定");
            return;
        }

        btnPackage.disabled = true;
        btnPackage.textContent = "正在打包...";

        try {
            const resp = await fetch("/forensics/api/forensics/package", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: sessionId }),
            });
            const data = await resp.json();

            if (data.success) {
                packageResult.style.display = "block";

                // 文件列表
                fileList.innerHTML = (data.files || []).map(f => `
                    <li>📄 ${f.name} <span class="hash-text">${f.sha256.substring(0, 16)}...</span></li>
                `).join("");

                // 压缩包哈希
                packageHash.textContent = data.package_sha256;

                // 下载链接
                btnDownload.href = `/forensics/api/forensics/download/${sessionId}`;
                btnDownload.download = data.package_path.split("/").pop()
                    .replace(/\\/g, "/").split("/").pop();

            } else {
                alert("打包失败: " + data.message);
            }
        } catch (err) {
            alert("打包失败: " + err.message);
        } finally {
            btnPackage.disabled = false;
            btnPackage.textContent = "生成证据压缩包";
        }
    });

    // --- 复制哈希 ---
    btnCopyHash.addEventListener("click", () => {
        const hash = packageHash.textContent;
        if (hash && navigator.clipboard) {
            navigator.clipboard.writeText(hash).then(() => {
                btnCopyHash.textContent = "✅ 已复制";
                setTimeout(() => { btnCopyHash.textContent = "📋 复制哈希值"; }, 2000);
            });
        }
    });
});
