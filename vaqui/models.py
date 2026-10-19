import uuid
from datetime import datetime, date
from flask_login import UserMixin
from extensions import db


def gen_uuid():
    return str(uuid.uuid4())


DEFAULT_CATEGORIES = [
    ("Salario", "income"), ("Otros ingresos", "income"),
    ("Alimentación", "expense"), ("Transporte", "expense"), ("Vivienda", "expense"),
    ("Servicios", "expense"), ("Salud", "expense"), ("Educación", "expense"),
    ("Entretenimiento", "expense"), ("Otros gastos", "expense"),
]


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    accounts = db.relationship("Account", backref="owner", cascade="all, delete-orphan")
    categories = db.relationship("Category", backref="owner", cascade="all, delete-orphan")
    movements = db.relationship("Movement", backref="owner", cascade="all, delete-orphan")
    budgets = db.relationship("Budget", backref="owner", cascade="all, delete-orphan")

    def get_id(self):
        return self.id


class Account(db.Model):
    """Cuenta o bolsillo que el usuario quiere consultar (efectivo, banco, tarjeta...)."""
    __tablename__ = "accounts"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    kind = db.Column(db.String(20), default="cash")  # cash | bank | card | savings
    initial_balance = db.Column(db.Numeric(14, 2), default=0)

    movements = db.relationship("Movement", backref="account")


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(60), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # income | expense

    movements = db.relationship("Movement", backref="category")
    budgets = db.relationship("Budget", backref="category", cascade="all, delete-orphan")


class Movement(db.Model):
    """Ingreso o gasto registrado manualmente (no mueve dinero real)."""
    __tablename__ = "movements"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    account_id = db.Column(db.String(36), db.ForeignKey("accounts.id"), nullable=False)
    category_id = db.Column(db.String(36), db.ForeignKey("categories.id"), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # income | expense
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    description = db.Column(db.String(255))
    date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "amount": float(self.amount),
            "description": self.description or "",
            "date": self.date.isoformat(),
            "category_id": self.category_id,
            "category": self.category.name,
            "account_id": self.account_id,
            "account": self.account.name,
        }


class Budget(db.Model):
    """Límite mensual de gasto por categoría."""
    __tablename__ = "budgets"
    __table_args__ = (db.UniqueConstraint("user_id", "category_id", name="uq_budget_user_category"),)

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.String(36), db.ForeignKey("categories.id"), nullable=False)
    monthly_limit = db.Column(db.Numeric(14, 2), nullable=False)
