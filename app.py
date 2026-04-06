from flask import Flask, render_template, request, send_file, redirect
from flask import session
import sqlite3
from datetime import datetime, timedelta
import os
import pandas as pd
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
template_folder=os.path.join(BASE_DIR,"templates"),
static_folder=os.path.join(BASE_DIR,"static"))

app.secret_key = "clave_super_segura_123"
USUARIO = "admin"
PASSWORD = "56161"

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        user = request.form["usuario"]
        password = request.form["password"]

        if user == USUARIO and password == PASSWORD:
            session["login"] = True
            return redirect("/admin")

    return """
    <h2>Login</h2>
    <form method="POST">
    Usuario<br>
    <input name="usuario"><br><br>
    Contraseña<br>
    <input name="password" type="password"><br><br>
    <button>Ingresar</button>
    </form>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# =========================
# CONFIG
# =========================

EMPRESA = "Hamburguesas La Parrillera"
WHATSAPP = "573137770641"

FACTURAS = os.path.join(BASE_DIR,"facturas")
EXCEL = os.path.join(BASE_DIR,"excel")
DB = os.path.join(BASE_DIR,"pedidos.db")

# =========================
# CREAR CARPETAS
# =========================

if not os.path.exists(FACTURAS):
    os.makedirs(FACTURAS)

if not os.path.exists(EXCEL):
    os.makedirs(EXCEL)

# =========================
# BASE DATOS
# =========================

conn = sqlite3.connect(DB)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS pedidos(
id INTEGER,
cliente TEXT,
telefono TEXT,
direccion TEXT,
barrio TEXT,
observaciones TEXT,
producto TEXT,
cantidad INTEGER,
valor INTEGER,
total INTEGER,
entrega TEXT,
estado TEXT
)
""")

conn.commit()
conn.close()

# =========================
# PRECIOS
# =========================

precios = {
"Hamburguesa 100g":1600,
"Caja 100g":47100,
"Hamburguesa 125g":2000,
"Caja 125g":59250,
"Hamburguesa 160g":2500,
"Caja 160g":72600
}

# =========================
# CONSECUTIVO
# =========================

def siguiente_consecutivo():

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(id) FROM pedidos")

    r = cursor.fetchone()[0]

    conn.close()

    if r is None:
        return 1
    else:
        return r + 1

# =========================
# PEDIDO
# =========================

@app.route("/", methods=["GET","POST"])
def pedido():
    try:

        if request.method == "POST":

            cliente = request.form.get("cliente","")
            telefono = request.form.get("telefono","")
            direccion = request.form.get("direccion","")
            barrio = request.form.get("barrio","")
            observaciones = request.form.get("observaciones","")

            pedidos = []
            total_general = 0

            for producto, precio in precios.items():

                cantidad = int(request.form.get(producto, 0) or 0)

                if cantidad > 0:

                    total = cantidad * precio
                    total_general += total

                    pedidos.append((producto,cantidad,precio,total))

            if not pedidos:
                return redirect("/")

            entrega = (datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d")

            pedido_id = siguiente_consecutivo()

            conn = sqlite3.connect(DB)
            cursor = conn.cursor()

            for p in pedidos:
                cursor.execute("""
                INSERT INTO pedidos
                (id,cliente,telefono,direccion,barrio,observaciones,
                producto,cantidad,valor,total,entrega,estado)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,(pedido_id,cliente,telefono,direccion,barrio,observaciones,
                     p[0],p[1],p[2],p[3],entrega,"pendiente"))

            conn.commit()
            conn.close()

            texto = f"{EMPRESA}\n"
            texto += f"Pedido No: {pedido_id}\n\n"
            texto += f"Cliente: {cliente}\n"
            texto += f"Telefono: {telefono}\n"
            texto += f"Direccion: {direccion}\n"
            texto += f"Barrio: {barrio}\n\n"

            texto += "PRODUCTOS:\n"

            for p in pedidos:
                texto += f"{p[0]} x {p[1]} = ${p[3]}\n"

            texto += f"\nTOTAL: ${total_general}\n"
            texto += f"Entrega: {entrega}\n"

            if observaciones:
                texto += f"\nObs: {observaciones}"

            mensaje = urllib.parse.quote(texto)

            url = f"https://api.whatsapp.com/send?phone={WHATSAPP}&text={mensaje}"

            return redirect(url)

        return render_template("pedido.html", precios=precios)

    except Exception as e:
        return f"ERROR: {str(e)}"


# =========================
# GENERAR FACTURA
# =========================

def generar_pdf(id,cliente,telefono,direccion,barrio,
observaciones,pedidos,total,entrega):

    archivo = os.path.join(FACTURAS,f"pedido_{id}.txt")

    f = open(archivo,"w",encoding="utf-8")

    f.write(f"{EMPRESA}\n")
    f.write("-------------------------\n\n")

    f.write(f"Pedido: {id}\n")
    f.write(f"Cliente: {cliente}\n")
    f.write(f"Telefono: {telefono}\n")
    f.write(f"Direccion: {direccion}\n")
    f.write(f"Barrio: {barrio}\n")
    f.write(f"Entrega: {entrega}\n\n")

    for p in pedidos:
        f.write(f"{p[0]}  {p[1]} x {p[2]} = {p[3]}\n")

    f.write(f"\nTOTAL: ${total}\n")

    if observaciones:
        f.write(f"\nOBS: {observaciones}")

    f.close()

# =========================
# MARCAR ENTREGADO
# =========================

@app.route("/entregado/<id>")
def entregado(id):

    if "login" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE pedidos 
    SET estado='entregado'
    WHERE id=?
    """,(id,))

    conn.commit()
    conn.close()

    return redirect("/rutas")

# =========================
# RUTAS
# =========================

@app.route("/rutas")
def rutas():

    if "login" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
    id,
    cliente,
    direccion,
    barrio,
    producto,
    cantidad,
    valor,
    total,
    entrega
    FROM pedidos
    WHERE estado='pendiente'
    ORDER BY entrega,barrio
    """)

    rows = cursor.fetchall()
    conn.close()

    pedidos = {}

    for r in rows:

        pedido_id = r[0]

        if pedido_id not in pedidos:
            pedidos[pedido_id] = {
                "cliente": r[1],
                "direccion": r[2],
                "barrio": r[3],
                "productos": [],
                "total": 0,
                "entrega": r[8]
            }

        pedidos[pedido_id]["productos"].append({
            "producto": r[4],
            "cantidad": r[5],
            "valor": r[6],
            "total": r[7]
        })

        pedidos[pedido_id]["total"] += r[7]

    fecha = ""
    if rows:
        fecha = rows[0][8]

    return render_template(
        "rutas.html",
        pedidos=pedidos,
        fecha=fecha
    )

# =========================
# ADMIN
# =========================

@app.route("/admin")
def admin():

    if "login" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pedidos ORDER BY id DESC")

    datos = cursor.fetchall()

    conn.close()

    return render_template("admin.html",datos=datos)

# =========================
# EXCEL
# =========================

@app.route("/excel")
def excel():

    if "login" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB)

    df = pd.read_sql_query("SELECT * FROM pedidos", conn)

    archivo = os.path.join(EXCEL,"pedidos.xlsx")

    df.to_excel(archivo,index=False)

    conn.close()

    return send_file(archivo, as_attachment=True)

# =========================

if __name__ == "__main__":
    app.run()