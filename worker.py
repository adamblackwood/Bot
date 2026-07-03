import os
import time
import json
from datetime import datetime, timezone, timedelta
from utils import (
    get_utc_now, format_utc, read_state, write_state,
    git_pull, git_commit_push, send_telegram, fetch_market_data, format_market_message
)

# ===================== CONFIGURATION =====================
WORKER_NAME = os.getenv("WORKER_NAME", "Worker_A")
SYMBOL = os.getenv("SYMBOL", "EUR/USD")
SHIFT_HOURS = 4
MAX_RUNTIME_HOURS = 5.5  # Hard stop before GitHub's 6h limit
HEARTBEAT_INTERVAL = 60  # seconds
ANALYSIS_INTERVAL = 15 * 60  # 15 minutes

# ===================== MAIN WORKER LOOP =====================
def main():
    start_time = get_utc_now()
    hard_stop_time = start_time + timedelta(hours=MAX_RUNTIME_HOURS)
    
    # 1. Pull latest state
    git_pull()
    
    # 2. Take over as active worker
    state = read_state()
    previous_worker = state.get("active_worker", "none")
    
    write_state({
        "active_worker": WORKER_NAME,
        "worker_start_time": format_utc(start_time),
        "last_heartbeat": format_utc(start_time),
        "status": "RUNNING"
    })
    git_commit_push(f"🟢 {WORKER_NAME} started shift")
    
    # 3. Send start notification
    send_telegram(
        f"🟢 <b>[START]</b> {WORKER_NAME} بدأ وردية جديدة\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 <b>الموظف:</b> {WORKER_NAME}\n"
        f"⏰ <b>وقت البدء:</b> {format_utc(start_time)}\n"
        f"🔄 <b>المدة:</b> {SHIFT_HOURS} ساعات\n"
        f"📊 <b>الرمز:</b> {SYMBOL}\n"
        f"{'🔁 الموظف السابق: ' + previous_worker if previous_worker != 'none' else ''}",
        channel="ops"
    )
    
    # 4. Main loop
    last_analysis = None
    
    while True:
        current_time = get_utc_now()
        
        # ---- CHECK HARD STOP ----
        if current_time > hard_stop_time:
            send_telegram(
                f"⚠️ <b>[HARD STOP]</b> {WORKER_NAME} تجاوز الحد الأقصى للوقت (5.5 ساعات)\n"
                f"الخروج اضطرارياً لتجنب قتل GitHub للعملية",
                channel="ops"
            )
            write_state({"status": "HARD_STOP"})
            git_commit_push(f"⚠️ {WORKER_NAME} hard stop")
            break
        
        # ---- PULL LATEST STATE ----
        git_pull()
        state = read_state()
        
        # ---- CHECK HANDOVER ----
        if state.get("active_worker") != WORKER_NAME:
            new_worker = state.get("active_worker", "unknown")
            send_telegram(
                f"✅ <b>[HANDOVER]</b> {WORKER_NAME} سلم الوردية بنجاح\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📤 <b>المسلم:</b> {WORKER_NAME}\n"
                f"📥 <b>المستلم:</b> {new_worker}\n"
                f"⏰ <b>وقت التسليم:</b> {format_utc(current_time)}",
                channel="ops"
            )
            break
        
        # ---- UPDATE HEARTBEAT ----
        write_state({
            "last_heartbeat": format_utc(current_time)
        })
        git_commit_push(f"💓 {WORKER_NAME} heartbeat")
        
        # ---- MARKET DATA ANALYSIS (Every 15 minutes) ----
        if last_analysis is None or (current_time - last_analysis).total_seconds() >= ANALYSIS_INTERVAL:
            market_data = fetch_market_data(SYMBOL)
            
            if market_data:
                msg = format_market_message(market_data, WORKER_NAME)
                send_telegram(msg, channel="market")
                
                write_state({"last_analysis_time": format_utc(current_time)})
                git_commit_push(f"📊 {WORKER_NAME} analysis done")
                last_analysis = current_time
            else:
                send_telegram(
                    f"❌ <b>[API ERROR]</b> {WORKER_NAME} فشل في جلب البيانات من جميع الـ APIs",
                    channel="ops"
                )
        
        # ---- SLEEP ----
        time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    main()