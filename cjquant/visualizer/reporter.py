import os
import pandas as pd
from .metrics import QualityMetrics
from .plotter import ReportPlotter

class CJQuantReporter:
    def __init__(self, stats_csv_path: str, trades_csv_path: str = None):
        self.daily_stats = pd.read_csv(stats_csv_path, index_col='date', parse_dates=True)
        self.trade_history = None
        if trades_csv_path and os.path.exists(trades_csv_path):
            self.trade_history = pd.read_csv(trades_csv_path)
            
        self.plotter = ReportPlotter(self.daily_stats, self.trade_history)
        self.metrics = QualityMetrics.calculate(self.daily_stats)

    def generate_html(self, output_path: str):
        fig = self.plotter.create_interactive_figure()
        
        # 构造简单的 HTML 模板，嵌入指标表格
        metrics_html = "".join([f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in self.metrics.items()])
        
        html_content = f"""
        <html>
        <head><title>cjquant Report</title>
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            table {{ border-collapse: collapse; width: 300px; margin-bottom: 20px; }}
            td, th {{ border: 1px solid #ddd; padding: 8px; }}
            th {{ background-color: #f2f2f2; }}
        </style>
        </head>
        <body>
            <h1>cjquant 回测报告</h1>
            <table>
                <tr><th>指标</th><th>数值</th></tr>
                {metrics_html}
            </table>
            <div>{fig.to_html(full_html=False, include_plotlyjs='cdn')}</div>
        </body>
        </html>
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"HTML 报告已生成: {output_path}")

    def generate_png(self, output_path: str):
        self.plotter.create_static_summary(save_path=output_path)
        print(f"PNG 报告已生成: {output_path}")

    def generate_pdf(self, output_path: str):
        try:
            import img2pdf
            temp_img = "temp_report.png"
            self.generate_png(temp_img)
            with open(output_path, "wb") as f:
                f.write(img2pdf.convert(temp_img))
            os.remove(temp_img)
            print(f"PDF 报告已生成: {output_path}")
        except ImportError:
            print("未安装 img2pdf，无法生成PDF。请执行: pip install img2pdf")