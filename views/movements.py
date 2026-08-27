import streamlit as st
import pandas as pd
import datetime
from database.connection import get_db
from database.models import Transaction, TransactionTypeEnum, PeriodicityEnum, CreditCard

def render():
    st.title("Gestión de Movimientos")
    db = next(get_db())
    
    st.subheader("Nuevo Movimiento")
    with st.form("new_movement"):
        desc = st.text_input("Descripción")
        amount = st.number_input("Monto", min_value=0.01, value=100.0)
        
        type_val = st.selectbox("Tipo", ["Gasto", "Ingreso"])
        
        # Determine if paid with CC or cash pool
        cards = db.query(CreditCard).all()
        card_options = ["Ninguna (Cuentas Ahorro)"] + [c.name for c in cards]
        selected_card_name = st.selectbox("Método de Pago", card_options)
        
        is_rec = st.checkbox("Es Recurrente?")
        period = st.selectbox("Periodicidad", [e.value for e in PeriodicityEnum])
        
        start_date = st.date_input("Fecha (o Fecha de Inicio)", datetime.date.today())
        
        submitted = st.form_submit_button("Guardar")
        if submitted and desc:
            cc_id = None
            if selected_card_name != "Ninguna (Cuentas Ahorro)":
                cc = next(c for c in cards if c.name == selected_card_name)
                cc_id = cc.id
                
            enum_type = TransactionTypeEnum.expense if type_val == "Gasto" else TransactionTypeEnum.income
            enum_period = next(e for e in PeriodicityEnum if e.value == period)
            
            new_tx = Transaction(
                description=desc,
                amount=amount,
                type=enum_type,
                credit_card_id=cc_id,
                is_recurring=is_rec,
                periodicity=enum_period if is_rec else PeriodicityEnum.unique,
                start_date=start_date,
                is_active=True
            )
            db.add(new_tx)
            db.commit()
            st.success("Movimiento guardado")
            st.rerun()
            
    st.subheader("Movimientos Registrados")
    transactions = db.query(Transaction).all()
    if transactions:
        data = []
        for t in transactions:
            data.append({
                "ID": t.id,
                "Descripción": t.description,
                "Monto": t.amount,
                "Tipo": t.type.value,
                "Recurrente": "Sí" if t.is_recurring else "No",
                "Periodicidad": t.periodicity.value,
                "Fecha": t.start_date,
                "Activo": "Sí" if t.is_active else "No"
            })
        st.dataframe(pd.DataFrame(data), hide_index=True)
        
        col1, col2 = st.columns(2)
        with col1:
            toggle_id = st.selectbox("ID para Activar/Desactivar", [t.id for t in transactions], key="toggle")
            if st.button("Cambiar Estado"):
                t = db.query(Transaction).get(toggle_id)
                t.is_active = not t.is_active
                db.commit()
                st.rerun()
                
        with col2:
            del_id = st.selectbox("ID para Eliminar", [t.id for t in transactions], key="del_tx")
            if st.button("Eliminar"):
                t = db.query(Transaction).get(del_id)
                db.delete(t)
                db.commit()
                st.rerun()

