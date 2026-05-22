import os
import sys
import socket
import time
import subprocess
import webview

def is_port_open(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(('127.0.0.1', port))
        return True
    except:
        return False
    finally:
        s.close()

def main():
    port = 8000
    server_proc = None
    
    # Check if FastAPI server is already running
    if not is_port_open(port):
        print("FastAPI server not detected on port 8000. Starting it...")
        # Get path of cjquant root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir)
        
        # Start uvicorn process
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--host", "127.0.0.1"],
            cwd=root_dir
        )
        # Wait a bit for the server to spin up
        for _ in range(15):
            if is_port_open(port):
                break
            time.sleep(0.5)
            
    print(f"Opening CJQuant GUI pointing to http://127.0.0.1:{port}...")
    
    # Create webview window
    window = webview.create_window(
        title="CJQuant 场外量化策略与交易终端",
        url=f"http://127.0.0.1:{port}",
        width=1366,
        height=850,
        resizable=True,
        min_size=(1024, 700)
    )
    
    # Start webview loop
    webview.start()
    
    # When window is closed, clean up the server if we started it
    if server_proc:
        print("Closing FastAPI server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            
if __name__ == '__main__':
    main()
