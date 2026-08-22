import sqlite3
from datetime import datetime, timedelta

# Subscriptions Plan Config (Days: Price)
PLANS = {
    7: 19,    # 7 Days  -> ₹19
    14: 35,   # 14 Days -> ₹35
    30: 59    # 30 Days -> ₹59
}

def init_db():
    """Database aur Table Initialize karta hai."""
    conn = sqlite3.connect("hosting_data.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_name TEXT NOT NULL,
            plan_days INTEGER NOT NULL,
            price INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            notified INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_user_bot(user_id: int, bot_name: str, days: int):
    """Naye user ka bot database me add karne ke liye."""
    if days not in PLANS:
        return False, "⚠️ Invalid Plan! Valid plans: 7, 14, ya 30 days."
    
    price = PLANS[days]
    start_dt = datetime.now()
    expiry_dt = start_dt + timedelta(days=days)

    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect("hosting_data.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_bots (user_id, bot_name, plan_days, price, start_date, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, bot_name, days, price, start_str, expiry_str))
    conn.commit()
    conn.close()
    
    return True, f"✅ **Bot Successfully Added!**\n\n👤 **User ID:** `{user_id}`\n🤖 **Bot Name:** `{bot_name}`\n📅 **Plan:** {days} Days (₹{price})\n⌛ **Expiry Date:** `{expiry_str[:10]}`"

def get_user_bots(user_id: int):
    """User ke sare active/registered bots fetch karne ke liye."""
    conn = sqlite3.connect("hosting_data.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, bot_name, plan_days, price, expiry_date 
        FROM user_bots WHERE user_id = ?
    ''', (user_id,))
    records = cursor.fetchall()
    conn.close()
    return records

def extend_user_bot(user_id: int, bot_name: str, days: int):
    """Subscription validity badhane (renew) ke liye."""
    if days not in PLANS:
        return False, "⚠️ Invalid Plan! Choose 7, 14, ya 30 days."
    
    price = PLANS[days]
    conn = sqlite3.connect("hosting_data.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT expiry_date FROM user_bots WHERE user_id = ? AND bot_name = ?", (user_id, bot_name))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return False, "❌ Ye Bot Record Database me nahi mila!"
    
    curr_expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    
    # Agar bot pehle se active h to uski date me days add honge, warna aaj se add honge
    if curr_expiry > now:
        new_expiry = curr_expiry + timedelta(days=days)
    else:
        new_expiry = now + timedelta(days=days)
        
    new_expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        UPDATE user_bots 
        SET plan_days = plan_days + ?, price = price + ?, expiry_date = ?, notified = 0 
        WHERE user_id = ? AND bot_name = ?
    ''', (days, price, new_expiry_str, user_id, bot_name))
    
    conn.commit()
    conn.close()
    return True, f"🎉 **Validity Extended!**\n\n🤖 **Bot:** `{bot_name}`\n➕ **Added:** {days} Days (₹{price})\n📅 **Nayi Expiry Date:** `{new_expiry_str[:10]}`"

def get_expiring_users():
    """Expiring bots (24 hrs bache ho) fetch karne ke liye."""
    conn = sqlite3.connect("hosting_data.db")
    cursor = conn.cursor()
    
    now = datetime.now()
    warning_threshold = now + timedelta(days=1)
    
    cursor.execute('''
        SELECT id, user_id, bot_name, expiry_date FROM user_bots 
        WHERE notified = 0 AND expiry_date <= ?
    ''', (warning_threshold.strftime("%Y-%m-%d %H:%M:%S"),))
    
    records = cursor.fetchall()
    conn.close()
    return records

def mark_notified(record_id: int):
    """Notification bhejne ke baad status updated mark karein."""
    conn = sqlite3.connect("hosting_data.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE user_bots SET notified = 1 WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
