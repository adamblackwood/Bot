import os
import json
import subprocess
import requests
from datetime import datetime, timezone

STATE_FILE = "state.json"

# ===================== TIME FUNCTIONS =====================
def get_utc_now():
    return datetime.now(timezone.utc)

def format_utc(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

# ===================== STATE MANAGEMENT =====================
def read_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"active_worker": "none", "last_heartbeat": "", "last_analysis_time": "", "backup_attempts": 0}

def write_state(updates):
    state = read_state()
    state.update(updates)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# ===================== GIT OPERATIONS =====================
def git_pull():
    try:
        branch = os.getenv("GITHUB_REF_NAME", "main")
        subprocess.run(["git", "pull", "--rebase", "origin", branch], check=True, capture_output=True)
    except:
        pass

def git_commit_push(message):
    try:
        subprocess.run(["git", "config", "user.name", "GitHub Actions Bot"], check=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "add", STATE_FILE], check=True)
        
        # Check if there are changes to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", message], check=True)
            branch = os.getenv("GITHUB_REF_NAME", "main")
            subprocess.run(["git", "pull", "--rebase", "origin", branch], check=True, capture_output=True)
            subprocess.run(["git", "push"], check=True)
            return True
    except Exception as e:
        print(f"Git error: {e}")
    return False

# ===================== TELEGRAM =====================
def send_telegram(message, channel="ops"):
    token = os.getenv("TELEGRAM_TOKEN")
    if channel == "market":
        chat_id = os.getenv("TELEGRAM_CHAT_ID_MARKET", os.getenv("TELEGRAM_CHAT_ID"))
    else:
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ===================== MARKET DATA =====================
def fetch_market_data(symbol="EUR/USD"):
    """Fetch market data from Twelve Data with API key rotation"""
    keys_str = os.getenv("TWELVEDATA_KEYS", "[]")
    try:
        keys = json.loads(keys_str)
    except:
        keys = []

    if not keys:
        return None

    for key in keys:
        try:
            url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=1&apikey={key}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get("status") == "ok" and "values" in data:
                candle = data["values"][0]
                return {
                    "symbol": symbol,
                    "timeframe": "M15",
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "datetime": candle["datetime"]
                }
            elif data.get("code") == 429:
                print(f"Key {key[:8]}... rate limited, trying next")
                continue
            else:
                print(f"API error: {data.get('message', 'Unknown')}")
                continue
        except Exception as e:
            print(f"Error with key {key[:8]}...: {e}")
            continue
    
    return None

def format_market_message(data, worker_name):
    """Format market data for Telegram"""
    try:
        close = float(data["close"])
        open_price = float(data["open"])
        change = close - open_price
        change_pct = (change / open_price) * 100 if open_price != 0 else 0
        
        arrow = "🟢" if change >= 0 else "🔴"
        
        msg = f"📊 <b>MARKET DATA</b>\n"
        msg += f"━━━━━━━━━━━━━━━\n"
        msg += f"💱 <b>Symbol:</b> {data['symbol']}\n"
        msg += f"⏱ <b>Timeframe:</b> {data['timeframe']}\n"
        msg += f"💹 <b>Price:</b> {close}\n"
        msg += f"📈 <b>High:</b> {data['high']}\n"
        msg += f"📉 <b>Low:</b> {data['low']}\n"
        msg += f"🔓 <b>Open:</b> {open_price}\n"
        msg += f"{arrow} <b>Change:</b> {change:+.5f} ({change_pct:+.2f}%)\n"
        msg += f"━━━━━━━━━━━━━━━\n"
        msg += f"⏰ <b>Time:</b> {data['datetime']}\n"
        msg += f"👤 <b>Worker:</b> {worker_name}"
        return msg
    except:
        return f"📊 Market data received but formatting error occurred.\n👤 Worker: {worker_name}"