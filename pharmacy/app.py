import locale
import os
import random
import string # Not strictly used, but often useful for key generation etc.
from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
import requests # For reCAPTCHA verification

# --- Basic App Setup ---
app = Flask(__name__)
db_path = os.path.join(app.instance_path, 'pharmacy.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_very_secret_key_for_flashing_change_me_also_for_session' # IMPORTANT: Change this!

# --- reCAPTCHA Configuration ---
# !!! IMPORTANT: For production, REPLACE the TEST KEYS below with YOUR ACTUAL KEYS from Google reCAPTCHA admin console. !!!
# The keys currently configured are Google's TEST keys for reCAPTCHA v2 "I'm not a robot" Checkbox.
app.config['RECAPTCHA_SITE_KEY'] = '6Lfj4TQrAAAAAP8Hn7myLVYUZSUvAKM4KVDl6QLA' # Google's TEST Key
app.config['RECAPTCHA_SECRET_KEY'] = '6Lfj4TQrAAAAAOPOt7RPXObg9BBPGMIaETHrJKll' # Google's TEST Key

# These are example placeholder strings the code internally checks against.
# Your configured keys should NOT be these literal strings if you want reCAPTCHA to work.
INTERNAL_PLACEHOLDER_SITE_KEY = 'YOUR_RECAPTCHA_SITE_KEY_SHOULD_NOT_BE_THIS_STRING'
INTERNAL_PLACEHOLDER_SECRET_KEY = 'YOUR_RECAPTCHA_SECRET_KEY_SHOULD_NOT_BE_THIS_STRING'

try:
    os.makedirs(app.instance_path)
except OSError:
    pass 
db = SQLAlchemy(app)

# --- Locale Setup ---
locale_set_successfully = False
try:
    locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8'); locale_set_successfully = True
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'en_IN'); locale_set_successfully = True
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8'); locale_set_successfully = True
            print("Warning: 'en_IN' locale not found. Using 'en_US.UTF-8' for currency.")
        except locale.Error:
            print("Warning: 'en_IN' and 'en_US.UTF-8' locales not found. Using default system locale for currency.")

def format_currency_inr(amount):
    if amount is None: amount = 0.0
    try: amount = float(amount)
    except (ValueError, TypeError): return "Invalid Amount"
    if locale_set_successfully:
        current_locale = locale.getlocale(locale.LC_MONETARY)[0] 
        if current_locale and ('en_IN' in current_locale or 'en_US' in current_locale):
            try:
                if 'en_IN' in current_locale: return locale.currency(amount, symbol=True, grouping=True)
                else: return f"₹{amount:,.2f}" # Fallback for en_US to still show INR symbol
            except ValueError: return f"₹{amount:,.2f}"
        else: return f"₹{amount:,.2f}" # Fallback if locale is neither en_IN nor en_US
    else: return f"₹{amount:,.2f}" # Fallback if locale setting failed
app.jinja_env.filters['inr'] = format_currency_inr

# --- In-Memory Data ---
admin_users = {"admin@example.com": "password123"}
dealers = [] 
next_dealer_id = 1
stock = { "tablet": [], "painkiller": [], "bodylotion": [], "coughsyrup": [] }
initial_stock = {
    "tablet": [{"name": "Paracetamol 500mg", "price": 2.50}, {"name": "Amoxicillin 250mg", "price": 5.00}],
    "painkiller": [{"name": "Tramadol 50mg", "price": 7.00}, {"name": "Diclofenac Gel", "price": 5.50}],
    "bodylotion": [{"name": "Cetaphil Lotion 250ml", "price": 12.00}, {"name": "Vaseline Intensive Care 400ml", "price": 9.00}],
    "coughsyrup": [{"name": "Benadryl Cough Syrup 100ml", "price": 9.50}, {"name": "Ascoril LS Syrup 100ml", "price": 17.00}],
}
for category, items in initial_stock.items():
    if category in stock:
        for item_data in items:
            if not any(existing_item['name'] == item_data['name'] for existing_item in stock[category]):
                 stock[category].append({"name": item_data["name"], "price": item_data["price"], "quantity": 100})
cart = []

# --- Database Model & Creation ---
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    payment_method = db.Column(db.String(50))
    total_amount = db.Column(db.Float)
    items = db.Column(db.Text)
    def __repr__(self): return f"<Transaction {self.id} on {self.timestamp.strftime('%Y-%m-%d')}>"

class FakeTransaction: 
    def __init__(self, id, timestamp, items, payment_method, total_amount):
        self.id=id; self.timestamp=timestamp; self.items=items; self.payment_method=payment_method; self.total_amount=total_amount

def create_db():
    with app.app_context(): db.create_all()

# --- Decorators ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash("Admin access required.", "warning"); return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def customer_or_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not (session.get('admin_logged_in') or session.get('customer_email')):
            flash("Please login to view this page.", "warning"); return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('customer_email'):
            if session.get('admin_logged_in'):
                flash("This action is available for customers only.", "info")
                return redirect(url_for('dashboard')) 
            flash("Please login as a customer to access this page.", "warning")
            return redirect(url_for('login', persisted_email=session.get('customer_email', '')))
        return f(*args, **kwargs)
    return decorated_function

