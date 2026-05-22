document.addEventListener("DOMContentLoaded", () => {
    // Current state variables
    let currentSelectedTaskForLogs = null;
    let logPollingInterval = null;
    let portfolioPollingInterval = null;
    let activeTab = "tab-portfolio";

    // Initialize clock
    function updateClock() {
        const timeBox = document.getElementById("system-time");
        if (timeBox) {
            const now = new Date();
            timeBox.textContent = now.toLocaleTimeString("zh-CN", { hour12: false });
        }
    }
    setInterval(updateClock, 1000);
    updateClock();

    // Tab Navigation switching
    const menuItems = document.querySelectorAll(".menu-item");
    menuItems.forEach(item => {
        item.addEventListener("click", () => {
            // Remove active from all buttons & contents
            document.querySelectorAll(".menu-item").forEach(i => i.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            
            // Add active to current
            item.classList.add("active");
            const tabId = item.getAttribute("data-tab");
            document.getElementById(tabId).classList.add("active");
            
            activeTab = tabId;
            
            // Update breadcrumb title
            const labelText = item.querySelector(".label").textContent;
            document.getElementById("current-view-title").textContent = labelText;
            
            // Handle view changes (e.g. stop polling or trigger fetches)
            onTabChanged(tabId);
        });
    });

    function onTabChanged(tabId) {
        // Clear background log pollers if we leave scheduler
        if (tabId !== "tab-scheduler") {
            clearInterval(logPollingInterval);
            logPollingInterval = null;
        }
        
        // Stop portfolio poller if we leave portfolio
        if (tabId !== "tab-portfolio") {
            clearInterval(portfolioPollingInterval);
            portfolioPollingInterval = null;
        }
        
        // Trigger page-specific loaders
        if (tabId === "tab-portfolio") {
            fetchPortfolio();
            // Start tick poller (every 5 seconds) for simulated ticks
            portfolioPollingInterval = setInterval(fetchPortfolio, 5000);
        } else if (tabId === "tab-scheduler") {
            fetchTasks();
            loadStrategyOptions();
        } else if (tabId === "tab-research") {
            fetchStrategyFiles();
        }
    }

    // ----------------- TAB: PORTFOLIO -----------------
    async function fetchPortfolio(force = false) {
        try {
            const res = await fetch("/api/portfolio");
            if (!res.ok) throw new Error("加载持仓失败");
            const data = await res.json();
            
            // Check if user is currently editing cash or table inputs
            const isEditing = document.activeElement && (
                document.activeElement.classList.contains("table-input") ||
                document.activeElement.id === "edit-initial-cash" ||
                document.activeElement.id === "edit-cash" ||
                document.activeElement.id === "edit-pnl-override"
            );
            
            // Update summary displays (always safe to overwrite)
            document.getElementById("portfolio-total").textContent = data.total_value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            document.getElementById("portfolio-cash").textContent = data.cash.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            
            // Render PnL with colors
            const pnlBox = document.getElementById("portfolio-pnl");
            pnlBox.textContent = (data.pnl >= 0 ? "+" : "") + data.pnl.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            if (data.pnl >= 0) {
                pnlBox.style.color = "var(--color-red)";
                pnlBox.className = "number text-up";
            } else {
                pnlBox.style.color = "var(--color-green)";
                pnlBox.className = "number text-down";
            }
            
            // Only update input box values and positions table if not editing, or if forced
            if (!isEditing || force) {
                const initCashInput = document.getElementById("edit-initial-cash");
                if (document.activeElement !== initCashInput || force) {
                    initCashInput.value = data.initial_cash;
                }
                const cashInput = document.getElementById("edit-cash");
                if (document.activeElement !== cashInput || force) {
                    cashInput.value = data.cash;
                }
                const pnlOverrideInput = document.getElementById("edit-pnl-override");
                if (document.activeElement !== pnlOverrideInput || force) {
                    pnlOverrideInput.value = data.pnl_override !== null ? data.pnl_override : "";
                }
                
                // Render positions rows
                const posList = document.getElementById("positions-list");
                posList.innerHTML = "";
                
                if (data.positions.length === 0) {
                    posList.innerHTML = `<tr><td colspan="8" class="loading">目前无任何场外基金持仓</td></tr>`;
                } else {
                    data.positions.forEach(pos => {
                        const pnl = pos.cost_nav > 0 ? ((pos.current_nav - pos.cost_nav) / pos.cost_nav) * 100 : 0.0;
                        const pnlClass = pnl >= 0 ? "badge-red" : "badge-green";
                        const pnlText = (pnl >= 0 ? "+" : "") + pnl.toFixed(2) + "%";
                        
                        const tr = document.createElement("tr");
                        tr.innerHTML = `
                            <td><input type="text" class="table-input pos-code" value="${pos.fund_code}"></td>
                            <td><input type="text" class="table-input pos-name" value="${pos.fund_name}"></td>
                            <td><input type="number" class="table-input pos-shares" value="${pos.shares}" step="0.01"></td>
                            <td><input type="number" class="table-input pos-cost-nav" value="${pos.cost_nav}" step="0.0001"></td>
                            <td><input type="number" class="table-input pos-current-nav" value="${pos.current_nav}" step="0.0001"></td>
                            <td><span class="cell-text font-mono" style="color: var(--color-blue); font-weight: 500;">${pos.market_value.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                            <td><span class="badge ${pnlClass}">${pnlText}</span></td>
                            <td style="text-align: center;"><button class="btn-delete-pos" style="color: var(--color-red); border: none; background: transparent; cursor: pointer; padding: 6px 10px; font-weight: 600;">删除</button></td>
                        `;
                        
                        tr.querySelector(".btn-delete-pos").addEventListener("click", () => {
                            tr.remove();
                            if (posList.children.length === 0) {
                                posList.innerHTML = `<tr><td colspan="8" class="loading">目前无任何场外基金持仓</td></tr>`;
                            }
                        });
                        
                        posList.appendChild(tr);
                    });
                }
            }
            
            // Render Transactions
            const txList = document.getElementById("transactions-list");
            txList.innerHTML = "";
            
            if (data.transactions.length === 0) {
                txList.innerHTML = `<tr><td colspan="7" class="loading">暂无历史交易流水</td></tr>`;
            } else {
                data.transactions.forEach(tx => {
                    const typeClass = tx.type === "申购" ? "badge-blue" : "badge-orange";
                    
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td style="color: var(--text-muted); font-size: 12px; height: 30px;"><span class="cell-text">${tx.time}</span></td>
                        <td style="font-family: var(--font-mono);"><span class="cell-text">${tx.fund_code}</span></td>
                        <td><span class="cell-text"><span class="badge ${typeClass}">${tx.type}</span></span></td>
                        <td style="font-weight: 500;"><span class="cell-text">${tx.amount.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                        <td><span class="cell-text">${tx.shares.toLocaleString("zh-CN")}</span></td>
                        <td><span class="cell-text">${tx.fee.toFixed(2)}</span></td>
                        <td><span class="cell-text"><span class="badge badge-green">${tx.status}</span></span></td>
                    `;
                    txList.appendChild(tr);
                });
            }
        } catch (err) {
            console.error("加载组合数据错误: ", err);
        }
    }

    async function savePortfolioData() {
        const initialCash = parseFloat(document.getElementById("edit-initial-cash").value) || 0.0;
        const cash = parseFloat(document.getElementById("edit-cash").value) || 0.0;
        const pnlOverrideVal = document.getElementById("edit-pnl-override").value;
        const pnlOverride = pnlOverrideVal.trim() === "" ? null : parseFloat(pnlOverrideVal);
        
        // Collect positions
        const positionRows = document.querySelectorAll("#positions-list tr");
        const positions = [];
        
        positionRows.forEach(row => {
            if (row.querySelector(".loading") || row.cells.length < 8) {
                return;
            }
            
            const code = row.querySelector(".pos-code").value.trim();
            const name = row.querySelector(".pos-name").value.trim();
            const shares = parseFloat(row.querySelector(".pos-shares").value) || 0.0;
            const costNav = parseFloat(row.querySelector(".pos-cost-nav").value) || 0.0;
            const currentNav = parseFloat(row.querySelector(".pos-current-nav").value) || 0.0;
            
            if (code !== "") {
                positions.push({
                    fund_code: code,
                    fund_name: name,
                    shares: shares,
                    cost_nav: costNav,
                    current_nav: currentNav
                });
            }
        });
        
        try {
            const res = await fetch("/api/portfolio/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    initial_cash: initialCash,
                    cash: cash,
                    pnl_override: pnlOverride,
                    positions: positions
                })
            });
            
            if (!res.ok) throw new Error("保存资产信息失败");
            
            alert("保存资产持仓信息成功！");
            fetchPortfolio(true); // force reload to redraw the calculated values
        } catch (err) {
            alert(err.message);
        }
    }

    async function refreshNavs() {
        const btn = document.getElementById("btn-refresh-navs");
        btn.disabled = true;
        btn.textContent = "更新中...";
        
        try {
            const res = await fetch("/api/portfolio/refresh_navs", { method: "POST" });
            if (!res.ok) throw new Error("刷新净值失败");
            
            alert("实时净值更新成功！");
            await fetchPortfolio(true); // force reload to draw new net assets
        } catch (err) {
            alert(err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = "更新净值";
        }
    }

    function addPositionRow() {
        const posList = document.getElementById("positions-list");
        const emptyRow = posList.querySelector("td.loading");
        if (emptyRow) {
            posList.innerHTML = "";
        }
        
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><input type="text" class="table-input pos-code" value="" placeholder="如: 000001.OF"></td>
            <td><input type="text" class="table-input pos-name" value="" placeholder="如: 华夏成长混合"></td>
            <td><input type="number" class="table-input pos-shares" value="0.00" step="0.01"></td>
            <td><input type="number" class="table-input pos-cost-nav" value="1.0000" step="0.0001"></td>
            <td><input type="number" class="table-input pos-current-nav" value="1.0000" step="0.0001"></td>
            <td><span class="cell-text font-mono" style="color: var(--text-muted); font-style: italic;">保存后计算</span></td>
            <td><span class="badge badge-blue">0.00%</span></td>
            <td style="text-align: center;"><button class="btn-delete-pos" style="color: var(--color-red); border: none; background: transparent; cursor: pointer; padding: 6px 10px; font-weight: 600;">删除</button></td>
        `;
        
        tr.querySelector(".btn-delete-pos").addEventListener("click", () => {
            tr.remove();
            if (posList.children.length === 0) {
                posList.innerHTML = `<tr><td colspan="8" class="loading">目前无任何场外基金持仓</td></tr>`;
            }
        });
        
        posList.appendChild(tr);
        tr.querySelector(".pos-code").focus();
    }

    // Register button event listeners
    document.getElementById("btn-refresh-portfolio").addEventListener("click", () => fetchPortfolio(true));
    document.getElementById("btn-save-cash-info").addEventListener("click", savePortfolioData);
    document.getElementById("btn-save-positions").addEventListener("click", savePortfolioData);
    document.getElementById("btn-refresh-navs").addEventListener("click", refreshNavs);
    document.getElementById("btn-add-position").addEventListener("click", addPositionRow);


    // ----------------- TAB: SCHEDULER -----------------
    async function loadStrategyOptions() {
        try {
            const res = await fetch("/api/strategies");
            const data = await res.json();
            const select = document.getElementById("task-strategy");
            
            // Clear but keep first option
            select.innerHTML = '<option value="">请选择策略文件...</option>';
            data.strategies.forEach(file => {
                const opt = document.createElement("option");
                opt.value = file;
                opt.textContent = file;
                select.appendChild(opt);
            });
        } catch (err) {
            console.error("加载下拉策略文件失败: ", err);
        }
    }

    async function fetchTasks() {
        try {
            const res = await fetch("/api/tasks");
            const data = await res.json();
            const tasksList = document.getElementById("tasks-list");
            tasksList.innerHTML = "";
            
            if (data.length === 0) {
                tasksList.innerHTML = `<tr><td colspan="8" class="loading">目前无任何调度任务，请在左侧新建</td></tr>`;
                return;
            }
            
            data.forEach(task => {
                const tr = document.createElement("tr");
                
                // Enabled state toggle switch
                const checked = task.enabled ? "checked" : "";
                const switchHtml = `
                    <label class="switch">
                        <input type="checkbox" class="toggle-task-btn" data-name="${task.name}" ${checked}>
                        <span class="slider"></span>
                    </label>
                `;
                
                // Status mapping
                let statusBadge = "";
                if (task.status === "running") {
                    statusBadge = '<span class="badge badge-green"><span class="dot live" style="display:inline-block; margin-right:4px;"></span>执行中</span>';
                } else if (task.status === "idle") {
                    statusBadge = '<span class="badge badge-blue">空闲</span>';
                } else {
                    statusBadge = '<span class="badge badge-red">异常</span>';
                }
                
                tr.innerHTML = `
                    <td style="font-weight:600; color:#fff;">${task.name}</td>
                    <td style="font-family: var(--font-mono); font-size:12px;">${task.strategy_file}</td>
                    <td>${task.schedule_value}秒</td>
                    <td>${switchHtml}</td>
                    <td>${statusBadge}</td>
                    <td style="font-size:11px; color:var(--text-muted);">${task.last_run || "-"}</td>
                    <td style="font-size:11px; color:var(--text-muted);">${task.next_run || "-"}</td>
                    <td>
                        <div style="display:flex; gap:6px;">
                            <button class="btn btn-secondary btn-sm btn-logs" data-name="${task.name}">日志</button>
                            <button class="btn btn-primary btn-sm btn-run" data-name="${task.name}">立即运行</button>
                            <button class="btn btn-secondary btn-sm btn-del" style="color:var(--color-red); border-color:rgba(239,68,68,0.2);" data-name="${task.name}">删除</button>
                        </div>
                    </td>
                `;
                tasksList.appendChild(tr);
            });
            
            // Attach button action handlers
            document.querySelectorAll(".toggle-task-btn").forEach(sw => {
                sw.addEventListener("change", async (e) => {
                    const name = e.target.getAttribute("data-name");
                    await toggleTask(name);
                });
            });
            
            document.querySelectorAll(".btn-logs").forEach(btn => {
                btn.addEventListener("click", () => {
                    const name = btn.getAttribute("data-name");
                    selectTaskForLogs(name);
                });
            });
            
            document.querySelectorAll(".btn-run").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const name = btn.getAttribute("data-name");
                    btn.disabled = true;
                    await runTaskImmediately(name);
                    btn.disabled = false;
                });
            });
            
            document.querySelectorAll(".btn-del").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const name = btn.getAttribute("data-name");
                    if (confirm(`确认删除策略任务 '${name}' 吗?`)) {
                        await deleteTask(name);
                    }
                });
            });
        } catch (err) {
            console.error("加载任务列表失败: ", err);
        }
    }

    async function toggleTask(name) {
        try {
            const res = await fetch(`/api/tasks/${name}/toggle`, { method: "POST" });
            if (!res.ok) throw new Error("切换状态失败");
            fetchTasks();
        } catch (err) {
            alert(err.message);
        }
    }

    async function runTaskImmediately(name) {
        try {
            const res = await fetch(`/api/tasks/${name}/run`, { method: "POST" });
            if (!res.ok) throw new Error("手动触发失败");
            alert(`已成功发送策略运行信号，正在触发 '${name}'...`);
            fetchTasks();
            selectTaskForLogs(name);
        } catch (err) {
            alert(err.message);
        }
    }

    async function deleteTask(name) {
        try {
            const res = await fetch(`/api/tasks/${name}`, { method: "DELETE" });
            if (!res.ok) throw new Error("删除失败");
            fetchTasks();
            if (currentSelectedTaskForLogs === name) {
                currentSelectedTaskForLogs = null;
                document.getElementById("log-header-title").textContent = "任务运行控制台日志";
                document.getElementById("log-console-box").textContent = "--- 选中任务已被删除 ---";
                document.getElementById("btn-refresh-logs").disabled = true;
                clearInterval(logPollingInterval);
            }
        } catch (err) {
            alert(err.message);
        }
    }

    // Task Create submit handler
    document.getElementById("form-create-task").addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("task-name").value.trim();
        const strategy_file = document.getElementById("task-strategy").value;
        const schedule_value = parseInt(document.getElementById("task-interval").value);
        
        if (!name || !strategy_file || !schedule_value) return;
        
        try {
            const res = await fetch("/api/tasks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, strategy_file, schedule_value })
            });
            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "创建任务失败");
            }
            
            // Success reset form
            document.getElementById("task-name").value = "";
            document.getElementById("task-strategy").value = "";
            document.getElementById("task-interval").value = "300";
            
            fetchTasks();
        } catch (err) {
            alert(err.message);
        }
    });

    // Logging viewing & polling
    function selectTaskForLogs(name) {
        currentSelectedTaskForLogs = name;
        document.getElementById("log-header-title").textContent = `任务控制台日志: ${name} (实时刷新中)`;
        document.getElementById("btn-refresh-logs").disabled = false;
        
        // Fetch logs immediately
        fetchLogs(name);
        
        // Setup live polling (every 2 seconds)
        clearInterval(logPollingInterval);
        logPollingInterval = setInterval(() => {
            fetchLogs(name);
            // Also refresh task list status to check if finished
            fetchTasks();
        }, 2000);
    }

    async function fetchLogs(name) {
        try {
            const res = await fetch(`/api/tasks/${name}/logs`);
            const data = await res.json();
            const logBox = document.getElementById("log-console-box");
            
            // Preserve scroll height if user is looking at top, else scroll to bottom
            const isScrolledToBottom = logBox.scrollHeight - logBox.clientHeight <= logBox.scrollTop + 40;
            logBox.textContent = data.logs;
            
            if (isScrolledToBottom) {
                logBox.scrollTop = logBox.scrollHeight;
            }
        } catch (err) {
            document.getElementById("log-console-box").textContent = "拉取日志数据出错: " + err.message;
        }
    }

    document.getElementById("btn-refresh-logs").addEventListener("click", () => {
        if (currentSelectedTaskForLogs) {
            fetchLogs(currentSelectedTaskForLogs);
        }
    });


    // ----------------- TAB: MODEL RESEARCH -----------------
    let currentSelectedFile = null;

    async function fetchStrategyFiles() {
        try {
            const res = await fetch("/api/strategies");
            const data = await res.json();
            const list = document.getElementById("strategy-file-list");
            list.innerHTML = "";
            
            data.strategies.forEach(file => {
                const li = document.createElement("li");
                li.innerHTML = `<span class="fn">${file}</span>`;
                li.setAttribute("data-filename", file);
                
                if (currentSelectedFile === file) {
                    li.classList.add("active");
                }
                
                li.addEventListener("click", () => {
                    selectStrategyFile(file);
                });
                
                list.appendChild(li);
            });
        } catch (err) {
            console.error("无法加载文件列表: ", err);
        }
    }

    async function selectStrategyFile(filename) {
        currentSelectedFile = filename;
        document.querySelectorAll("#strategy-file-list li").forEach(li => {
            if (li.getAttribute("data-filename") === filename) {
                li.classList.add("active");
            } else {
                li.classList.remove("active");
            }
        });
        
        try {
            const res = await fetch(`/api/strategies/${filename}`);
            if (!res.ok) throw new Error("加载文件失败");
            const data = await res.json();
            
            document.getElementById("code-editor").value = data.code;
            document.getElementById("editor-filename").textContent = filename;
            document.getElementById("btn-save-strategy").disabled = false;
        } catch (err) {
            alert(err.message);
        }
    }

    // Save changes
    document.getElementById("btn-save-strategy").addEventListener("click", async () => {
        if (!currentSelectedFile) return;
        const code = document.getElementById("code-editor").value;
        const btn = document.getElementById("btn-save-strategy");
        
        btn.textContent = "正在保存...";
        btn.disabled = true;
        
        try {
            const res = await fetch(`/api/strategies/${currentSelectedFile}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });
            if (!res.ok) throw new Error("保存代码失败");
            
            // Brief success state representation
            btn.textContent = "保存成功";
            setTimeout(() => {
                btn.textContent = "保存修改";
                btn.disabled = false;
            }, 1500);
        } catch (err) {
            alert(err.message);
            btn.textContent = "保存修改";
            btn.disabled = false;
        }
    });

    // Create new strategy file
    document.getElementById("btn-new-strategy").addEventListener("click", async () => {
        const name = prompt("请输入策略文件名 (包含 .py 后缀):", "new_strategy.py");
        if (!name) return;
        
        const starterTemplate = `import os
import sys
from datetime import datetime

# 引入 cjquant 并执行场外交易或分析
print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 新策略开始运行...")
print("核心量化计算完毕。")
`;

        try {
            const res = await fetch("/api/strategies/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: name, code: starterTemplate })
            });
            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "创建文件失败");
            }
            
            const data = await res.json();
            alert(`策略文件 '${data.filename}' 创建成功!`);
            
            await fetchStrategyFiles();
            // Automatically select new file
            selectStrategyFile(data.filename);
        } catch (err) {
            alert(err.message);
        }
    });


    // ----------------- TAB: ANALYTICS TOOLS -----------------
    
    // Optimizer Form
    document.getElementById("form-optimize").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        // Collect checked funds
        const checkboxes = document.querySelectorAll("input[name='opt-funds']:checked");
        const funds = Array.from(checkboxes).map(cb => cb.value);
        const method = document.getElementById("opt-method").value;
        
        if (funds.length < 2) {
            alert("请选择至少两个基金标的进行优化!");
            return;
        }
        
        try {
            const res = await fetch("/api/analytics/optimize", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ funds, method })
            });
            
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "计算优化权重失败");
            }
            
            const data = await res.json();
            
            // Draw result table
            const resultsDiv = document.getElementById("optimization-results");
            const tbody = document.getElementById("opt-results-body");
            tbody.innerHTML = "";
            
            data.weights.forEach(item => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td style="font-family: var(--font-mono);">${item.fund}</td>
                    <td style="font-weight: 600; color: var(--color-blue);">${(item.weight * 100).toFixed(2)}%</td>
                `;
                tbody.appendChild(tr);
            });
            
            resultsDiv.classList.remove("hidden");
        } catch (err) {
            alert(err.message);
        }
    });

    // Look-Through Form
    document.getElementById("form-look-through").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const w1 = parseFloat(document.getElementById("lt-w1").value);
        const w2 = parseFloat(document.getElementById("lt-w2").value);
        const w3 = parseFloat(document.getElementById("lt-w3").value);
        
        const sum = w1 + w2 + w3;
        if (Math.abs(sum - 1.0) > 0.0001) {
            alert(`配置权重加总不等于 100% (当前为: ${(sum*100).toFixed(1)}%)，请重新分配！`);
            return;
        }
        
        const weights = {
            "000001.OF": w1,
            "000002.OF": w2,
            "000003.OF": w3
        };
        
        try {
            const res = await fetch("/api/analytics/look_through", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ weights })
            });
            
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "穿透分析失败");
            }
            
            const data = await res.json();
            const resultsDiv = document.getElementById("look-through-results");
            
            // Draw Industry Bars
            const indContainer = document.getElementById("lt-industry-bars");
            indContainer.innerHTML = "";
            Object.entries(data.industry).sort((a,b) => b[1] - a[1]).forEach(([ind, exp]) => {
                const pct = (exp * 100).toFixed(2) + "%";
                const row = document.createElement("div");
                row.className = "bar-row";
                row.innerHTML = `
                    <div class="bar-label"><span>${ind}</span><span>${pct}</span></div>
                    <div class="bar-bg"><div class="bar-fill" style="width: 0%;"></div></div>
                `;
                indContainer.appendChild(row);
                // Trigger animation
                setTimeout(() => {
                    row.querySelector(".bar-fill").style.width = pct;
                }, 50);
            });
            
            // Draw Style Bars
            const styleContainer = document.getElementById("lt-style-bars");
            styleContainer.innerHTML = "";
            Object.entries(data.style).sort((a,b) => b[1] - a[1]).forEach(([style, exp]) => {
                const pct = (exp * 100).toFixed(2) + "%";
                const row = document.createElement("div");
                row.className = "bar-row";
                row.innerHTML = `
                    <div class="bar-label"><span>${style}风格</span><span>${pct}</span></div>
                    <div class="bar-bg"><div class="bar-fill" style="background-color: var(--color-orange); width: 0%;"></div></div>
                `;
                styleContainer.appendChild(row);
                // Trigger animation
                setTimeout(() => {
                    row.querySelector(".bar-fill").style.width = pct;
                }, 50);
            });
            
            resultsDiv.classList.remove("hidden");
        } catch (err) {
            alert(err.message);
        }
    });

    // ----------------- TAB: FOF BACKTESTING -----------------
    
    // SVG Chart Plotter
    function drawBacktestChart(dailyStats) {
        const svg = document.getElementById("backtest-svg");
        if (!svg) return;
        
        // Clear previous elements
        svg.innerHTML = "";
        
        if (!dailyStats || dailyStats.length === 0) {
            svg.innerHTML = `<text x="50%" y="50%" fill="var(--text-muted)" font-size="12" text-anchor="middle" id="svg-placeholder-text">暂无数据，请运行回测</text>`;
            return;
        }
        
        // SVG Dimensions
        const svgWidth = 800;
        const svgHeight = 320;
        svg.setAttribute("viewBox", `0 0 ${svgWidth} ${svgHeight}`);
        
        const margin = { top: 25, right: 30, bottom: 40, left: 60 };
        const chartWidth = svgWidth - margin.left - margin.right;
        const chartHeight = svgHeight - margin.top - margin.bottom;
        
        // Find min and max returns
        const returns = dailyStats.map(s => s.return);
        let minRet = Math.min(...returns);
        let maxRet = Math.max(...returns);
        
        // Add small padding to min/max
        const retRange = maxRet - minRet;
        if (retRange === 0) {
            minRet -= 0.05;
            maxRet += 0.05;
        } else {
            minRet -= retRange * 0.1;
            maxRet += retRange * 0.1;
        }
        
        // Ensure we see 0.0 line if possible
        if (minRet > 0) minRet = 0;
        if (maxRet < 0) maxRet = 0;
        
        // Scales
        const getX = (index) => margin.left + (index / (dailyStats.length - 1)) * chartWidth;
        const getY = (val) => margin.top + chartHeight - ((val - minRet) / (maxRet - minRet)) * chartHeight;
        
        // Draw background grid lines (horizontal)
        const yTicks = 6;
        for (let i = 0; i <= yTicks; i++) {
            const val = minRet + (i / yTicks) * (maxRet - minRet);
            const y = getY(val);
            
            // Grid line
            const gridLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
            gridLine.setAttribute("x1", margin.left);
            gridLine.setAttribute("y1", y);
            gridLine.setAttribute("x2", margin.left + chartWidth);
            gridLine.setAttribute("y2", y);
            gridLine.setAttribute("stroke", val === 0 ? "rgba(255,255,255,0.25)" : "var(--border-color)");
            gridLine.setAttribute("stroke-width", val === 0 ? "1" : "0.5");
            if (val !== 0) {
                gridLine.setAttribute("stroke-dasharray", "2,2");
            }
            svg.appendChild(gridLine);
            
            // Y label
            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", margin.left - 8);
            text.setAttribute("y", y + 4);
            text.setAttribute("fill", val >= 0 ? "var(--color-red)" : "var(--color-green)");
            if (val === 0) text.setAttribute("fill", "var(--text-muted)");
            text.setAttribute("font-size", "10");
            text.setAttribute("font-family", "var(--font-mono)");
            text.setAttribute("text-anchor", "end");
            text.textContent = (val >= 0 ? "+" : "") + (val * 100).toFixed(2) + "%";
            svg.appendChild(text);
        }
        
        // Draw vertical grid lines & X labels
        const xTicksCount = Math.min(5, dailyStats.length);
        for (let i = 0; i < xTicksCount; i++) {
            const index = Math.floor((i / (xTicksCount - 1)) * (dailyStats.length - 1));
            const s = dailyStats[index];
            const x = getX(index);
            
            // Vertical grid line
            const gridLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
            gridLine.setAttribute("x1", x);
            gridLine.setAttribute("y1", margin.top);
            gridLine.setAttribute("x2", x);
            gridLine.setAttribute("y2", margin.top + chartHeight);
            gridLine.setAttribute("stroke", "var(--border-color)");
            gridLine.setAttribute("stroke-width", "0.5");
            gridLine.setAttribute("stroke-dasharray", "2,2");
            svg.appendChild(gridLine);
            
            // X label
            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", x);
            text.setAttribute("y", margin.top + chartHeight + 16);
            text.setAttribute("fill", "var(--text-muted)");
            text.setAttribute("font-size", "10");
            text.setAttribute("font-family", "var(--font-mono)");
            text.setAttribute("text-anchor", "middle");
            text.textContent = s.date;
            svg.appendChild(text);
        }
        
        // Draw performance curve line path
        let pathD = "";
        dailyStats.forEach((s, idx) => {
            const x = getX(idx);
            const y = getY(s.return);
            if (idx === 0) {
                pathD += `M ${x} ${y}`;
            } else {
                pathD += ` L ${x} ${y}`;
            }
        });
        
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", pathD);
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "var(--color-red)"); // Portfolio line is QMT Red
        path.setAttribute("stroke-width", "2");
        svg.appendChild(path);
        
        // Draw interactive vertical crosshair, circle and tooltip group
        const crosshair = document.createElementNS("http://www.w3.org/2000/svg", "line");
        crosshair.setAttribute("x1", 0);
        crosshair.setAttribute("y1", margin.top);
        crosshair.setAttribute("x2", 0);
        crosshair.setAttribute("y2", margin.top + chartHeight);
        crosshair.setAttribute("stroke", "rgba(255, 255, 255, 0.4)");
        crosshair.setAttribute("stroke-width", "1");
        crosshair.setAttribute("stroke-dasharray", "3,3");
        crosshair.style.display = "none";
        svg.appendChild(crosshair);
        
        const trackerDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        trackerDot.setAttribute("r", "4");
        trackerDot.setAttribute("fill", "#fff");
        trackerDot.setAttribute("stroke", "var(--color-red)");
        trackerDot.setAttribute("stroke-width", "2");
        trackerDot.style.display = "none";
        svg.appendChild(trackerDot);
        
        // Tooltip elements
        const tooltipGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
        tooltipGroup.style.display = "none";
        
        const tooltipRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        tooltipRect.setAttribute("fill", "rgba(10, 14, 23, 0.95)");
        tooltipRect.setAttribute("stroke", "var(--border-color)");
        tooltipRect.setAttribute("stroke-width", "1");
        tooltipRect.setAttribute("width", "150");
        tooltipRect.setAttribute("height", "55");
        tooltipGroup.appendChild(tooltipRect);
        
        const tooltipTextDate = document.createElementNS("http://www.w3.org/2000/svg", "text");
        tooltipTextDate.setAttribute("x", "8");
        tooltipTextDate.setAttribute("y", "16");
        tooltipTextDate.setAttribute("fill", "var(--text-muted)");
        tooltipTextDate.setAttribute("font-size", "10");
        tooltipGroup.appendChild(tooltipTextDate);
        
        const tooltipTextRet = document.createElementNS("http://www.w3.org/2000/svg", "text");
        tooltipTextRet.setAttribute("x", "8");
        tooltipTextRet.setAttribute("y", "32");
        tooltipTextRet.setAttribute("fill", "#fff");
        tooltipTextRet.setAttribute("font-size", "11");
        tooltipTextRet.setAttribute("font-weight", "600");
        tooltipGroup.appendChild(tooltipTextRet);
        
        const tooltipTextAssets = document.createElementNS("http://www.w3.org/2000/svg", "text");
        tooltipTextAssets.setAttribute("x", "8");
        tooltipTextAssets.setAttribute("y", "46");
        tooltipTextAssets.setAttribute("fill", "var(--color-blue)");
        tooltipTextAssets.setAttribute("font-size", "10");
        tooltipTextAssets.setAttribute("font-family", "var(--font-mono)");
        tooltipGroup.appendChild(tooltipTextAssets);
        
        svg.appendChild(tooltipGroup);
        
        // Invisible overlay for tracking mouse
        const overlay = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        overlay.setAttribute("x", margin.left);
        overlay.setAttribute("y", margin.top);
        overlay.setAttribute("width", chartWidth);
        overlay.setAttribute("height", chartHeight);
        overlay.setAttribute("fill", "transparent");
        overlay.style.cursor = "crosshair";
        svg.appendChild(overlay);
        
        overlay.addEventListener("mousemove", (e) => {
            const rect = svg.getBoundingClientRect();
            const mouseX = ((e.clientX - rect.left) / rect.width) * svgWidth;
            
            const relativeX = mouseX - margin.left;
            const percent = Math.min(Math.max(relativeX / chartWidth, 0), 1);
            const index = Math.round(percent * (dailyStats.length - 1));
            const dataPoint = dailyStats[index];
            if (!dataPoint) return;
            
            const ptX = getX(index);
            const ptY = getY(dataPoint.return);
            
            // Update crosshair
            crosshair.setAttribute("x1", ptX);
            crosshair.setAttribute("x2", ptX);
            crosshair.style.display = "block";
            
            // Update dot
            trackerDot.setAttribute("cx", ptX);
            trackerDot.setAttribute("cy", ptY);
            trackerDot.style.display = "block";
            
            // Update Tooltip
            tooltipTextDate.textContent = `日期: ${dataPoint.date}`;
            
            const retVal = dataPoint.return;
            tooltipTextRet.textContent = `收益: ${(retVal * 100).toFixed(2)}%`;
            tooltipTextRet.setAttribute("fill", retVal >= 0 ? "var(--color-red)" : "var(--color-green)");
            
            tooltipTextAssets.textContent = `资产: ${dataPoint.total_assets.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`;
            
            // Tooltip position
            let tooltipX = ptX + 15;
            let tooltipY = ptY - 20;
            
            if (tooltipX + 150 > margin.left + chartWidth) {
                tooltipX = ptX - 165;
            }
            if (tooltipY + 55 > margin.top + chartHeight) {
                tooltipY = margin.top + chartHeight - 55;
            }
            if (tooltipY < margin.top) {
                tooltipY = margin.top;
            }
            
            tooltipGroup.setAttribute("transform", `translate(${tooltipX}, ${tooltipY})`);
            tooltipGroup.style.display = "block";
        });
        
        overlay.addEventListener("mouseleave", () => {
            crosshair.style.display = "none";
            trackerDot.style.display = "none";
            tooltipGroup.style.display = "none";
        });
    }

    // Submit backtest request
    document.getElementById("form-backtest").addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const btn = document.getElementById("btn-run-backtest");
        btn.disabled = true;
        btn.textContent = "回测运行中...";
        
        const fundsRaw = document.getElementById("backtest-funds").value;
        const funds = fundsRaw.split(",").map(f => f.trim()).filter(f => f !== "");
        const initialCash = parseFloat(document.getElementById("backtest-initial-cash").value) || 0;
        const startDate = document.getElementById("backtest-start-date").value;
        const endDate = document.getElementById("backtest-end-date").value;
        const rebalanceFreq = document.getElementById("backtest-rebalance-freq").value;
        
        if (funds.length === 0) {
            alert("请选择至少一个基金标的！");
            btn.disabled = false;
            btn.textContent = "运行回测模拟";
            return;
        }
        
        try {
            const res = await fetch("/api/analytics/backtest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    funds: funds,
                    start_date: startDate,
                    end_date: endDate,
                    initial_cash: initialCash,
                    rebalance_freq: rebalanceFreq
                })
            });
            
            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "后端计算回测失败");
            }
            
            const data = await res.json();
            
            // 1. Render Summary Stats
            const summary = data.summary;
            
            const trSpan = document.getElementById("bt-stat-total-return");
            trSpan.textContent = (summary.total_return >= 0 ? "+" : "") + (summary.total_return * 100).toFixed(2) + "%";
            trSpan.className = "value font-mono " + (summary.total_return >= 0 ? "text-up" : "text-down");
            
            const arSpan = document.getElementById("bt-stat-annualized-return");
            arSpan.textContent = (summary.annualized_return >= 0 ? "+" : "") + (summary.annualized_return * 100).toFixed(2) + "%";
            arSpan.className = "value font-mono " + (summary.annualized_return >= 0 ? "text-up" : "text-down");
            
            const mdSpan = document.getElementById("bt-stat-max-drawdown");
            mdSpan.textContent = (summary.max_drawdown * 100).toFixed(2) + "%";
            mdSpan.className = "value font-mono text-down"; // Drawdown is always negative/loss
            
            const srSpan = document.getElementById("bt-stat-sharpe-ratio");
            srSpan.textContent = summary.sharpe_ratio.toFixed(2);
            srSpan.className = "value font-mono " + (summary.sharpe_ratio >= 1.0 ? "text-up" : "text-flat");
            
            document.getElementById("bt-stat-final-assets").textContent = summary.final_assets.toLocaleString("zh-CN", { minimumFractionDigits: 2 });
            
            // 2. Render SVG chart
            drawBacktestChart(data.daily_stats);
            
            // 3. Render Daily Ledger Table
            const dailyList = document.getElementById("backtest-daily-list");
            dailyList.innerHTML = "";
            
            if (data.daily_stats.length === 0) {
                dailyList.innerHTML = `<tr><td colspan="6" class="loading">暂无回测明细数据</td></tr>`;
            } else {
                data.daily_stats.forEach(s => {
                    const tr = document.createElement("tr");
                    const retClass = s.return >= 0 ? "text-up" : "text-down";
                    const retText = (s.return >= 0 ? "+" : "") + (s.return * 100).toFixed(2) + "%";
                    
                    tr.innerHTML = `
                        <td style="color: var(--text-muted); font-size: 12px; height: 30px;"><span class="cell-text">${s.date}</span></td>
                        <td style="font-family: var(--font-mono);"><span class="cell-text">${s.available_cash.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                        <td style="font-family: var(--font-mono);"><span class="cell-text">${s.transit_cash.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                        <td style="font-family: var(--font-mono);"><span class="cell-text">${s.market_value.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                        <td style="font-family: var(--font-mono); font-weight: 500;"><span class="cell-text text-blue">${s.total_assets.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                        <td><span class="cell-text ${retClass}" style="font-weight: 600;">${retText}</span></td>
                    `;
                    dailyList.appendChild(tr);
                });
            }
            
            // 4. Render Trade History Table
            const tradeList = document.getElementById("backtest-trade-list");
            tradeList.innerHTML = "";
            
            if (data.trades.length === 0) {
                tradeList.innerHTML = `<tr><td colspan="11" class="loading">无任何交易订单确认历史</td></tr>`;
            } else {
                data.trades.forEach(t => {
                    const tr = document.createElement("tr");
                    const dirClass = t.direction === "买入" ? "badge-red" : "badge-orange";
                    
                    tr.innerHTML = `
                        <td style="color: var(--text-muted);"><span class="cell-text">${t.trade_id}</span></td>
                        <td style="color: var(--text-muted);"><span class="cell-text">${t.order_id}</span></td>
                        <td style="font-family: var(--font-mono);"><span class="cell-text">${t.fund_code}</span></td>
                        <td><span class="cell-text"><span class="badge ${dirClass}">${t.direction}</span></span></td>
                        <td style="font-size: 11px;"><span class="cell-text">${t.submit_date}</span></td>
                        <td style="font-size: 11px;"><span class="cell-text">${t.confirm_date}</span></td>
                        <td style="font-size: 11px;"><span class="cell-text">${t.settle_date}</span></td>
                        <td style="font-family: var(--font-mono);"><span class="cell-text">${t.nav.toFixed(4)}</span></td>
                        <td style="font-family: var(--font-mono);"><span class="cell-text">${t.shares.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                        <td style="font-weight: 500;"><span class="cell-text">${t.volume.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</span></td>
                        <td><span class="cell-text">${t.fee.toFixed(2)}</span></td>
                    `;
                    tradeList.appendChild(tr);
                });
            }
            
        } catch (err) {
            alert(err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = "运行回测模拟";
        }
    });

    // ----------------- APP INITIAL LOADING -----------------
    // Start on portfolio tab
    onTabChanged("tab-portfolio");
});

