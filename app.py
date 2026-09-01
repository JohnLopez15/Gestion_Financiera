import os
import json
import datetime
import pandas as pd

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import plotly.express as px
import plotly.graph_objects as go
import plotly.utils
from dotenv import load_dotenv

from database.connection import engine, Base, SessionLocal
from database.models import (
    User, Account, CreditCard, Transaction,
    AccountBalanceHistory, CreditCardDebtHistory,
    TransactionTypeEnum, PeriodicityEnum
)
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
login_manager.login_view = "login"
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
            print(f"[INFO] Usuario administrador '{admin_username}' configurado correctamente.")
    except Exception as e:
        print(f"[WARN] No se pudo inicializar admin user automáticamente: {e}")
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
        # 1. Proyección predictiva futura
        df_proj, events = generate_cashflow_projection(db, months_ahead=months)
        accounts = db.query(Account).all()
        cards = db.query(CreditCard).all()

        initial_balance = sum(acc.balance for acc in accounts)
        total_cc_debt = sum(c.current_debt for c in cards)
        min_balance = df_proj['balance'].min() if not df_proj.empty else 0.0

        # Gráfico predictivo
        fig_proj = px.line(
            df_proj, x='date', y='balance',
            title="Evolución Diaria del Saldo Proyectado (Predictivo)",
            labels={'date': 'Fecha', 'balance': 'Saldo ($)'}
        )
        fig_proj.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="Límite Liquidez (0)")
        fig_proj.update_layout(
            template="plotly_white",
            margin=dict(l=20, r=20, t=40, b=20),
            hovermode="x unified"
        )
        chart_proj_json = json.dumps(fig_proj, cls=plotly.utils.PlotlyJSONEncoder)

        # 2. Análisis Histórico Real (Día a Día registrado)
        acc_history = db.query(AccountBalanceHistory).order_by(AccountBalanceHistory.recorded_at.asc()).all()
        card_history = db.query(CreditCardDebtHistory).order_by(CreditCardDebtHistory.recorded_at.asc()).all()

        has_history = len(acc_history) > 0 or len(card_history) > 0
        chart_real_json = None

        if has_history:
            fig_real = go.Figure()

            # Agregar trazas por cada cuenta
            for acc in accounts:
                history_for_acc = [h for h in acc_history if h.account_id == acc.id]
                if history_for_acc:
                    dates = [h.recorded_at for h in history_for_acc]
                    balances = [h.balance for h in history_for_acc]
                    fig_real.add_trace(go.Scatter(
                        x=dates, y=balances,
                        mode='lines+markers',
                        name=f"Cuenta: {acc.name}",
                        line=dict(width=2)
                    ))

            # Agregar trazas por cada tarjeta de crédito (Deuda)
            for c in cards:
                history_for_card = [h for h in card_history if h.credit_card_id == c.id]
                if history_for_card:
                    dates = [h.recorded_at for h in history_for_card]
                    debts = [h.current_debt for h in history_for_card]
                    fig_real.add_trace(go.Scatter(
                        x=dates, y=debts,
                        mode='lines+markers',
                        name=f"Deuda TC: {c.name}",
                        line=dict(dash='dot', width=2)
                    ))

            fig_real.update_layout(
                title="Evolución Histórica Real Registrada (Día a Día)",
                xaxis_title="Fecha de Registro",
                yaxis_title="Monto ($)",
                template="plotly_white",
                margin=dict(l=20, r=20, t=40, b=20),
                hovermode="x unified"
            )
            chart_real_json = json.dumps(fig_real, cls=plotly.utils.PlotlyJSONEncoder)

        # Próximos eventos (30 días)
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
            chart_json=chart_proj_json,
            chart_real_json=chart_real_json,
            has_history=has_history,
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
        today_str = datetime.date.today().isoformat()
        return render_template(
            'products.html',
            active_page='products',
            accounts=accounts,
            cards=cards,
            today=today_str
        )
    finally:
        db.close()


@app.route('/accounts/add', methods=['POST'])
@login_required
def add_account():
    name = request.form.get('name', '').strip()
    balance = parse_currency(request.form.get('balance', '0'))
    date_str = request.form.get('recorded_at')
    note = request.form.get('note', 'Saldo inicial').strip()

    try:
        rec_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    except ValueError:
        rec_date = datetime.date.today()

    if name:
        db = SessionLocal()
        try:
            acc = Account(name=name, balance=balance, updated_at=rec_date)
            db.add(acc)
            db.flush()  # Obtener el ID asignado

            # Guardar el primer registro en el historial
            history_entry = AccountBalanceHistory(
                account_id=acc.id,
                balance=balance,
                recorded_at=rec_date,
                note=note or "Saldo inicial"
            )
            db.add(history_entry)
            db.commit()
            flash(f"Cuenta '{name}' agregada con saldo inicial registrado en el historial.", "success")
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
            new_name = request.form.get('name', acc.name).strip()
            new_balance = parse_currency(request.form.get('balance', str(acc.balance)))
            date_str = request.form.get('recorded_at')
            note = request.form.get('note', 'Actualización de saldo').strip()

            try:
                rec_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
            except ValueError:
                rec_date = datetime.date.today()

            acc.name = new_name
            acc.balance = new_balance
            acc.updated_at = rec_date

            # Guardar nuevo snapshot en el historial
            history_entry = AccountBalanceHistory(
                account_id=acc.id,
                balance=new_balance,
                recorded_at=rec_date,
                note=note or "Actualización de saldo"
            )
            db.add(history_entry)
            db.commit()
            flash(f"Cuenta '{acc.name}' actualizada y nuevo saldo registrado en el historial.", "success")
    finally:
        db.close()
    return redirect(url_for('products_view'))


