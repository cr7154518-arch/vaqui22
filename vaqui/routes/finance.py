from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import Account, Category, Movement, Budget

finance_bp = Blueprint("finance", __name__)


# ---------- Helpers ----------

def parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount > 0 else None


def parse_month(value):
    """'YYYY-MM' -> (primer día, primer día del mes siguiente). Por defecto el mes actual."""
    try:
        start = datetime.strptime(value, "%Y-%m").date()
    except (TypeError, ValueError):
        today = date.today()
        start = date(today.year, today.month, 1)
    end = date(start.year + (start.month == 12), (start.month % 12) + 1, 1)
    return start, end


def own(model, obj_id):
    return model.query.filter_by(id=obj_id, user_id=current_user.id).first()


def account_balance(account):
    income = db.session.query(func.coalesce(func.sum(Movement.amount), 0)).filter_by(
        account_id=account.id, type="income").scalar()
    expense = db.session.query(func.coalesce(func.sum(Movement.amount), 0)).filter_by(
        account_id=account.id, type="expense").scalar()
    return float(account.initial_balance or 0) + float(income) - float(expense)


# ---------- Página ----------

@finance_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


# ---------- Resumen ----------

@finance_bp.route("/api/summary")
@login_required
def api_summary():
    start, end = parse_month(request.args.get("month"))
    base = Movement.query.filter(
        Movement.user_id == current_user.id, Movement.date >= start, Movement.date < end)

    def total(mtype):
        return float(db.session.query(func.coalesce(func.sum(Movement.amount), 0)).filter(
            Movement.user_id == current_user.id, Movement.type == mtype,
            Movement.date >= start, Movement.date < end).scalar())

    income, expense = total("income"), total("expense")

    # Gasto por categoría (mes)
    rows = (db.session.query(Category.id, Category.name, func.sum(Movement.amount))
            .join(Movement, Movement.category_id == Category.id)
            .filter(Movement.user_id == current_user.id, Movement.type == "expense",
                    Movement.date >= start, Movement.date < end)
            .group_by(Category.id, Category.name)
            .order_by(func.sum(Movement.amount).desc()).all())
    by_category = [{"id": r[0], "name": r[1], "amount": float(r[2])} for r in rows]
    spent_by_cat = {r["id"]: r["amount"] for r in by_category}

    # Presupuestos (mes)
    budgets = []
    for b in Budget.query.filter_by(user_id=current_user.id).all():
        spent = spent_by_cat.get(b.category_id, 0)
        limit = float(b.monthly_limit)
        budgets.append({
            "id": b.id, "category": b.category.name, "limit": limit, "spent": spent,
            "percent": round(spent / limit * 100, 1) if limit else 0,
        })

    # Últimos 6 meses (ingresos vs gastos)
    trend = []
    y, m = start.year, start.month
    months = []
    for _ in range(6):
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    for (y, m) in reversed(months):
        s = date(y, m, 1)
        e = date(y + (m == 12), (m % 12) + 1, 1)
        vals = dict(db.session.query(Movement.type, func.coalesce(func.sum(Movement.amount), 0)).filter(
            Movement.user_id == current_user.id, Movement.date >= s, Movement.date < e
        ).group_by(Movement.type).all())
        trend.append({"month": f"{y}-{m:02d}", "income": float(vals.get("income", 0)),
                      "expense": float(vals.get("expense", 0))})

    accounts = [{"id": a.id, "name": a.name, "kind": a.kind, "balance": account_balance(a)}
                for a in Account.query.filter_by(user_id=current_user.id).all()]

    return jsonify({
        "month": start.strftime("%Y-%m"),
        "income": income, "expense": expense, "net": income - expense,
        "total_balance": sum(a["balance"] for a in accounts),
        "by_category": by_category, "budgets": budgets, "trend": trend, "accounts": accounts,
        "movement_count": base.count(),
    })


# ---------- Movimientos ----------

@finance_bp.route("/api/movements", methods=["GET"])
@login_required
def list_movements():
    q = Movement.query.filter_by(user_id=current_user.id)
    if request.args.get("month"):
        start, end = parse_month(request.args["month"])
        q = q.filter(Movement.date >= start, Movement.date < end)
    for arg, col in (("type", Movement.type), ("category_id", Movement.category_id),
                     ("account_id", Movement.account_id)):
        if request.args.get(arg):
            q = q.filter(col == request.args[arg])
    if request.args.get("q"):
        q = q.filter(Movement.description.ilike(f"%{request.args['q']}%"))
    items = q.order_by(Movement.date.desc(), Movement.created_at.desc()).limit(200).all()
    return jsonify([m.to_dict() for m in items])


def _apply_movement(mv, data):
    """Valida y asigna los campos de un movimiento. Devuelve mensaje de error o None."""
    mtype = data.get("type")
    if mtype not in ("income", "expense"):
        return "Tipo inválido"
    amount = parse_amount(data.get("amount"))
    if amount is None:
        return "El monto debe ser mayor a cero"
    category = own(Category, data.get("category_id"))
    account = own(Account, data.get("account_id"))
    if not category or not account:
        return "Categoría o cuenta inválida"
    if category.type != mtype:
        return "La categoría no corresponde al tipo de movimiento"
    try:
        mv_date = datetime.strptime(data.get("date") or date.today().isoformat(), "%Y-%m-%d").date()
    except ValueError:
        return "Fecha inválida"

    mv.type, mv.amount, mv.date = mtype, amount, mv_date
    mv.category_id, mv.account_id = category.id, account.id
    mv.description = str(data.get("description", "")).strip()[:255]
    return None


