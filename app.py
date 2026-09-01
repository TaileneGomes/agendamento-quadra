from flask import Flask, render_template, request, redirect, flash, session, Response
import sqlite3
import os
import random
import csv
import io
from datetime import date, datetime
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = "chave_secreta"

HORARIOS_DISPONIVEIS = [f"{h:02d}:00" for h in range(8, 22)]  # 08:00 até 21:00

# -----------------------------
# Criar/migrar banco automaticamente
# -----------------------------
def criar_banco():
    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            rua TEXT NOT NULL DEFAULT '',
            numero_casa TEXT NOT NULL DEFAULT '',
            data TEXT NOT NULL,
            horario TEXT NOT NULL,
            codigo TEXT NOT NULL DEFAULT ''
        )
    """)

    # migração leve, caso o banco já exista sem as colunas novas
    colunas_existentes = [c[1] for c in cursor.execute("PRAGMA table_info(agendamentos)")]
    if "rua" not in colunas_existentes:
        cursor.execute("ALTER TABLE agendamentos ADD COLUMN rua TEXT NOT NULL DEFAULT ''")
    if "numero_casa" not in colunas_existentes:
        cursor.execute("ALTER TABLE agendamentos ADD COLUMN numero_casa TEXT NOT NULL DEFAULT ''")
    if "codigo" not in colunas_existentes:
        cursor.execute("ALTER TABLE agendamentos ADD COLUMN codigo TEXT NOT NULL DEFAULT ''")

    conexao.commit()
    conexao.close()

criar_banco()

def gerar_codigo():
    return str(random.randint(1000, 9999))

# -----------------------------
# Página inicial
# -----------------------------
@app.route("/")
def index():
    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, data, horario, rua, numero_casa
        FROM agendamentos
        ORDER BY data, horario
    """)
    agendamentos = cursor.fetchall()

    mes_atual = date.today().strftime("%Y-%m")
    cursor.execute(
        "SELECT COUNT(*) FROM agendamentos WHERE data LIKE ?",
        (mes_atual + "%",)
    )
    total_mes = cursor.fetchone()[0]
    conexao.close()

    # mostra o código e o link do WhatsApp logo após um agendamento novo
    ultimo = None
    ultimo_id = session.pop("ultimo_agendamento_id", None)
    ultimo_codigo = session.pop("ultimo_codigo", None)
    if ultimo_id:
        conexao = sqlite3.connect("agenda.db")
        cursor = conexao.cursor()
        cursor.execute("SELECT nome, data, horario FROM agendamentos WHERE id = ?", (ultimo_id,))
        row = cursor.fetchone()
        conexao.close()
        if row:
            texto = f"Reservei a quadra do Moradas Sul para {row[0]} no dia {row[1]} às {row[2]}."
            ultimo = {
                "codigo": ultimo_codigo,
                "whatsapp_link": f"https://wa.me/?text={quote(texto)}"
            }

    return render_template(
        "index.html",
        agendamentos=agendamentos,
        horarios=HORARIOS_DISPONIVEIS,
        data_minima=date.today().isoformat(),
        total_mes=total_mes,
        ultimo=ultimo
    )

