import gradio as gr
import subprocess
import sys
import os
import signal
import threading
import time
from pathlib import Path

bot_process = None
bot_log = []

def start_bot():
    global bot_process
    if bot_process and bot_process.poll() is None:
        return "⚠️ Bot is already running!"
    
    script_path = str(Path(__file__).parent / "bot.py")
    bot_process = subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    def read_output():
        for line in bot_process.stdout:
            bot_log.append(line.strip())
    
    thread = threading.Thread(target=read_output, daemon=True)
    thread.start()
    
    return "✅ Bot started!"

def stop_bot():
    global bot_process
    if not bot_process or bot_process.poll() is not None:
        return "⚠️ Bot is not running!"
    
    bot_process.terminate()
    bot_process.wait(timeout=5)
    bot_process = None
    return "🛑 Bot stopped!"

def get_status():
    if bot_process and bot_process.poll() is None:
        return f"🟢 Running (PID: {bot_process.pid})"
    return "🔴 Stopped"

def get_logs():
    return "\n".join(bot_log[-50:])

with gr.Blocks(title="Telegram Bot Controller") as app:
    gr.Markdown("# 🤖 Telegram Signal Bot Controller")
    
    with gr.Row():
        start_btn = gr.Button("▶️ Start Bot", variant="primary")
        stop_btn = gr.Button("⏹ Stop Bot", variant="stop")
        status_btn = gr.Button("🔄 Refresh Status")
    
    status_output = gr.Textbox(label="Status", interactive=False)
    
    start_btn.click(fn=start_bot, outputs=status_output)
    stop_btn.click(fn=stop_bot, outputs=status_output)
    status_btn.click(fn=get_status, outputs=status_output)
    
    logs_output = gr.Textbox(label="Bot Logs", lines=20, interactive=False)
    refresh_logs = gr.Button("🔄 Refresh Logs")
    refresh_logs.click(fn=get_logs, outputs=logs_output)

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
