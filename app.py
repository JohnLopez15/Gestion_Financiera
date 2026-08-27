import os
import json
import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import plotly.express as px
import plotly.utils
from dotenv import load_dotenv

from database.connection import engine, Base, SessionLocal
from database.models import User, Account, CreditCard, Transaction, TransactionTypeEnum, PeriodicityEnum
from core.projections import generate_cashflow_projection

load_dotenv()

# ──────────────────────────────────────────────
# INICIALIZACIÓN DE BASE DE DATOS
# ──────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ──────────────────────────────────────────────
# APLICACIÓN FLASK
# ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-antes-de-produccion")

# ──────────────────────────────────────────────
# FLASK-LOGIN: Configuración del gestor de sesiones
# ──────────────────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"           # Ruta a la que redirige si no está autenticado
login_manager.login_message = "Por favor inicia sesión para acceder."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    """Callback requerido por Flask-Login para recargar el usuario desde la sesión."""
    db = SessionLocal()
    try:
        return db.query(User).get(int(user_id))
    finally:
        db.close()


# ──────────────────────────────────────────────
# INICIALIZACIÓN DEL USUARIO ADMINISTRADOR
# Se ejecuta una sola vez al arrancar la app.
# Lee ADMIN_USERNAME y ADMIN_PASSWORD de las variables de entorno.
# ──────────────────────────────────────────────
def init_admin_user():
    """Crea el usuario administrador si no existe aún en la base de datos."""
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "changeme123")

    db = SessionLocal()
    try:
        existing = db.query(User).filter_by(username=admin_username).first()
        if not existing:
            hashed = generate_password_hash(admin_password)
            admin = User(username=admin_username, password_hash=hashed)
            db.add(admin)
            db.commit()
            print(f"[INFO] Usuario administrador '{admin_username}' creado correctamente.")
    finally:
        db.close()

init_admin_user()


# ──────────────────────────────────────────────
# FILTRO JINJA2: Formateo monetario $ XXX XXX,XX
# ──────────────────────────────────────────────
@app.template_filter('format_currency')
def format_currency_filter(value):
    if value is None:
        value = 0.0
    try:
        val = float(value)
    except (ValueError, TypeError):
        return "$ 0,00"
    parts = f"{val:,.2f}".split('.')
    integer_part = parts[0].replace(',', ' ')
    decimal_part = parts[1]
    return f"$ {integer_part},{decimal_part}"


# ──────────────────────────────────────────────
# UTILIDAD: Parsear montos con formato visual
# ──────────────────────────────────────────────
def parse_currency(value_str):
    """Convierte '$ 1 234 567,89' → 1234567.89 (float)."""
    if not value_str:
        return 0.0
    if isinstance(value_str, (int, float)):
        return float(value_str)
    cleaned = (
        str(value_str)
        .replace('$', '')
        .replace(' ', '')
        .replace('.', '')
        .replace(',', '.')
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ══════════════════════════════════════════════
# RUTAS DE AUTENTICACIÓN
# ══════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username=username).first()
        finally:
            db.close()

        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            # Redirige a la página que intentaban visitar antes del login, si existe
            next_page = request.args.get('next')
            flash(f"Bienvenido, {user.username}.", "success")
            return redirect(next_page or url_for('index'))
        else:
            flash("Usuario o contraseña incorrectos. Intenta de nuevo.", "danger")

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('login'))


