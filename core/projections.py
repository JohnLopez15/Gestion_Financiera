import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session
from database.models import Account, CreditCard, Transaction, TransactionTypeEnum, PeriodicityEnum
from core.utils import generate_recurring_dates, calculate_cc_due_date_for_transaction, calculate_next_due_date_from_today

def generate_cashflow_projection(db: Session, months_ahead: int = 12):
    today = datetime.date.today()
    end_date = today + relativedelta(months=months_ahead)
    
    # 1. Fetch current balances
    accounts = db.query(Account).all()
    total_initial_balance = sum(acc.balance for acc in accounts)
    
    # 2. Fetch active transactions
    transactions = db.query(Transaction).filter(Transaction.is_active == True).all()
    
    # 3. Fetch credit cards
    credit_cards = db.query(CreditCard).all()
    
    events = []
    
    # CC initial debts processing
    for cc in credit_cards:
        if cc.next_payment_amount > 0:
            first_due_date = calculate_next_due_date_from_today(today, cc.statement_day, cc.due_day)
            events.append({
                "date": first_due_date,
                "amount": -cc.next_payment_amount,
                "description": f"Pago Tarjeta: {cc.name} (Próximo)",
                "category": "CC_PAYMENT"
            })
            
        remaining_debt = cc.current_debt - cc.next_payment_amount
        if remaining_debt > 0:
            first_due_date = calculate_next_due_date_from_today(today, cc.statement_day, cc.due_day)
            # The remaining debt goes to the cycle AFTER the first due date.
            second_due_date = calculate_next_due_date_from_today(first_due_date + datetime.timedelta(days=1), cc.statement_day, cc.due_day)
            events.append({
                "date": second_due_date,
                "amount": -remaining_debt,
                "description": f"Pago Tarjeta: {cc.name} (Restante)",
                "category": "CC_PAYMENT"
            })
            
    # CC accumulated expenses per due date
    cc_accumulated = {} # (cc_id, due_date): amount
    
    # Process transactions
    for tx in transactions:
        tx_dates = []
        if tx.is_recurring:
            # We want to project only from today onwards, but keeping the original periodicity cadence.
            # However, for simplicity if start_date < today we still generate from start_date and filter later,
            # or just start from today if start_date is in the past.
            # Let's generate from start_date and filter.
            all_dates = generate_recurring_dates(tx.start_date, end_date, tx.periodicity)
            tx_dates = [d for d in all_dates if d >= today]
        else:
            if tx.start_date >= today and tx.start_date <= end_date:
                tx_dates = [tx.start_date]
                
        for d in tx_dates:
            amount = tx.amount if tx.type == TransactionTypeEnum.income else -tx.amount
            
            if tx.credit_card_id:
                # Calculate when this will be paid
                cc = next((c for c in credit_cards if c.id == tx.credit_card_id), None)
                if cc:
                    due_date = calculate_cc_due_date_for_transaction(d, cc.statement_day, cc.due_day)
                    key = (cc.id, due_date)
                    cc_accumulated[key] = cc_accumulated.get(key, 0) + amount # amount is negative
            else:
                events.append({
                    "date": d,
                    "amount": amount,
                    "description": tx.description,
                    "category": "INCOME" if amount > 0 else "EXPENSE"
                })
                
    # Add accumulated CC expenses to events
    for (cc_id, due_date), amount in cc_accumulated.items():
        cc = next((c for c in credit_cards if c.id == cc_id), None)
        events.append({
            "date": due_date,
            "amount": amount, # already negative
            "description": f"Pago Tarjeta: {cc.name} (Proyectado)",
            "category": "CC_PAYMENT"
        })
        
    # 4. Build DataFrame
    if not events:
        dates = pd.date_range(start=today, end=end_date)
        df = pd.DataFrame({"date": dates})
        df['date'] = df['date'].dt.date
        df['balance'] = total_initial_balance
        return df, []
        
    df_events = pd.DataFrame(events)
    # Aggregate by date
    df_grouped = df_events.groupby('date')['amount'].sum().reset_index()
    
    # Generate timeline
    dates = pd.date_range(start=today, end=end_date)
    df = pd.DataFrame({"date": dates})
    df['date'] = df['date'].dt.date
    
    df = pd.merge(df, df_grouped, on='date', how='left').fillna(0)
    
    df['balance'] = total_initial_balance + df['amount'].cumsum()
    
    return df, events

