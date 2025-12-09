import streamlit as st
import sqlite3
import json
from datetime import datetime

DB_FILE = "kite_sim.db"

class WalletManager:
    def __init__(self, username):
        self.username = username
        self._init_db()
        self._load_user_data()

    def _init_db(self):
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            # User State Table (Snapshot)
            c.execute('''CREATE TABLE IF NOT EXISTS user_state (
                        username TEXT PRIMARY KEY,
                        balance REAL,
                        pnl REAL,
                        positions TEXT,
                        last_updated TIMESTAMP
                    )''')
            # Trade History Table (Log)
            c.execute('''CREATE TABLE IF NOT EXISTS trade_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT,
                        action TEXT,
                        instrument TEXT,
                        qty INTEGER,
                        price REAL,
                        timestamp TIMESTAMP
                    )''')
            conn.commit()

    def _load_user_data(self):
        """Loads balance and positions from DB into Session State"""
        if 'balance' not in st.session_state:
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT balance, pnl, positions FROM user_state WHERE username=?", (self.username,))
                row = c.fetchone()
                
                if row:
                    st.session_state.balance = row[0]
                    st.session_state.pnl = row[1]
                    try:
                        st.session_state.positions = json.loads(row[2])
                    except:
                        st.session_state.positions = []
                else:
                    # New User Defaults
                    st.session_state.balance = 100000.0
                    st.session_state.pnl = 0.0
                    st.session_state.positions = []
                    self._save_state() # Create initial record

    def _save_state(self):
        """Persists current session state to DB"""
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            # Custom serializer for potential numpy types if casting missed somewhere
            def default_serializer(obj):
                if hasattr(obj, 'item'): # numpy types
                    return obj.item()
                raise TypeError(f"Type {type(obj)} not serializable")

            pos_json = json.dumps(st.session_state.positions, default=default_serializer)
            c.execute('''INSERT OR REPLACE INTO user_state (username, balance, pnl, positions, last_updated)
                        VALUES (?, ?, ?, ?, ?)''', 
                        (self.username, st.session_state.balance, st.session_state.pnl, pos_json, datetime.now()))
            conn.commit()

    def get_balance(self):
        return st.session_state.balance

    def get_realized_pnl(self):
        return st.session_state.pnl

    def execute_trade(self, type, instrument, quantity, price):
        """
        Executes a trade and saves state.
        """
        success = False
        msg = ""
        if type == "BUY":
            quantity = int(quantity)
            price = float(price)
            cost = quantity * price

            if st.session_state.balance >= cost:
                st.session_state.balance -= cost
                
                # Check if we already have a position for this instrument
                existing_pos = next((p for p in st.session_state.positions if p['instrument'] == instrument), None)
                
                if existing_pos:
                    # Average Price Logic
                    total_qty = existing_pos['qty'] + quantity
                    total_cost = (existing_pos['qty'] * existing_pos['avg_price']) + cost
                    existing_pos['qty'] = total_qty
                    existing_pos['avg_price'] = total_cost / total_qty
                else:
                    st.session_state.positions.append({
                        "instrument": instrument,
                        "type": "BUY",
                        "qty": quantity,
                        "avg_price": price,
                        "status": "OPEN",
                        "timestamp": datetime.now().isoformat()
                    })
                success = True
                msg = "Buy Order Executed"
            else:
                 msg = "Insufficient Balance"
        
        elif type == "SELL":
            quantity = int(quantity)
            price = float(price)
            cost = quantity * price
            
            # Find the position
            existing_pos = next((p for p in st.session_state.positions if p['instrument'] == instrument), None)
            
            if not existing_pos:
                 return False, "No open position to sell."
            
            if existing_pos['qty'] < quantity:
                 return False, f"Not enough quantity. You have {existing_pos['qty']}."
            
            # Execute Sell
            st.session_state.balance += cost
            
            # Calculate Realized P&L for this chunk
            buy_avg = existing_pos['avg_price']
            pnl_chunk = (price - buy_avg) * quantity
            st.session_state.pnl += pnl_chunk 
            
            # Update Position
            existing_pos['qty'] -= quantity
            
            # Remove if closed completely
            if existing_pos['qty'] == 0:
                st.session_state.positions.remove(existing_pos)
            
            success = True
            msg = f"Sold {quantity}. Realized P&L: {pnl_chunk:.2f}"
             
        if success:
            self._save_state()
            self._log_trade(type, instrument, quantity, price)
            return True, msg
            
        return False, msg

    def _log_trade(self, action, instrument, qty, price):
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO trade_logs (username, action, instrument, qty, price, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                      (self.username, action, instrument, qty, price, datetime.now()))
            conn.commit()

    def update_pnl_heatmap(self, current_ltp_dict):
        """
        Updates the P&L positions but DOES NOT persist to DB constantly (too heavy).
        Only persists when trade happens or maybe on page unload (hard to catch).
        We will rely on session state for live P&L, db for hard state.
        """
        unrealized = 0.0
        for pos in st.session_state.positions:
            inst = pos['instrument']
            qty = pos['qty']
            avg = pos['avg_price']
            
            ltp = current_ltp_dict.get(inst)
            
            if ltp:
                pos_pnl = (ltp - avg) * qty
                pos['current_price'] = ltp
                pos['unrealized_pnl'] = pos_pnl
                unrealized += pos_pnl
            else:
                pos['unrealized_pnl'] = pos.get('unrealized_pnl', 0.0)
                unrealized += pos.get('unrealized_pnl', 0.0)
                
        return st.session_state.pnl + unrealized

    def reset_account(self):
        """Resets the user's account to initial state."""
        # 1. Reset Session State
        st.session_state.balance = 100000.0
        st.session_state.pnl = 0.0
        st.session_state.positions = []
        
        # 2. Reset DB State
        self._save_state()
        
        # 3. Clear Logs
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM trade_logs WHERE username=?", (self.username,))
            conn.commit()
            
        return True, "Account Reset Successfully"
