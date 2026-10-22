# Despliegue en Render: paso a paso

Guía de configuración del Web Service en Render para esta app (Flask + SQLAlchemy + Supabase).

## Qué cambió en el código y por qué

El error `ModuleNotFoundError: No module named 'psycopg'` se producía porque Render instalaba
la última versión de SQLAlchemy (2.1.x), que usa **psycopg 3** como driver por defecto para
URLs `postgresql://`, mientras el proyecto solo tenía instalado `psycopg2-binary`.

| Archivo | Cambio |
|---|---|
| `requirements.txt` | Todas las versiones fijadas (`==`). Se reemplazó `psycopg2-binary` por `psycopg[binary]`. |
| `.python-version` | Nuevo. Fija Python **3.12** (Render usaba 3.14 por defecto). |
| `database/connection.py` | Convierte `postgres://` y `postgresql://` a `postgresql+psycopg://` automáticamente. Añade `pool_pre_ping` y `pool_recycle` para Supabase. |

**No necesitas cambiar tu `DATABASE_URL` en Render**: puede seguir empezando por
`postgresql://postgres...`; el código agrega el driver por ti.

---

## Paso 1: Subir los cambios a GitHub

```bash
git add requirements.txt .python-version database/connection.py DEPLOY_RENDER.md
git commit -m "Fijar versiones y driver psycopg 3 para despliegue en Render"
git push origin main
```

## Paso 2: Revisar la configuración del servicio

En Render → tu Web Service → **Settings**:

| Campo | Valor |
|---|---|
| **Runtime** | Python 3 |
| **Branch** | `main` |
| **Root Directory** | *(vacío)* |
| **Build Command** | `pip install --upgrade pip && pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app --workers 2 --timeout 120` |

> `--timeout 120` evita que gunicorn mate al worker si la primera conexión a Supabase tarda
> (el código crea tablas y el usuario admin al arrancar).

## Paso 3: Revisar las variables de entorno

En Render → **Environment** → *Environment Variables*:

| Variable | Valor | Notas |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres.<proyecto>:<password>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres` | Ver advertencias abajo. |
| `SECRET_KEY` | Una cadena larga y aleatoria | Genérala con `python -c "import secrets; print(secrets.token_hex(32))"`. Si no la defines, la app usa una clave por defecto insegura. |
| `ADMIN_USERNAME` | Tu usuario | |
| `ADMIN_PASSWORD` | Una contraseña fuerte | Nunca dejes `changeme123`. |
| `FLASK_DEBUG` | `false` | |

**Elimina la variable `PYTHON_VERSION` si existe.** Tiene prioridad sobre `.python-version`
y podría volver a forzar otra versión de Python.

### Advertencias sobre `DATABASE_URL`

1. **Usa el host del *pooler* de Supabase**, no la conexión directa.
   - Correcto: `...@aws-0-sa-east-1.pooler.supabase.com:5432/postgres` (usuario `postgres.<proyecto>`)
   - Evitar: `...@db.<proyecto>.supabase.co:5432/postgres` (usuario `postgres` a secas).
     La conexión directa de Supabase es solo IPv6 y Render no la alcanza; falla con
     errores tipo `Network is unreachable`.
   - Lo encuentras en Supabase → *Connect* → **Session pooler**.
2. **Usa el puerto 5432 (Session mode).** El puerto 6543 (Transaction mode) requiere desactivar
   los *prepared statements* de psycopg; no lo cambies sin ajustar el código.
3. **Caracteres especiales en la contraseña** (`@ # / : ? %` etc.) deben ir codificados en la URL
   (por ejemplo `@` → `%40`, `#` → `%23`). Si no, la conexión falla con errores de host o de
   autenticación. Lo más simple es usar una contraseña solo alfanumérica.
4. Pega la URL **sin comillas y sin espacios** al inicio o al final.

## Paso 4: Desplegar limpiando la caché

En Render → **Manual Deploy** → **Clear build cache & deploy**.

Limpiar la caché asegura que no se reutilice el entorno anterior (Python 3.14 y paquetes viejos).

## Paso 5: Verificar los logs

Durante el **build** debes ver:

- [ ] `Using Python version 3.12.x` (o similar indicando 3.12)
- [ ] `Successfully installed ... psycopg-3.3.6 psycopg-binary-3.3.6 ... SQLAlchemy-2.0.55 ...`

Durante el **arranque**:

- [ ] `==> Running 'gunicorn app:app --workers 2 --timeout 120'`
- [ ] `[INFO] Usuario administrador '...' configurado correctamente.`
- [ ] `Listening at: http://0.0.0.0:10000`
- [ ] `==> Your service is live`

Luego abre la URL pública, inicia sesión y comprueba que el dashboard carga los datos de Supabase.

---

## Solución de problemas

| Error en los logs | Causa probable | Solución |
|---|---|---|
| `No module named 'psycopg'` | Build con caché o `requirements.txt` viejo | Confirmar que el push llegó a GitHub y usar *Clear build cache & deploy*. |
| `No module named 'psycopg2'` | La `DATABASE_URL` empieza por `postgresql+psycopg2://` | Cambiarla a `postgresql://...`. |
| `Python 3.14` en el build | Existe la variable `PYTHON_VERSION` o falta `.python-version` en el repo | Eliminar la variable y verificar que `.python-version` está subido. |
| `Network is unreachable` / `could not translate host name` | Se usa la conexión directa `db.<proyecto>.supabase.co` | Usar la URL del *Session pooler* (Paso 3). |
| `password authentication failed` | Contraseña incorrecta o con caracteres sin codificar | Revisar o codificar la contraseña. |
| `WORKER TIMEOUT` | Arranque lento conectando a Supabase | Mantener `--timeout 120`; revisar que Supabase no esté pausado (proyectos gratuitos se pausan por inactividad). |
| `server closed the connection unexpectedly` | Conexión inactiva cerrada por el pooler | Ya mitigado con `pool_pre_ping`; si persiste, revisar el estado de Supabase. |

## Mantenimiento: cómo actualizar dependencias sin romper el despliegue

1. Crea un entorno limpio con Python 3.12: `python -m venv .venv`, actívalo.
2. Cambia la versión en `requirements.txt` e instala: `pip install -r requirements.txt`.
3. Ejecuta `pip check` y prueba la app localmente (`python app.py`) contra Supabase.
4. Solo entonces haz commit, push y despliega.

Evita usar `>=` en `requirements.txt`: hace que Render instale versiones nuevas sin aviso,
que es justo lo que causó este error.
