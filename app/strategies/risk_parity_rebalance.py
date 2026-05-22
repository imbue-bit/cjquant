import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Add project root to path to ensure cjquant import works if run as a script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from cjquant.optimizer.traditional import RiskParityOptimizer
from cjquant.execution import OTCExecutor

def run_strategy():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting Risk Parity Rebalance Strategy...")
    
    # 1. Simulate historical returns for 3 FOF component funds
    funds = ["000001.OF", "000002.OF", "000003.OF"]
    np.random.seed(42)
    # Generate 252 days of daily returns
    returns_data = np.random.normal(0.0002, 0.01, size=(252, len(funds)))
    returns_df = pd.DataFrame(returns_data, columns=funds)
    
    print("Historical return matrix loaded (simulated 252 business days).")
    print(returns_df.head(2))
    
    # 2. Compute Risk Parity Optimal Weights
    print("Initializing RiskParityOptimizer...")
    optimizer = RiskParityOptimizer(returns_df)
    weights = optimizer.optimize()
    
    print("\n--- Risk Parity Optimization Results ---")
    for fund, w in zip(funds, weights):
        print(f"Fund: {fund} | Target Weight: {w:.4%}")
    print("----------------------------------------\n")
    
    # 3. Create Orders based on target allocation (Rebalance Execution)
    # Suppose we want to rebalance a 10M portfolio
    portfolio_value = 10000000.0
    
    # For demonstration, we place orders to align current allocation with target
    # Suppose current cash is available and we generate buy/sell orders:
    executor = OTCExecutor(
        portfolio_id="FOF_RP_DEMO",
        asset_unit="RP_UNIT_01",
        output_dir="./",  # Saved to current running directory
        strip_suffix=True
    )
    
    # Simulate buying 10M * weight for each fund
    print("Generating OTC buy/sell orders based on target weights:")
    for fund, w in zip(funds, weights):
        target_value = portfolio_value * w
        print(f"  - Placing BUY order for {fund} of amount: {target_value:.2f} CNY")
        executor.buy(fund, target_value)
        
    # 4. Execute and export O32 and WeChat orders
    print("\nExporting orders to target channels...")
    exported_files = executor.execute(channels=["o32", "wechat"], file_prefix="rp_rebalance")
    
    print("\nStrategy rebalance execution complete.")
    for channel, path in exported_files.items():
        print(f"  - [{channel.upper()}] Exported file: {os.path.abspath(path)}")
        
if __name__ == "__main__":
    run_strategy()