@finance_bp.route("/api/movements", methods=["POST"])
@login_required
def create_movement():
    mv = Movement(user_id=current_user.id)
    err = _apply_movement(mv, request.get_json(force=True))
    if err:
        return jsonify({"error": err}), 400
    db.session.add(mv)
    db.session.commit()
    return jsonify(mv.to_dict()), 201


@finance_bp.route("/api/movements/<mv_id>", methods=["PUT"])
@login_required
def update_movement(mv_id):
    mv = own(Movement, mv_id)
    if not mv:
        return jsonify({"error": "Movimiento no encontrado"}), 404
    err = _apply_movement(mv, request.get_json(force=True))
    if err:
        return jsonify({"error": err}), 400
    db.session.commit()
    return jsonify(mv.to_dict())


@finance_bp.route("/api/movements/<mv_id>", methods=["DELETE"])
@login_required
def delete_movement(mv_id):
    mv = own(Movement, mv_id)
    if not mv:
        return jsonify({"error": "Movimiento no encontrado"}), 404
    db.session.delete(mv)
    db.session.commit()
    return jsonify({"ok": True})


# ---------- Categorías ----------

@finance_bp.route("/api/categories", methods=["GET"])
@login_required
def list_categories():
    cats = Category.query.filter_by(user_id=current_user.id).order_by(Category.type, Category.name).all()
    return jsonify([{"id": c.id, "name": c.name, "type": c.type} for c in cats])


@finance_bp.route("/api/categories", methods=["POST"])
@login_required
def create_category():
    data = request.get_json(force=True)
    name = str(data.get("name", "")).strip()[:60]
    ctype = data.get("type")
    if not name or ctype not in ("income", "expense"):
        return jsonify({"error": "Nombre o tipo inválido"}), 400
    if Category.query.filter_by(user_id=current_user.id, name=name, type=ctype).first():
        return jsonify({"error": "Esa categoría ya existe"}), 400
    c = Category(user_id=current_user.id, name=name, type=ctype)
    db.session.add(c)
    db.session.commit()
    return jsonify({"id": c.id, "name": c.name, "type": c.type}), 201


@finance_bp.route("/api/categories/<cat_id>", methods=["DELETE"])
@login_required
def delete_category(cat_id):
    c = own(Category, cat_id)
    if not c:
        return jsonify({"error": "Categoría no encontrada"}), 404
    if c.movements:
        return jsonify({"error": "No puedes borrar una categoría con movimientos"}), 400
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True})


# ---------- Cuentas ----------

@finance_bp.route("/api/accounts", methods=["POST"])
@login_required
def create_account():
    data = request.get_json(force=True)
    name = str(data.get("name", "")).strip()[:80]
    kind = data.get("kind", "cash")
    if not name or kind not in ("cash", "bank", "card", "savings"):
        return jsonify({"error": "Nombre o tipo inválido"}), 400
    try:
        initial = Decimal(str(data.get("initial_balance") or 0))
    except InvalidOperation:
        return jsonify({"error": "Saldo inicial inválido"}), 400
    a = Account(user_id=current_user.id, name=name, kind=kind, initial_balance=initial)
    db.session.add(a)
    db.session.commit()
    return jsonify({"id": a.id, "name": a.name, "kind": a.kind, "balance": account_balance(a)}), 201


@finance_bp.route("/api/accounts/<acc_id>", methods=["DELETE"])
@login_required
def delete_account(acc_id):
    a = own(Account, acc_id)
    if not a:
        return jsonify({"error": "Cuenta no encontrada"}), 404
    if a.movements:
        return jsonify({"error": "No puedes borrar una cuenta con movimientos"}), 400
    db.session.delete(a)
    db.session.commit()
    return jsonify({"ok": True})


@finance_bp.route("/api/accounts", methods=["GET"])
@login_required
def list_accounts():
    return jsonify([{"id": a.id, "name": a.name, "kind": a.kind, "balance": account_balance(a)}
                    for a in Account.query.filter_by(user_id=current_user.id).all()])


# ---------- Presupuestos ----------

@finance_bp.route("/api/budgets", methods=["POST"])
@login_required
def upsert_budget():
    data = request.get_json(force=True)
    category = own(Category, data.get("category_id"))
    limit = parse_amount(data.get("monthly_limit"))
    if not category or category.type != "expense":
        return jsonify({"error": "Elige una categoría de gasto"}), 400
    if limit is None:
        return jsonify({"error": "El límite debe ser mayor a cero"}), 400
    b = Budget.query.filter_by(user_id=current_user.id, category_id=category.id).first()
    if b:
        b.monthly_limit = limit
    else:
        db.session.add(Budget(user_id=current_user.id, category_id=category.id, monthly_limit=limit))
    db.session.commit()
    return jsonify({"ok": True}), 201


@finance_bp.route("/api/budgets/<b_id>", methods=["DELETE"])
@login_required
def delete_budget(b_id):
    b = own(Budget, b_id)
    if not b:
        return jsonify({"error": "Presupuesto no encontrado"}), 404
    db.session.delete(b)
    db.session.commit()
    return jsonify({"ok": True})
