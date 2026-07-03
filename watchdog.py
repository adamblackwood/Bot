import os
import subprocess
from datetime import datetime, timezone
from utils import get_utc_now, format_utc, read_state, git_pull, send_telegram

WATCHDOG_NAME = os.getenv("WATCHDOG_NAME", "Watchdog_Alpha")
HEARTBEAT_TIMEOUT_MINUTES = 3

def parse_utc(time_str):
    """Parse UTC time string to datetime object"""
    try:
        # Handle both with and without timezone info
        if time_str.endswith("UTC"):
            time_str = time_str.replace("UTC", "").strip()
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except:
        return None

def main():
    git_pull()
    state = read_state()
    
    active_worker = state.get("active_worker", "none")
    last_heartbeat_str = state.get("last_heartbeat", "")
    last_analysis_str = state.get("last_analysis_time", "")
    backup_attempts = state.get("backup_attempts", 0)
    
    if active_worker == "none" or not last_heartbeat_str:
        print(f"[{WATCHDOG_NAME}] No active worker or no heartbeat. Exiting.")
        return
    
    last_heartbeat = parse_utc(last_heartbeat_str)
    current_time = get_utc_now()
    
    if not last_heartbeat:
        print(f"[{WATCHDOG_NAME}] Could not parse heartbeat. Exiting.")
        return
    
    time_diff = (current_time - last_heartbeat).total_seconds() / 60
    
    print(f"[{WATCHDOG_NAME}] Active: {active_worker} | Last heartbeat: {time_diff:.1f} min ago")
    
    if time_diff > HEARTBEAT_TIMEOUT_MINUTES:
        # Worker is dead!
        send_telegram(
            f"🔴 <b>[FAIL]</b> {active_worker} توقف عن العمل!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💀 <b>الموظف:</b> {active_worker}\n"
            f"⏰ <b>آخر نبضة:</b> {last_heartbeat_str}\n"
            f"⏱ <b>الوقت المنقضي:</b> {time_diff:.1f} دقيقة\n"
            f"🚨 <b>المراقب:</b> {WATCHDOG_NAME}",
            channel="ops"
        )
        
        # Check if backup was already called recently
        if backup_attempts < 3:
            send_telegram(
                f"🚨 <b>[WATCHDOG]</b> {WATCHDOG_NAME} يستدعي الموظف الاحتياطي...\n"
                f"🔄 <b>محاولة رقم:</b> {backup_attempts + 1}",
                channel="ops"
            )
            
            # Trigger backup worker
            try:
                subprocess.run([
                    "gh", "workflow", "run", "backup.yml",
                    "-f", "reason=watchdog_trigger",
                    "-f", "failed_worker=" + active_worker
                ], check=True)
                
                # Update backup attempts
                from utils import write_state, git_commit_push
                write_state({"backup_attempts": backup_attempts + 1})
                git_commit_push(f"🚨 {WATCHDOG_NAME} triggered backup (attempt {backup_attempts + 1})")
                
            except Exception as e:
                send_telegram(
                    f"❌ <b>[WATCHDOG ERROR]</b> فشل في استدعاء الاحتياطي!\n"
                    f"Error: {str(e)}",
                    channel="ops"
                )
        else:
            send_telegram(
                f"⛔ <b>[WATCHDOG]</b> تم تجاوز الحد الأقصى لمحاولات الاستدعاء ({backup_attempts})\n"
                f"الانتظار للموظف المجدول التالي...",
                channel="ops"
            )
    else:
        print(f"[{WATCHDOG_NAME}] ✅ System healthy. No action needed.")

if __name__ == "__main__":
    main()