# ══════════════════════════════════════════════
# RUTAS PROTEGIDAS: DASHBOARD
# ══════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    months = request.args.get('months', default=12, type=int)
    db = SessionLocal()
    try:
        df, events = generate_cashflow_projection(db, months_ahead=months)
        accounts = db.query(Account).all()
        cards = db.query(CreditCard).all()

        initial_balance = sum(acc.balance for acc in accounts)
        total_cc_debt = sum(c.current_debt for c in cards)
        min_balance = df['balance'].min() if not df.empty else 0.0

        fig = px.line(
            df, x='date', y='balance',
            title="Evolución Diaria del Saldo Total Proyectado",
            labels={'date': 'Fecha', 'balance': 'Saldo ($)'}
        )
        fig.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="Límite Liquidez (0)")
        fig.update_layout(
            template="plotly_white",
            margin=dict(l=20, r=20, t=40, b=20),
            hovermode="x unified"
        )
        chart_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        today = datetime.date.today()
        next_30 = today + datetime.timedelta(days=30)
        next_events = [ev for ev in events if today <= ev['date'] <= next_30]
        next_events.sort(key=lambda x: x['date'])

        return render_template(
            'dashboard.html',
            active_page='dashboard',
            months=months,
            initial_balance=initial_balance,
            min_balance=min_balance,
            total_cc_debt=total_cc_debt,
            chart_json=chart_json,
            next_events=next_events
        )
    finally:
        db.close()


# ══════════════════════════════════════════════
# RUTAS PROTEGIDAS: CUENTAS Y TARJETAS
# ══════════════════════════════════════════════

@app.route('/products')
@login_required
def products_view():
    db = SessionLocal()
    try:
        accounts = db.query(Account).all()
        cards = db.query(CreditCard).all()
        return render_template('products.html', active_page='products', accounts=accounts, cards=cards)
    finally:
        db.close()

@app.route('/accounts/add', methods=['POST'])
@login_required
def add_account():
    name = request.form.get('name', '').strip()
    balance = parse_currency(request.form.get('balance', '0'))
    if name:
        db = SessionLocal()
        try:
            db.add(Account(name=name, balance=balance, updated_at=datetime.date.today()))
            db.commit()
            flash(f"Cuenta '{name}' agregada exitosamente.", "success")
        finally:
            db.close()
    else:
        flash("El nombre de la cuenta es obligatorio.", "danger")
    return redirect(url_for('products_view'))

@app.route('/accounts/<int:id>/edit', methods=['POST'])
@login_required
def edit_account(id):
    db = SessionLocal()
    try:
        acc = db.query(Account).get(id)
        if acc:
            acc.name = request.form.get('name', acc.name).strip()
            acc.balance = parse_currency(request.form.get('balance', str(acc.balance)))
            acc.updated_at = datetime.date.today()
            db.commit()
            flash(f"Cuenta '{acc.name}' actualizada.", "success")
    finally:
        db.close()
    return redirect(url_for('products_view'))

@app.route('/accounts/<int:id>/delete', methods=['POST'])
@login_required
def delete_account(id):
    db = SessionLocal()
    try:
        acc = db.query(Account).get(id)
        if acc:
            db.delete(acc)
            db.commit()
            flash("Cuenta eliminada correctamente.", "info")
    finally:
        db.close()
    return redirect(url_for('products_view'))

@app.route('/cards/add', methods=['POST'])
@login_required
def add_card():
    name = request.form.get('name', '').strip()
    if not name:
        flash("El nombre de la tarjeta es requerido.", "danger")
        return redirect(url_for('products_view'))
    db = SessionLocal()
    try:
        db.add(CreditCard(
            name=name,
            credit_limit=parse_currency(request.form.get('credit_limit', '0')),
            current_debt=parse_currency(request.form.get('current_debt', '0')),
            next_payment_amount=parse_currency(request.form.get('next_payment_amount', '0')),
            statement_day=int(request.form.get('statement_day', 15)),
            due_day=int(request.form.get('due_day', 5))
        ))
        db.commit()
        flash(f"Tarjeta '{name}' agregada con éxito.", "success")
    finally:
        db.close()
    return redirect(url_for('products_view'))

@app.route('/cards/<int:id>/edit', methods=['POST'])
@login_required
def edit_card(id):
    db = SessionLocal()
    try:
        card = db.query(CreditCard).get(id)
        if card:
            card.name = request.form.get('name', card.name).strip()
            card.credit_limit = parse_currency(request.form.get('credit_limit', str(card.credit_limit)))
            card.current_debt = parse_currency(request.form.get('current_debt', str(card.current_debt)))
            card.next_payment_amount = parse_currency(request.form.get('next_payment_amount', str(card.next_payment_amount)))
            card.statement_day = int(request.form.get('statement_day', card.statement_day))
            card.due_day = int(request.form.get('due_day', card.due_day))
            db.commit()
            flash(f"Tarjeta '{card.name}' actualizada.", "success")
    finally:
        db.close()
    return redirect(url_for('products_view'))

