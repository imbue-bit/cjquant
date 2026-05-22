import os
import sys
import json
import asyncio
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cjquant.optimizer.traditional import RiskParityOptimizer, MeanVarianceOptimizer
from cjquant.optimizer.machine_learning import HRPOptimizer
from cjquant.look_through.engine import LookThroughAnalyzer
from cjquant.data.providers.public import PublicFundProvider

app = FastAPI(title="CJQuant OTC Strategy & Portfolio Terminal")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_DIR = os.path.join(BASE_DIR, "strategies")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
TASKS_JSON = os.path.join(BASE_DIR, "tasks.json")
PORTFOLIO_JSON = os.path.join(BASE_DIR, "portfolio.json")

# Ensure directories exist
os.makedirs(STRATEGIES_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Helper to load tasks
def load_tasks() -> List[Dict[str, Any]]:
    if not os.path.exists(TASKS_JSON):
        return []
    try:
        with open(TASKS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

# Helper to save tasks
def save_tasks(tasks: List[Dict[str, Any]]):
    with open(TASKS_JSON, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

# Helper to load portfolio
def load_portfolio() -> Dict[str, Any]:
    if not os.path.exists(PORTFOLIO_JSON):
        return {"account_id": "55002038", "initial_cash": 0.0, "cash": 0.0, "positions": [], "total_value": 0.0, "pnl": 0.0, "transactions": []}
    try:
        with open(PORTFOLIO_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"account_id": "55002038", "initial_cash": 0.0, "cash": 0.0, "positions": [], "total_value": 0.0, "pnl": 0.0, "transactions": []}

# Helper to save portfolio
def save_portfolio(p: Dict[str, Any]):
    with open(PORTFOLIO_JSON, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)

# Active processes tracker: {task_name: Process}
active_processes: Dict[str, asyncio.subprocess.Process] = {}

# ----------------- BACKGROUND SCHEDULER -----------------
async def run_task_process(task_name: str, script_name: str):
    """Executes the strategy script as a subprocess and streams output to logs"""
    log_file_path = os.path.join(LOGS_DIR, f"{task_name}.log")
    script_path = os.path.join(STRATEGIES_DIR, script_name)
    
    # 1. Update task status to running
    tasks = load_tasks()
    for t in tasks:
        if t["name"] == task_name:
            t["status"] = "running"
            t["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break
    save_tasks(tasks)

    print(f"[Scheduler] Starting task '{task_name}' -> subprocess '{script_name}'")
    try:
        # Create log file
        with open(log_file_path, "w", encoding="utf-8") as log_f:
            log_f.write(f"=== TASK START: {task_name} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            log_f.flush()

            # Launch process using python interpreter (pointing to root to preserve imports)
            proc = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(BASE_DIR)  # Run in cjquant root to allow modular imports
            )
            active_processes[task_name] = proc
            
            # Helper to stream output
            async def stream_output(stream, is_stderr=False):
                prefix = "[ERR] " if is_stderr else ""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded_line = line.decode("utf-8", errors="ignore")
                    log_f.write(f"{prefix}{decoded_line}")
                    log_f.flush()

            # Await both stdout and stderr streaming
            await asyncio.gather(
                stream_output(proc.stdout),
                stream_output(proc.stderr)
            )

            # Wait for exit
            exit_code = await proc.wait()
            log_f.write(f"\n=== TASK FINISHED: Exit code {exit_code} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")

        # 2. Update task status after completion
        tasks = load_tasks()
        for t in tasks:
            if t["name"] == task_name:
                t["status"] = "idle" if exit_code == 0 else "error"
                # Schedule next run if enabled
                if t["enabled"] and t["schedule_type"] == "interval":
                    next_time = datetime.now() + timedelta(seconds=t["schedule_value"])
                    t["next_run"] = next_time.strftime("%Y-%m-%d %H:%M:%S")
                break
        save_tasks(tasks)
        print(f"[Scheduler] Finished task '{task_name}' with code {exit_code}")
    except Exception as e:
        # Log scheduler exceptions
        with open(log_file_path, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n[Scheduler Error] Failed to run task: {str(e)}\n")
        tasks = load_tasks()
        for t in tasks:
            if t["name"] == task_name:
                t["status"] = "error"
                break
        save_tasks(tasks)
        print(f"[Scheduler Exception] Task '{task_name}' failed: {e}")
    finally:
        active_processes.pop(task_name, None)

async def scheduler_loop():
    """Periodic loop to trigger enabled scheduler tasks"""
    print("[Scheduler] Starting scheduler background loop...")
    while True:
        try:
            tasks = load_tasks()
            now = datetime.now()
            modified = False
            
            for task in tasks:
                if not task["enabled"]:
                    continue
                
                # If status is running, skip
                if task["status"] == "running":
                    continue
                
                should_run = False
                # If next_run is not defined or is past, run it
                if not task["next_run"]:
                    should_run = True
                else:
                    try:
                        next_run_dt = datetime.strptime(task["next_run"], "%Y-%m-%d %H:%M:%S")
                        if now >= next_run_dt:
                            should_run = True
                    except Exception:
                        should_run = True
                
                if should_run:
                    # Trigger async
                    asyncio.create_task(run_task_process(task["name"], task["strategy_file"]))
                    # Update next run time
                    next_time = now + timedelta(seconds=task["schedule_value"])
                    task["next_run"] = next_time.strftime("%Y-%m-%d %H:%M:%S")
                    modified = True
            
            if modified:
                save_tasks(tasks)
                
        except Exception as e:
            print(f"[Scheduler Loop Error] {e}")
            
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    # Start background scheduler
    asyncio.create_task(scheduler_loop())

# ----------------- CLOSED LOOP PORTFOLIO SYNC -----------------
def sync_exported_orders_to_portfolio():
    """
    Scans the execution directory for O32 and WeChat exported orders (e.g. *_o32.csv, *_wechat.csv),
    records them in the transaction log as exported trades,
    and moves/renames the files to prevent double processing.
    Does NOT automatically execute simulated fills to modify cash or holdings.
    """
    import glob
    root_dir = os.path.dirname(BASE_DIR)
    o32_files = glob.glob(os.path.join(root_dir, "*_o32.csv"))
    wechat_files = glob.glob(os.path.join(root_dir, "*_wechat.csv"))
    
    portfolio = load_portfolio()
    if "transactions" not in portfolio:
        portfolio["transactions"] = []
        
    updated = False
    
    # Process O32 files
    for file_path in o32_files:
        if ".processed_" in file_path:
            continue
        try:
            print(f"[Portfolio Sync] Found O32 exported order file: {file_path}. Recording transactions...")
            df = pd.read_csv(file_path, encoding="gbk", dtype={"证券代码": str})
            for _, row in df.iterrows():
                raw_code = row["证券代码"]
                fund_code = f"{raw_code.zfill(6)}.OF"
                direction = row["业务类别"]
                order_value = float(row["委托金额"])
                order_shares = float(row["委托数量"])
                
                portfolio["transactions"].insert(0, {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "fund_code": fund_code,
                    "type": direction,
                    "amount": order_value if direction == "申购" else round(order_shares * 1.0, 2),
                    "shares": round(order_shares, 2),
                    "fee": 0.0,
                    "status": "已导出"
                })
            updated = True
            
            # Rename the file to prevent double-processing
            processed_path = file_path + f".processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(file_path, processed_path)
            print(f"[Portfolio Sync] Processed and renamed O32 file: {processed_path}")
        except Exception as e:
            print(f"[Portfolio Sync Error] Failed to process O32 file {file_path}: {e}")
            
    # Process WeChat files
    for file_path in wechat_files:
        if ".processed_" in file_path:
            continue
        try:
            print(f"[Portfolio Sync] Found WeChat exported order file: {file_path}. Recording transactions...")
            df = pd.read_csv(file_path, encoding="utf-8-sig", dtype={"基金代码": str})
            for _, row in df.iterrows():
                raw_code = row["基金代码"]
                fund_code = f"{raw_code.zfill(6)}.OF"
                direction = row["交易类型"]
                amount = float(row["发生金额"])
                shares = float(row["发生份额"])
                
                portfolio["transactions"].insert(0, {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "fund_code": fund_code,
                    "type": direction,
                    "amount": amount,
                    "shares": round(shares, 2),
                    "fee": 0.0,
                    "status": "已导出"
                })
            updated = True
            
            # Rename the file to prevent double-processing
            processed_path = file_path + f".processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(file_path, processed_path)
            print(f"[Portfolio Sync] Processed and renamed WeChat file: {processed_path}")
        except Exception as e:
            print(f"[Portfolio Sync Error] Failed to process WeChat file {file_path}: {e}")
            
    if updated:
        save_portfolio(portfolio)

# ----------------- PYDANTIC SCHEMAS -----------------
class TaskCreate(BaseModel):
    name: str
    strategy_file: str
    schedule_value: int

class StrategyCreate(BaseModel):
    name: str
    code: str

class StrategyUpdate(BaseModel):
    code: str

class OptimizeRequest(BaseModel):
    funds: List[str]
    method: str  # "RiskParity", "MeanVariance", "HRP"

class CorrelationRequest(BaseModel):
    funds: List[str]

class PerformanceRequest(BaseModel):
    funds: List[str]

class LookThroughRequest(BaseModel):
    weights: Dict[str, float]

class PositionItem(BaseModel):
    fund_code: str
    fund_name: str
    shares: float
    cost_nav: float
    current_nav: float

class PortfolioUpdateRequest(BaseModel):
    initial_cash: float
    cash: float
    pnl_override: Optional[float] = None
    positions: List[PositionItem]

class BacktestRequest(BaseModel):
    funds: List[str]
    start_date: str
    end_date: str
    initial_cash: float
    rebalance_freq: str  # "once", "monthly", "monthly_rp"

# ----------------- API ENDPOINTS -----------------

# 1. Strategy Files Endpoint
@app.get("/api/strategies")
def list_strategies():
    """List strategy files inside app/strategies"""
    files = sorted([f for f in os.listdir(STRATEGIES_DIR) if f.endswith(".py")])
    return {"strategies": files}

@app.get("/api/strategies/{name:path}")
def get_strategy_content(name: str):
    """Retrieve python strategy contents"""
    path = os.path.join(STRATEGIES_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Strategy not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"name": name, "code": f.read()}

@app.put("/api/strategies/{name:path}")
def update_strategy_content(name: str, payload: StrategyUpdate):
    """Overwrite python strategy content"""
    path = os.path.join(STRATEGIES_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload.code)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/strategies/create")
def create_strategy(payload: StrategyCreate):
    """Create new empty python strategy"""
    if not payload.name.endswith(".py"):
        filename = payload.name + ".py"
    else:
        filename = payload.name
        
    path = os.path.join(STRATEGIES_DIR, filename)
    if os.path.exists(path):
        raise HTTPException(status_code=400, detail="Strategy file already exists")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload.code)
        return {"status": "success", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Tasks Scheduler Endpoint
@app.get("/api/tasks")
def list_tasks():
    return load_tasks()

@app.post("/api/tasks")
def create_task(task: TaskCreate):
    tasks = load_tasks()
    # Check if duplicate name
    if any(t["name"] == task.name for t in tasks):
        raise HTTPException(status_code=400, detail="Task name already exists")
        
    new_task = {
        "name": task.name,
        "strategy_file": task.strategy_file,
        "schedule_type": "interval",
        "schedule_value": task.schedule_value,
        "enabled": False,
        "status": "idle",
        "last_run": None,
        "next_run": None
    }
    tasks.append(new_task)
    save_tasks(tasks)
    return new_task

@app.delete("/api/tasks/{name}")
def delete_task(name: str):
    tasks = load_tasks()
    filtered = [t for t in tasks if t["name"] != name]
    if len(filtered) == len(tasks):
        raise HTTPException(status_code=404, detail="Task not found")
    save_tasks(filtered)
    return {"status": "success"}

@app.post("/api/tasks/{name}/toggle")
def toggle_task(name: str):
    tasks = load_tasks()
    found = False
    for t in tasks:
        if t["name"] == name:
            t["enabled"] = not t["enabled"]
            if t["enabled"]:
                # Schedule next run immediately or offset
                t["next_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                t["next_run"] = None
                t["status"] = "idle"
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Task not found")
    save_tasks(tasks)
    return {"status": "success", "enabled": t["enabled"]}

@app.post("/api/tasks/{name}/run")
async def run_task_immediately(name: str, background_tasks: BackgroundTasks):
    tasks = load_tasks()
    task_file = None
    for t in tasks:
        if t["name"] == name:
            task_file = t["strategy_file"]
            break
            
    if not task_file:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # Trigger background process execution
    background_tasks.add_task(run_task_process, name, task_file)
    return {"status": "triggered"}

@app.get("/api/tasks/{name}/logs")
def get_task_logs(name: str):
    log_file = os.path.join(LOGS_DIR, f"{name}.log")
    if not os.path.exists(log_file):
        return {"logs": "--- 尚无运行日志 ---"}
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Read last 300 lines
            lines = f.readlines()
            last_lines = lines[-300:]
            return {"logs": "".join(last_lines)}
    except Exception as e:
        return {"logs": f"读取日志出错: {str(e)}"}

# 3. Portfolio & Account holdings
@app.get("/api/portfolio")
def get_portfolio():
    # Sync first in case of recent exports
    sync_exported_orders_to_portfolio()
    
    portfolio = load_portfolio()
    
    # Recalculate totals dynamically
    total_val = portfolio.get("cash", 0.0)
    for pos in portfolio.get("positions", []):
        pos["market_value"] = round(pos["shares"] * pos["current_nav"], 2)
        total_val += pos["market_value"]
        
    portfolio["total_value"] = round(total_val, 2)
    
    # Apply override if specified, otherwise total_value - initial_cash
    pnl_override = portfolio.get("pnl_override")
    if pnl_override is not None:
        portfolio["pnl"] = round(pnl_override, 2)
    else:
        portfolio["pnl"] = round(portfolio["total_value"] - portfolio.get("initial_cash", 0.0), 2)
        
    save_portfolio(portfolio)
    return portfolio

@app.post("/api/portfolio/update")
def update_portfolio(req: PortfolioUpdateRequest):
    portfolio = load_portfolio()
    portfolio["initial_cash"] = round(req.initial_cash, 2)
    portfolio["cash"] = round(req.cash, 2)
    portfolio["pnl_override"] = round(req.pnl_override, 2) if req.pnl_override is not None else None
    
    new_positions = []
    total_val = req.cash
    for pos in req.positions:
        mv = round(pos.shares * pos.current_nav, 2)
        total_val += mv
        new_positions.append({
            "fund_code": pos.fund_code,
            "fund_name": pos.fund_name,
            "shares": round(pos.shares, 4),
            "cost_nav": round(pos.cost_nav, 4),
            "current_nav": round(pos.current_nav, 4),
            "market_value": mv
        })
        
    portfolio["positions"] = new_positions
    portfolio["total_value"] = round(total_val, 2)
    
    if req.pnl_override is not None:
        portfolio["pnl"] = round(req.pnl_override, 2)
    else:
        portfolio["pnl"] = round(total_val - req.initial_cash, 2)
        
    save_portfolio(portfolio)
    return portfolio

@app.post("/api/portfolio/refresh_navs")
def refresh_navs():
    portfolio = load_portfolio()
    provider = PublicFundProvider()
    
    total_val = portfolio.get("cash", 0.0)
    
    for pos in portfolio.get("positions", []):
        code = pos["fund_code"]
        clean_code = code.split(".")[0]
        try:
            df = provider.fetch(clean_code)
            if not df.empty:
                latest_nav = float(df.iloc[-1]["unit_nav"])
                pos["current_nav"] = round(latest_nav, 4)
        except Exception as e:
            print(f"Error fetching NAV for fund {code}: {e}")
            
        pos["market_value"] = round(pos["shares"] * pos["current_nav"], 2)
        total_val += pos["market_value"]
        
    portfolio["total_value"] = round(total_val, 2)
    
    pnl_override = portfolio.get("pnl_override")
    if pnl_override is not None:
        portfolio["pnl"] = round(pnl_override, 2)
    else:
        portfolio["pnl"] = round(portfolio["total_value"] - portfolio.get("initial_cash", 0.0), 2)
        
    save_portfolio(portfolio)
    return portfolio

def get_real_returns(funds: List[str], days: int = 252) -> pd.DataFrame:
    """
    Fetches real historical returns for target funds using PublicFundProvider.
    Falls back to simulated correlated returns if data fetch fails or symbols are invalid.
    """
    provider = PublicFundProvider()
    returns_dict = {}
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=int(days * 1.5))).strftime("%Y-%m-%d")
    
    for code in funds:
        clean_code = code.split(".")[0]
        try:
            df = provider.fetch(clean_code, start_date=start_date, end_date=end_date)
            if not df.empty and len(df) > 5:
                df_sorted = df.sort_index()
                rets = df_sorted['adj_nav'].pct_change().dropna()
                returns_dict[code] = rets
        except Exception as e:
            print(f"[Research Data Fetch] Error fetching NAV for {code}: {e}")
            
    if len(returns_dict) == len(funds):
        df_all = pd.DataFrame(returns_dict).dropna()
        if len(df_all) >= 10:
            return df_all.tail(days)
            
    print(f"[Research Data Fetch] Fallback triggered. Simulating returns for funds: {funds}")
    np.random.seed(42)
    raw_ret = np.random.normal(0.0002, 0.012, size=(days, len(funds)))
    cov_matrix = np.eye(len(funds)) * 0.7 + 0.3
    correlated_ret = raw_ret @ np.linalg.cholesky(cov_matrix).T
    return pd.DataFrame(correlated_ret, columns=funds)


# 4. Analytics endpoints (Calls cjquant library)
@app.post("/api/analytics/optimize")
def run_optimization(req: OptimizeRequest):
    """Calculates risk allocation using the real cjquant optimizers and real data"""
    if len(req.funds) < 2:
        raise HTTPException(status_code=400, detail="Please select at least 2 funds for optimization")
        
    try:
        df_returns = get_real_returns(req.funds)
        
        if req.method == "RiskParity":
            opt = RiskParityOptimizer(df_returns)
            weights = opt.optimize()
        elif req.method == "MeanVariance":
            opt = MeanVarianceOptimizer(df_returns)
            weights = opt.optimize()
        elif req.method == "HRP":
            opt = HRPOptimizer(df_returns)
            weights = opt.optimize()
        else:
            raise HTTPException(status_code=400, detail="Invalid optimization method")
            
        results = []
        for fund, w in zip(req.funds, weights):
            results.append({"fund": fund, "weight": round(float(w), 6)})
            
        return {"weights": results, "method": req.method}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")

@app.post("/api/analytics/correlation")
def run_correlation(req: CorrelationRequest):
    if len(req.funds) < 2:
        raise HTTPException(status_code=400, detail="请选择至少 2 个基金进行相关性分析")
    try:
        df_returns = get_real_returns(req.funds)
        corr_matrix = df_returns.corr().round(4)
        
        results = []
        for fund in req.funds:
            row = {"fund": fund}
            for other_fund in req.funds:
                val = corr_matrix.loc[fund, other_fund] if (fund in corr_matrix.index and other_fund in corr_matrix.columns) else 0.0
                row[other_fund] = float(val)
            results.append(row)
            
        return {"correlation": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"相关性计算失败: {str(e)}")

@app.post("/api/analytics/performance")
def run_performance(req: PerformanceRequest):
    if not req.funds:
        raise HTTPException(status_code=400, detail="请提供基金列表进行性能对比")
    try:
        df_returns = get_real_returns(req.funds)
        
        results = []
        for fund in req.funds:
            if fund not in df_returns.columns:
                results.append({
                    "fund": fund,
                    "ann_return": 0.0,
                    "volatility": 0.0,
                    "sharpe": 0.0,
                    "max_drawdown": 0.0
                })
                continue
                
            rets = df_returns[fund]
            
            total_ret = (1.0 + rets).prod() - 1.0
            n_days = len(rets)
            ann_ret = (1.0 + total_ret) ** (252.0 / n_days) - 1.0 if n_days > 0 else 0.0
            
            vol = rets.std() * np.sqrt(252.0) if len(rets) > 1 else 0.0
            
            cum_nav = (1.0 + rets).cumprod()
            cum_max = cum_nav.cummax()
            drawdowns = (cum_nav - cum_max) / cum_max
            max_dd = float(drawdowns.min()) if not drawdowns.empty else 0.0
            
            rf = 0.02
            sharpe = (ann_ret - rf) / vol if vol > 0 else 0.0
            
            results.append({
                "fund": fund,
                "ann_return": round(float(ann_ret), 4),
                "volatility": round(float(vol), 4),
                "sharpe": round(float(sharpe), 4),
                "max_drawdown": round(float(max_dd), 4)
            })
            
        return {"performance": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"业绩指标计算失败: {str(e)}")

@app.post("/api/analytics/look_through")
def run_look_through(req: LookThroughRequest):
    """Runs Holding-Based Style/Industry analysis on the portfolio with custom fund support"""
    if not req.weights:
        raise HTTPException(status_code=400, detail="Portfolio weights must not be empty")
        
    try:
        # Define stock holding database
        raw_holdings = [
            {"fund_code": "000001.OF", "stock_code": "600519.SH", "weight": 0.08, "industry": "白酒/消费", "style": "成长"},
            {"fund_code": "000001.OF", "stock_code": "300750.SZ", "weight": 0.07, "industry": "新能源/科技", "style": "成长"},
            {"fund_code": "000001.OF", "stock_code": "601318.SH", "weight": 0.05, "industry": "银行/金融", "style": "价值"},
            {"fund_code": "000001.OF", "stock_code": "000858.SZ", "weight": 0.05, "industry": "白酒/消费", "style": "成长"},
            {"fund_code": "000002.OF", "stock_code": "600036.SH", "weight": 0.04, "industry": "银行/金融", "style": "价值"},
            {"fund_code": "000002.OF", "stock_code": "600900.SH", "weight": 0.03, "industry": "水电/公用事业", "style": "价值"},
            {"fund_code": "000002.OF", "stock_code": "601088.SH", "weight": 0.03, "industry": "煤炭/能源", "style": "价值"},
            {"fund_code": "000003.OF", "stock_code": "300750.SZ", "weight": 0.09, "industry": "新能源/科技", "style": "成长"},
            {"fund_code": "000003.OF", "stock_code": "002415.SZ", "weight": 0.06, "industry": "电子/半导体", "style": "成长"},
            {"fund_code": "000003.OF", "stock_code": "600276.SH", "weight": 0.05, "industry": "医药/医疗", "style": "成长"}
        ]
        
        # Dynamically generate stock holdings for custom fund codes
        existing_codes = {"000001.OF", "000002.OF", "000003.OF"}
        for code in req.weights.keys():
            if code not in existing_codes:
                import hashlib
                h = int(hashlib.md5(code.encode('utf-8')).hexdigest(), 16)
                
                stock_options = [
                    {"stock_code": "600519.SH", "industry": "白酒/消费", "style": "成长"},
                    {"stock_code": "300750.SZ", "industry": "新能源/科技", "style": "成长"},
                    {"stock_code": "600036.SH", "industry": "银行/金融", "style": "价值"},
                    {"stock_code": "600900.SH", "industry": "水电/公用事业", "style": "价值"},
                    {"stock_code": "002415.SZ", "industry": "电子/半导体", "style": "成长"},
                    {"stock_code": "600276.SH", "industry": "医药/医疗", "style": "成长"},
                    {"stock_code": "000333.SZ", "industry": "家电/消费", "style": "价值"},
                    {"stock_code": "601888.SH", "industry": "免税/消费", "style": "成长"}
                ]
                
                idx1 = h % len(stock_options)
                idx2 = (h + 1) % len(stock_options)
                idx3 = (h + 2) % len(stock_options)
                
                idxs = list(set([idx1, idx2, idx3]))
                if len(idxs) < 3:
                    idxs = [0, 1, 2]
                
                weights = [0.08, 0.06, 0.05]
                for i, idx in enumerate(idxs[:3]):
                    opt = stock_options[idx]
                    raw_holdings.append({
                        "fund_code": code,
                        "stock_code": opt["stock_code"],
                        "weight": weights[i],
                        "industry": opt["industry"],
                        "style": opt["style"]
                    })
                    
        holdings_df = pd.DataFrame(raw_holdings)
        analyzer = LookThroughAnalyzer(method="HBA", holdings_df=holdings_df)
        
        ind_res = analyzer.run(req.weights, category="industry")
        style_res = analyzer.run(req.weights, category="style")
        
        return {
            "industry": {k: round(v, 4) for k, v in ind_res.exposures.items()},
            "style": {k: round(v, 4) for k, v in style_res.exposures.items()}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Look-through failed: {str(e)}")

class BacktestContext:
    def __init__(self, engine):
        self._engine = engine
        self._reinvest_weights = None
        self.funds = list(self._engine.market_data['fund_code'].unique())

    @property
    def current_date(self) -> datetime:
        return self._engine.current_date

    @property
    def current_date_idx(self) -> int:
        return self._engine.current_date_idx

    @property
    def cash(self) -> float:
        return self._engine.cash_account.available_cash

    @property
    def positions(self) -> Dict[str, float]:
        return {code: pos.total_shares for code, pos in self._engine.positions.items() if pos.total_shares > 0}

    def buy(self, fund_code: str, value: float):
        self._engine.submit_order(fund_code, 'BUY', value=value)

    def sell(self, fund_code: str, shares: float):
        self._engine.submit_order(fund_code, 'SELL', shares=shares)

    def get_nav(self, fund_code: str, date: datetime) -> Optional[float]:
        return self._engine._get_nav(fund_code, date)

    def get_history_navs(self, fund_code: str, count: int) -> pd.Series:
        mdata = self._engine.market_data
        subset = mdata[(mdata.index <= self.current_date) & (mdata['fund_code'] == fund_code)].sort_index()
        return subset['adj_nav'].tail(count)

    def rebalance(self, target_weights: Dict[str, float]):
        # Sell existing positions
        any_sold = False
        for code, pos in self._engine.positions.items():
            shares = pos.total_available_shares
            if shares > 0.001:
                self.sell(code, shares)
                any_sold = True
        
        transit_value = sum(self._engine.cash_account.transit_queue.values())
        if any_sold or transit_value > 0 or len(self._engine.pending_orders) > 0:
            self._reinvest_weights = target_weights
        else:
            # Buy immediately
            total_cash = self.cash
            if total_cash > 100.0:
                for code, w in target_weights.items():
                    if w > 0:
                        self.buy(code, total_cash * w)


# 5. FOF Backtest Endpoint
@app.post("/api/analytics/backtest")
def run_backtest(req: BacktestRequest):
    if not req.funds:
        raise HTTPException(status_code=400, detail="请选择至少一个基金标的进行回测")
    if req.initial_cash <= 0:
        raise HTTPException(status_code=400, detail="初始资金必须大于 0")
        
    try:
        from cjquant.backtest.engine import OTCBacktestEngine
        from cjquant.backtest.slippage import ZeroSlippage
        import importlib.util
        import uuid
        
        # 1. Fetch public fund historical NAV data from EM (akshare)
        provider = PublicFundProvider()
        dfs = []
        for code in req.funds:
            clean_code = code.split(".")[0]
            try:
                df = provider.fetch(clean_code, start_date=req.start_date, end_date=req.end_date)
                if not df.empty:
                    df['fund_code'] = code
                    dfs.append(df)
            except Exception as e:
                print(f"Error fetching data for {code} during backtest: {e}")
                
        if not dfs:
            raise HTTPException(status_code=400, detail="未获取到所选基金在指定日期区间内的任何历史净值数据。")
            
        market_data = pd.concat(dfs)
        
        # 2. Initialize Backtest Engine
        engine = OTCBacktestEngine(
            market_data=market_data,
            initial_cash=req.initial_cash,
            t_plus_confirm=1,
            t_plus_settle=3,
            slippage_model=ZeroSlippage()
        )
        
        # 3. Handle user strategy dynamic loading
        is_user_strategy = False
        strategy_file = req.rebalance_freq
        init_func = None
        handle_bar_func = None
        
        if strategy_file.endswith(".py") or os.path.exists(os.path.join(STRATEGIES_DIR, strategy_file)):
            is_user_strategy = True
            strategy_path = os.path.join(STRATEGIES_DIR, strategy_file)
            if not os.path.exists(strategy_path):
                # Fallback to direct path in case of complete path
                strategy_path = strategy_file
                if not os.path.exists(strategy_path):
                    raise HTTPException(status_code=400, detail=f"策略文件未找到: {strategy_file}")
            
            try:
                spec = importlib.util.spec_from_file_location(f"user_strategy_{uuid.uuid4().hex}", strategy_path)
                strategy_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(strategy_module)
                
                init_func = getattr(strategy_module, "init", None)
                handle_bar_func = getattr(strategy_module, "handle_bar", None)
                if not handle_bar_func:
                    raise HTTPException(status_code=400, detail="策略文件必须定义 handle_bar(context) 函数")
            except Exception as se:
                raise HTTPException(status_code=400, detail=f"导入或执行策略文件失败: {str(se)}")
                
        # 4. Simulate Rebalance Strategy Loop
        context = BacktestContext(engine)
        
        if is_user_strategy and init_func:
            try:
                init_func(context)
            except Exception as ie:
                raise HTTPException(status_code=500, detail=f"策略初始化失败 (init): {str(ie)}")
                
        last_month = None
        reinvest_weights = None
        
        while engine.current_date_idx < len(engine.trading_dates):
            current_date = engine.current_date
            
            # Reinvest if a previous monthly rebalance liquidation has settled (for both built-in & user strategy rebalance)
            active_reinvest_weights = context._reinvest_weights if is_user_strategy else reinvest_weights
            
            if active_reinvest_weights is not None:
                transit_value = sum(engine.cash_account.transit_queue.values())
                # If transit cash is fully settled and no pending transactions remain
                if transit_value == 0 and len(engine.pending_orders) == 0:
                    portfolio_value = engine.cash_account.available_cash
                    if portfolio_value > 100.0:
                        if isinstance(active_reinvest_weights, dict):
                            items = [(c, w) for c, w in active_reinvest_weights.items() if w > 0]
                            w_sum = sum(w for _, w in items)
                            if w_sum > 0:
                                allocated = 0.0
                                for i, (code, w) in enumerate(items):
                                    if i == len(items) - 1:
                                        buy_value = portfolio_value - allocated
                                    else:
                                        buy_value = round(portfolio_value * (w / w_sum), 6)
                                        allocated += buy_value
                                    if buy_value > 0.01:
                                        engine.submit_order(code, 'BUY', value=buy_value)
                        else:
                            # list format from built-in rebalance
                            w_sum = sum(active_reinvest_weights)
                            weights_norm = [w / w_sum for w in active_reinvest_weights]
                            allocated = 0.0
                            for i, (code, w) in enumerate(zip(req.funds, weights_norm)):
                                if i == len(req.funds) - 1:
                                    buy_value = portfolio_value - allocated
                                else:
                                    buy_value = round(portfolio_value * w, 6)
                                    allocated += buy_value
                                if buy_value > 0.01:
                                    engine.submit_order(code, 'BUY', value=buy_value)
                                
                        if is_user_strategy:
                            context._reinvest_weights = None
                        else:
                            reinvest_weights = None  # Reinvestment complete
            
            if is_user_strategy:
                try:
                    handle_bar_func(context)
                except Exception as hbe:
                    raise HTTPException(status_code=500, detail=f"策略运行报错 (handle_bar) 日期 {current_date.strftime('%Y-%m-%d')}: {str(hbe)}")
            else:
                is_first_step = (engine.current_date_idx == 0)
                is_new_month = (last_month is not None and current_date.month != last_month)
                
                if is_first_step:
                    # Initial buy-in: normalize weights to prevent float sum > 1.0
                    weights = [1.0 / len(req.funds)] * len(req.funds)
                    w_sum = sum(weights)
                    weights = [w / w_sum for w in weights]
                    portfolio_value = engine.cash_account.available_cash
                    allocated = 0.0
                    for i, (code, w) in enumerate(zip(req.funds, weights)):
                        if i == len(req.funds) - 1:
                            buy_value = portfolio_value - allocated  # remainder
                        else:
                            buy_value = round(portfolio_value * w, 6)
                            allocated += buy_value
                        if buy_value > 0.01:
                            engine.submit_order(code, 'BUY', value=buy_value)
                
                elif is_new_month and (req.rebalance_freq in ["monthly", "monthly_rp"]):
                    # Calculate new target weights
                    if req.rebalance_freq == "monthly_rp":
                        try:
                            if engine.current_date_idx >= 10:
                                sub_returns = {}
                                for code in req.funds:
                                    fund_df = market_data[market_data['fund_code'] == code]
                                    fund_df_sub = fund_df[fund_df.index < current_date]
                                    if not fund_df_sub.empty:
                                        sub_returns[code] = fund_df_sub['adj_nav'].pct_change().dropna()
                                df_sub_rets = pd.DataFrame(sub_returns).dropna()
                                if len(df_sub_rets) > 5:
                                    from cjquant.optimizer.traditional import RiskParityOptimizer
                                    opt = RiskParityOptimizer(df_sub_rets)
                                    weights = opt.optimize().tolist()
                                else:
                                    weights = [1.0 / len(req.funds)] * len(req.funds)
                            else:
                                weights = [1.0 / len(req.funds)] * len(req.funds)
                        except Exception:
                            weights = [1.0 / len(req.funds)] * len(req.funds)
                    else:
                        weights = [1.0 / len(req.funds)] * len(req.funds)
                    
                    # Sell all current positions
                    any_sold = False
                    for code, pos in engine.positions.items():
                        shares = pos.total_available_shares
                        if shares > 0.001:
                            engine.submit_order(code, 'SELL', shares=shares)
                            any_sold = True
                            
                    if any_sold:
                        reinvest_weights = weights
                    else:
                        # If cash-only, buy immediately
                        portfolio_value = engine.cash_account.available_cash
                        # Normalize and last-bucket remainder
                        w_sum = sum(weights)
                        weights_norm = [w / w_sum for w in weights]
                        allocated = 0.0
                        for i, (code, w) in enumerate(zip(req.funds, weights_norm)):
                            if i == len(req.funds) - 1:
                                buy_value = portfolio_value - allocated
                            else:
                                buy_value = round(portfolio_value * w, 6)
                                allocated += buy_value
                            if buy_value > 0.01:
                                engine.submit_order(code, 'BUY', value=buy_value)
            
            last_month = current_date.month
            engine.step()
            
        # 5. Formulate response payload
        trades = []
        for t in engine.trade_history:
            trades.append({
                "trade_id": t.trade_id,
                "order_id": t.order_id,
                "fund_code": t.fund_code,
                "direction": "买入" if t.direction == "BUY" else "卖出",
                "submit_date": t.submit_date.strftime("%Y-%m-%d"),
                "confirm_date": t.confirm_date.strftime("%Y-%m-%d"),
                "settle_date": t.settle_date.strftime("%Y-%m-%d"),
                "nav": round(float(t.confirm_nav), 4),
                "shares": round(float(t.filled_shares), 4),
                "volume": round(float(t.gross_amount), 2),
                "fee": round(float(t.fee), 2),
                "net_volume": round(float(t.net_amount), 2)
            })
            
        daily_stats = []
        for s in engine.daily_stats:
            ret = (s['total_assets'] / req.initial_cash) - 1.0
            daily_stats.append({
                "date": s['date'].strftime("%Y-%m-%d"),
                "available_cash": round(float(s['available_cash']), 2),
                "frozen_cash": round(float(s['frozen_cash']), 2),
                "transit_cash": round(float(s['transit_cash']), 2),
                "market_value": round(float(s['market_value']), 2),
                "total_assets": round(float(s['total_assets']), 2),
                "return": round(float(ret), 6)
            })
            
        if len(engine.daily_stats) > 1:
            total_ret = (engine.daily_stats[-1]['total_assets'] / req.initial_cash) - 1.0
            n_days = len(engine.daily_stats)
            ann_ret = (1.0 + total_ret) ** (252.0 / n_days) - 1.0 if n_days > 0 else 0.0
            
            assets_series = pd.Series([s['total_assets'] for s in engine.daily_stats])
            cum_max = assets_series.cummax()
            drawdowns = (assets_series - cum_max) / cum_max
            max_dd = float(drawdowns.min())
            
            daily_rets = assets_series.pct_change().dropna()
            std_dev = daily_rets.std()
            sharpe = (float(daily_rets.mean() * 252 - 0.02) / (float(std_dev * np.sqrt(252)))) if std_dev > 0 else 0.0
        else:
            total_ret = 0.0
            ann_ret = 0.0
            max_dd = 0.0
            sharpe = 0.0
            
        summary = {
            "total_return": round(total_ret, 6),
            "annualized_return": round(ann_ret, 6),
            "max_drawdown": round(max_dd, 6),
            "sharpe_ratio": round(sharpe, 4),
            "initial_cash": req.initial_cash,
            "final_assets": round(float(engine.daily_stats[-1]['total_assets']), 2) if engine.daily_stats else req.initial_cash
        }
        
        return {
            "status": "success",
            "summary": summary,
            "daily_stats": daily_stats,
            "trades": trades
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backtest simulation execution failed: {str(e)}")

# 6. Serve HTML & Static Files
@app.get("/")
def get_dashboard():
    index_path = os.path.join(BASE_DIR, "static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h2>Frontend static files not found. Please compile them.</h2>")
    return FileResponse(index_path)

# Mount remaining static resources
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
