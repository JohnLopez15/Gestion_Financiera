import os
import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
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
    sign = "−" if val < 0 else ""
    parts = f"{abs(val):,.2f}".split('.')
    integer_part = parts[0].replace(',', ' ')
    decimal_part = parts[1]
    return f"{sign}$ {integer_part},{decimal_part}"


# ──────────────────────────────────────────────
# FILTROS JINJA2: Fechas en español
# ──────────────────────────────────────────────
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


@app.template_filter('fecha_corta')
def fecha_corta_filter(d):
    """2026-10-18 → '18 oct' (añade el año si no es el actual)."""
    if not d:
        return "—"
    text = f"{d.day} {MESES_CORTOS[d.month - 1]}"
    if d.year != datetime.date.today().year:
        text += f" {d.year}"
    return text


@app.template_filter('fecha_relativa')
def fecha_relativa_filter(d):
    """'Hoy', 'Mañana' o 'jueves, 22 de octubre'."""
    if not d:
        return "—"
    delta = (d - datetime.date.today()).days
    if delta == 0:
        return "Hoy"
    if delta == 1:
        return "Mañana"
    return f"{DIAS_SEMANA[d.weekday()].capitalize()}, {d.day} de {MESES_LARGOS[d.month - 1]}"


@app.context_processor
def inject_quick_add():
    """Datos para la hoja global de 'Nuevo movimiento' disponible en todas las vistas."""
    if not current_user.is_authenticated:
        return {}
    db = SessionLocal()
    try:
        cards = [{"id": c.id, "name": c.name} for c in db.query(CreditCard).all()]
    finally:
        db.close()
    today = datetime.date.today()
    return {
        "qa_cards": cards,
        "qa_today": today.isoformat(),
        "today_label": f"{DIAS_SEMANA[today.weekday()].capitalize()}, {today.day} de {MESES_LARGOS[today.month - 1]}",
    }


