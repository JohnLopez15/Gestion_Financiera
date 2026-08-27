import streamlit as st
import plotly.express as px
from database.connection import get_db
from core.projections import generate_cashflow_projection

def render():
    st.title("Dashboard de Flujo de Caja")
    
    months = st.slider("Meses a proyectar", min_value=1, max_value=24, value=12)
    
    db = next(get_db())
    df, events = generate_cashflow_projection(db, months_ahead=months)
    
    if df.empty:
        st.warning("No hay datos para proyectar.")
        return
        
    # Check for illiquidity
    min_balance = df['balance'].min()
    if min_balance < 0:
        st.error(f"⚠️ Alerta de Iliquidez: El saldo proyectado cae a ${min_balance:,.2f} en algún punto del periodo.")
    else:
        st.success("✅ Flujo de caja saludable. No se detectan saldos negativos en la proyección.")
        
    # Chart
    fig = px.line(df, x='date', y='balance', title="Evolución del Saldo Total Proyectado")
    fig.add_hline(y=0, line_dash="dash", line_color="red")
    fig.update_layout(xaxis_title="Fecha", yaxis_title="Saldo ($)")
    st.plotly_chart(fig, use_container_width=True)
    
    with st.expander("Ver próximos eventos (30 días)"):
        if events:
            import pandas as pd
            import datetime
            events_df = pd.DataFrame(events)
            events_df['date'] = pd.to_datetime(events_df['date']).dt.date
            
            today = datetime.date.today()
            mask = (events_df['date'] >= today) & (events_df['date'] <= today + datetime.timedelta(days=30))
            filtered = events_df[mask].sort_values('date')
            
            if not filtered.empty:
                st.dataframe(filtered, use_container_width=True)
            else:
                st.write("No hay eventos en los próximos 30 días.")
        else:
            st.write("No hay eventos registrados.")

