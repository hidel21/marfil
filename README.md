# Sistema Marfil

Aplicación Streamlit para gestionar inventario, ventas, cuotas, cobranza y reportes.

## Ejecución local

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATABASE_URL="postgresql://usuario:contraseña@localhost:5432/marfil"
streamlit run app.py
```

La aplicación queda disponible en <http://localhost:8501>.

También puedes guardar la conexión local en `.streamlit/secrets.toml`:

```toml
DATABASE_URL = "postgresql://usuario:contraseña@localhost:5432/marfil"
```

Este archivo está excluido de Git. En Streamlit Community Cloud, configura
`DATABASE_URL` desde **App settings → Secrets**.
