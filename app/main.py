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

# ----------------- API ENDPOINTS -----------------

# 1. Strategy Files Endpoint
@app.get("/api/strategies")
def list_strategies():
    """List strategy files inside app/strategies"""
    files = [f for f in os.listdir(STRATEGIES_DIR) if f.endswith(".py")]
    return {"strategies": files}

@app.get("/api/strategies/{name}")
def get_strategy_content(name: str):
    """Retrieve python strategy contents"""
    path = os.path.join(STRATEGIES_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Strategy not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"name": name, "code": f.read()}

@app.put("/api/strategies/{name}")
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

# 4. Analytics endpoints (Calls cjquant library)
@app.post("/api/analytics/optimize")
def run_optimization(req: OptimizeRequest):
    """Calculates risk allocation using the real cjquant optimizers"""
    if len(req.funds) < 2:
        raise HTTPException(status_code=400, detail="Please select at least 2 funds for optimization")
        
    try:
        # Simulate returns data to feed the optimizer
        np.random.seed(42)
        n_days = 252
        # Generate correlated returns
        raw_ret = np.random.normal(0.0002, 0.012, size=(n_days, len(req.funds)))
        # Introduce some correlation
        cov_matrix = np.eye(len(req.funds)) * 0.8 + 0.2
        correlated_ret = raw_ret @ np.linalg.cholesky(cov_matrix).T
        
        df_returns = pd.DataFrame(correlated_ret, columns=req.funds)
        
        if req.method == "RiskParity":
            opt = RiskParityOptimizer(df_returns)
            weights = opt.optimize()
        elif req.method == "MeanVariance":
            opt = MeanVarianceOptimizer(df_returns)
            weights = opt.optimize(target_return=0.08) # Target 8% return
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

@app.post("/api/analytics/look_through")
def run_look_through(req: LookThroughRequest):
    """Runs Holding-Based Style/Industry analysis on the portfolio"""
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
        holdings_df = pd.DataFrame(raw_holdings)
        
        analyzer = LookThroughAnalyzer(method="HBA", holdings_df=holdings_df)
        
        # Industry exposure
        ind_res = analyzer.run(req.weights, category="industry")
        style_res = analyzer.run(req.weights, category="style")
        
        return {
            "industry": {k: round(v, 4) for k, v in ind_res.exposures.items()},
            "style": {k: round(v, 4) for k, v in style_res.exposures.items()}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Look-through failed: {str(e)}")

# 5. Serve HTML & Static Files
@app.get("/")
def get_dashboard():
    index_path = os.path.join(BASE_DIR, "static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h2>Frontend static files not found. Please compile them.</h2>")
    return FileResponse(index_path)

# Mount remaining static resources
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