def safe_next(target, fallback):
    """Solo permite redirecciones internas relativas."""
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return fallback


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
            return redirect(safe_next(next_page, url_for('index')))
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
    if months not in (1, 3, 6, 12, 24):
        months = 12
    db = SessionLocal()
    try:
        # 1. Proyección predictiva futura
        df_proj, events = generate_cashflow_projection(db, months_ahead=months)
        accounts = db.query(Account).all()
        cards = db.query(CreditCard).all()
        today = datetime.date.today()

        initial_balance = sum(acc.balance for acc in accounts)
        total_cc_debt = sum(c.current_debt for c in cards)
        total_cc_limit = sum(c.credit_limit for c in cards)
        net_worth = initial_balance - total_cc_debt

        min_idx = df_proj['balance'].idxmin()
        min_balance = float(df_proj.loc[min_idx, 'balance'])
        min_date = df_proj.loc[min_idx, 'date']
        end_balance = float(df_proj['balance'].iloc[-1])
        end_date = df_proj['date'].iloc[-1]

        # Primer día en que el saldo proyectado cae bajo cero (si ocurre)
        negative = df_proj[df_proj['balance'] < 0]
        first_negative_date = negative['date'].iloc[0] if not negative.empty else None

        projection = {
            "dates": [d.isoformat() for d in df_proj['date']],
            "balance": [round(float(b), 2) for b in df_proj['balance']],
            "min": {"date": min_date.isoformat(), "value": round(min_balance, 2)},
        }

        # 2. Flujo mensual (ingresos vs. egresos) dentro del horizonte
        monthly = {}
        for ev in events:
            if not (today <= ev['date'] <= end_date):
                continue
            key = (ev['date'].year, ev['date'].month)
            bucket = monthly.setdefault(key, {"income": 0.0, "expense": 0.0})
            if ev['amount'] >= 0:
                bucket["income"] += ev['amount']
            else:
                bucket["expense"] += ev['amount']
        month_keys = []
        cursor = datetime.date(today.year, today.month, 1)
        while cursor <= end_date:
            month_keys.append((cursor.year, cursor.month))
            cursor = (cursor.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        monthly_flow = {
            "labels": [
                MESES_CORTOS[m - 1] + (f" {str(y)[2:]}" if y != today.year else "")
                for y, m in month_keys
            ],
            "income": [round(monthly.get(k, {}).get("income", 0.0), 2) for k in month_keys],
            "expense": [round(monthly.get(k, {}).get("expense", 0.0), 2) for k in month_keys],
        }

        # 3. Histórico real registrado (snapshots por producto)
        history = {
            "accounts": [
                {
                    "name": acc.name,
                    "dates": [h.recorded_at.isoformat() for h in acc.balance_history],
                    "values": [round(h.balance, 2) for h in acc.balance_history],
                }
                for acc in accounts if acc.balance_history
            ],
            "cards": [
                {
                    "name": c.name,
                    "dates": [h.recorded_at.isoformat() for h in c.debt_history],
                    "values": [round(h.current_debt, 2) for h in c.debt_history],
                }
                for c in cards if c.debt_history
            ],
        }
        has_history = bool(history["accounts"] or history["cards"])

        # 4. Próximos eventos (30 días) agrupados por día, con el saldo proyectado resultante
        balance_by_date = dict(zip(df_proj['date'], df_proj['balance']))
        next_30 = today + datetime.timedelta(days=30)
        next_events = sorted(
            (ev for ev in events if today <= ev['date'] <= next_30),
            key=lambda x: (x['date'], -x['amount'])
        )
        upcoming = []
        for ev in next_events:
            if not upcoming or upcoming[-1]["date"] != ev['date']:
                upcoming.append({
                    "date": ev['date'],
                    "items": [],
                    "balance_after": float(balance_by_date.get(ev['date'], 0.0)),
                })
            upcoming[-1]["items"].append(ev)
        upcoming_in = sum(ev['amount'] for ev in next_events if ev['amount'] > 0)
        upcoming_out = sum(ev['amount'] for ev in next_events if ev['amount'] < 0)

        return render_template(
            'dashboard.html',
            active_page='dashboard',
            months=months,
            initial_balance=initial_balance,
            total_cc_debt=total_cc_debt,
            total_cc_limit=total_cc_limit,
            net_worth=net_worth,
            min_balance=min_balance,
            min_date=min_date,
            end_balance=end_balance,
            end_date=end_date,
            first_negative_date=first_negative_date,
            accounts_count=len(accounts),
            cards_count=len(cards),
            projection=projection,
            monthly_flow=monthly_flow,
            history=history,
            has_history=has_history,
            upcoming=upcoming,
            upcoming_in=upcoming_in,
            upcoming_out=upcoming_out,
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

        # Equivalente mensual de los movimientos periódicos activos
        factor = {
            PeriodicityEnum.weekly: 52 / 12, PeriodicityEnum.biweekly: 26 / 12,
            PeriodicityEnum.monthly: 1, PeriodicityEnum.bimonthly: 1 / 2,
            PeriodicityEnum.semiannual: 1 / 6, PeriodicityEnum.annual: 1 / 12,
        }
        monthly_income = monthly_expense = 0.0
        for t in transactions:
            if t.is_active and t.is_recurring:
                value = t.amount * factor.get(t.periodicity, 0)
                if t.type == TransactionTypeEnum.income:
                    monthly_income += value
                else:
                    monthly_expense += value

        return render_template(
            'movements.html',
            active_page='movements',
            recurring=[t for t in transactions if t.is_recurring],
            one_off=[t for t in transactions if not t.is_recurring],
            total_count=len(transactions),
            monthly_income=monthly_income,
            monthly_expense=monthly_expense,
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

    back = safe_next(request.form.get('next'), url_for('movements_view'))

    if not description or amount <= 0:
        flash("Debes ingresar una descripción y un monto válido mayor a 0.", "danger")
        return redirect(back)

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
        flash(f"Movimiento '{description}' registrado.", "success")
    finally:
        db.close()
    return redirect(back)


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
