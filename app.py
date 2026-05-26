from flask import Flask, render_template, request, jsonify
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Store trades in memory
trades = []
cash_balance = 10000  # Starting cash

def get_stock_data(ticker):
    """Fetch stock data from Yahoo Finance"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        info = stock.info
        
        if hist.empty:
            return None
            
        current_price = hist['Close'].iloc[-1]
        sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        sma_200 = hist['Close'].rolling(window=200).mean().iloc[-1]
        rsi = calculate_rsi(hist['Close'])
        
        return {
            'ticker': ticker.upper(),
            'price': round(current_price, 2),
            'pe': round(info.get('trailingPE', 0), 2),
            'pb': round(info.get('priceToBook', 0), 2),
            'dividend_yield': round(info.get('dividendYield', 0) * 100, 2),
            'debt_to_equity': round(info.get('debtToEquity', 0), 2),
            'week_52_high': round(info.get('fiftyTwoWeekHigh', 0), 2),
            'week_52_low': round(info.get('fiftyTwoWeekLow', 0), 2),
            'volume': info.get('volume', 0),
            'market_cap': info.get('marketCap', 0),
            'sma_50': round(sma_50, 2),
            'sma_200': round(sma_200, 2),
            'rsi': round(rsi, 2)
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def get_ai_recommendation(stock_data, investment_amount):
    """Rule-based AI advisor"""
    if not stock_data:
        return None
    
    score = 0
    reasoning = []
    
    # P/E Ratio analysis
    pe = stock_data['pe']
    if 0 < pe < 15:
        score += 2
        reasoning.append("✓ P/E ratio is low (< 15) - undervalued")
    elif pe > 30:
        score -= 2
        reasoning.append("✗ P/E ratio is high (> 30) - overvalued")
    else:
        reasoning.append("= P/E ratio is moderate")
    
    # Price-to-Book analysis
    pb = stock_data['pb']
    if 0 < pb < 1.5:
        score += 1
        reasoning.append("✓ Price-to-Book is low (< 1.5)")
    elif pb > 3:
        score -= 1
        reasoning.append("✗ Price-to-Book is high (> 3)")
    
    # RSI analysis
    rsi = stock_data['rsi']
    if rsi < 30:
        score += 2
        reasoning.append("✓ RSI < 30 - oversold, buy signal")
    elif rsi > 70:
        score -= 2
        reasoning.append("✗ RSI > 70 - overbought, sell signal")
    else:
        reasoning.append("= RSI is neutral")
    
    # Moving Average analysis
    sma_50 = stock_data['sma_50']
    sma_200 = stock_data['sma_200']
    if sma_50 > sma_200:
        score += 1
        reasoning.append("✓ 50MA > 200MA - uptrend")
    else:
        score -= 1
        reasoning.append("✗ 50MA < 200MA - downtrend")
    
    # 52-week position
    price = stock_data['price']
    week_52_low = stock_data['week_52_low']
    week_52_high = stock_data['week_52_high']
    position = (price - week_52_low) / (week_52_high - week_52_low) * 100 if week_52_high > week_52_low else 50
    
    if position < 30:
        score += 1
        reasoning.append("✓ Trading near 52-week low")
    elif position > 70:
        score -= 1
        reasoning.append("✗ Trading near 52-week high")
    
    # Debt analysis
    debt = stock_data['debt_to_equity']
    if 0 < debt < 1:
        score += 1
        reasoning.append("✓ Debt-to-Equity is low (< 1.0)")
    elif debt > 3:
        score -= 1
        reasoning.append("✗ Debt-to-Equity is high (> 3.0)")
    
    # Dividend analysis
    div = stock_data['dividend_yield']
    if div > 2:
        score += 1
        reasoning.append(f"✓ Dividend yield is good ({div}%)")
    
    # Check cash availability
    shares_available = investment_amount / price
    if investment_amount > cash_balance:
        reasoning.insert(0, "⚠ Insufficient cash balance")
        confidence = 0
        recommendation = "HOLD"
    else:
        # Determine recommendation
        if score >= 5:
            recommendation = "BUY"
            confidence = min(90, 50 + score * 5)
        elif score <= -5:
            recommendation = "SELL"
            confidence = min(90, 50 + abs(score) * 5)
        else:
            recommendation = "HOLD"
            confidence = 50 + score * 3
    
    return {
        'recommendation': recommendation,
        'confidence': max(0, min(100, confidence)),
        'reasoning': reasoning,
        'score': score
    }

def get_options_chain(ticker):
    """Fetch options chain data"""
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options[:5]  # Get first 5 expiration dates
        
        chains = []
        for exp in expirations:
            opt = stock.option_chain(exp)
            calls = opt.calls[['strike', 'bid', 'ask', 'impliedVolatility', 'volume']].head(5).to_dict('records')
            puts = opt.puts[['strike', 'bid', 'ask', 'impliedVolatility', 'volume']].head(5).to_dict('records')
            
            chains.append({
                'expiration': exp,
                'calls': calls,
                'puts': puts
            })
        
        return chains
    except Exception as e:
        print(f"Error fetching options: {e}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stock/<ticker>', methods=['GET'])
def get_stock(ticker):
    data = get_stock_data(ticker)
    if data:
        return jsonify(data)
    return jsonify({'error': 'Stock not found'}), 404

@app.route('/api/advice', methods=['POST'])
def get_advice():
    data = request.json
    ticker = data.get('ticker')
    investment = float(data.get('investment', 1000))
    
    stock_data = get_stock_data(ticker)
    if not stock_data:
        return jsonify({'error': 'Stock not found'}), 404
    
    advice = get_ai_recommendation(stock_data, investment)
    return jsonify(advice)

@app.route('/api/options/<ticker>', methods=['GET'])
def get_options(ticker):
    chains = get_options_chain(ticker)
    return jsonify(chains)

@app.route('/api/trade', methods=['POST'])
def execute_trade():
    global cash_balance, trades
    
    data = request.json
    trade_type = data.get('type')  # 'STOCK_BUY', 'STOCK_SELL', 'CALL_BUY', 'PUT_BUY'
    ticker = data.get('ticker')
    quantity = int(data.get('quantity', 1))
    price = float(data.get('price', 0))
    
    total_cost = quantity * price
    
    if total_cost > cash_balance and 'BUY' in trade_type:
        return jsonify({'error': 'Insufficient cash'}), 400
    
    if 'BUY' in trade_type:
        cash_balance -= total_cost
    else:
        cash_balance += total_cost
    
    trade = {
        'timestamp': datetime.now().isoformat(),
        'type': trade_type,
        'ticker': ticker,
        'quantity': quantity,
        'price': price,
        'total': total_cost,
        'cash_remaining': cash_balance
    }
    
    trades.append(trade)
    
    return jsonify({
        'success': True,
        'trade': trade,
        'cash_balance': cash_balance
    })

@app.route('/api/trades', methods=['GET'])
def get_trades():
    return jsonify({'trades': trades, 'cash_balance': cash_balance})

if __name__ == '__main__':
    print("🚀 StockAI Trading Platform")
    print("📊 Open: http://localhost:5000")
    app.run(debug=True, port=5000)