@app.route('/accounts/<int:id>/history/add', methods=['POST'])
@login_required
def add_account_history_record(id):
    """Permite registrar un nuevo balance histórico sin necesariamente cambiar el nombre."""
    db = SessionLocal()
    try:
        acc = db.query(Account).get(id)
        if acc:
            balance = parse_currency(request.form.get('balance', '0'))
            date_str = request.form.get('recorded_at')
            note = request.form.get('note', '').strip()

            try:
                rec_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
            except ValueError:
                rec_date = datetime.date.today()

            # Actualizamos el saldo actual de la cuenta y su fecha
            acc.balance = balance
            acc.updated_at = rec_date

            history_entry = AccountBalanceHistory(
                account_id=acc.id,
                balance=balance,
                recorded_at=rec_date,
                note=note or "Registro histórico"
            )
            db.add(history_entry)
            db.commit()
            flash(f"Nuevo saldo para '{acc.name}' guardado en el historial con fecha {rec_date}.", "success")
    finally:
        db.close()
    return redirect(url_for('products_view'))


@app.route('/accounts/history/<int:history_id>/delete', methods=['POST'])
@login_required
def delete_account_history_record(history_id):
    db = SessionLocal()
    try:
        rec = db.query(AccountBalanceHistory).get(history_id)
        if rec:
            db.delete(rec)
            db.commit()
            flash("Registro del historial eliminado.", "info")
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

    credit_limit = parse_currency(request.form.get('credit_limit', '0'))
    current_debt = parse_currency(request.form.get('current_debt', '0'))
    next_payment_amount = parse_currency(request.form.get('next_payment_amount', '0'))
    statement_day = int(request.form.get('statement_day', 15))
    due_day = int(request.form.get('due_day', 5))
    date_str = request.form.get('recorded_at')
    note = request.form.get('note', 'Registro inicial').strip()

    try:
        rec_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    except ValueError:
        rec_date = datetime.date.today()

    db = SessionLocal()
    try:
        card = CreditCard(
            name=name,
            credit_limit=credit_limit,
            current_debt=current_debt,
            next_payment_amount=next_payment_amount,
            statement_day=statement_day,
            due_day=due_day
        )
        db.add(card)
        db.flush()

        history_entry = CreditCardDebtHistory(
            credit_card_id=card.id,
            current_debt=current_debt,
            next_payment_amount=next_payment_amount,
            recorded_at=rec_date,
            note=note or "Registro inicial"
        )
        db.add(history_entry)
        db.commit()
        flash(f"Tarjeta '{name}' agregada y deuda inicial registrada en el historial.", "success")
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
            new_debt = parse_currency(request.form.get('current_debt', str(card.current_debt)))
            new_next_pay = parse_currency(request.form.get('next_payment_amount', str(card.next_payment_amount)))
            card.current_debt = new_debt
            card.next_payment_amount = new_next_pay
            card.statement_day = int(request.form.get('statement_day', card.statement_day))
            card.due_day = int(request.form.get('due_day', card.due_day))

            date_str = request.form.get('recorded_at')
            note = request.form.get('note', 'Actualización de tarjeta').strip()

            try:
                rec_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
            except ValueError:
                rec_date = datetime.date.today()

            history_entry = CreditCardDebtHistory(
                credit_card_id=card.id,
                current_debt=new_debt,
                next_payment_amount=new_next_pay,
                recorded_at=rec_date,
                note=note or "Actualización de tarjeta"
            )
            db.add(history_entry)
            db.commit()
            flash(f"Tarjeta '{card.name}' actualizada y nuevo saldo registrado en historial.", "success")
    finally:
        db.close()
    return redirect(url_for('products_view'))


@app.route('/cards/<int:id>/history/add', methods=['POST'])
@login_required
def add_card_history_record(id):
    """Permite registrar un nuevo balance/deuda de tarjeta con fecha específica."""
    db = SessionLocal()
    try:
        card = db.query(CreditCard).get(id)
        if card:
            current_debt = parse_currency(request.form.get('current_debt', '0'))
            next_payment_amount = parse_currency(request.form.get('next_payment_amount', '0'))
            date_str = request.form.get('recorded_at')
            note = request.form.get('note', '').strip()

            try:
                rec_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
            except ValueError:
                rec_date = datetime.date.today()

            card.current_debt = current_debt
            card.next_payment_amount = next_payment_amount

            history_entry = CreditCardDebtHistory(
                credit_card_id=card.id,
                current_debt=current_debt,
                next_payment_amount=next_payment_amount,
                recorded_at=rec_date,
                note=note or "Actualización de deuda"
            )
            db.add(history_entry)
            db.commit()
            flash(f"Deuda de '{card.name}' registrada en el historial con fecha {rec_date}.", "success")
    finally:
        db.close()
    return redirect(url_for('products_view'))


@app.route('/cards/history/<int:history_id>/delete', methods=['POST'])
@login_required
def delete_card_history_record(history_id):
    db = SessionLocal()
    try:
        rec = db.query(CreditCardDebtHistory).get(history_id)
        if rec:
            db.delete(rec)
            db.commit()
            flash("Registro del historial de tarjeta eliminado.", "info")
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
