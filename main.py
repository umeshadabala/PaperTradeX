import os
import json
import requests
from datetime import datetime
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

STARTING_BALANCE = 10000.0

def load_data(user_file):
    if os.path.exists(user_file):
        with open(user_file, "r") as f:
            return json.load(f)
    else:
        return {
            "wallet": STARTING_BALANCE,
            "holdings": {},
            "history": [],
            "profits": 0.0,
        }

def save_data(user_file, data):
    with open(user_file, "w") as f:
        json.dump(data, f, indent=4)

@st.cache_data(ttl=3600)
def fetch_top_100_coins():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": False,
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        coins = response.json()
        return [{"id": c["id"], "symbol": c["symbol"], "name": c["name"]} for c in coins]
    except Exception as e:
        st.error(f"Error fetching top 100 coins: {e}")
        return []

@st.cache_data(ttl=60)
def fetch_crypto_price(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get(coin_id, {}).get("usd", None)
    except Exception:
        return None

@st.cache_data(ttl=300)
def fetch_crypto_history(coin_id, days=30):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": days}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        prices = data.get("prices", [])
        df = pd.DataFrame(prices, columns=["timestamp", "price"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df
    except Exception as e:
        st.warning(f"Failed to fetch price history: {e}")
        return pd.DataFrame()

def add_transaction(data, action, coin_id, quantity, price, profit=None):
    data["history"].append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "coin_id": coin_id,
            "quantity": quantity,
            "price": price,
            "profit": profit,
        }
    )

def main():
    st.set_page_config(page_title="PaperTradeX", page_icon="💰", layout="wide")
    
    st.title("💰 PaperTradeX")
    st.write("Trade. Learn. Dominate.")

    username = st.text_input("Enter your username to start:", key="user")
    if not username:
        st.stop()

    user_file = f"trading_data_{username}.json"
    data = load_data(user_file)

    with st.sidebar:
        st.header(f"👤 User: {username}")
        st.subheader("💵 Wallet Balance")
        st.write(f"${data['wallet']:.2f}")

        st.subheader("📦 Holdings")
        if data["holdings"]:
            for coin, info in data["holdings"].items():
                st.write(f"{coin.upper()}: {info['quantity']:.4f} @ ${info['avg_price']:.2f}")
        else:
            st.write("No holdings yet.")

        st.subheader("📊 Realized Profit")
        st.write(f"${data['profits']:.2f}")

    coins = fetch_top_100_coins()
    if not coins:
        st.stop()

    coin_map = {c["id"]: f"{c['symbol'].upper()} - {c['name']}" for c in coins}
    coin_id = st.selectbox("Choose a coin", list(coin_map.keys()), format_func=lambda x: coin_map[x])
    current_price = fetch_crypto_price(coin_id)

    if current_price is None:
        st.error("Unable to fetch price.")
        st.stop()

    st.write(f"### {coin_map[coin_id]}: ${current_price:.4f}")

    col1, col2 = st.columns([3, 2])

    with col1:
        quantity = st.number_input("Quantity", min_value=0.0001, step=0.0001, format="%.4f")
        action = st.radio("Action", ["Buy", "Sell"], horizontal=True)

        if st.button(f"{action} {coin_map[coin_id]}"):
            total = quantity * current_price
            if action == "Buy":
                if total > data["wallet"]:
                    st.warning("Insufficient funds.")
                else:
                    data["wallet"] -= total
                    if coin_id in data["holdings"]:
                        existing = data["holdings"][coin_id]
                        new_qty = existing["quantity"] + quantity
                        new_avg = (existing["avg_price"] * existing["quantity"] + current_price * quantity) / new_qty
                        data["holdings"][coin_id] = {"quantity": new_qty, "avg_price": new_avg}
                    else:
                        data["holdings"][coin_id] = {"quantity": quantity, "avg_price": current_price}
                    add_transaction(data, "BUY", coin_id, quantity, current_price)
                    st.success(f"Bought {quantity:.4f} {coin_map[coin_id]}")
            else:
                if coin_id not in data["holdings"] or data["holdings"][coin_id]["quantity"] < quantity:
                    st.warning("Not enough holdings.")
                else:
                    avg = data["holdings"][coin_id]["avg_price"]
                    profit = (current_price - avg) * quantity
                    data["profits"] += profit
                    data["wallet"] += total
                    remaining = data["holdings"][coin_id]["quantity"] - quantity
                    if remaining <= 0:
                        del data["holdings"][coin_id]
                    else:
                        data["holdings"][coin_id]["quantity"] = remaining
                    add_transaction(data, "SELL", coin_id, quantity, current_price, profit)
                    st.success(f"Sold {quantity:.4f} {coin_map[coin_id]} | Profit: ${profit:.2f}")
            save_data(user_file, data)

        st.subheader("📄 Recent Transactions")
        if data["history"]:
            for tx in reversed(data["history"][-10:]):
                profit_text = f" | Profit: ${tx['profit']:.2f}" if tx["action"] == "SELL" and tx.get("profit") else ""
                st.write(f"[{tx['timestamp'][:19]}] {tx['action']} {tx['quantity']:.4f} {tx['coin_id']} @ ${tx['price']:.4f}{profit_text}")
        else:
            st.write("No transactions yet.")

    with col2:
        st.subheader(f"{coin_map[coin_id]} Price Chart")
        df = fetch_crypto_history(coin_id)
        if not df.empty:
            fig, ax = plt.subplots()
            ax.plot(df.index, df["price"], label="Price (USD)")
            ax.set_xlabel("Date")
            ax.set_ylabel("Price")
            ax.grid(True)
            ax.legend()
            st.pyplot(fig)
        else:
            st.info("No chart data available.")

if __name__ == "__main__":
    main()
