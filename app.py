import os
import json
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import plotly.express as px
import plotly.utils
from dotenv import load_dotenv

from database.connection import engine, Base, SessionLocal
from database.models import Account, CreditCard, Transaction, TransactionTypeEnum, PeriodicityEnum
from core.projections import generate_cashflow_projection

load_dotenv()

# Inicializar Base de Datos
Base.metadata.create_all(bind=engine)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "finance-secret-key-12345")

# Filtro Jinja2 para formatear moneda: $ XXX XXX XXX,XX
@app.template_filter('format_currency')
def format_currency_filter(value):
    if value is None:
        value = 0.0
    try:
        val = float(value)
    except (ValueError, TypeError):
        return "$ 0,00"
    
    parts = f"{val:,.2f}".split('.')
    # Formato con espacio como separador de miles y coma como separador decimal
    integer_part = parts[0].replace(',', ' ')
    decimal_part = parts[1]
    return f"$ {integer_part},{decimal_part}"

def parse_currency(value_str):
    """
    Parsea strings del formato "$ 1 234 567,89" o "1234567.89" a float
    """
    if not value_str:
        return 0.0
    if isinstance(value_str, (int, float)):
        return float(value_str)
    
    cleaned = str(value_str).replace('$', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(cleaned)
    except ValueError:
        # Fallback simple
        try:
            return float(str(value_str).replace('$', '').replace(' ', '').strip())
        except ValueError:
            return 0.0

@app.route('/')
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

        # Crear gráfico interactivo con Plotly
        fig = px.line(
            df, 
            x='date', 
            y='balance', 
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

        # Filtrar próximos eventos de los siguientes 30 días
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

# ===============================
# RUTAS DE CUENTAS Y TARJETAS
# ===============================
@app.route('/products')
def products_view():
    db = SessionLocal()
    try:
        accounts = db.query(Account).all()
        cards = db.query(CreditCard).all()
        return render_template('products.html', active_page='products', accounts=accounts, cards=cards)
    finally:
        db.close()

@app.route('/accounts/add', methods=['POST'])
def add_account():
    name = request.form.get('name', '').strip()
    balance = parse_currency(request.form.get('balance', '0'))
    
    if name:
        db = SessionLocal()
        try:
            acc = Account(name=name, balance=balance, updated_at=datetime.date.today())
            db.add(acc)
            db.commit()
            flash(f"Cuenta '{name}' agregada exitosamente.", "success")
        finally:
            db.close()
    else:
        flash("El nombre de la cuenta es obligatorio.", "danger")
    return redirect(url_for('products_view'))

@app.route('/accounts/<int:id>/edit', methods=['POST'])
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
def add_card():
    name = request.form.get('name', '').strip()
    credit_limit = parse_currency(request.form.get('credit_limit', '0'))
    current_debt = parse_currency(request.form.get('current_debt', '0'))
    next_payment_amount = parse_currency(request.form.get('next_payment_amount', '0'))
    statement_day = int(request.form.get('statement_day', 15))
    due_day = int(request.form.get('due_day', 5))

    if name:
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
            db.commit()
            flash(f"Tarjeta '{name}' agregada con éxito.", "success")
        finally:
            db.close()
    else:
        flash("El nombre de la tarjeta es requerido.", "danger")
    return redirect(url_for('products_view'))

@app.route('/cards/<int:id>/edit', methods=['POST'])
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

# ===============================
# RUTAS DE MOVIMIENTOS
# ===============================
@app.route('/movements')
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

    enum_type = TransactionTypeEnum.expense if type_str == "Gasto" else TransactionTypeEnum.income
    
    credit_card_id = None
    if payment_method.startswith('card_'):
        try:
            credit_card_id = int(payment_method.replace('card_', ''))
        except ValueError:
            credit_card_id = None

    periodicity_map = {
        "Única": PeriodicityEnum.unique,
        "Semanal": PeriodicityEnum.weekly,
        "Quincenal": PeriodicityEnum.biweekly,
        "Mensual": PeriodicityEnum.monthly,
        "Bimestral": PeriodicityEnum.bimonthly,
        "Semestral": PeriodicityEnum.semiannual,
        "Anual": PeriodicityEnum.annual
    }
    enum_periodicity = periodicity_map.get(periodicity_str, PeriodicityEnum.monthly) if is_recurring else PeriodicityEnum.unique

    db = SessionLocal()
    try:
        tx = Transaction(
            description=description,
            amount=amount,
            start_date=start_date,
            is_recurring=is_recurring,
            is_active=True,
            periodicity=enum_periodicity,
            type=enum_type,
            credit_card_id=credit_card_id
        )
        db.add(tx)
        db.commit()
        flash("Movimiento registrado con éxito.", "success")
    finally:
        db.close()

    return redirect(url_for('movements_view'))

@app.route('/movements/<int:id>/toggle', methods=['POST'])
def toggle_movement(id):
    db = SessionLocal()
    try:
        tx = db.query(Transaction).get(id)
        if tx:
            tx.is_active = not tx.is_active
            db.commit()
            state_str = "activado" if tx.is_active else "pausado"
            flash(f"Movimiento '{tx.description}' {state_str}.", "info")
    finally:
        db.close()
    return redirect(url_for('movements_view'))

@app.route('/movements/<int:id>/delete', methods=['POST'])
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

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
