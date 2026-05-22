import pandas as pd
from cjquant.optimizer.traditional import RiskParityOptimizer

def init(context):
    # This matches the standard QMT design.
    # Default to the backtested funds list. Can also be explicitly modified.
    print(f"Initializing Risk Parity Backtest Strategy with funds: {context.funds}")
    context.last_month = None

def handle_bar(context):
    current_date = context.current_date
    is_first_day = (context.current_date_idx == 0)
    is_new_month = (context.last_month is not None and current_date.month != context.last_month)
    context.last_month = current_date.month
    
    if is_first_day:
        print(f"[{current_date.strftime('%Y-%m-%d')}] Day 1: Performing equal weight initial asset allocation.")
        weights = {fund: 1.0 / len(context.funds) for fund in context.funds}
        context.rebalance(weights)
    elif is_new_month:
        print(f"[{current_date.strftime('%Y-%m-%d')}] Monthly trigger: Rebalancing portfolio using Risk Parity optimizer.")
        
        # Calculate Risk Parity weights using recent history
        try:
            hist_returns = {}
            for fund in context.funds:
                # Retrieve last 60 days of historical adjusted NAV values
                navs = context.get_history_navs(fund, count=60)
                if len(navs) > 5:
                    hist_returns[fund] = navs.pct_change().dropna()
            
            df_returns = pd.DataFrame(hist_returns).dropna()
            
            if len(df_returns) > 10:
                opt = RiskParityOptimizer(df_returns)
                weights_series = opt.optimize()
                weights = weights_series.to_dict()
            else:
                # Equal weight fallback
                weights = {fund: 1.0 / len(context.funds) for fund in context.funds}
        except Exception as e:
            print(f"Risk Parity optimizer failed: {e}. Falling back to equal weight rebalance.")
            weights = {fund: 1.0 / len(context.funds) for fund in context.funds}
            
        print(f"New target allocation: {weights}")
        context.rebalance(weights)