# --- HTML Templates ---
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pharmacy Login</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://www.google.com/recaptcha/api.js" async defer></script>
    <style>
        :root {
            --primary-color: #3498db; --secondary-color: #2193b0; --light-text: #f0f4f8;
            --dark-text: #333; --background-light: #f0f4f8; --white: #ffffff;
            --error-bg: rgba(255, 77, 77, 0.6); --error-text: #ffdddd;
            --input-bg: rgba(255, 255, 255, 0.15); --input-focus-bg: rgba(255, 255, 255, 0.25);
        }
        html { height: 100%; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(to bottom right, #6dd5ed, var(--secondary-color));
            height: 100%; display: flex; justify-content: center; align-items: center;
            margin: 0; overflow: auto; padding: 20px 0;
        }
        .login-container-wrapper { display: flex; flex-direction: column; align-items: center; gap: 20px; width: 90%; max-width: 420px; }
        .login-section {
            background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(8px); padding: 35px 30px; border-radius: 15px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37); border: 1px solid rgba(255, 255, 255, 0.18);
            width: 100%; text-align: center; color: var(--light-text); animation: fadeIn 0.8s ease-in-out; margin-bottom: 20px;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
        .login-section img.logo { width: 70px; margin-bottom: 15px; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.2)); }
        .login-section h2 { margin-bottom: 25px; font-size: 24px; letter-spacing: 1px; font-weight: 400; text-transform: uppercase; }
        .input-group { margin: 20px 0; text-align: left; position: relative; }
        .input-group label { position: absolute; top: 14px; left: 45px; font-size: 15px; color: #ccc; pointer-events: none; transition: all 0.3s ease; }
        .input-group input {
            width: 100%; padding: 14px 16px 14px 45px; border: none; border-radius: 8px; font-size: 15px;
            background: var(--input-bg); color: var(--light-text); transition: background 0.3s ease, box-shadow 0.3s ease; box-sizing: border-box;
        }
        .input-group input::placeholder { color: #bbb; opacity: 1; }
        .input-group input:focus { outline: none; background: var(--input-focus-bg); box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.5); }
        .input-group input:focus + label, .input-group input:not(:placeholder-shown) + label {
             top: -10px; left: 12px; font-size: 12px; color: var(--white); background: var(--secondary-color); padding: 2px 6px; border-radius: 4px;
        }
        .input-group i { position: absolute; top: 50%; left: 15px; transform: translateY(-50%); color: #ccc; font-size: 16px; }
        .login-btn {
            width: 100%; padding: 14px; background: var(--primary-color); border: none; border-radius: 8px; color: var(--white);
            font-size: 17px; font-weight: 500; cursor: pointer; margin-top: 25px;
            transition: background 0.3s ease, transform 0.2s ease, box-shadow 0.3s ease; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .login-btn:hover { background: #2980b9; transform: translateY(-2px); box-shadow: 0 6px 10px rgba(0, 0, 0, 0.15); }
        .message { padding: 10px; border-radius: 6px; font-size: 15px; margin-top: 15px; text-align: center; }
        .admin-error, .customer-error { color: var(--error-text); background-color: var(--error-bg); border: 1px solid rgba(255, 77, 77, 0.8); }
        .recaptcha-container { margin: 20px 0; display: flex; justify-content: center; }
        .bg-animation { position:fixed;top:0;left:0;right:0;bottom:0;width:100%;height:100%;background:linear-gradient(-45deg, #ee7752, #e73c7e, #23a6d5, #23d5ab);background-size:400% 400%;animation:animateBackground 18s ease infinite;z-index:0;}
        @keyframes animateBackground{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        .flash-messages{position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:1000;width:80%;max-width:500px;}
        .flash{padding:12px 15px;margin-bottom:10px;border-radius:6px;color:#fff;font-size:15px;opacity:0.95;display:flex;justify-content:space-between;align-items:center;box-shadow:0 2px 5px rgba(0,0,0,0.2);}
        .flash.success{background-color:#2ecc71;}.flash.error{background-color:#e74c3c;}.flash.info{background-color:#3498db;}.flash.warning{background-color:#f39c12;color:#333;}
        .flash-close{background:none;border:none;color:inherit;font-size:20px;cursor:pointer;margin-left:15px;line-height:1;}
        .separator{margin:30px 0 20px;text-align:center;color:rgba(255,255,255,0.7);font-weight:bold;}
    </style>
</head>
<body>
    <div class="bg-animation"></div>
    <div class="flash-messages">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}{% for category, message in messages %}
            <div class="flash {{ category }}" role="alert"><span>{{ message }}</span><button type="button" class="flash-close" onclick="this.parentElement.style.display='none'">×</button></div>
            {% endfor %}{% endif %}
        {% endwith %}
    </div>

    <div class="login-container-wrapper">
        <div class="login-section">
            <img src="https://cdn-icons-png.flaticon.com/512/2966/2966327.png" alt="Pharmacy Icon" class="logo">
            <h2>Admin Login</h2>
            {% if admin_error %}<p class="message admin-error">{{ admin_error }}</p>{% endif %}
            <form method="POST" action="{{ url_for('login') }}">
                <input type="hidden" name="form_type" value="admin">
                <div class="input-group"><i class="fas fa-user-shield"></i><input type="email" name="email" id="admin_email" required autocomplete="email" placeholder=" "><label for="admin_email">Admin Email</label></div>
                <div class="input-group"><i class="fas fa-lock"></i><input type="password" name="password" id="admin_password" required autocomplete="current-password" placeholder=" "><label for="admin_password">Password</label></div>
                <button type="submit" class="login-btn">Admin Login</button>
            </form>
        </div>

        <div class="separator">OR</div>

        <div class="login-section">
            <img src="https://cdn-icons-png.flaticon.com/512/1077/1077114.png" alt="Customer Icon" class="logo">
            <h2>Customer Login</h2>
            {% if customer_error %}<p class="message customer-error">{{ customer_error }}</p>{% endif %}
            <form method="POST" action="{{ url_for('login') }}" id="customerLoginForm">
                <input type="hidden" name="form_type" value="customer_recaptcha_login">
                <div class="input-group">
                    <i class="fas fa-envelope"></i>
                    <input type="email" name="customer_email" id="customer_email" required autocomplete="email" placeholder=" " 
                           value="{{ persisted_customer_email if persisted_customer_email else (request.form.customer_email if request.form.customer_email else '') }}">
                    <label for="customer_email">Your Email</label>
                </div>
                <div class="recaptcha-container">
                    <div class="g-recaptcha" data-sitekey="{{ recaptcha_site_key }}"></div>
                </div>
                <button type="submit" class="login-btn" style="background-color: #27ae60;">Login</button>
            </form>
        </div>
    </div>
    <script>
        setTimeout(function() {
            let flashMessages = document.querySelectorAll('.flash, .message');
            flashMessages.forEach(function(msg) {
                msg.style.transition = 'opacity 0.5s ease'; msg.style.opacity = '0';
                setTimeout(() => msg.style.display = 'none', 500);
            });
        }, 7000);
    </script>
</body>
</html>
"""
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pharmacy Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary-color: #3498db; --secondary-color: #2980b9; --background-light: #f0f4f8;
            --card-bg: #ffffff; --text-dark: #333; --text-light: #555; --icon-color: var(--primary-color);
            --shadow-color: rgba(0, 0, 0, 0.1); --shadow-hover-color: rgba(0, 0, 0, 0.18);
            --logout-btn-bg: #e74c3c; --logout-btn-hover: #c0392b;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--background-light);
            margin: 0; padding: 0; color: var(--text-dark); display: flex; flex-direction: column; min-height: 100vh;
        }
        .header {
            background: linear-gradient(to right, var(--primary-color), var(--secondary-color));
            padding: 15px 30px; color: var(--card-bg); box-shadow: 0 4px 8px var(--shadow-color);
            border-bottom: 3px solid var(--secondary-color);
            display: flex; justify-content: space-between; align-items: center;
        }
        .header-title { font-size: 24px; font-weight: 500; letter-spacing: 1.2px; }
        .logout-btn {
            background-color: var(--logout-btn-bg); color: white; padding: 8px 15px;
            border: none; border-radius: 5px; text-decoration: none; font-size: 14px;
            transition: background-color 0.3s ease; display: inline-flex; align-items: center; gap: 5px;
        }
        .logout-btn:hover { background-color: var(--logout-btn-hover); }
        .dashboard {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 25px;
            justify-content: center; align-items: center; margin-top: 35px; padding: 25px; flex-grow: 1;
        }
        .dashboard-item {
            text-align: center; background: var(--card-bg); border-radius: 12px;
            box-shadow: 0 4px 12px var(--shadow-color); transition: transform 0.3s ease, box-shadow 0.3s ease;
            padding: 30px 15px; display: flex; flex-direction: column; align-items: center;
            text-decoration: none; color: inherit; overflow: hidden; position: relative;
        }
        .dashboard-item:hover { transform: translateY(-8px) scale(1.04); box-shadow: 0 10px 25px var(--shadow-hover-color); }
        .dashboard-item i { font-size: 48px; color: var(--icon-color); transition: color 0.3s ease, transform 0.3s ease; margin-bottom: 18px; }
        .dashboard-item:hover i { color: var(--secondary-color); transform: scale(1.15) rotate(5deg); }
        .dashboard-item p { margin: 0; font-size: 15px; font-weight: 500; color: var(--text-light); }
        .footer { text-align: center; margin-top: auto; padding: 18px; color: #777; font-size: 14px; border-top: 1px solid #e0e0e0; background-color: #fdfdfd; }
        .flash-messages { position: fixed; top: 80px; left: 50%; transform: translateX(-50%); z-index: 1000; width: 90%; max-width: 600px; }
        .flash { padding: 12px 15px; margin-bottom: 10px; border-radius: 6px; color: #fff; font-size: 15px; opacity: 0.95; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        .flash.success { background-color: #2ecc71; } .flash.error { background-color: #e74c3c; }
        .flash.info { background-color: #3498db; } .flash.warning { background-color: #f39c12; color: #333; }
        .flash-close { background: none; border: none; color: inherit; font-size: 20px; cursor: pointer; margin-left: 15px; line-height: 1; }
    </style>
</head>
<body>
    <div class="header">
        <span class="header-title">Pharmacy Management Dashboard</span>
        <a href="{{ url_for('admin_logout') }}" class="logout-btn"><i class="fas fa-sign-out-alt"></i> Logout Admin</a>
    </div>
    <div class="flash-messages">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="flash {{ category }}" role="alert">
                    <span>{{ message }}</span>
                    <button type="button" class="flash-close" onclick="this.parentElement.style.display='none'">×</button>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
    <div class="dashboard">
        <a href="{{ url_for('dashboard') }}" class="dashboard-item"><i class="fas fa-tachometer-alt"></i><p>Dashboard</p></a>
        <a href="{{ url_for('dealers_list') }}" class="dashboard-item"><i class="fas fa-handshake"></i><p>Dealer Mgt.</p></a>
        <a href="{{ url_for('stock_categories') }}" class="dashboard-item"><i class="fas fa-boxes-stacked"></i><p>Stock Mgt.</p></a>
        <a href="{{ url_for('cashier') }}" class="dashboard-item"><i class="fas fa-cash-register"></i><p>Transactions</p></a>
    </div>
    <div class="footer">© <span id="current-year"></span> Pharmacy Management System</div>
    <script>
        document.getElementById('current-year').textContent = new Date().getFullYear();
        setTimeout(function() {
            let flashMessages = document.querySelectorAll('.flash');
            flashMessages.forEach(function(msg) {
                msg.style.transition = 'opacity 0.5s ease'; msg.style.opacity = '0';
                setTimeout(() => msg.style.display = 'none', 500);
            });
        }, 5000);
    </script>
</body>
</html>
"""
DEALER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dealer Management</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary-color: #3498db; --secondary-color: #2ecc71; --danger-color: #e74c3c;
            --info-color: #8e44ad;
            --background-light: #f0f4f8; --card-bg: #ffffff; --text-dark: #333; --text-light: #555;
            --border-color: #e0e4e8; --input-border: #ccc; --form-bg: #f9f9f9;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--background-light);
            margin: 0; padding: 25px; color: var(--text-dark); min-height: 100vh;
            display: flex; flex-direction: column; align-items: center;
        }
        .container {
            width: 100%; max-width: 850px;
            margin: 20px 0; padding: 30px; background: var(--card-bg);
            border-radius: 12px; box-shadow: 0 6px 15px rgba(0, 0, 0, 0.1); flex-grow: 1;
        }
        h1 {
            text-align: center; color: var(--primary-color); margin-top: 0; margin-bottom: 30px;
            border-bottom: 2px solid var(--border-color); padding-bottom: 15px; font-weight: 500; letter-spacing: 0.5px;
        }
        h1 i { margin-right: 10px; }
        h2 { color: #34495e; margin-top: 35px; margin-bottom: 18px; font-size: 1.3em; font-weight: 500; }
        h2 i { margin-right: 8px; color: #7f8c8d; }
        .add-form {
            margin-bottom: 35px; padding: 20px; background-color: var(--form-bg); border-radius: 8px;
            border: 1px solid var(--border-color); display: flex; gap: 15px; align-items: center;
        }
        .add-form input[type="text"] {
            flex-grow: 1; padding: 12px 15px; border: 1px solid var(--input-border); border-radius: 6px;
            font-size: 16px; box-sizing: border-box; transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }
        .add-form input[type="text"]:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2); }
        .add-form button[type="submit"] {
            padding: 12px 22px; background: var(--secondary-color); color: white; border: none; border-radius: 6px;
            cursor: pointer; font-size: 16px; font-weight: 500; transition: background 0.3s ease, transform 0.2s ease;
            display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
        }
        .add-form button[type="submit"]:hover { background: #27ae60; transform: translateY(-1px); }
        .dealer-list { list-style: none; padding: 0; margin: 0; }
        .dealer-list li {
            display: flex; justify-content: space-between; align-items: center; padding: 16px 20px;
            margin-bottom: 12px; background: #fdfdfd; border: 1px solid var(--border-color); border-radius: 8px;
            transition: background-color 0.2s ease, border-left 0.3s ease; border-left: 4px solid transparent;
        }
        .dealer-list li:hover { background-color: #f5f7fa; border-left: 4px solid var(--primary-color); }
        .dealer-info-container { flex-grow: 1; display: flex; flex-direction: column; }
        .dealer-info { margin-right: 15px; color: var(--text-light); }
        .dealer-id {
            font-weight: 600; color: var(--primary-color); margin-right: 8px; background-color: #eaf2f8;
            padding: 2px 6px; border-radius: 4px; font-size: 0.9em;
        }
        .dealer-name { color: var(--text-dark); font-weight: 500; }
        .supplied-items-summary { font-size: 0.85em; color: #7f8c8d; margin-top: 5px; }
        .dealer-actions { display: flex; gap: 10px; align-items: center; }
        .action-btn {
            padding: 7px 12px; border-radius: 5px; cursor: pointer;
            transition: background 0.3s ease, color 0.3s ease, transform 0.2s ease;
            font-size: 14px; font-weight: 500; display: inline-flex; align-items: center; gap: 5px; text-decoration: none;
        }
        .manage-btn { background: var(--info-color); color: white; border: 1px solid var(--info-color); }
        .manage-btn:hover { background: #823aa0; transform: scale(1.05); }
        .remove-btn { background: transparent; color: var(--danger-color); border: 1px solid var(--danger-color); }
        .remove-btn:hover { background: var(--danger-color); color: white; transform: scale(1.05); }
        .remove-btn i { font-size: 13px; }
        .back-link-container { margin-top: 35px; text-align: center; }
        .back-link {
            color: var(--primary-color); text-decoration: none; font-size: 16px; padding: 10px 15px;
            border-radius: 5px; transition: background-color 0.2s ease, text-decoration 0.2s ease;
            display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--primary-color);
        }
        .back-link:hover { background-color: #eaf2f8; text-decoration: none; }
        .empty-list { text-align: center; color: #777; margin-top: 25px; font-style: italic; padding: 15px; background-color: var(--form-bg); border-radius: 6px; border: 1px dashed var(--border-color); }
        .flash-messages { margin-bottom: 20px; }
        .flash { padding: 12px 15px; margin-bottom: 10px; border-radius: 6px; color: #fff; font-size: 15px; opacity: 0.95; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.15); }
        .flash.success { background-color: #2ecc71; } .flash.error { background-color: #e74c3c; }
        .flash.info { background-color: #3498db; } .flash.warning { background-color: #f39c12; color: #333; }
        .flash-close { background: none; border: none; color: inherit; font-size: 20px; cursor: pointer; margin-left: 15px; line-height: 1; }
    </style>
</head><body>
    <div class="container">
        <h1><i class="fas fa-handshake"></i> Dealer Management</h1>
        <div class="flash-messages">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}{% for category, message in messages %}
                <div class="flash {{ category }}" role="alert"><span>{{ message }}</span><button type="button" class="flash-close" onclick="this.parentElement.style.display='none'">×</button></div>
                {% endfor %}{% endif %}
            {% endwith %}
        </div>
        <form method="POST" action="{{ url_for('add_dealer') }}" class="add-form">
            <input type="text" name="dealer_name" placeholder="Enter New Dealer Name" required>
            <button type="submit"><i class="fas fa-plus"></i> Add Dealer</button>
        </form>
        <h2><i class="fas fa-list-ul"></i> Dealer List</h2>
        <ul class="dealer-list">
            {% if dealers %}
                {% for dealer in dealers %}
                    <li>
                        <div class="dealer-info-container">
                            <div class="dealer-info">
                                <span class="dealer-id">ID: {{ dealer.id }}</span><span class="dealer-name">{{ dealer.name }}</span>
                            </div>
                            <div class="supplied-items-summary">
                                Supplies: {{ dealer.supplied_items|length }} item(s)
                            </div>
                        </div>
                        <div class="dealer-actions">
                            <a href="{{ url_for('manage_dealer_products_and_order', dealer_id=dealer.id) }}" class="action-btn manage-btn">
                                <i class="fas fa-tasks"></i> Manage & Order
                            </a>
                            <form method="POST" action="{{ url_for('remove_dealer', dealer_id=dealer.id) }}" style="margin: 0;" onsubmit="return confirm('Are you sure you want to remove {{ dealer.name }}? This will not affect existing stock.');">
                                <button type="submit" class="action-btn remove-btn"><i class="fas fa-user-minus"></i> Remove</button>
                            </form>
                        </div>
                    </li>
                {% endfor %}
            {% else %}
                <p class="empty-list">No dealers have been added yet.</p>
            {% endif %}
        </ul>
        <div class="back-link-container"><a href="{{ url_for('dashboard') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Dashboard</a></div>
    </div>
    <script>
        setTimeout(function() {
            let flashMessages = document.querySelectorAll('.flash');
            flashMessages.forEach(function(msg) { msg.style.transition = 'opacity 0.5s ease'; msg.style.opacity = '0'; setTimeout(() => msg.style.display = 'none', 500); });
        }, 5000);
    </script>
</body></html>
"""
MANAGE_DEALER_PRODUCTS_ORDER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manage & Order - {{ dealer.name }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary-color: #3498db; --secondary-color: #2ecc71; --danger-color: #e74c3c;
            --info-color: #8e44ad; --neutral-bg: #ecf0f1;
            --background-light: #f0f4f8; --card-bg: #ffffff; --text-dark: #333; --text-light: #555;
            --border-color: #e0e4e8; --input-border: #ccc; --form-bg: #f9f9f9;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--background-light); margin: 0; padding: 25px; color: var(--text-dark); }
        .container { max-width: 900px; margin: 20px auto; padding: 30px; background: var(--card-bg); border-radius: 12px; box-shadow: 0 6px 15px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: var(--primary-color); margin-top: 0; margin-bottom: 25px; font-weight: 500; }
        h1 i { margin-right: 10px; }
        h2 { color: #34495e; font-size: 1.4em; margin-top: 30px; margin-bottom: 15px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; font-weight: 500; }
        h2 i { margin-right: 8px; color: var(--text-light); }
        .section { margin-bottom: 40px; padding: 20px; background-color: var(--form-bg); border: 1px solid var(--border-color); border-radius: 8px; }
        
        .supplied-items-list { list-style: none; padding: 0; margin: 0; }
        .supplied-items-list li { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; margin-bottom: 8px; background: #fdfdfd; border: 1px solid #e9ecef; border-radius: 6px; }
        .item-details { flex-grow: 1; }
        .item-name { font-weight: 500; } .item-category { font-size: 0.9em; color: #7f8c8d; margin-left: 5px; }
        .remove-supply-btn { background: transparent; color: var(--danger-color); border: 1px solid var(--danger-color); padding: 5px 10px; border-radius: 4px; cursor: pointer; transition: all 0.2s; font-size: 0.9em; }
        .remove-supply-btn:hover { background: var(--danger-color); color: white; }
        .empty-list-msg { color: #777; font-style: italic; margin-top: 10px; }

        .add-supply-form { display: flex; gap: 10px; align-items: center; margin-top: 15px; }
        .add-supply-form select { flex-grow: 1; padding: 10px; border: 1px solid var(--input-border); border-radius: 6px; font-size: 15px; background-color: white; }
        .add-supply-form button { padding: 10px 18px; background: var(--info-color); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 15px; font-weight: 500; transition: background 0.3s; white-space: nowrap; }
        .add-supply-form button:hover { background: #732d91; }

        .order-table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        .order-table th, .order-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-color); }
        .order-table th { background-color: var(--neutral-bg); font-weight: 600; font-size: 0.95em; }
        .order-table td input[type="number"] { width: 70px; padding: 8px; border: 1px solid var(--input-border); border-radius: 4px; font-size: 15px; text-align: center; }
        .order-table td input[type="number"]:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2); }
        .order-actions { text-align: right; margin-top: 20px; }
        .place-order-btn { padding: 12px 25px; background: var(--secondary-color); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: 500; transition: background 0.3s; }
        .place-order-btn:hover { background: #27ae60; }
        .place-order-btn:disabled { background: #bdc3c7; cursor: not-allowed; }

        .back-link-container { margin-top: 30px; text-align: center; }
        .back-link { color: var(--primary-color); text-decoration: none; font-size: 16px; padding: 10px 15px; border-radius: 5px; transition: background-color 0.2s; display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--primary-color); }
        .back-link:hover { background-color: #eaf2f8; }
        .flash-messages { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 1000; width: 90%; max-width: 600px; }
        .flash { padding: 12px 15px; margin-bottom: 10px; border-radius: 6px; color: #fff; font-size: 15px; opacity: 0.95; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        .flash.success { background-color: #2ecc71; } .flash.error { background-color: #e74c3c; } .flash.info { background-color: #3498db; }
        .flash-close { background: none; border: none; color: inherit; font-size: 20px; cursor: pointer; margin-left: 15px; line-height: 1; }
    </style>
</head>
<body>
    <div class="flash-messages">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}{% for category, message in messages %}
            <div class="flash {{ category }}" role="alert"><span>{{ message }}</span><button type="button" class="flash-close" onclick="this.parentElement.style.display='none'">×</button></div>
            {% endfor %}{% endif %}
        {% endwith %}
    </div>
    <div class="container">
        <h1><i class="fas fa-user-tie"></i> Manage & Order: {{ dealer.name }}</h1>
        <div class="section">
            <h2><i class="fas fa-clipboard-list"></i> Products Supplied by this Dealer</h2>
            {% if dealer.supplied_items %}
                <ul class="supplied-items-list">
                {% for item in dealer.supplied_items %}
                    <li>
                        <div class="item-details">
                            <span class="item-name">{{ item.name }}</span>
                            <span class="item-category">({{ item.category }})</span>
                        </div>
                        <form method="POST" action="{{ url_for('remove_item_from_dealer_supply', dealer_id=dealer.id) }}" style="display: inline;">
                            <input type="hidden" name="item_name_to_remove" value="{{ item.name }}">
                            <input type="hidden" name="item_category_to_remove" value="{{ item.category }}">
                            <button type="submit" class="remove-supply-btn" title="Remove from supply list"><i class="fas fa-times"></i> Remove</button>
                        </form>
                    </li>
                {% endfor %}
                </ul>
            {% else %}
                <p class="empty-list-msg">This dealer currently supplies no specific products from your stock.</p>
            {% endif %}
            <form method="POST" action="{{ url_for('add_item_to_dealer_supply', dealer_id=dealer.id) }}" class="add-supply-form">
                <select name="item_to_add_to_supply" required>
                    <option value="" disabled selected>-- Select a stock item to add --</option>
                    {% for stock_item in available_stock_for_dropdown %}
                        <option value="{{ stock_item.category }}__{{ stock_item.name }}">{{ stock_item.display_name }}</option>
                    {% else %}
                        <option value="" disabled>No unassigned stock items available.</option>
                    {% endfor %}
                </select>
                <button type="submit"><i class="fas fa-plus-circle"></i> Add to Supply List</button>
            </form>
        </div>
        <div class="section">
            <h2><i class="fas fa-truck-loading"></i> Order Products from this Dealer</h2>
            {% if dealer_items_for_order %}
                <form method="POST" action="{{ url_for('place_order_from_dealer', dealer_id=dealer.id) }}">
                    <table class="order-table">
                        <thead>
                            <tr><th>Product Name</th><th>Category</th><th>Current Stock</th><th>Order Quantity</th></tr>
                        </thead>
                        <tbody>
                        {% for item_for_order in dealer_items_for_order %}
                            <tr>
                                <td>{{ item_for_order.name }}</td>
                                <td>{{ item_for_order.category }}</td>
                                <td>{{ item_for_order.current_quantity if item_for_order.current_quantity is not none else 'N/A' }}</td>
                                <td>
                                    <input type="number" name="order_qty_{{ loop.index0 }}" min="0" value="0" class="order-qty-input">
                                    <input type="hidden" name="order_name_{{ loop.index0 }}" value="{{ item_for_order.name }}">
                                    <input type="hidden" name="order_category_{{ loop.index0 }}" value="{{ item_for_order.category }}">
                                </td>
                            </tr>
                        {% endfor %}
                        </tbody>
                    </table>
                    <div class="order-actions">
                        <button type="submit" class="place-order-btn" id="placeOrderBtn"><i class="fas fa-check-circle"></i> Place Order</button>
                    </div>
                </form>
            {% else %}
                <p class="empty-list-msg">This dealer has no items assigned to their supply list. Add items above to enable ordering.</p>
            {% endif %}
        </div>
        <div class="back-link-container">
            <a href="{{ url_for('dealers_list') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Dealer List</a>
        </div>
    </div>
    <script>
        setTimeout(function() {
            let flashMessages = document.querySelectorAll('.flash');
            flashMessages.forEach(function(msg) { msg.style.transition = 'opacity 0.5s ease'; msg.style.opacity = '0'; setTimeout(() => msg.style.display = 'none', 500); });
        }, 7000);
        const orderInputs = document.querySelectorAll('.order-qty-input');
        const placeOrderBtn = document.getElementById('placeOrderBtn');
        function checkOrderQuantities() {
            if (!placeOrderBtn) return;
            let totalQuantity = 0;
            orderInputs.forEach(input => { totalQuantity += parseInt(input.value) || 0; });
            placeOrderBtn.disabled = totalQuantity <= 0;
        }
        orderInputs.forEach(input => input.addEventListener('input', checkOrderQuantities));
        if(placeOrderBtn) { checkOrderQuantities(); }
    </script>
</body>
</html>
"""
STOCK_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stock - {{ category|capitalize }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary-color: #3498db; --secondary-color: #2ecc71; --warning-color: #e67e22;
            --danger-color: #e74c3c; --background-light: #f0f4f8; --card-bg: #ffffff;
            --text-dark: #2c3e50; --text-light: #566573; --border-color: #e0e4e8;
            --input-border: #ccc; --form-bg: #f9f9f9; --price-color: #27ae60;
            --logout-btn-bg: #e74c3c; --logout-btn-hover: #c0392b;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--background-light); margin: 0; padding: 0; color: var(--text-dark); }
        .page-header {
            background: linear-gradient(to right, var(--primary-color), #2980b9);
            padding: 15px 30px; color: white;
            display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .page-header .title { font-size: 1.5em; font-weight: 500; }
        .page-header .user-info { font-size: 0.9em; }
        .page-header .user-info a { color: white; text-decoration: underline; margin-left:10px; }
        .page-header .logout-btn {
            background-color: var(--logout-btn-bg); color: white; padding: 8px 15px;
            border: none; border-radius: 5px; text-decoration: none; font-size: 14px;
            transition: background-color 0.3s ease; display: inline-flex; align-items: center; gap: 5px;
        }
        .page-header .logout-btn:hover { background-color: var(--logout-btn-hover); }
        .container { max-width: 900px; margin: 20px auto; padding: 20px; background: var(--card-bg); border-radius: 12px; box-shadow: 0 6px 15px rgba(0, 0, 0, 0.1); }
        h1 { text-align: center; color: var(--primary-color); margin-top: 10px; margin-bottom: 20px; font-weight: 500; letter-spacing: 0.5px; }
        h1 i { margin-right: 10px; }
        h2 { color: #34495e; font-size: 1.4em; margin-top: 25px; margin-bottom: 15px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; font-weight: 500; }
        h2 i { margin-right: 8px; color: var(--text-light); }
        .categories { display: flex; justify-content: center; flex-wrap: wrap; gap: 12px; margin-bottom: 25px; padding-bottom: 20px; border-bottom: 1px solid var(--border-color); }
        .category-link {
            padding: 10px 20px; background: #eaf2f8; color: var(--primary-color); border: 1px solid #d6eaf8;
            border-radius: 25px; cursor: pointer; font-size: 15px; font-weight: 500; text-decoration: none;
            transition: all 0.3s ease; display: inline-flex; align-items: center; gap: 8px;
        }
        .category-link.active, .category-link:hover { background: var(--primary-color); color: white; border-color: var(--primary-color); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(52, 152, 219, 0.2); }
        .category-link.active { font-weight: 600; } .category-link i { font-size: 17px; transition: transform 0.3s ease; }
        .category-link:hover i { transform: scale(1.1); }
        .stock-list { list-style: none; padding: 0; margin-top: 20px; }
        .stock-list li { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; padding: 18px 20px; margin-bottom: 14px; background: #fdfdfd; border: 1px solid var(--border-color); border-radius: 8px; transition: border-color 0.2s ease, box-shadow 0.2s ease; }
        .stock-list li:hover { border-color: #bdc3c7; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        .stock-item-info { flex-grow: 1; line-height: 1.5; }
        .item-name { font-weight: 600; color: var(--text-dark); font-size: 1.05em; }
        .item-details { font-size: 0.95em; color: var(--text-light); margin-top: 4px; }
        .item-price { font-weight: bold; color: var(--price-color); } .item-quantity { font-style: italic; }
        .item-quantity.low-stock { color: var(--warning-color); font-weight: bold; background-color: #fef5e7; padding: 2px 5px; border-radius: 3px; }
        .item-quantity.out-of-stock { color: var(--danger-color); font-weight: bold; background-color: #fdedec; padding: 2px 5px; border-radius: 3px; }
        .add-to-cart-btn {
            background: var(--warning-color); color: white; border: none; padding: 9px 16px; border-radius: 6px;
            cursor: pointer; transition: background 0.3s ease, transform 0.2s ease; text-decoration: none;
            font-size: 14px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
        }
        .add-to-cart-btn:hover { background: #d35400; transform: scale(1.05); }
        .add-to-cart-btn[disabled] { background: #bdc3c7; cursor: not-allowed; transform: none; opacity: 0.7; }
        .add-to-cart-btn[disabled]:hover { background: #bdc3c7; }
        .add-stock-form { margin-top: 30px; padding: 25px; background-color: var(--form-bg); border: 1px solid var(--border-color); border-radius: 8px; }
        .add-stock-form h3 { margin-top: 0; margin-bottom: 20px; color: #34495e; font-weight: 500; text-align: center; }
        .add-stock-form .form-row { margin-bottom: 15px; display: flex; flex-wrap: wrap; gap: 15px; align-items: center; justify-content: center; }
        .add-stock-form input[type="text"], .add-stock-form input[type="number"] { padding: 11px 14px; border: 1px solid var(--input-border); border-radius: 6px; font-size: 15px; box-sizing: border-box; transition: border-color 0.3s ease, box-shadow 0.3s ease; flex-grow: 1; min-width: 120px; }
        .add-stock-form input[type="number"] { max-width: 130px; flex-grow: 0; }
        .add-stock-form input:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2); }
        .add-stock-form button[type="submit"] { padding: 11px 20px; background: var(--secondary-color); color: white; border: none; border-radius: 6px; cursor: pointer; transition: background 0.3s ease, transform 0.2s ease; font-size: 15px; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; margin-left: auto; }
        .add-stock-form button[type="submit"]:hover { background: #27ae60; transform: translateY(-1px); }
        .empty-stock { text-align: center; color: #777; margin-top: 25px; font-style: italic; padding: 15px; background-color: var(--form-bg); border-radius: 6px; border: 1px dashed var(--border-color); }
        .action-buttons-footer { margin-top: 35px; text-align: center; display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; }
        .action-buttons-footer .back-link { 
            color: var(--primary-color); text-decoration: none; font-size: 16px; padding: 10px 15px;
            border-radius: 5px; transition: background-color 0.2s ease, text-decoration 0.2s ease;
            display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--primary-color);
        }
        .action-buttons-footer .back-link:hover { background-color: #eaf2f8; text-decoration: none; }
        .action-buttons-footer .view-cart-link { background-color: var(--warning-color); color:white; border-color:var(--warning-color); }
        .flash-messages { position: fixed; top: 80px; left: 50%; transform: translateX(-50%); z-index: 1000; width: 90%; max-width: 600px; }
        .flash { padding: 12px 15px; margin-bottom: 10px; border-radius: 6px; color: #fff; font-size: 15px; opacity: 0.95; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        .flash.success { background-color: #2ecc71; } .flash.error { background-color: #e74c3c; }
        .flash.info { background-color: #3498db; } .flash.warning { background-color: #f39c12; color: #333; }
        .flash-close { background: none; border: none; color: inherit; font-size: 20px; cursor: pointer; margin-left: 15px; line-height: 1; }
    </style>
</head>
<body>
    <div class="page-header">
        <span class="title"><i class="fas fa-pills"></i> Pharmacy Stock</span>
        <div class="user-info">
        {% if session.get('customer_email') %}
            Logged in as: {{ session.get('customer_email') }}
            <a href="{{ url_for('customer_logout') }}" class="logout-btn" style="margin-left:15px; background-color: #f39c12;"><i class="fas fa-sign-out-alt"></i> Logout</a>
        {% elif session.get('admin_logged_in') %}
            Admin View
             <a href="{{ url_for('dashboard') }}" class="back-link" style="margin-left:15px; padding: 8px 12px; color:white; border-color:white; background:transparent;"><i class="fas fa-arrow-left"></i> Dashboard</a>
        {% endif %}
        </div>
    </div>
    <div class="flash-messages">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="flash {{ category }}" role="alert">
                    <span>{{ message }}</span>
                    <button type="button" class="flash-close" onclick="this.parentElement.style.display='none'">×</button>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
    <div class="container">
        <h1><i class="fas fa-boxes-stacked"></i> Stock Management</h1>
        <div class="categories">
            <a href="{{ url_for('show_stock', category='tablet') }}" class="category-link {% if category == 'tablet' %}active{% endif %}"><i class="fas fa-tablets"></i> Tablets</a>
            <a href="{{ url_for('show_stock', category='painkiller') }}" class="category-link {% if category == 'painkiller' %}active{% endif %}"><i class="fas fa-pills"></i> Painkillers</a>
            <a href="{{ url_for('show_stock', category='bodylotion') }}" class="category-link {% if category == 'bodylotion' %}active{% endif %}"><i class="fas fa-spa"></i> Body Lotions</a>
            <a href="{{ url_for('show_stock', category='coughsyrup') }}" class="category-link {% if category == 'coughsyrup' %}active{% endif %}"><i class="fas fa-prescription-bottle"></i> Cough Syrups</a>
        </div>
        <h2><i class="fas fa-tag"></i> {{ category|capitalize }} Stock</h2>
        <ul class="stock-list">
            {% if stock_items %}
                {% for item in stock_items %}
                    <li>
                        <div class="stock-item-info">
                            <div class="item-name">{{ item.name }}</div>
                            <div class="item-details">Price: <span class="item-price">{{ item.price | inr }}</span> |
                                {% set qty = item.quantity | default(0) | int %}
                                Quantity: {% if qty <= 0 %}<span class="item-quantity out-of-stock">Out of Stock</span>
                                {% elif qty <= 10 %}<span class="item-quantity low-stock">{{ qty }} (Low)</span>
                                {% else %}<span class="item-quantity">{{ qty }}</span>{% endif %}
                            </div>
                        </div>
                        {% if session.get('customer_email') %}
                        <a href="{{ url_for('add_to_cart', category=category, item_name=item.name) }}" class="add-to-cart-btn" {% if item.quantity <= 0 %}disabled title="Out of stock"{% endif %}>
                           <i class="fas fa-cart-plus"></i> Add to Cart
                        </a>
                        {% endif %}
                    </li>
                {% endfor %}
            {% else %}
                 <p class="empty-stock">No items in {{ category|capitalize }} stock.</p>
            {% endif %}
        </ul>
        {% if session.get('admin_logged_in') %}
        <form method="POST" action="{{ url_for('add_stock', category=category) }}" class="add-stock-form">
             <h3>Add New Item to {{ category|capitalize }}</h3>
             <div class="form-row">
                 <input type="text" name="item_name" placeholder="New Item Name" required>
                 <input type="number" name="item_price" placeholder="Price (₹)" required min="0.01" step="0.01" title="Price per unit">
                 <input type="number" name="item_quantity" placeholder="Quantity" required min="1" title="Initial quantity">
                 <button type="submit"><i class="fas fa-plus-circle"></i> Add Item</button>
             </div>
        </form>
        {% endif %}
        <div class="action-buttons-footer">
             {% if session.get('customer_email') %}
                 <a href="{{ url_for('show_prescription') }}" class="back-link view-cart-link">
                    <i class="fas fa-shopping-cart"></i> View Cart ({{ cart|length }})
                </a>
            {% elif session.get('admin_logged_in') %}
                 <a href="{{ url_for('dashboard') }}" class="back-link">
                    <i class="fas fa-arrow-left"></i> Back to Dashboard
                </a>
            {% endif %}
            {% if not session.get('admin_logged_in') and not session.get('customer_email') %}
                 <a href="{{ url_for('login') }}" class="back-link"><i class="fas fa-sign-in-alt"></i> Login to Shop</a>
            {% endif %}
        </div>
    </div>
    <script>
        setTimeout(function() {
            let flashMessages = document.querySelectorAll('.flash');
            flashMessages.forEach(function(msg) {
                msg.style.transition = 'opacity 0.5s ease'; msg.style.opacity = '0';
                setTimeout(() => msg.style.display = 'none', 500);
            });
        }, 5000);
    </script>
</body>
</html>
"""
PRESCRIPTION_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pharmacy Cart</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary-color: #3498db; --secondary-color: #2ecc71; --danger-color: #e74c3c;
            --print-color: #9b59b6; --back-color: #95a5a6; --background-light: #f0f4f8;
            --card-bg: #ffffff; --text-dark: #333; --text-light: #555;
            --border-color: #e0e4e8; --price-color: #27ae60;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--background-light); margin: 0; padding: 25px; color: var(--text-dark); }
        .container { max-width: 750px; margin: 20px auto; padding: 30px; background: var(--card-bg); border-radius: 12px; box-shadow: 0 6px 15px rgba(0, 0, 0, 0.1); }
        .header-section { text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid var(--border-color); }
        .header-section img { width: 55px; height: auto; margin-bottom: 12px; opacity: 0.9; }
        .header-section h1 { color: var(--primary-color); margin: 0; font-size: 1.9em; font-weight: 500; }
        h2 { text-align: center; color: #34495e; margin-bottom: 25px; font-size: 1.5em; font-weight: 500; }
        h2 i { margin-right: 10px; color: var(--primary-color); }
        .cart-list { list-style: none; padding: 0; margin: 0 0 25px 0; }
        .cart-list li { display: flex; justify-content: space-between; align-items: center; padding: 14px 10px; border-bottom: 1px solid #f0f0f0; transition: background-color 0.2s ease; }
        .cart-list li:last-child { border-bottom: none; } .cart-list li:hover { background-color: #f9f9f9; }
        .item-info { flex-grow: 1; margin-right: 15px; color: var(--text-light); }
        .item-name { font-weight: 500; color: var(--text-dark); }
        .item-price { font-weight: bold; color: var(--price-color); min-width: 90px; text-align: right; font-size: 1.05em; }
        .remove-item-btn { background: none; border: none; color: var(--danger-color); cursor: pointer; font-size: 1.2em; padding: 5px 8px; margin-left: 10px; transition: color 0.2s ease, transform 0.2s ease; line-height: 1; }
        .remove-item-btn:hover { color: #c0392b; transform: scale(1.1); }
        .total-section { text-align: right; margin-top: 25px; padding-top: 18px; border-top: 2px solid #ccc; font-size: 1.3em; font-weight: bold; }
        .total-label { color: var(--text-light); margin-right: 10px; font-weight: 500; }
        .total-amount { color: var(--danger-color); }
        .action-buttons { margin-top: 35px; display: flex; flex-direction: column; gap: 15px; }
        .payment-form-row { display: flex; flex-wrap: wrap; gap: 15px; align-items: center; justify-content: center; background-color: var(--background-light); padding: 15px; border-radius: 8px; border: 1px solid var(--border-color); }
        .payment-form { display: contents; }
        .payment-form label { font-weight: 500; margin-right: 5px; color: var(--text-light); }
        .payment-form select { padding: 9px 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 15px; background-color: white; min-width: 100px; cursor: pointer; }
        .action-button { padding: 10px 20px; border-radius: 6px; font-size: 15px; font-weight: 500; cursor: pointer; text-decoration: none; border: none; display: inline-flex; align-items: center; justify-content: center; gap: 8px; transition: all 0.3s ease; flex-grow: 1; min-width: 150px; }
        .action-button:hover { opacity: 0.9; transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        .action-button i { font-size: 1.1em; }
        .pay-button { background-color: var(--secondary-color); color: white; }
        .print-button { background-color: var(--print-color); color: white; }
        .bottom-buttons { display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; margin-top: 15px; }
        .back-link { background-color: var(--back-color); color: white; } 
        .back-to-stock-link { background-color: var(--primary-color); color:white; } 
        .empty-cart { text-align: center; color: #777; font-style: italic; margin: 50px 0; padding: 20px; background-color: #f9f9f9; border: 1px dashed #ddd; border-radius: 8px; }
        .empty-cart i { display: block; font-size: 2em; margin-bottom: 10px; color: #ccc;}
        @media print {
            body { background: white; padding: 0; margin: 10mm; font-size: 12pt; }
            .container { box-shadow: none; border: none; max-width: 100%; padding: 0; margin: 0; }
            .header-section { border-bottom: 1px solid #000; padding-bottom: 10px; margin-bottom: 20px; text-align: left; }
            .header-section img { display: none; } .header-section h1 { color: #000; font-size: 16pt; }
            h2 { text-align: left; font-size: 14pt; margin-bottom: 15px; border-bottom: 1px dashed #ccc; padding-bottom: 5px; }
            .action-buttons, .back-link-container, .remove-item-btn, .flash-messages { display: none; }
            .cart-list { margin-bottom: 15px; } .cart-list li { border-bottom: 1px dotted #999; padding: 8px 0; }
            .item-info, .item-price, .item-name { color: #000 !important; } .item-price { font-size: 1em; }
            .total-section { border-top: 1px solid #000; color: #000; text-align: right; margin-top: 20px; padding-top: 10px; font-size: 13pt;}
            .total-amount { color: #000; }
        }
        .flash-messages { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 1000; width: 90%; max-width: 600px; }
        .flash { padding: 12px 15px; margin-bottom: 10px; border-radius: 6px; color: #fff; font-size: 15px; opacity: 0.95; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        .flash.success { background-color: #2ecc71; } .flash.error { background-color: #e74c3c; }
        .flash.info { background-color: #3498db; } .flash.warning { background-color: #f39c12; color: #333; }
        .flash-close { background: none; border: none; color: inherit; font-size: 20px; cursor: pointer; margin-left: 15px; line-height: 1; }
    </style>
</head>
<body>
    <div class="flash-messages">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="flash {{ category }}" role="alert">
                    <span>{{ message }}</span>
                    <button type="button" class="flash-close" onclick="this.parentElement.style.display='none'">×</button>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
    <div class="container">
        <div class="header-section">
             <img src="https://cdn-icons-png.flaticon.com/512/2966/2966327.png" alt="Pharmacy Logo">
             <h1>Pharmacy Cart</h1>
        </div>
        <h2><i class="fas fa-shopping-cart"></i> Your Items</h2>
        {% if cart %}
            <ul class="cart-list">
                {% for item in cart %}
                    <li>
                        <div class="item-info"><span class="item-name">{{ item.name }}</span></div>
                        <div class="item-price">{{ item.price | inr }}</div>
                        <form method="POST" action="{{ url_for('remove_from_cart', item_name=item.name) }}" style="display: inline;">
                             <button type="submit" class="remove-item-btn" title="Remove {{ item.name }}"><i class="fas fa-times-circle"></i></button>
                        </form>
                    </li>
                {% endfor %}
            </ul>
            <div class="total-section">
                <span class="total-label">Total:</span><span class="total-amount">{{ total | inr }}</span>
            </div>
            <div class="action-buttons">
                <div class="payment-form-row">
                    <form method="POST" action="{{ url_for('process_payment') }}" class="payment-form">
                        <label for="payment_method"><i class="fas fa-money-check-alt"></i> Payment:</label>
                        <select name="payment_method" id="payment_method">
                            <option value="Cash">Cash</option><option value="Card">Card</option><option value="UPI">UPI</option>
                        </select>
                        <button type="submit" class="action-button pay-button"><i class="fas fa-credit-card"></i> Process Payment</button>
                    </form>
                </div>
                <div class="bottom-buttons">
                    <button onclick="window.print()" class="action-button print-button"><i class="fas fa-print"></i> Print Receipt</button>
                    <a href="{{ url_for('stock_categories') }}" class="action-button back-to-stock-link"><i class="fas fa-pills"></i> Continue Shopping</a>
                </div>
            </div>
        {% else %}
             <div class="empty-cart">
                <i class="fas fa-cart-arrow-down"></i> <p>Your cart is empty.</p>
                <p><a href="{{ url_for('stock_categories') }}">Browse stock</a> to add items.</p>
             </div>
             <div class="back-link-container" style="text-align: center;">
                 <a href="{{ url_for('stock_categories') }}" class="action-button back-to-stock-link"><i class="fas fa-pills"></i> Browse Stock</a>
             </div>
        {% endif %}
    </div>
    <script>
        setTimeout(function() {
            let flashMessages = document.querySelectorAll('.flash');
            flashMessages.forEach(function(msg) {
                msg.style.transition = 'opacity 0.5s ease'; msg.style.opacity = '0';
                setTimeout(() => msg.style.display = 'none', 500);
            });
        }, 5000);
    </script>
</body>
</html>
"""
CASHIER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cashier - Transaction History</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
         :root {
            --primary-color: #3498db; --secondary-color: #2ecc71; --danger-color: #e74c3c;
            --info-color: #9b59b6; --back-color: #95a5a6; --background-light: #f0f4f8;
            --card-bg: #ffffff; --text-dark: #333; --text-light: #555; --border-color: #e0e4e8;
            --input-border: #ccc; --form-bg: #f9f9f9; --table-header-bg: var(--primary-color);
            --table-row-hover: #eaf2f8; --price-color: #27ae60; --fake-data-bg: #fff9e6;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--background-light); margin: 0; padding: 25px; color: var(--text-dark); }
        .container { max-width: 1000px; margin: 20px auto; padding: 30px; background: var(--card-bg); border-radius: 12px; box-shadow: 0 6px 15px rgba(0, 0, 0, 0.1); }
        h1 { text-align: center; color: var(--primary-color); margin-top: 0; margin-bottom: 15px; font-weight: 500; }
        h1 i { margin-right: 10px; }
        h2 { text-align: center; color: #34495e; font-size: 1.5em; margin-top: 0; margin-bottom: 30px; font-weight: 400; }
        .filter-form { margin-bottom: 35px; padding: 20px 25px; background-color: var(--form-bg); border: 1px solid var(--border-color); border-radius: 8px; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; justify-content: center; }
        .filter-group { display: flex; align-items: center; gap: 8px; }
        .filter-form label { font-weight: 500; color: var(--text-light); }
        .filter-form input[type="date"], .filter-form input[type="text"] { padding: 9px 12px; border: 1px solid var(--input-border); border-radius: 6px; font-size: 15px; min-width: 160px; background-color: white; transition: border-color 0.3s ease, box-shadow 0.3s ease; }
        .filter-form input:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2); }
        .filter-form button, .filter-form a.clear-filter { padding: 9px 18px; color: white; border: none; border-radius: 6px; cursor: pointer; transition: background 0.3s ease, transform 0.2s ease; font-size: 15px; font-weight: 500; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
        .filter-form button { background: var(--primary-color); } .filter-form button:hover { background: #2980b9; transform: translateY(-1px); }
        .filter-form a.clear-filter { background: var(--back-color); } .filter-form a.clear-filter:hover { background: #7f8c8d; transform: translateY(-1px); }
        .table-container { overflow-x: auto; }
        .transaction-table { width: 100%; border-collapse: collapse; margin-top: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.08); border: 1px solid var(--border-color); }
        .transaction-table th, .transaction-table td { padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
        .transaction-table th { background-color: var(--table-header-bg); color: white; font-weight: 600; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; }
        .transaction-table tr:nth-child(even) { background-color: #fcfcfc; } .transaction-table tr:hover { background-color: var(--table-row-hover); }
        .transaction-table td { font-size: 15px; color: var(--text-light); }
        .transaction-table tr.fake-data { background-color: var(--fake-data-bg); font-style: italic; opacity: 0.8; }
        .transaction-table tr.fake-data:hover { background-color: #fff3d4; } .transaction-table tr.fake-data td { color: #8a6d3b; }
        .col-id { width: 6%; font-weight: 500; color: var(--text-dark); } tr.fake-data .col-id { font-weight: normal; }
        .col-time { width: 18%; } .col-items { width: 40%; line-height: 1.4; font-size: 14px; }
        .col-payment { width: 12%; text-align: center; }
        .col-total { width: 14%; text-align: right; font-weight: bold; color: var(--price-color); font-size: 1.05em; }
        tr.fake-data .col-total { color: #8a6d3b; }
        .payment-badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; color: white; background-color: #bdc3c7; }
        .payment-badge.cash { background-color: var(--secondary-color); } .payment-badge.card { background-color: var(--info-color); } .payment-badge.upi { background-color: var(--primary-color); }
        .no-results { text-align: center; color: #777; margin-top: 40px; font-style: italic; padding: 25px; background-color: var(--form-bg); border-radius: 8px; border: 1px dashed var(--border-color); }
        .no-results i { display: block; font-size: 2em; margin-bottom: 10px; color: #ccc;}
        .no-results.with-fakes { background-color: var(--fake-data-bg); border-color: #fbeed5; color: #8a6d3b; }
        .back-link-container { margin-top: 35px; text-align: center; }
        .back-link { color: var(--primary-color); text-decoration: none; font-size: 16px; padding: 10px 15px; border-radius: 5px; transition: background-color 0.2s ease, text-decoration 0.2s ease; display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--primary-color); }
        .back-link:hover { background-color: #eaf2f8; text-decoration: none; }
        .flash-messages { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 1000; width: 90%; max-width: 600px; }
        .flash { padding: 12px 15px; margin-bottom: 10px; border-radius: 6px; color: #fff; font-size: 15px; opacity: 0.95; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        .flash.success { background-color: #2ecc71; } .flash.error { background-color: #e74c3c; }
        .flash.info { background-color: #3498db; } .flash.warning { background-color: #f39c12; color: #333; }
        .flash-close { background: none; border: none; color: inherit; font-size: 20px; cursor: pointer; margin-left: 15px; line-height: 1; }
    </style>
</head>
<body>
    <div class="flash-messages">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}{% for category, message in messages %}
            <div class="flash {{ category }}" role="alert"><span>{{ message }}</span><button type="button" class="flash-close" onclick="this.parentElement.style.display='none'">×</button></div>
            {% endfor %}{% endif %}
        {% endwith %}
    </div>
    <div class="container">
        <h1><i class="fas fa-cash-register"></i> Cashier</h1><h2>Transaction History</h2>
        <form method="GET" action="{{ url_for('cashier') }}" class="filter-form">
            <div class="filter-group"><label for="filter_date"><i class="fas fa-calendar-alt"></i> Date:</label><input type="date" id="filter_date" name="filter_date" value="{{ filter_date or '' }}"></div>
            <div class="filter-group"><label for="filter_medicine"><i class="fas fa-search"></i> Item:</label><input type="text" id="filter_medicine" name="filter_medicine" placeholder="Search item..." value="{{ filter_medicine or '' }}"></div>
            <button type="submit"><i class="fas fa-filter"></i> Filter</button>
            {% if filter_date or filter_medicine %}<a href="{{ url_for('cashier') }}" class="clear-filter"><i class="fas fa-times"></i> Clear</a>{% endif %}
        </form>
        <div class="table-container">
            {% if transactions %}
                <table class="transaction-table">
                    <thead><tr><th class="col-id">ID</th><th class="col-time">Timestamp</th><th class="col-items">Items</th><th class="col-payment">Payment</th><th class="col-total">Total</th></tr></thead>
                    <tbody>
                        {% for transaction in transactions %}<tr class="{{ 'fake-data' if transaction.id < 0 else '' }}">
                                <td class="col-id">{{ transaction.id if transaction.id > 0 else 'DEMO' }}</td>
                                <td class="col-time">{{ transaction.timestamp.strftime('%d %b %Y, %I:%M %p') }}</td>
                                <td class="col-items">{{ transaction.items }}</td>
                                <td class="col-payment"><span class="payment-badge {{ transaction.payment_method | lower }}">{{ transaction.payment_method }}</span></td>
                                <td class="col-total">{{ transaction.total_amount | inr }}</td></tr>{% endfor %}
                    </tbody></table>
                {% if transactions and transactions|length > 0 and transactions[0].id < 0 and not (filter_date or filter_medicine) %}<p class="no-results with-fakes" style="margin-top: 15px;"><i class="fas fa-info-circle"></i> No real transactions found. Showing sample data as no filters are active.</p>{% endif %}
            {% else %}<div class="no-results"><i class="fas fa-folder-open"></i><p>No transactions found matching your criteria.</p></div>{% endif %}
        </div>
        <div class="back-link-container"><a href="{{ url_for('dashboard') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Dashboard</a></div>
    </div>
    <script>
        setTimeout(function() {
            let flashMessages = document.querySelectorAll('.flash');
            flashMessages.forEach(function(msg) {
                msg.style.transition = 'opacity 0.5s ease'; msg.style.opacity = '0';
                setTimeout(() => msg.style.display = 'none', 500); });
        }, 5000);
    </script>
</body>
</html>
"""

# --- Helper Functions ---
def get_dealer_by_id(dealer_id_to_find):
    return next((d for d in dealers if d.get("id") == dealer_id_to_find), None)

def find_stock_item_info(category_name, item_name_to_find):
    if category_name in stock:
        for index, item_data in enumerate(stock[category_name]):
            if item_data.get('name') == item_name_to_find:
                return index, item_data
    return -1, None

# --- Flask Routes ---

@app.route("/", methods=["GET", "POST"])
def login():
    admin_error = None
    customer_error = None
    persisted_customer_email = request.form.get('customer_email', '') if request.method == 'POST' else request.args.get('persisted_email', '')

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "admin":
            email = request.form.get("email")
            password = request.form.get("password")
            if email in admin_users and admin_users[email] == password:
                session['admin_logged_in'] = True
                session.pop('customer_email', None)
                flash("Admin login successful!", "success")
                return redirect(url_for("dashboard"))
            else:
                admin_error = "Invalid Admin Email or Password."
        
        elif form_type == "customer_recaptcha_login": 
            customer_email_from_form = request.form.get("customer_email", "").strip().lower()
            recaptcha_response = request.form.get('g-recaptcha-response')
            
            persisted_customer_email = customer_email_from_form 

            if not customer_email_from_form:
                customer_error = "Email is required."
            elif "@" not in customer_email_from_form or "." not in customer_email_from_form.split('@')[-1]:
                customer_error = "Please enter a valid-looking email address."
            elif not recaptcha_response:
                customer_error = "Please complete the 'I'm not a robot' verification."
            else:
                secret_key_from_config = app.config['RECAPTCHA_SECRET_KEY']
                site_key_from_config = app.config['RECAPTCHA_SITE_KEY']

                if (secret_key_from_config == INTERNAL_PLACEHOLDER_SECRET_KEY or
                    site_key_from_config == INTERNAL_PLACEHOLDER_SITE_KEY or
                    not secret_key_from_config or not site_key_from_config):
                    customer_error = "reCAPTCHA is not configured correctly on the server (keys might be placeholders or missing). Please obtain valid keys from Google reCAPTCHA."
                    print(f"FATAL: RECAPTCHA keys appear to be unconfigured placeholders or are missing. Please check app.config.")
                else:
                    payload = {'secret': secret_key_from_config, 'response': recaptcha_response, 'remoteip': request.remote_addr}
                    try:
                        verify_response = requests.post('https://www.google.com/recaptcha/api/siteverify', data=payload, timeout=10)
                        verify_response.raise_for_status() 
                        result = verify_response.json()

                        if result.get('success'):
                            session['customer_email'] = customer_email_from_form
                            session.pop('admin_logged_in', None)
                            flash(f"Welcome, {customer_email_from_form}! Login successful.", "success")
                            return redirect(url_for("stock_categories"))
                        else:
                            customer_error = "reCAPTCHA verification failed. Please try again."
                            if result.get('error-codes'):
                                customer_error += f" (Errors: {', '.join(result.get('error-codes'))})"
                                print(f"reCAPTCHA error codes: {result.get('error-codes')}")
                    except requests.exceptions.Timeout:
                        customer_error = "Could not verify reCAPTCHA: The request timed out. Please try again."
                        print("Error verifying reCAPTCHA: Timeout")
                    except requests.exceptions.RequestException as e:
                        customer_error = "Could not verify reCAPTCHA due to a network or server issue. Please try again later."
                        print(f"Error verifying reCAPTCHA: {e}")
    
    current_recaptcha_site_key = app.config['RECAPTCHA_SITE_KEY']
    if current_recaptcha_site_key == INTERNAL_PLACEHOLDER_SITE_KEY:
        flash("Warning: reCAPTCHA Site Key is a placeholder. The reCAPTCHA widget may not display correctly and will fail verification.", "warning")

    return render_template_string(LOGIN_TEMPLATE,
                                  admin_error=admin_error,
                                  customer_error=customer_error,
                                  persisted_customer_email=persisted_customer_email,
                                  recaptcha_site_key=current_recaptcha_site_key)


@app.route("/admin_logout")
@admin_required
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("Admin logged out.", "info")
    return redirect(url_for('login'))

@app.route("/customer_logout")
def customer_logout():
    if 'customer_email' in session:
        session.pop('customer_email', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route("/dashboard")
@admin_required
def dashboard():
    return render_template_string(DASHBOARD_TEMPLATE)

@app.route("/dealers")
@admin_required
def dealers_list():
    return render_template_string(DEALER_TEMPLATE, dealers=sorted(dealers, key=lambda p: p.get('id',0)))

@app.route("/add_dealer", methods=["POST"])
@admin_required
def add_dealer():
    global next_dealer_id
    name = request.form.get("dealer_name", "").strip()
    if not name:
        flash("Dealer name cannot be empty.", "error")
    elif any(d['name'].lower() == name.lower() for d in dealers):
        flash(f"Dealer '{name}' already exists.", "warning")
    else:
        dealers.append({"id": next_dealer_id, "name": name, "supplied_items": []})
        next_dealer_id += 1
        flash(f"Dealer '{name}' added successfully.", "success")
    return redirect(url_for("dealers_list"))

@app.route("/remove_dealer/<int:dealer_id>", methods=["POST"])
@admin_required
def remove_dealer(dealer_id):
    global dealers
    dealer_to_remove = get_dealer_by_id(dealer_id)
    if dealer_to_remove:
        dealers = [d for d in dealers if d.get("id") != dealer_id]
        flash(f"Dealer '{dealer_to_remove['name']}' removed successfully.", "success")
    else:
        flash(f"Dealer ID {dealer_id} not found.", "error")
    return redirect(url_for("dealers_list"))

@app.route('/dealer/<int:dealer_id>/manage', methods=['GET'])
@admin_required
def manage_dealer_products_and_order(dealer_id):
    dealer = get_dealer_by_id(dealer_id)
    if not dealer:
        flash(f"Dealer with ID {dealer_id} not found.", "error")
        return redirect(url_for('dealers_list'))

    dealer_supplied_set = set((item['category'], item['name']) for item in dealer['supplied_items'])
    available_stock_for_dropdown = []
    for category, items_in_cat in stock.items():
        for item_data in items_in_cat:
            if (category, item_data['name']) not in dealer_supplied_set:
                available_stock_for_dropdown.append({
                    'category': category,
                    'name': item_data['name'],
                    'display_name': f"{item_data['name']} ({category}) - Stock: {item_data.get('quantity',0)}"
                })
    available_stock_for_dropdown.sort(key=lambda x: x['display_name'])

    dealer_items_for_order = []
    for supplied_item in dealer['supplied_items']:
        cat = supplied_item['category']
        name = supplied_item['name']
        _, stock_data = find_stock_item_info(cat, name)
        dealer_items_for_order.append({
            'name': name,
            'category': cat,
            'current_quantity': stock_data.get('quantity', 'N/A') if stock_data else 'N/A'
        })

    return render_template_string(MANAGE_DEALER_PRODUCTS_ORDER_TEMPLATE,
                                  dealer=dealer,
                                  available_stock_for_dropdown=available_stock_for_dropdown,
                                  dealer_items_for_order=dealer_items_for_order)

@app.route('/dealer/<int:dealer_id>/add_supply', methods=['POST'])
@admin_required
def add_item_to_dealer_supply(dealer_id):
    dealer = get_dealer_by_id(dealer_id)
    if not dealer:
        flash(f"Dealer with ID {dealer_id} not found.", "error"); return redirect(url_for('dealers_list'))

    item_to_add_str = request.form.get('item_to_add_to_supply')
    if not item_to_add_str or '__' not in item_to_add_str:
        flash("Invalid item selected.", "error"); return redirect(url_for('manage_dealer_products_and_order', dealer_id=dealer_id))
    try:
        category, name = item_to_add_str.split('__', 1)
    except ValueError:
        flash("Malformed item data.", "error"); return redirect(url_for('manage_dealer_products_and_order', dealer_id=dealer_id))
    
    _, stock_item_data = find_stock_item_info(category, name)
    if not stock_item_data:
        flash(f"Item '{name}' ({category}) not in stock.", "error"); return redirect(url_for('manage_dealer_products_and_order', dealer_id=dealer_id))

    if any(s_item['name'] == name and s_item['category'] == category for s_item in dealer['supplied_items']):
        flash(f"'{name}' ({category}) already in supply list.", "warning")
    else:
        dealer['supplied_items'].append({'category': category, 'name': name})
        flash(f"Added '{name}' ({category}) to {dealer['name']}'s supply.", "success")
    return redirect(url_for('manage_dealer_products_and_order', dealer_id=dealer_id))

@app.route('/dealer/<int:dealer_id>/remove_supply', methods=['POST'])
@admin_required
def remove_item_from_dealer_supply(dealer_id):
    dealer = get_dealer_by_id(dealer_id)
    if not dealer:
        flash(f"Dealer ID {dealer_id} not found.", "error"); return redirect(url_for('dealers_list'))

    item_name = request.form.get('item_name_to_remove')
    item_category = request.form.get('item_category_to_remove')
    if not item_name or not item_category:
        flash("Missing item details.", "error"); return redirect(url_for('manage_dealer_products_and_order', dealer_id=dealer_id))

    initial_len = len(dealer['supplied_items'])
    dealer['supplied_items'] = [s for s in dealer['supplied_items'] if not (s['name'] == item_name and s['category'] == item_category)]
    if len(dealer['supplied_items']) < initial_len:
        flash(f"Removed '{item_name}' ({item_category}) from {dealer['name']}'s supply.", "success")
    else:
        flash(f"Item not found in supply list.", "warning")
    return redirect(url_for('manage_dealer_products_and_order', dealer_id=dealer_id))

@app.route('/dealer/<int:dealer_id>/order', methods=['POST'])
@admin_required
def place_order_from_dealer(dealer_id):
    dealer = get_dealer_by_id(dealer_id)
    if not dealer:
        flash(f"Dealer ID {dealer_id} not found.", "error"); return redirect(url_for('dealers_list'))

    items_ordered_summary, items_error = [], []
    total_updated = 0
    i = 0
    while True:
        qty_str = request.form.get(f'order_qty_{i}')
        if qty_str is None: break
        item_name = request.form.get(f'order_name_{i}')
        item_category = request.form.get(f'order_category_{i}')
        
        if not item_name or not item_category: items_error.append(f"Malformed data (index {i})"); i+=1; continue
        try:
            qty = int(qty_str)
            if qty < 0: items_error.append(f"Negative qty for '{item_name}'."); i+=1; continue
            if qty == 0: i+=1; continue
        except ValueError: items_error.append(f"Invalid qty for '{item_name}'."); i+=1; continue

        idx, item_data = find_stock_item_info(item_category, item_name)
        if item_data:
            new_qty = item_data.get('quantity', 0) + qty
            stock[item_category][idx]['quantity'] = new_qty
            items_ordered_summary.append(f"{item_name}: +{qty} (now {new_qty})")
            total_updated += 1
        else: items_error.append(f"'{item_name}' ({item_category}) not in stock.")
        i += 1

    if total_updated > 0: flash(f"Order for {dealer['name']} placed. {total_updated} items updated: {'; '.join(items_ordered_summary)}", "success")
    else: flash(f"No items updated from order for {dealer['name']}.", "info")
    if items_error: flash(f"Order issues: {'; '.join(items_error)}", "warning")
    return redirect(url_for('manage_dealer_products_and_order', dealer_id=dealer_id))

@app.route("/stock")
@customer_or_admin_required
def stock_categories():
    if not stock or not any(stock.values()):
        flash("No stock categories or items available.", "warning")
        return redirect(url_for('dashboard') if session.get('admin_logged_in') else url_for('login'))
    first_category = next(iter(stock), None)
    if first_category:
        return redirect(url_for("show_stock", category=first_category))
    else: # Should be caught by first condition, but for safety
        flash("Stock system error: No categories found.", "error")
        return redirect(url_for('dashboard') if session.get('admin_logged_in') else url_for('login'))


@app.route("/stock/<category>")
@customer_or_admin_required
def show_stock(category):
    if category not in stock:
        flash(f"Invalid stock category: {category}", "error"); return redirect(url_for('stock_categories'))
    items = sorted(stock.get(category, []), key=lambda item: item.get('name', '').lower())
    return render_template_string(STOCK_TEMPLATE, stock_items=items, category=category, cart=cart)

@app.route("/add_stock/<category>", methods=["POST"])
@admin_required
def add_stock(category):
    if category not in stock: flash(f"Invalid category: {category}", "error"); return redirect(url_for('stock_categories'))
    name = request.form.get("item_name", "").strip()
    price_str, qty_str = request.form.get("item_price"), request.form.get("item_quantity")
    if not name: flash("Item name empty.", "error"); return redirect(url_for("show_stock", category=category))
    try:
        price, qty = float(price_str), int(qty_str)
        if price <= 0 or qty <= 0: raise ValueError("Price and quantity must be positive.")
    except (ValueError, TypeError): flash(f"Invalid price/qty. Must be positive numbers.", "error"); return redirect(url_for("show_stock", category=category))
    if any(i['name'].lower() == name.lower() for i in stock[category]): flash(f"'{name}' already in '{category}'.", "warning")
    else: stock[category].append({"name": name, "price": price, "quantity": qty}); flash(f"'{name}' added.", "success")
    return redirect(url_for("show_stock", category=category))

@app.route("/add_to_cart/<category>/<item_name>")
@customer_required 
def add_to_cart(category, item_name):
    _, item_stock_data = find_stock_item_info(category, item_name)
    if item_stock_data:
        if item_stock_data.get("quantity",0) > 0:
            cart.append({"name": item_stock_data["name"], "price": item_stock_data["price"]})
            flash(f"'{item_name}' added to cart.", "success")
        else: flash(f"'{item_name}' out of stock.", "warning")
    else: flash(f"'{item_name}' not in '{category}' stock.", "error")
    return redirect(url_for("show_stock", category=category))

@app.route("/remove_from_cart/<item_name>", methods=["POST"])
@customer_required 
def remove_from_cart(item_name):
    global cart
    idx_remove = next((i for i, item in enumerate(cart) if item.get("name") == item_name), -1)
    if idx_remove != -1: flash(f"Removed '{cart.pop(idx_remove)['name']}' from cart.", "info")
    else: flash(f"'{item_name}' not in cart.", "warning")
    return redirect(url_for("show_prescription"))

@app.route("/prescription")
@customer_required 
def show_prescription():
    total = sum(item.get("price", 0) for item in cart)
    return render_template_string(PRESCRIPTION_TEMPLATE, cart=cart, total=total)

@app.route("/process_payment", methods=["POST"])
@customer_required 
def process_payment():
    if not cart: flash("Cart empty.", "warning"); return redirect(url_for("show_prescription"))
    payment_method = request.form.get("payment_method", "Unknown")
    total_amount = sum(item.get("price",0) for item in cart)
    
    consolidated = {}
    for item in cart:
        name, price = item['name'], item['price']
        cat = next((c for c, items in stock.items() if any(s['name'] == name for s in items)), None)
        if not cat: flash(f"Error: Category for '{name}' not found.", "error"); return redirect(url_for('show_prescription'))
        consolidated[name] = consolidated.get(name, {'count': 0, 'price': price, 'category': cat})
        consolidated[name]['count'] += 1
    
    items_db_str = ", ".join([f"{n} (x{d['count']})" for n, d in consolidated.items()])
    stock_revert = []
    try:
        with app.app_context():
            for name, data in consolidated.items():
                idx, item_data = find_stock_item_info(data['category'], name)
                if not item_data: raise ValueError(f"Item '{name}' not found in stock for deduction.")
                orig_qty = item_data['quantity']
                if orig_qty < data['count']: raise ValueError(f"Insufficient stock for '{name}'. Available: {orig_qty}, Tried: {data['count']}")
                stock[data['category']][idx]['quantity'] -= data['count']
                stock_revert.append({'category': data['category'], 'index': idx, 'original_quantity': orig_qty})
            
            db.session.add(Transaction(payment_method=payment_method, total_amount=total_amount, items=items_db_str))
            db.session.commit()
            cart.clear()
            flash("Payment successful! Stock updated.", "success")
            return redirect(url_for("stock_categories")) 
    except ValueError as ve:
        db.session.rollback()
        for change in stock_revert: stock[change['category']][change['index']]['quantity'] = change['original_quantity']
        flash(f"Payment failed: {ve}. Stock restored.", "error"); return redirect(url_for('show_prescription'))
    except Exception as e:
        db.session.rollback()
        for change in stock_revert: stock[change['category']][change['index']]['quantity'] = change['original_quantity']
        flash(f"Error: {e}. Payment failed. Stock restored.", "error"); print(f"Payment error: {e}"); return redirect(url_for('show_prescription'))

@app.route("/cashier")
@admin_required
def cashier():
    date_str, med_str = request.args.get('filter_date','').strip(), request.args.get('filter_medicine','').strip().lower()
    filters_active = bool(date_str or med_str)
    query = Transaction.query
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Transaction.timestamp >= datetime.combine(date_obj, datetime.min.time()),
                                 Transaction.timestamp <= datetime.combine(date_obj, datetime.max.time()))
        except ValueError: flash("Invalid date format.", "warning"); date_str = None
    if med_str: query = query.filter(Transaction.items.ilike(f"%{med_str}%"))
    
    real_tx = query.order_by(Transaction.timestamp.desc()).all()
    display_tx = real_tx
    if not real_tx and not filters_active:
        display_tx = [ FakeTransaction(-1, datetime.now() - timedelta(hours=1), "Demo A (x1)", "Cash", 25.50),
                       FakeTransaction(-2, datetime.now() - timedelta(days=1), "Sample B (x2)", "UPI", 150.00) ]
        flash("No real transactions. Showing sample data.", "info")
    return render_template_string(CASHIER_TEMPLATE, transactions=display_tx, filter_date=date_str, filter_medicine=med_str)

# --- Main Execution ---
if __name__ == "__main__":
    with app.app_context():
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0: 
            print("Creating database tables...")
            create_db()
            print("Database tables created.")
        else:
            print("Database found.")
    app.run(debug=True, host='127.0.0.1', port=5000)