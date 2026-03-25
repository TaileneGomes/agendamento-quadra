from flask import Flask, render_template, request, redirect, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "chave_secreta"

# -----------------------------
# Criar banco de dados
# -----------------------------
def criar_banco():
    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            data TEXT NOT NULL,
            horario TEXT NOT NULL
        )
    """)
    conexao.commit()
    conexao.close()

criar_banco()

# -----------------------------
# Página inicial
# -----------------------------
@app.route("/")
def index():
    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, data, horario 
        FROM agendamentos 
        ORDER BY data, horario
    """)

    agendamentos = cursor.fetchall()
    conexao.close()

    return render_template("index.html", agendamentos=agendamentos)

# -----------------------------
# Novo agendamento
# -----------------------------
@app.route("/agenda", methods=["POST"])
def agenda():
    nome = request.form["nome"]
    data = request.form["data"]
    horario = request.form["horario"]

    # Limite de horário
    if horario < "08:00" or horario > "22:00":
        flash("⚠️ Horário permitido apenas entre 08:00 e 22:00")
        return redirect("/")

    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    # Verificar conflito
    cursor.execute(
        "SELECT * FROM agendamentos WHERE data = ? AND horario = ?",
        (data, horario)
    )

    if cursor.fetchone():
        conexao.close()
        flash("⚠️ Horário já reservado! Escolha outro.")
        return redirect("/")

    cursor.execute(
        "INSERT INTO agendamentos (nome, data, horario) VALUES (?, ?, ?)",
        (nome, data, horario)
    )

    conexao.commit()
    conexao.close()

    flash("✅ Agendamento realizado com sucesso!")
    return redirect("/")

# -----------------------------
# Cancelar
# -----------------------------
@app.route("/cancelar/<int:id>")
def cancelar(id):
    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    cursor.execute("DELETE FROM agendamentos WHERE id = ?", (id,))
    conexao.commit()
    conexao.close()

    flash("❌ Agendamento cancelado!")
    return redirect("/")

# -----------------------------
# Editar
# -----------------------------
@app.route("/editar/<int:id>")
def editar(id):
    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    cursor.execute("SELECT * FROM agendamentos WHERE id = ?", (id,))
    agendamento = cursor.fetchone()

    conexao.close()
    return render_template("editar.html", agendamento=agendamento)

# -----------------------------
# Atualizar
# -----------------------------
@app.route("/atualizar/<int:id>", methods=["POST"])
def atualizar(id):
    data = request.form["data"]
    horario = request.form["horario"]

    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    # evitar conflito
    cursor.execute("""
        SELECT * FROM agendamentos 
        WHERE data = ? AND horario = ? AND id != ?
    """, (data, horario, id))

    if cursor.fetchone():
        conexao.close()
        flash("⚠️ Esse horário já está reservado!")
        return redirect("/")

    cursor.execute(
        "UPDATE agendamentos SET data = ?, horario = ? WHERE id = ?",
        (data, horario, id)
    )

    conexao.commit()
    conexao.close()

    flash("✏️ Agendamento atualizado!")
    return redirect("/")

# -----------------------------
# RODAR NO RENDER (IMPORTANTE)
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)