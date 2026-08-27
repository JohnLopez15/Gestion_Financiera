import streamlit as st
from database.connection import Base, engine
import views.dashboard
import views.products
import views.movements

# Initialize DB
Base.metadata.create_all(bind=engine)

st.set_page_config(page_title="Gestión Financiera", page_icon="💰", layout="wide")

st.sidebar.title("Gestión Financiera")
page = st.sidebar.radio("Navegación", ["Dashboard", "Cuentas y Tarjetas", "Movimientos"])

if page == "Dashboard":
    views.dashboard.render()
elif page == "Cuentas y Tarjetas":
    views.products.render()
elif page == "Movimientos":
    views.movements.render()

