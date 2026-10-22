import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()


def normalize_database_url(url):
    """Fuerza el driver psycopg (v3) en URLs de PostgreSQL.

    Render y Supabase entregan "postgres://" o "postgresql://" sin driver, y el
    driver por defecto cambia según la versión de SQLAlchemy (psycopg2 en 2.0,
    psycopg en 2.1). Declararlo explícitamente evita depender de ese default.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./finance.db"))
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # pool_pre_ping descarta conexiones que el pooler de Supabase ya cerró;
    # pool_recycle las renueva antes de que expiren por inactividad.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
