import os
import sys
import pandas as pd
from datetime import datetime

# Add project root to path to ensure cjquant import works
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from cjquant.look_through.engine import LookThroughAnalyzer

def run_monitor():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting OTC Look-Through Monitor...")
    
    # 1. Setup holdings data for funds
    # In practice, this would be fetched from a database/valuation table
    raw_holdings = [
        # Fund 000001.OF holdings
        {"fund_code": "000001.OF", "stock_code": "600519.SH", "weight": 0.08, "industry": "Consumer", "style": "Growth"},
        {"fund_code": "000001.OF", "stock_code": "300750.SZ", "weight": 0.07, "industry": "Technology", "style": "Growth"},
        {"fund_code": "000001.OF", "stock_code": "601318.SH", "weight": 0.05, "industry": "Financials", "style": "Value"},
        {"fund_code": "000001.OF", "stock_code": "000858.SZ", "weight": 0.05, "industry": "Consumer", "style": "Growth"},
        # Fund 000002.OF holdings (Bond/Conservative fund, represented as mixed asset)
        {"fund_code": "000002.OF", "stock_code": "600036.SH", "weight": 0.04, "industry": "Financials", "style": "Value"},
        {"fund_code": "000002.OF", "stock_code": "600900.SH", "weight": 0.03, "industry": "Utilities", "style": "Value"},
        {"fund_code": "000002.OF", "stock_code": "601088.SH", "weight": 0.03, "industry": "Energy", "style": "Value"},
        # Fund 000003.OF holdings
        {"fund_code": "000003.OF", "stock_code": "300750.SZ", "weight": 0.09, "industry": "Technology", "style": "Growth"},
        {"fund_code": "000003.OF", "stock_code": "002415.SZ", "weight": 0.06, "industry": "Technology", "style": "Growth"},
        {"fund_code": "000003.OF", "stock_code": "600276.SH", "weight": 0.05, "industry": "Healthcare", "style": "Growth"}
    ]
    holdings_df = pd.DataFrame(raw_holdings)
    
    # 2. Define our FOF portfolio weights
    portfolio_weights = {
        "000001.OF": 0.40,
        "000002.OF": 0.30,
        "000003.OF": 0.30
    }
    print("Portfolio Weights:")
    for f, w in portfolio_weights.items():
        print(f"  - {f}: {w:.1%}")
        
    # 3. Instantiate look-through analyzer with HBA (Holding-Based) method
    print("\nInitializing LookThroughAnalyzer using HBA...")
    analyzer = LookThroughAnalyzer(method="HBA", holdings_df=holdings_df)
    
    # Run look-through for industries
    industry_res = analyzer.run(portfolio_weights, category="industry")
    
    print("\n--- Industry Exposure Analysis ---")
    for industry, exp_val in sorted(industry_res.exposures.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {industry:12}: {exp_val:.2%}")
    print("----------------------------------")
    
    # 4. Compliance check
    # Suppose we have a limit that Technology exposure cannot exceed 35%
    tech_limit = 0.35
    tech_exposure = industry_res.exposures.get("Technology", 0.0)
    
    print(f"\nCompliance Check:")
    print(f"  - Technology exposure: {tech_exposure:.2%}")
    if tech_exposure > tech_limit:
        print(f"  [WARNING] Technology exposure ({tech_exposure:.2%}) exceeds the compliance limit of {tech_limit:.2%}!")
    else:
        print(f"  [PASS] Technology exposure is within limits.")

if __name__ == "__main__":
    run_monitor()
