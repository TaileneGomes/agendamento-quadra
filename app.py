from flask import Flask, render_template, request, redirect, flash, session, Response
import psycopg2
import os
import random
import csv
import io
from datetime import date, datetime
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = "chave_secreta"

HORARIOS_DISPONIVEIS = [f"{h:02d}:00" for h in range(8, 22)]

DATABASE_URL = os.environ["DATABASE_URL"]

def conectar():
    return psycopg2.connect(DATABASE_URL)

def criar_banco():
    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            rua TEXT NOT NULL DEFAULT '',
            numero_casa TEXT NOT NULL DEFAULT '',
            data TEXT NOT NULL,
            horario TEXT NOT NULL,
            codigo TEXT NOT NULL DEFAULT ''
        )
    """)
    conexao.commit()
    conexao.close()

criar_banco()

def gerar_codigo():
    return str(random.randint(1000, 9999))

@app.route("/")
def index():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, data, horario, rua, numero_casa
        FROM agendamentos
        ORDER BY data, horario
    """)
    agendamentos = cursor.fetchall()

    mes_atual = date.today().strftime("%Y-%m")
    cursor.execute(
        "SELECT COUNT(*) FROM agendamentos WHERE data LIKE %s",
        (mes_atual + "%",)
    )
    total_mes = cursor.fetchone()[0]
    conexao.close()

    ultimo = None
    ultimo_id = session.pop("ultimo_agendamento_id", None)
    ultimo_codigo = session.pop("ultimo_codigo", None)
    if ultimo_id:
        conexao = conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT nome, data, horario FROM agendamentos WHERE id = %s", (ultimo_id,))
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

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT * FROM agendamentos WHERE data = %s AND horario = %s",
        (data_str, horario)
    )
    if cursor.fetchone():
        conexao.close()
        flash("⚠️ Horário já reservado!")
        return redirect("/")

    codigo = gerar_codigo()
    cursor.execute(
        "INSERT INTO agendamentos (nome, rua, numero_casa, data, horario, codigo) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (nome, rua, numero_casa, data_str, horario, codigo)
    )
    novo_id = cursor.fetchone()[0]
    conexao.commit()
    conexao.close()

    session["ultimo_agendamento_id"] = novo_id
    session["ultimo_codigo"] = codigo

    flash(f"✅ Agendamento realizado com sucesso! Guarde seu código: {codigo}")
    return redirect("/")

@app.route("/cancelar/<int:id>", methods=["POST"])
def cancelar(id):
    codigo = request.form.get("codigo", "").strip()

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("SELECT codigo FROM agendamentos WHERE id = %s", (id,))
    row = cursor.fetchone()

    if not row:
        conexao.close()
        flash("⚠️ Agendamento não encontrado")
        return redirect("/")

    if row[0] != codigo:
        conexao.close()
        flash("⚠️ Código incorreto. O cancelamento não foi feito")
        return redirect("/")

    cursor.execute("DELETE FROM agendamentos WHERE id = %s", (id,))
    conexao.commit()
    conexao.close()

    flash("❌ Agendamento cancelado!")
    return redirect("/")

@app.route("/editar/<int:id>")
def editar(id):
    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM agendamentos WHERE id = %s", (id,))
    agendamento = cursor.fetchone()
    conexao.close()

    return render_template(
        "editar.html",
        agendamento=agendamento,
        horarios=HORARIOS_DISPONIVEIS,
        data_minima=date.today().isoformat()
    )

@app.route("/atualizar/<int:id>", methods=["POST"])
def atualizar(id):
    codigo = request.form.get("codigo", "").strip()
    data_str = request.form["data"]
    horario = request.form["horario"]

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("SELECT codigo FROM agendamentos WHERE id = %s", (id,))
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
        WHERE data = %s AND horario = %s AND id != %s
    """, (data_str, horario, id))
    if cursor.fetchone():
        conexao.close()
        flash("⚠️ Esse horário já está ocupado!")
        return redirect("/")

    cursor.execute(
        "UPDATE agendamentos SET data = %s, horario = %s WHERE id = %s",
        (data_str, horario, id)
    )
    conexao.commit()
    conexao.close()

    flash("✏️ Agendamento atualizado!")
    return redirect("/")

@app.route("/relatorio")
def relatorio():
    conexao = conectar()
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)