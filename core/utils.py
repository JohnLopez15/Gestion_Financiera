import datetime
import calendar
from dateutil.relativedelta import relativedelta
from database.models import PeriodicityEnum

def get_safe_date(year, month, day):
    """
    Returns a safe date, rolling over to the last day of the month if the day exceeds
    the number of days in that month.
    """
    last_day = calendar.monthrange(year, month)[1]
    safe_day = min(day, last_day)
    return datetime.date(year, month, safe_day)

def generate_recurring_dates(start_date, end_date, periodicity):
    """
    Generates a list of dates from start_date up to end_date based on periodicity.
    """
    dates = []
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date)
        if periodicity == PeriodicityEnum.weekly:
            current_date += datetime.timedelta(weeks=1)
        elif periodicity == PeriodicityEnum.biweekly:
            current_date += datetime.timedelta(weeks=2)
        elif periodicity == PeriodicityEnum.monthly:
            current_date += relativedelta(months=1)
        elif periodicity == PeriodicityEnum.bimonthly:
            current_date += relativedelta(months=2)
        elif periodicity == PeriodicityEnum.semiannual:
            current_date += relativedelta(months=6)
        elif periodicity == PeriodicityEnum.annual:
            current_date += relativedelta(years=1)
        else:
            break
    return dates

def calculate_cc_due_date_for_transaction(transaction_date, statement_day, due_day):
    """
    Determines the due date for a transaction based on the credit card's statement and due days.
    """
    # Statement date for the transaction's month
    statement_date = get_safe_date(transaction_date.year, transaction_date.month, statement_day)
    
    # If the transaction is strictly after the statement date of its month, it goes to the next cycle
    if transaction_date > statement_date:
        statement_date = get_safe_date((transaction_date + relativedelta(months=1)).year, 
                                       (transaction_date + relativedelta(months=1)).month, 
                                       statement_day)
    
    # Determine due date based on the computed statement_date
    if due_day <= statement_day:
        # Due date is in the month following the statement month
        due_month = statement_date + relativedelta(months=1)
        return get_safe_date(due_month.year, due_month.month, due_day)
    else:
        # Due date is in the same month as the statement
        return get_safe_date(statement_date.year, statement_date.month, due_day)

def calculate_next_due_date_from_today(today, statement_day, due_day):
    """
    Calculates the very next due date for a credit card from today.
    Useful for placing the 'next_payment_amount'.
    """
    statement_date = get_safe_date(today.year, today.month, statement_day)
    if due_day <= statement_day:
        due_month = statement_date + relativedelta(months=1)
        due_date = get_safe_date(due_month.year, due_month.month, due_day)
    else:
        due_date = get_safe_date(statement_date.year, statement_date.month, due_day)
        
    if due_date < today:
        # We missed this month's due date, get next month's
        due_date = due_date + relativedelta(months=1)
        due_date = get_safe_date(due_date.year, due_date.month, due_day)
    return due_date

