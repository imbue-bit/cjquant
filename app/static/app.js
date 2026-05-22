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
    async function fetchPortfolio() {
        try {
            const res = await fetch("/api/portfolio");
            if (!res.ok) throw new Error("加载持仓失败");
            const data = await res.json();
            
            // Update summary cards
            document.getElementById("portfolio-total").textContent = data.total_value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            document.getElementById("portfolio-cash").textContent = data.cash.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            
            // Render Positions
            const posList = document.getElementById("positions-list");
            posList.innerHTML = "";
            
            if (data.positions.length === 0) {
                posList.innerHTML = `<tr><td colspan="7" class="loading">目前无任何场外基金持仓</td></tr>`;
            } else {
                data.positions.forEach(pos => {
                    const pnl = ((pos.current_nav - pos.cost_nav) / pos.cost_nav) * 100;
                    const pnlClass = pnl >= 0 ? "badge-red" : "badge-green";
                    const pnlText = (pnl >= 0 ? "+" : "") + pnl.toFixed(2) + "%";
                    
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td style="font-family: var(--font-mono); font-weight: 500;">${pos.fund_code}</td>
                        <td style="font-weight: 500; color: #fff;">${pos.fund_name}</td>
                        <td>${pos.shares.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}</td>
                        <td>${pos.cost_nav.toFixed(4)}</td>
                        <td>${pos.current_nav.toFixed(4)}</td>
                        <td style="font-family: var(--font-mono); font-weight: 500; color: var(--color-blue);">${pos.market_value.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</td>
                        <td><span class="badge ${pnlClass}">${pnlText}</span></td>
                    `;
                    posList.appendChild(tr);
                });
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
                        <td style="color: var(--text-muted); font-size: 12px;">${tx.time}</td>
                        <td style="font-family: var(--font-mono);">${tx.fund_code}</td>
                        <td><span class="badge ${typeClass}">${tx.type}</span></td>
                        <td style="font-weight: 500;">${tx.amount.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</td>
                        <td>${tx.shares.toLocaleString("zh-CN")}</td>
                        <td>${tx.fee.toFixed(2)}</td>
                        <td><span class="badge badge-green">${tx.status}</span></td>
                    `;
                    txList.appendChild(tr);
                });
            }
        } catch (err) {
            console.error("加载组合数据错误: ", err);
        }
    }

    document.getElementById("btn-refresh-portfolio").addEventListener("click", fetchPortfolio);


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

    // ----------------- APP INITIAL LOADING -----------------
    // Start on portfolio tab
    onTabChanged("tab-portfolio");
});
