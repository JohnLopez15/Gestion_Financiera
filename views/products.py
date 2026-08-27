import streamlit as st
import pandas as pd
from database.connection import get_db
from database.models import Account, CreditCard

def render():
    st.title("Gestión de Cuentas y Tarjetas")
    
    db = next(get_db())
    
    tab1, tab2 = st.tabs(["Cuentas de Ahorro", "Tarjetas de Crédito"])
    
    with tab1:
        st.subheader("Nueva Cuenta")
        with st.form("new_account"):
            name = st.text_input("Nombre de la cuenta")
            balance = st.number_input("Saldo Actual", value=0.0, format="%.2f")
            submitted = st.form_submit_button("Guardar")
            if submitted and name:
                new_acc = Account(name=name, balance=balance)
                db.add(new_acc)
                db.commit()
                st.success("Cuenta agregada")
                st.rerun()
                
        st.subheader("Cuentas Existentes")
        accounts = db.query(Account).all()
        if accounts:
            data = [{"ID": a.id, "Nombre": a.name, "Saldo": a.balance} for a in accounts]
            st.dataframe(pd.DataFrame(data), hide_index=True)
            
            # Simple Delete
            del_id = st.selectbox("Selecciona ID para eliminar", [a.id for a in accounts], key="del_acc")
            if st.button("Eliminar Cuenta"):
                acc = db.query(Account).get(del_id)
                db.delete(acc)
                db.commit()
                st.rerun()

    with tab2:
        st.subheader("Nueva Tarjeta de Crédito")
        with st.form("new_cc"):
            name = st.text_input("Nombre de la Tarjeta")
            limit = st.number_input("Cupo Total", min_value=0.0, value=0.0)
            debt = st.number_input("Deuda Actual", min_value=0.0, value=0.0)
            next_pay = st.number_input("Monto Próximo Pago", min_value=0.0, value=0.0)
            statement_day = st.number_input("Día de Corte (1-31)", min_value=1, max_value=31, value=15)
            due_day = st.number_input("Día de Pago (1-31)", min_value=1, max_value=31, value=5)
            
            submitted = st.form_submit_button("Guardar Tarjeta")
            if submitted and name:
                new_cc = CreditCard(
                    name=name, 
                    credit_limit=limit, 
                    current_debt=debt,
                    next_payment_amount=next_pay,
                    statement_day=statement_day,
                    due_day=due_day
                )
                db.add(new_cc)
                db.commit()
                st.success("Tarjeta agregada")
                st.rerun()
                
        st.subheader("Tarjetas Existentes")
        cards = db.query(CreditCard).all()
        if cards:
            data = [{
                "ID": c.id, "Nombre": c.name, "Deuda": c.current_debt, 
                "Próximo Pago": c.next_payment_amount, 
                "Corte": c.statement_day, "Pago": c.due_day
            } for c in cards]
            st.dataframe(pd.DataFrame(data), hide_index=True)
            
            del_cc_id = st.selectbox("Selecciona ID para eliminar", [c.id for c in cards], key="del_cc")
            if st.button("Eliminar Tarjeta"):
                cc = db.query(CreditCard).get(del_cc_id)
                db.delete(cc)
                db.commit()
                st.rerun()