@app.route('/cards/<int:id>/delete', methods=['POST'])
@login_required
def delete_card(id):
    db = SessionLocal()
    try:
        card = db.query(CreditCard).get(id)
        if card:
            db.delete(card)
            db.commit()
            flash("Tarjeta eliminada correctamente.", "info")
    finally:
        db.close()
    return redirect(url_for('products_view'))


# ══════════════════════════════════════════════
# RUTAS PROTEGIDAS: MOVIMIENTOS
# ══════════════════════════════════════════════

@app.route('/movements')
@login_required
def movements_view():
    db = SessionLocal()
    try:
        transactions = db.query(Transaction).order_by(Transaction.start_date.desc()).all()
        cards = db.query(CreditCard).all()
        today_str = datetime.date.today().isoformat()
        return render_template(
            'movements.html',
            active_page='movements',
            transactions=transactions,
            cards=cards,
            today=today_str
        )
    finally:
        db.close()

@app.route('/movements/add', methods=['POST'])
@login_required
def add_movement():
    description = request.form.get('description', '').strip()
    amount = parse_currency(request.form.get('amount', '0'))
    type_str = request.form.get('type', 'Gasto')
    start_date_str = request.form.get('start_date')
    payment_method = request.form.get('payment_method', 'account')
    is_recurring = 'is_recurring' in request.form
    periodicity_str = request.form.get('periodicity', 'Mensual')

    if not description or amount <= 0:
        flash("Debes ingresar una descripción y un monto válido mayor a 0.", "danger")
        return redirect(url_for('movements_view'))

    try:
        start_date = datetime.date.fromisoformat(start_date_str) if start_date_str else datetime.date.today()
    except ValueError:
        start_date = datetime.date.today()

    credit_card_id = None
    if payment_method.startswith('card_'):
        try:
            credit_card_id = int(payment_method.replace('card_', ''))
        except ValueError:
            credit_card_id = None

    periodicity_map = {
        "Única": PeriodicityEnum.unique, "Semanal": PeriodicityEnum.weekly,
        "Quincenal": PeriodicityEnum.biweekly, "Mensual": PeriodicityEnum.monthly,
        "Bimestral": PeriodicityEnum.bimonthly, "Semestral": PeriodicityEnum.semiannual,
        "Anual": PeriodicityEnum.annual
    }
    enum_periodicity = periodicity_map.get(periodicity_str, PeriodicityEnum.monthly) if is_recurring else PeriodicityEnum.unique
    enum_type = TransactionTypeEnum.expense if type_str == "Gasto" else TransactionTypeEnum.income

    db = SessionLocal()
    try:
        db.add(Transaction(
            description=description, amount=amount, start_date=start_date,
            is_recurring=is_recurring, is_active=True,
            periodicity=enum_periodicity, type=enum_type,
            credit_card_id=credit_card_id
        ))
        db.commit()
        flash("Movimiento registrado con éxito.", "success")
    finally:
        db.close()
    return redirect(url_for('movements_view'))

@app.route('/movements/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_movement(id):
    db = SessionLocal()
    try:
        tx = db.query(Transaction).get(id)
        if tx:
            tx.is_active = not tx.is_active
            db.commit()
            flash(f"Movimiento '{tx.description}' {'activado' if tx.is_active else 'pausado'}.", "info")
    finally:
        db.close()
    return redirect(url_for('movements_view'))

@app.route('/movements/<int:id>/delete', methods=['POST'])
@login_required
def delete_movement(id):
    db = SessionLocal()
    try:
        tx = db.query(Transaction).get(id)
        if tx:
            db.delete(tx)
            db.commit()
            flash("Movimiento eliminado.", "info")
    finally:
        db.close()
    return redirect(url_for('movements_view'))


# ──────────────────────────────────────────────
# PUNTO DE ENTRADA
# ──────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
