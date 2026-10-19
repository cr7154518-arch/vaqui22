# Vaquí — Consulta y control de finanzas personales

Vaquí ya **no es una billetera que mueve dinero** (recargas/transferencias tipo Nequi).
Ahora es una app para **consultar y controlar tus finanzas personales**: registras tus
ingresos y gastos, los clasificas por categoría, defines presupuestos y ves el panorama.
Hecha con **Flask + PostgreSQL**, lista para **Render**.

## Funciones
- Registro / login (correo + contraseña, bcrypt). Sin PIN ni celular.
- **Cuentas** (efectivo, banco, tarjeta, ahorros) con saldo calculado = saldo inicial + ingresos − gastos.
- **Movimientos**: ingresos y gastos con categoría, cuenta, fecha y descripción; filtros por tipo, categoría y texto.
- **Categorías** por defecto al registrarse (editables vía API).
- **Presupuestos** mensuales por categoría de gasto, con alerta al 80 % y al superar el límite.
- **Resumen mensual**: ingresos, gastos, ahorro, gasto por categoría y tendencia de 6 meses.

## Estructura
```
app.py · config.py · extensions.py · models.py
routes/auth.py        # /login /registro /logout
routes/finance.py     # /dashboard + API JSON
templates/            # base, index, login, register, dashboard
static/css/style.css · static/js/{main,dashboard}.js
```

## API (todas requieren sesión)
| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/summary?month=YYYY-MM` | KPIs, categorías, presupuestos, tendencia, cuentas |
| GET/POST | `/api/movements` | listar (filtros `month,type,category_id,account_id,q`) / crear |
| PUT/DELETE | `/api/movements/<id>` | editar / borrar |
| GET/POST | `/api/categories` · DELETE `/api/categories/<id>` | categorías |
| GET/POST | `/api/accounts` · DELETE `/api/accounts/<id>` | cuentas |
| POST | `/api/budgets` · DELETE `/api/budgets/<id>` | crear/actualizar y quitar presupuesto |

## Cambios respecto a la versión billetera
- Eliminados: `Wallet`, `Transaction`, `pin_hash`, `phone`, `/api/deposit`, `/api/transfer`, `routes/wallet.py`.
- Nuevos modelos: `Account`, `Category`, `Movement`, `Budget`.
- **Base de datos existente:** `db.create_all()` no modifica tablas viejas. En Render (o local) hay que
  borrar/recrear la base (`wallet-db`) o migrar: la tabla `users` ya no tiene `phone` ni `pin_hash`
  (NOT NULL), y las tablas `wallets`/`transactions` quedan obsoletas.

## Instalación local
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
createdb wallet_db
cp .env.example .env   # ajusta DATABASE_URL y SECRET_KEY
python app.py          # http://localhost:5000
```

## Despliegue en Render
Igual que antes: **New → Blueprint** con este repo (`render.yaml`), o manual con
Build `pip install -r requirements.txt` y Start `gunicorn app:app`, más `DATABASE_URL` y `SECRET_KEY`.

## Ideas siguientes
Editar movimientos desde la UI, movimientos recurrentes, metas de ahorro, exportar a CSV, migraciones con Flask-Migrate.