# -----------------------------
# Novo agendamento
# -----------------------------
@app.route("/agenda", methods=["POST"])
def agenda():
    nome = request.form["nome"].strip()
    rua = request.form["rua"].strip()
    numero_casa = request.form["numero_casa"].strip()
    data_str = request.form["data"]
    horario = request.form["horario"]

    if horario not in HORARIOS_DISPONIVEIS:
        flash("⚠️ Horário inválido")
        return redirect("/")

    try:
        data_escolhida = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        flash("⚠️ Data inválida")
        return redirect("/")

    if data_escolhida < date.today():
        flash("⚠️ Não é possível agendar em uma data que já passou")
        return redirect("/")

    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT * FROM agendamentos WHERE data = ? AND horario = ?",
        (data_str, horario)
    )
    if cursor.fetchone():
        conexao.close()
        flash("⚠️ Horário já reservado!")
        return redirect("/")

    codigo = gerar_codigo()
    cursor.execute(
        "INSERT INTO agendamentos (nome, rua, numero_casa, data, horario, codigo) VALUES (?, ?, ?, ?, ?, ?)",
        (nome, rua, numero_casa, data_str, horario, codigo)
    )
    conexao.commit()
    novo_id = cursor.lastrowid
    conexao.close()

    session["ultimo_agendamento_id"] = novo_id
    session["ultimo_codigo"] = codigo

    flash(f"✅ Agendamento realizado com sucesso! Guarde seu código: {codigo}")
    return redirect("/")

# -----------------------------
# Cancelar (exige código)
# -----------------------------
@app.route("/cancelar/<int:id>", methods=["POST"])
def cancelar(id):
    codigo = request.form.get("codigo", "").strip()

    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()
    cursor.execute("SELECT codigo FROM agendamentos WHERE id = ?", (id,))
    row = cursor.fetchone()

    if not row:
        conexao.close()
        flash("⚠️ Agendamento não encontrado")
        return redirect("/")

    if row[0] != codigo:
        conexao.close()
        flash("⚠️ Código incorreto. O cancelamento não foi feito")
        return redirect("/")

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

    return render_template(
        "editar.html",
        agendamento=agendamento,
        horarios=HORARIOS_DISPONIVEIS,
        data_minima=date.today().isoformat()
    )

# -----------------------------
# Atualizar (exige código)
# -----------------------------
@app.route("/atualizar/<int:id>", methods=["POST"])
def atualizar(id):
    codigo = request.form.get("codigo", "").strip()
    data_str = request.form["data"]
    horario = request.form["horario"]

    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()

    cursor.execute("SELECT codigo FROM agendamentos WHERE id = ?", (id,))
    row = cursor.fetchone()
    if not row:
        conexao.close()
        flash("⚠️ Agendamento não encontrado")
        return redirect("/")

    if row[0] != codigo:
        conexao.close()
        flash("⚠️ Código incorreto. A edição não foi feita")
        return redirect("/")

    if horario not in HORARIOS_DISPONIVEIS:
        conexao.close()
        flash("⚠️ Horário inválido")
        return redirect("/")

    try:
        data_escolhida = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        conexao.close()
        flash("⚠️ Data inválida")
        return redirect("/")

    if data_escolhida < date.today():
        conexao.close()
        flash("⚠️ Não é possível agendar em uma data que já passou")
        return redirect("/")

    cursor.execute("""
        SELECT * FROM agendamentos
        WHERE data = ? AND horario = ? AND id != ?
    """, (data_str, horario, id))
    if cursor.fetchone():
        conexao.close()
        flash("⚠️ Esse horário já está ocupado!")
        return redirect("/")

    cursor.execute(
        "UPDATE agendamentos SET data = ?, horario = ? WHERE id = ?",
        (data_str, horario, id)
    )
    conexao.commit()
    conexao.close()

    flash("✏️ Agendamento atualizado!")
    return redirect("/")

# -----------------------------
# Relatório em CSV (evidência de uso)
# -----------------------------
@app.route("/relatorio")
def relatorio():
    conexao = sqlite3.connect("agenda.db")
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT id, nome, rua, numero_casa, data, horario
        FROM agendamentos
        ORDER BY data, horario
    """)
    linhas = cursor.fetchall()
    conexao.close()

    saida = io.StringIO()
    escritor = csv.writer(saida)
    escritor.writerow(["ID", "Nome", "Rua", "Número da casa", "Data", "Horário"])
    escritor.writerows(linhas)

    return Response(
        saida.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=relatorio_agendamentos.csv"}
    )

# -----------------------------
# RODAR NO RENDER (ESSENCIAL)
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
