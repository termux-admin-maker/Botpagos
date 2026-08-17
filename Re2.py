import sqlite3
import logging
import os
import datetime
import html
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# ==========================================
# 🌸 CONFIGURACIÓN GLOBAL
# ==========================================
TOKEN = "8808351888:AAGAaklQEFzQ-wrP1Ywy4J4DhPp-C08wPSE"
ADMIN_ID = 8591487777  # TU ID DE TELEGRAM (El Jefe / La Jefa 👑)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "si.db")

# Estados de Conversación
(ENV_COMP_MONTO, ENV_COMP_FOTO, CREAR_COMP_MONTO,
 ADM_ADD_PAIS_NOM, ADM_ADD_PAIS_DATOS, ADM_EDIT_TASA, ADM_EDIT_DET,
 ADM_EDIT_SOPORTE, ADM_EDIT_BOT, ADM_EDIT_IMG, ADM_BUSCAR_USER) = range(11)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 🗄️ BASE DE DATOS Y HERRAMIENTAS
# ==========================================
def inicializar_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('PRAGMA journal_mode=WAL;')

        c.execute('''CREATE TABLE IF NOT EXISTS revendedores (user_id INTEGER PRIMARY KEY, username TEXT, fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP, rango TEXT DEFAULT 'revendedor', is_banned INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS metodos_pais (pais TEXT PRIMARY KEY, bandera TEXT, moneda TEXT, tasa REAL DEFAULT 1.0, detalles TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS comprobantes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, pais TEXT, monto REAL, foto TEXT, estado INTEGER DEFAULT 0, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT)''')

        defaults = [
            ('link_soporte', 'https://t.me/OwnerDripClient'),
            ('link_bot_oficial', 'https://t.me/StreamingSx_Bot'),
            ('imagen_inicio', '')
        ]
        c.executemany("INSERT OR IGNORE INTO config (clave, valor) VALUES (?, ?)", defaults)

        try: c.execute("ALTER TABLE revendedores ADD COLUMN rango TEXT DEFAULT 'revendedor'")
        except: pass
        try: c.execute("ALTER TABLE revendedores ADD COLUMN is_banned INTEGER DEFAULT 0")
        except: pass

        conn.commit()

def db_query(query, params=(), fetch=False, fetchall=False, commit=True):
    try:
        with sqlite3.connect(DB_NAME, timeout=20.0) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(query, params)
            if fetch:
                res = c.fetchone()
                return dict(res) if res else None
            if fetchall:
                res = c.fetchall()
                return [dict(row) for row in res] if res else []
            if commit:
                conn.commit()
            return None
    except sqlite3.Error as e:
        logger.error(f"Error BD ejecutando {query}: {e}")
        return [] if fetchall else None

def get_config(clave):
    res = db_query("SELECT valor FROM config WHERE clave = ?", (clave,), fetch=True)
    return res['valor'] if res else ""

def es_admin(user_id):
    if user_id == ADMIN_ID: return True
    u = db_query("SELECT rango FROM revendedores WHERE user_id = ?", (user_id,), fetch=True)
    return u and u['rango'] == 'admin'

def esta_baneado(user_id):
    u = db_query("SELECT is_banned FROM revendedores WHERE user_id = ?", (user_id,), fetch=True)
    return u and u['is_banned'] == 1

def marcar_ocupado(context, estado=True):
    context.user_data['ocupado'] = estado

def esta_ocupado(context):
    return context.user_data.get('ocupado', False)

def limpiar_html(texto):
    """Quita el HTML para que el bot nunca se quede mudo si hay un error de formato."""
    return re.sub(r'<[^>]+>', '', texto)

def truncar(texto, limite=35):
    """Evita que Telegram colapse si pones enlaces gigantes en los botones."""
    return texto[:limite-3] + '...' if len(texto) > limite else texto

# ==========================================
# ✨ FUNCIONES VISUALES (BLINDADAS AL 100%)
# ==========================================
async def render_msg(query, context, texto, teclado, photo=None):
    message = query.message
    has_photo_new = bool(photo and str(photo).strip() not in ['0', ''])
    has_photo_old = bool(message.photo or message.document)

    try:
        if has_photo_new and has_photo_old:
            await query.edit_message_media(media=InputMediaPhoto(media=photo, caption=texto, parse_mode='HTML'), reply_markup=teclado)
        elif not has_photo_new and not has_photo_old:
            await query.edit_message_text(text=texto, reply_markup=teclado, parse_mode='HTML')
        else:
            try: await message.delete()
            except: pass
            if has_photo_new:
                return await context.bot.send_photo(chat_id=message.chat_id, photo=photo, caption=texto, reply_markup=teclado, parse_mode='HTML')
            else:
                return await context.bot.send_message(chat_id=message.chat_id, text=texto, reply_markup=teclado, parse_mode='HTML')
        return message
    except Exception as e:
        logger.error(f"Error render_msg: {e}")
        try: await context.bot.send_message(chat_id=message.chat_id, text=limpiar_html(texto), reply_markup=teclado)
        except: pass
        return message

async def update_form(update, context, texto, teclado):
    try: await update.message.delete()
    except: pass

    prompt_id = context.user_data.get('prompt_msg_id')
    edit_success = False

    if prompt_id:
        try:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=prompt_id, text=texto, reply_markup=teclado, parse_mode='HTML')
            edit_success = True
        except Exception:
            try:
                await context.bot.edit_message_caption(chat_id=update.effective_chat.id, message_id=prompt_id, caption=texto, reply_markup=teclado, parse_mode='HTML')
                edit_success = True
            except Exception: pass

    if not edit_success:
        try:
            msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=texto, reply_markup=teclado, parse_mode='HTML')
            context.user_data['prompt_msg_id'] = msg.message_id
        except Exception:
            try:
                msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=limpiar_html(texto), reply_markup=teclado)
                context.user_data['prompt_msg_id'] = msg.message_id
            except: pass

async def cancelar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        try: await query.answer("🌸 ¡Operación cancelada, mi amor!")
        except: pass
    marcar_ocupado(context, False)
    await start_menu(update, context)
    return ConversationHandler.END

async def cancel_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_menu(update, context)
    return ConversationHandler.END

async def fallback_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    marcar_ocupado(context, False)
    await navegacion_menu(update, context)
    return ConversationHandler.END

# ==========================================
# 🎀 MENÚ PRINCIPAL REVENDEDOR
# ==========================================
async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    if esta_baneado(user.id): return

    marcar_ocupado(context, False)
    context.user_data.clear()

    safe_username = str(user.username or user.first_name or "Desconocido")
    rev = db_query("SELECT * FROM revendedores WHERE user_id = ?", (user.id,), fetch=True)

    if not rev:
        db_query("INSERT INTO revendedores (user_id, username) VALUES (?, ?)", (user.id, safe_username))
        rev = {'user_id': user.id, 'username': safe_username, 'fecha_registro': datetime.datetime.now().strftime("%Y-%m-%d")}

    stats = db_query("SELECT estado, COUNT(*) as c, SUM(monto) as total FROM comprobantes WHERE user_id = ? GROUP BY estado", (user.id,), fetchall=True) or []
    aprobados_usd = 0.0
    pendientes_cant = 0
    rechazados_cant = 0

    for s in stats:
        if s['estado'] == 1: aprobados_usd = s['total'] or 0.0
        elif s['estado'] == 0: pendientes_cant = s['c']
        elif s['estado'] == 2: rechazados_cant = s['c']

    nombre_seguro = f"@{html.escape(str(rev['username']))}" if rev.get('username') else "Corazón"
    pendientes_txt = f"\n⏳ <i>¡Tienes {pendientes_cant} comprobante(s) en revisión!</i>" if pendientes_cant > 0 else ""

    texto = (
        f"🎀 <b>¡Hola, {nombre_seguro}! Bienvenido</b> ✨\n"
        f"Me alegra muchísimo verte por aquí. Estoy lista para ayudarte. 👇\n\n"
        f"📊 <b>TUS ESTADÍSTICAS</b> 🌸\n"
        f"═══════════════════\n"
        f"🆔 <b>Tu ID:</b> <code>{user.id}</code>\n"
        f"✅ <b>Saldo Aprobado:</b> ${aprobados_usd:.2f} USD\n"
        f"❌ <b>Comprobantes Rechazados:</b> {rechazados_cant}{pendientes_txt}\n"
        f"═══════════════════\n\n"
        f"¿En qué te puedo apoyar el día de hoy, lindo? Escoge una opción:"
    )

    teclado = [
        [InlineKeyboardButton("⚖️ VALIDAR PAGO", callback_data="nav_env_inicio"), InlineKeyboardButton("🤝 CREAR PAGO", callback_data="nav_crear_inicio")],
        [InlineKeyboardButton("📜 MI HISTORIAL", callback_data="nav_hist_0"), InlineKeyboardButton("📖 GUÍA PREMIUM", callback_data="nav_guia")],
        [InlineKeyboardButton("🤖 BOT OFICIAL", url=get_config('link_bot_oficial')), InlineKeyboardButton("👻 SOPORTE", url=get_config('link_soporte'))]
    ]

    if es_admin(user.id):
        teclado.append([InlineKeyboardButton("😈 PANEL ADMINISTRADOR 😈", callback_data="nav_adm_panel")])

    markup = InlineKeyboardMarkup(teclado)
    img_inicio = get_config('imagen_inicio')

    if update.callback_query:
        try: await update.callback_query.answer()
        except: pass
        await render_msg(update.callback_query, context, texto, markup, img_inicio)
    else:
        try:
            if img_inicio and img_inicio != '0':
                await context.bot.send_photo(chat_id=chat_id, photo=img_inicio, caption=texto, reply_markup=markup, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=chat_id, text=texto, reply_markup=markup, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Fallo HTML al inicio: {e}")
            try: await context.bot.send_message(chat_id=chat_id, text=limpiar_html(texto), reply_markup=markup)
            except: pass

# ==========================================
# 🌸 RUTAS DE NAVEGACIÓN (MENÚS FLUIDOS)
# ==========================================
async def navegacion_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if esta_baneado(user_id): return
    if esta_ocupado(context):
        try: await query.answer("🥺 Ay, corazón. Aún tienes un menú abierto, dale a 'Cancelar Operación' primero.", show_alert=True)
        except: pass
        return

    try: await query.answer()
    except: pass
    data = query.data

    if data == "nav_env_inicio":
        paises = db_query("SELECT rowid, * FROM metodos_pais", fetchall=True) or []
        teclado = [[InlineKeyboardButton(truncar(f"{p['bandera']} {p['pais']}"), callback_data=f"conv_env_p_{p['rowid']}")] for p in paises]
        teclado.append([InlineKeyboardButton("❌ Cancelar, me equivoqué", callback_data="cancelar_cb")])
        await render_msg(query, context, "✨ ¡Perfecto, querido! ¿De qué <b>PAÍS</b> es el comprobante que me vas a enviar?", InlineKeyboardMarkup(teclado))

    elif data == "nav_crear_inicio":
        paises = db_query("SELECT rowid, * FROM metodos_pais", fetchall=True) or []
        teclado = [[InlineKeyboardButton(truncar(f"{p['bandera']} {p['pais']}"), callback_data=f"conv_crear_p_{p['rowid']}")] for p in paises]
        teclado.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_cb")])
        await render_msg(query, context, "💌 ¡Vamos a generarle un cobro a tu cliente! ¿De qué <b>PAÍS</b> es tu comprador?", InlineKeyboardMarkup(teclado))

    elif data.startswith("nav_hist_"):
        pagina = int(data.split("_")[2])
        limite = 5
        offset = pagina * limite

        comps = db_query("SELECT * FROM comprobantes WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?", (user_id, limite, offset), fetchall=True) or []
        total_res = db_query("SELECT COUNT(*) as c FROM comprobantes WHERE user_id = ?", (user_id,), fetch=True)
        total = total_res['c'] if total_res else 0

        texto = f"📜 <b>TU HISTORIAL DE PAGOS (Pág {pagina + 1})</b> 🌸\n══════════════════════\n"
        for c in comps:
            estado_lbl = "⏳ En Revisión" if c['estado'] == 0 else ("✅ Aprobado" if c['estado'] == 1 else "❌ Rechazado")
            fecha_str = str(c['fecha']).split('.')[0] if c['fecha'] else "Desconocida"
            pais_seguro = html.escape(str(c['pais']))
            texto += f"• <b>${c['monto']:.2f} USD</b> | {pais_seguro}\n  {estado_lbl} | 📅 {fecha_str}\n\n"

        if not comps: texto += "<i>Aún no tienes comprobantes registrados, mi amor.</i>\n"

        botones = []
        if pagina > 0: botones.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"nav_hist_{pagina - 1}"))
        if (pagina + 1) * limite < total: botones.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"nav_hist_{pagina + 1}"))

        teclado = [botones] if botones else []
        teclado.append([InlineKeyboardButton("🏠 Volver al Inicio", callback_data="cancelar_cb")])
        await render_msg(query, context, texto, InlineKeyboardMarkup(teclado))

    elif data == "nav_guia":
        texto = (
            f"📖 <b>AUDITORÍA Y GUÍA DE USO</b> 🌸\n"
            f"══════════════════════\n"
            f"¡Hola de nuevo! Aquí te explico cómo ser el mejor revendedor, paso a pasito:\n\n"
            f"1️⃣ <b>CREAR PAGO:</b> Te generaré un texto súper bonito con tus datos bancarios y el monto exacto para que se lo mandes por WhatsApp a tu cliente.\n\n"
            f"2️⃣ <b>ENVIAR COMPROBANTE:</b> Cuando tu cliente te pague, me pasas el monto en USD y la fotito. ¡Yo se lo mandaré corriendo al administrador/soporte!\n\n"
            f"3️⃣ <b>ESPERAR SALDO:</b> Verás en tu menú si tienes comprobantes ⏳ 'En Revisión'. Te avisaré cuando los validen. ✨"
        )
        await render_msg(query, context, texto, InlineKeyboardMarkup([[InlineKeyboardButton("🌸 ¡Entendido! Volver al Inicio", callback_data="cancelar_cb")]]))

    elif data == "nav_adm_panel":
        if not es_admin(user_id): return
        teclado = [
            [InlineKeyboardButton("📈 Estadísticas Financieras", callback_data="adm_stats"), InlineKeyboardButton("🔎 Inspeccionar Usuario", callback_data="conv_adm_buscar")],
            [InlineKeyboardButton("🌎 Divisas y Cuentas Bancarias", callback_data="nav_adm_paises")],
            [InlineKeyboardButton("🔗 Editar Soporte", callback_data="conv_adm_soporte"), InlineKeyboardButton("🤖 Editar Bot Oficial", callback_data="conv_adm_bot")],
            [InlineKeyboardButton("🖼️ Imagen de Portada", callback_data="conv_adm_img")],
            [InlineKeyboardButton("👥 Ver Usuarios Registrados", callback_data="nav_adm_users_0")],
            [InlineKeyboardButton("🏠 Salir del Panel", callback_data="cancelar_cb")]
        ]
        await render_msg(query, context, "👑 <b>PANEL DE REINA (ADMIN / SOPORTE)</b> ✨\nAquí mandas tú. Lleva la contabilidad, gestiona usuarios y configura todo.", InlineKeyboardMarkup(teclado))

    elif data.startswith("nav_adm_users_"):
        if not es_admin(user_id): return
        pagina = int(data.split("_")[3])
        limite = 8
        offset = pagina * limite

        users = db_query("SELECT * FROM revendedores ORDER BY user_id DESC LIMIT ? OFFSET ?", (limite, offset), fetchall=True) or []
        total_res = db_query("SELECT COUNT(*) as c FROM revendedores", fetch=True)
        total = total_res['c'] if total_res else 0

        texto = f"👥 <b>USUARIOS REGISTRADOS (Pág {pagina + 1})</b> 🌸\n══════════════════════\n"
        for u in users:
            rango = "👑" if u['rango'] == 'admin' else "🎀"
            ban = "🚫" if u['is_banned'] else "✅"
            safe_name = html.escape(str(u['username']))
            texto += f"{rango} <code>{u['user_id']}</code> | @{safe_name} | {ban}\n"

        if not users: texto += "<i>No hay usuarios registrados.</i>\n"

        botones = []
        if pagina > 0: botones.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"nav_adm_users_{pagina - 1}"))
        if (pagina + 1) * limite < total: botones.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"nav_adm_users_{pagina + 1}"))

        teclado = [botones] if botones else []
        teclado.append([InlineKeyboardButton("⬅️ Volver al Panel", callback_data="nav_adm_panel")])
        await render_msg(query, context, texto, InlineKeyboardMarkup(teclado))

    elif data == "adm_stats":
        if not es_admin(user_id): return
        stats_hoy = db_query("SELECT SUM(monto) as t FROM comprobantes WHERE estado = 1 AND date(fecha) = date('now')", fetch=True)
        stats_total = db_query("SELECT SUM(monto) as t FROM comprobantes WHERE estado = 1", fetch=True)

        h = stats_hoy['t'] if stats_hoy and stats_hoy['t'] else 0.0
        t = stats_total['t'] if stats_total and stats_total['t'] else 0.0

        texto = (
            f"📈 <b>ESTADÍSTICAS FINANCIERAS</b> 💸\n"
            f"══════════════════════\n"
            f"Aquí tienes tu contabilidad de saldo aprobado:\n\n"
            f"🌸 <b>Validado Hoy:</b> ${h:.2f} USD\n"
            f"👑 <b>Total:</b> ${t:.2f} USD\n\n"
            f"<i>¡Sigue así, estás rompiendo récords!</i> ✨"
        )
        await render_msg(query, context, texto, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver al Panel", callback_data="nav_adm_panel")]]))

    elif data == "nav_adm_paises":
        if not es_admin(user_id): return
        paises = db_query("SELECT rowid, * FROM metodos_pais", fetchall=True) or []
        teclado = [[InlineKeyboardButton(truncar(f"{p['bandera']} {p['pais']} (1 USD = {p['tasa']})"), callback_data=f"nav_adm_epais_{p['rowid']}")] for p in paises]
        teclado.append([InlineKeyboardButton("➕ Habilitar Nueva Región/Moneda", callback_data="conv_adm_add_pais")])
        teclado.append([InlineKeyboardButton("⬅️ Volver al Panel", callback_data="nav_adm_panel")])
        await render_msg(query, context, "🌎 <b>MÉTODOS DE PAGO Y TASAS</b>\nToca un país para editar su cuenta o tasa.", InlineKeyboardMarkup(teclado))

    elif data.startswith("nav_adm_epais_"):
        if not es_admin(user_id): return
        rowid = data.split("_", 3)[3]
        p_info = db_query("SELECT pais FROM metodos_pais WHERE rowid = ?", (rowid,), fetch=True)
        if not p_info:
            await render_msg(query, context, "❌ Uy, este país ya no existe.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver a Países", callback_data="nav_adm_paises")]]))
            return

        pais_seguro = html.escape(str(p_info['pais']))
        teclado = [
            [InlineKeyboardButton("✏️ Ajustar Tasa Cambiaria", callback_data=f"conv_adm_etasa_{rowid}")],
            [InlineKeyboardButton("✏️ Modificar Datos Bancarios", callback_data=f"conv_adm_edet_{rowid}")],
            [InlineKeyboardButton("🗑️ Inhabilitar Región", callback_data=f"nav_adm_delpais_{rowid}")],
            [InlineKeyboardButton("⬅️ Atrás", callback_data="nav_adm_paises")]
        ]
        await render_msg(query, context, f"⚙️ <b>EDITANDO PASARELA: {pais_seguro}</b>", InlineKeyboardMarkup(teclado))

    elif data.startswith("nav_adm_delpais_"):
        if not es_admin(user_id): return
        rowid = data.split("_", 3)[3]
        db_query("DELETE FROM metodos_pais WHERE rowid = ?", (rowid,))
        await render_msg(query, context, f"✅ ¡Listo! La región fue eliminada con éxito.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver a Países", callback_data="nav_adm_paises")]]))

    elif data.startswith("adm_togban_"):
        if user_id != ADMIN_ID: return
        uid = int(data.split("_")[2])
        u = db_query("SELECT is_banned FROM revendedores WHERE user_id = ?", (uid,), fetch=True)
        nuevo_est = 0 if u and u['is_banned'] == 1 else 1
        db_query("UPDATE revendedores SET is_banned = ? WHERE user_id = ?", (nuevo_est, uid))
        lbl = "Desbaneado 🌸" if nuevo_est == 0 else "Baneado 🚫"
        await render_msg(query, context, f"✅ El usuario <code>{uid}</code> ahora está: <b>{lbl}</b>.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")]]))

    elif data.startswith("adm_togradm_"):
        if user_id != ADMIN_ID: return
        uid = int(data.split("_")[2])
        u = db_query("SELECT rango FROM revendedores WHERE user_id = ?", (uid,), fetch=True)
        nuevo_rng = 'admin' if u and u['rango'] == 'revendedor' else 'revendedor'
        db_query("UPDATE revendedores SET rango = ? WHERE user_id = ?", (nuevo_rng, uid))
        lbl = "Soporte / Sub-Admin 👑" if nuevo_rng == 'admin' else "Revendedor 🎀"
        await render_msg(query, context, f"✅ Privilegios de <code>{uid}</code> actualizados a: <b>{lbl}</b>.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")]]))

# ==========================================
# 🎀 INICIO DE FORMULARIOS DE TEXTO
# ==========================================
async def conv_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data.startswith("conv_adm_") and not es_admin(query.from_user.id):
        try: await query.answer("🚫 Área restringida, corazón.", show_alert=True)
        except: pass
        return ConversationHandler.END

    if esta_ocupado(context):
        try: await query.answer("🥺 Tienes algo a medias, dale a 'Cancelar' primero.", show_alert=True)
        except: pass
        return

    try: await query.answer()
    except: pass
    marcar_ocupado(context, True)
    data = query.data
    cancel = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar Operación", callback_data="cancelar_cb")]])
    msg = None
    ret = ConversationHandler.END

    if data == "conv_adm_buscar":
        msg = await render_msg(query, context, "🔎 <b>INSPECTOR DE USUARIOS</b>\nDime el ID o Username del revendedor que quieres revisar detalladamente:", cancel)
        ret = ADM_BUSCAR_USER
    elif data == "conv_adm_add_pais":
        msg = await render_msg(query, context, "🌎 <b>NUEVA REGIÓN</b>\nFormato exacto: <code>País,Bandera,Moneda</code>\n(Ejemplo: <code>Colombia,🇨🇴,COP</code>)", cancel)
        ret = ADM_ADD_PAIS_NOM
    elif data.startswith("conv_adm_etasa_"):
        context.user_data['tmp_pais_id'] = data.split("_", 3)[3]
        msg = await render_msg(query, context, "💱 Ingresa la <b>NUEVA TASA DE CONVERSIÓN</b> frente al Dólar (Ej: Escribe <code>3850</code> si 1 USD = 3850 COP):", cancel)
        ret = ADM_EDIT_TASA
    elif data.startswith("conv_adm_edet_"):
        context.user_data['tmp_pais_id'] = data.split("_", 3)[3]
        msg = await render_msg(query, context, "✏️ Redacta los <b>DATOS DE LA CUENTA</b> y detalles de depósito para esta región:", cancel)
        ret = ADM_EDIT_DET
    elif data == "conv_adm_soporte":
        msg = await render_msg(query, context, "🔗 <b>ENLACE DE SOPORTE</b>\nPega aquí el nuevo link para que tus clientes te contacten (Ej: <code>https://t.me/Usuario</code>):", cancel)
        ret = ADM_EDIT_SOPORTE
    elif data == "conv_adm_bot":
        msg = await render_msg(query, context, "🤖 <b>ENLACE DEL BOT OFICIAL</b>\nPega aquí el link hacia tu tienda principal (Ej: <code>https://t.me/TuBot</code>):", cancel)
        ret = ADM_EDIT_BOT
    elif data == "conv_adm_img":
        msg = await render_msg(query, context, "🖼️ <b>IMAGEN DE PORTADA</b>\nEnvíame la <b>FOTOGRAFÍA</b> que quieres que adorne el menú de bienvenida (Manda <code>0</code> para quitarla):", cancel)
        ret = ADM_EDIT_IMG
    elif data.startswith("conv_env_p_"):
        context.user_data['tmp_pais_id'] = data.split("_", 3)[3]
        msg = await render_msg(query, context, "💰 ¡Excelente, querido! Dime, ¿qué <b>MONTO EXACTO EN USD</b> (Dólares) depositó tu cliente? (Ej: <code>15.50</code>):", cancel)
        ret = ENV_COMP_MONTO
    elif data.startswith("conv_crear_p_"):
        context.user_data['tmp_pais_id'] = data.split("_", 3)[3]
        msg = await render_msg(query, context, "💰 ¡Vamos a vender! Dime, ¿cuánto le vas a cobrar a tu cliente en <b>USD</b> (Dólares)? Yo le calcularé su moneda local solita. ✨", cancel)
        ret = CREAR_COMP_MONTO

    if msg: context.user_data['prompt_msg_id'] = msg.message_id
    return ret

# ==========================================
# 🛠️ GUARDADO DE DATOS (ADMIN)
# ==========================================
async def adm_buscar_user_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.message.text.strip().replace('@', '')
        u = db_query("SELECT * FROM revendedores WHERE user_id = ? OR username = ?", (uid, uid), fetch=True)
        try: await update.message.delete()
        except: pass

        if not u:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Uy, no encontré a nadie con ese dato, jefa/jefe.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")]]))
            return ConversationHandler.END

        stats = db_query("SELECT SUM(monto) as total, COUNT(*) as c FROM comprobantes WHERE user_id = ? AND estado = 1", (u['user_id'],), fetch=True)
        t_monto = stats['total'] if (stats and stats['total']) else 0.0
        t_comps = stats['c'] if (stats and stats['c']) else 0

        estado = "🚫 SUSPENDIDO" if u['is_banned'] == 1 else "🌸 Activo"
        rango = "👑 Soporte/Admin" if u['rango'] == 'admin' else "🎀 Revendedor"

        safe_name = html.escape(str(u['username'] or "Desconocido"))
        fecha_registro = str(u['fecha_registro']).split()[0] if u['fecha_registro'] else "Desconocida"

        txt = (
            f"🔎 <b>REPORTE DE USUARIO</b>\n"
            f"══════════════════════\n"
            f"🆔 <b>ID:</b> <code>{u['user_id']}</code>\n"
            f"👤 <b>Username:</b> @{safe_name}\n"
            f"🌟 <b>Nivel:</b> {rango}\n"
            f"📅 <b>Registro:</b> {fecha_registro}\n"
            f"✅ <b>Comprobantes Validados:</b> {t_comps}\n"
            f"💵 <b>Total Aprobado:</b> ${t_monto:.2f} USD\n"
            f"⚠️ <b>Estado:</b> {estado}\n"
            f"══════════════════════"
        )

        btns = []
        if update.effective_user.id == ADMIN_ID:
            btn_ban = "🔓 Desbanear" if u['is_banned'] == 1 else "🔨 Suspender (Ban)"
            btn_adm = "🎀 Quitar Soporte" if u['rango'] == 'admin' else "👑 Hacer Soporte (Sub-Admin)"
            btns.append([InlineKeyboardButton(btn_adm, callback_data=f"adm_togradm_{u['user_id']}")])
            btns.append([InlineKeyboardButton(btn_ban, callback_data=f"adm_togban_{u['user_id']}")])

        btns.append([InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")])

        await context.bot.send_message(chat_id=update.effective_chat.id, text=txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error buscar_user: {e}")
    finally:
        marcar_ocupado(context, False)
        return ConversationHandler.END

async def adm_config_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        est = context.user_data.get('conv_estado_real')
        val = str(update.message.text.strip()) if update.message.text else ""
        if update.message.photo: val = update.message.photo[-1].file_id
        if val == '0': val = ""

        if est == ADM_EDIT_SOPORTE: db_query("UPDATE config SET valor = ? WHERE clave = 'link_soporte'", (val,))
        elif est == ADM_EDIT_BOT: db_query("UPDATE config SET valor = ? WHERE clave = 'link_bot_oficial'", (val,))
        elif est == ADM_EDIT_IMG: db_query("UPDATE config SET valor = ? WHERE clave = 'imagen_inicio'", (val,))

        await update_form(update, context, "✅ ¡Todo guardadito y perfecto en la base de datos, jefe! ✨", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")]]))
    except Exception:
        await update_form(update, context, "🥺 Hubo un errorcito al guardar. Intenta de nuevo.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver", callback_data="cancelar_cb")]]))
    finally:
        marcar_ocupado(context, False)
        return ConversationHandler.END

async def wrapper_cfg(update: Update, context: ContextTypes.DEFAULT_TYPE, estado):
    context.user_data['conv_estado_real'] = estado
    return await adm_config_save(update, context)

async def adm_add_pais_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = update.message.text.split(",")
        context.user_data['tmp_p'] = str(p[0].strip())
        context.user_data['tmp_b'] = str(p[1].strip())
        context.user_data['tmp_m'] = str(p[2].strip())
        await update_form(update, context, f"💵 Escribe la <b>TASA DE CAMBIO</b> y los <b>DATOS DE LA CUENTA</b> separados por una coma <code>,</code>\n(Ej: <code>3850,Nequi: 3001234567 Titular: Juan</code>)", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_cb")]]))
        return ADM_ADD_PAIS_DATOS
    except Exception:
        await update_form(update, context, "❌ Formato incorrecto. Usa comas para separar la información.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver", callback_data="cancelar_cb")]]))
        marcar_ocupado(context, False)
        return ConversationHandler.END

async def adm_add_pais_datos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = update.message.text.split(",", 1)
        db_query("INSERT INTO metodos_pais VALUES (?, ?, ?, ?, ?)", (context.user_data['tmp_p'], context.user_data['tmp_b'], context.user_data['tmp_m'], float(p[0]), str(p[1].strip())))
        await update_form(update, context, "✅ Región configurada con éxito.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")]]))
    except Exception:
        await update_form(update, context, "❌ Error al procesar los datos.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver", callback_data="cancelar_cb")]]))
    marcar_ocupado(context, False)
    return ConversationHandler.END

async def adm_edit_tasa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tasa = float(update.message.text.strip())
        db_query("UPDATE metodos_pais SET tasa = ? WHERE rowid = ?", (tasa, context.user_data['tmp_pais_id']))
        await update_form(update, context, "✅ Tasa actualizada exitosamente.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")]]))
        marcar_ocupado(context, False)
        return ConversationHandler.END
    except ValueError:
        await update_form(update, context, "❌ Error. Ingresa solo números enteros o decimales.", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_cb")]]))
        return ADM_EDIT_TASA

async def adm_edit_det(update: Update, context: ContextTypes.DEFAULT_TYPE):
    detalles = str(update.message.text.strip())
    db_query("UPDATE metodos_pais SET detalles = ? WHERE rowid = ?", (detalles, context.user_data['tmp_pais_id']))
    await update_form(update, context, "✅ Datos de la cuenta bancaria actualizados.", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Panel", callback_data="nav_adm_panel")]]))
    marcar_ocupado(context, False)
    return ConversationHandler.END

# ==========================================
# 🌸 RUTINAS DEL REVENDEDOR (INPUTS)
# ==========================================
async def rev_env_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['tmp_monto'] = float(update.message.text.strip())
        await update_form(update, context, "📸 <b>¡Anotado!</b> Ahora porfis mándame la <b>FOTO o CAPTURA</b> de pantalla del comprobante de pago por aquí: 💖", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar Operación", callback_data="cancelar_cb")]]))
        return ENV_COMP_FOTO
    except ValueError:
        await update_form(update, context, "🥺 ¡Uy, mi amor! Ese monto no es válido. Ingresa solo numeritos con puntos (ej: <code>15.50</code>):", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_cb")]]))
        return ENV_COMP_MONTO

async def rev_env_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update_form(update, context, "🥺 Cariño, debes enviarme forzosamente una <b>FOTOGRAFÍA o CAPTURA</b>. Intenta de nuevo porfis:", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar Operación", callback_data="cancelar_cb")]]))
        return ENV_COMP_FOTO

    foto = update.message.photo[-1].file_id
    user_id = update.effective_user.id
    monto = context.user_data.get('tmp_monto')
    rowid = context.user_data.get('tmp_pais_id')

    p_info = db_query("SELECT pais FROM metodos_pais WHERE rowid = ?", (rowid,), fetch=True)
    pais = p_info['pais'] if p_info else "Desconocido"

    username = html.escape(str(update.effective_user.username or "Sin_Usuario"))

    db_query("INSERT INTO comprobantes (user_id, pais, monto, foto, estado) VALUES (?, ?, ?, ?, 0)", (user_id, pais, monto, foto))
    pend = db_query("SELECT id FROM comprobantes ORDER BY id DESC LIMIT 1", fetch=True)
    pend_id = pend['id']

    await update_form(update, context, "💌 <b>¡Recibido, lindo!</b>\nYa le pasé tu comprobante a revisión con soporte.\nEn tu menú principal verás que está ⏳ <i>'En Revisión'</i> hasta que te lo validemos. ¡Cruza los deditos! ✨", InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Volver al Inicio", callback_data="cancelar_cb")]]))
    marcar_ocupado(context, False)

    # 👑 NOTIFICAR AL ADMIN Y A LOS SUB-ADMINS
    pais_seguro = html.escape(str(pais))
    texto_admin = (
        f"🔔 NUEVO COMPROBANTE RECIBIDO\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Revendedor: @{username}\n"
        f"🆔 <b>ID: <code>{user_id}</code></b>\n"
        f"🌎 País: {pais_seguro}\n"
        f"💰 Monto: ${monto} USD\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    teclado_admin = [
        [InlineKeyboardButton("✅ VALIDAR PAGO", callback_data=f"val_ok_{pend_id}_{user_id}_{monto}")],
        [InlineKeyboardButton("❌ NO VALIDADO", callback_data=f"val_no_{pend_id}_{user_id}")]
    ]

    admins = db_query("SELECT user_id FROM revendedores WHERE rango = 'admin'", fetchall=True) or []
    admin_ids = set([a['user_id'] for a in admins] + [ADMIN_ID])

    for a_id in admin_ids:
        try: await context.bot.send_photo(chat_id=a_id, photo=foto, caption=texto_admin, reply_markup=InlineKeyboardMarkup(teclado_admin), parse_mode='HTML')
        except: pass

    return ConversationHandler.END

async def rev_crear_monto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto_usd = float(update.message.text.strip())
        rowid = context.user_data.get('tmp_pais_id')
        p_info = db_query("SELECT * FROM metodos_pais WHERE rowid = ?", (rowid,), fetch=True)

        if p_info:
            monto_local = monto_usd * p_info['tasa']
            texto_whatsapp = (
                f"🌸 *DATOS DE PAGO* 🌸\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🌎 *País:* {p_info['bandera']} {p_info['pais']}\n"
                f"💰 *Monto a pagar:* ${monto_local:,.2f} {p_info['moneda']}\n"
                f"💱 *Tasa:* 1 USD = {p_info['tasa']} {p_info['moneda']}\n\n"
                f"📌 *INSTRUCCIONES:*\n"
                f"✅ Paga EXACTAMENTE la cantidad indicada.\n"
                f"✅ Verifica los datos antes de transferir.\n"
                f"✅ Guarda y envíame tu comprobante.\n\n"
                f"🎀 *CUENTA A DEPOSITAR:* 🎀\n"
                f"{p_info['detalles']}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ _¡Gracias por tu preferencia!_ ✨"
            )
            safe_wa = html.escape(texto_whatsapp)
            mensaje_final = f"¡Listo, amigo querido! ✨ Cópiale el texto de aquí abajito a tu cliente (está formateado perfecto para que se vea negrita y lindo en WhatsApp). Toca el cuadro para copiarlo: \n\n<code>{safe_wa}</code>"
            await update_form(update, context, mensaje_final, InlineKeyboardMarkup([[InlineKeyboardButton("🌸 ¡Entendido! Volver al Inicio", callback_data="cancelar_cb")]]))
        marcar_ocupado(context, False)
        return ConversationHandler.END
    except ValueError:
        await update_form(update, context, "🥺 Ay amor, ese monto no es válido. Ingresa solo el número en Dólares (USD).", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_cb")]]))
        return CREAR_COMP_MONTO

# ==========================================
# 👑 DECISIÓN DEL ADMIN/SOPORTE
# ==========================================
async def procesar_validacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass

    data = query.data.split("_")
    accion = data[1]
    pend_id = data[2]
    user_id = data[3]

    # Evita que 2 admins aprueben la misma foto
    comp = db_query("SELECT estado FROM comprobantes WHERE id = ?", (pend_id,), fetch=True)
    if not comp or comp['estado'] != 0:
        try: await query.edit_message_caption(caption="⚠️ Este comprobante ya fue procesado por otro miembro del soporte.", parse_mode='HTML')
        except: pass
        return

    if accion == "ok":
        monto = float(data[4])
        db_query("UPDATE comprobantes SET estado = 1 WHERE id = ?", (pend_id,))
        db_query("UPDATE revendedores SET validados = validados + 1, total_confirmado = total_confirmado + ? WHERE user_id = ?", (monto, user_id))

        texto_rev = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>¡PAGO VALIDADO, CORAZÓN!</b> ✨\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Tu comprobante por ${monto} USD fue revisado y está bellísimo.\n"
            f"💳 Ya estamos sumando ese saldo a tu cuenta en\n"
            f"nuestro Bot Oficial.\n\n"
            f"⏱️ En unos momentitos ya podrás usarlo.\n"
            f"¡Mucho éxito con tus ventas, te quiero! 🌸\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        try: await query.edit_message_caption(caption=f"✅ VALIDADO: Comprobante de <code>{user_id}</code> por ${monto} aceptado por ti.", parse_mode='HTML')
        except: pass

    elif accion == "no":
        db_query("UPDATE comprobantes SET estado = 2 WHERE id = ?", (pend_id,))
        texto_rev = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ <b>PAGO NO VALIDADO</b> 🥺\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Ay, lindo, tuvimos que rechazar este comprobante. 💔\n"
            f"Revisa que el monto depositado sea el exacto\n"
            f"o que la foto se vea súper clarita, y envíalo otra vez.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        try: await query.edit_message_caption(caption=f"❌ RECHAZADO: Comprobante de <code>{user_id}</code> denegado por ti.", parse_mode='HTML')
        except: pass

    try: await context.bot.send_message(chat_id=user_id, text=texto_rev, parse_mode='HTML')
    except Exception: pass

# ==========================================
# 🚀 MAIN (INICIO DEL BOT)
# ==========================================
def main():
    inicializar_db()
    app = Application.builder().token(TOKEN).build()

    def admin_cfg_handler(estado_id):
        return MessageHandler(filters.TEXT | filters.PHOTO, lambda u,c: wrapper_cfg(u,c,estado_id))

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(conv_start, pattern="^conv_")
        ],
        states={
            ADM_BUSCAR_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_buscar_user_save)],
            ADM_ADD_PAIS_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_pais_nom)],
            ADM_ADD_PAIS_DATOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_pais_datos)],
            ADM_EDIT_TASA: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_edit_tasa)],
            ADM_EDIT_DET: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_edit_det)],
            ADM_EDIT_SOPORTE: [admin_cfg_handler(ADM_EDIT_SOPORTE)],
            ADM_EDIT_BOT: [admin_cfg_handler(ADM_EDIT_BOT)],
            ADM_EDIT_IMG: [admin_cfg_handler(ADM_EDIT_IMG)],
            ENV_COMP_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, rev_env_monto)],
            ENV_COMP_FOTO: [MessageHandler(filters.PHOTO | filters.TEXT, rev_env_foto)],
            CREAR_COMP_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, rev_crear_monto)],
        },
        fallbacks=[
            CallbackQueryHandler(fallback_nav, pattern="^(nav_|adm_)"),
            CallbackQueryHandler(cancelar_cb, pattern="^(cancelar_cb|start_menu)$"),
            CommandHandler("start", cancel_and_start)
        ], allow_reentry=True)

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start_menu))
    app.add_handler(CallbackQueryHandler(navegacion_menu, pattern="^(nav_|adm_)"))
    app.add_handler(CallbackQueryHandler(procesar_validacion, pattern="^val_"))
    app.add_handler(CallbackQueryHandler(cancelar_cb, pattern="^cancelar_cb$"))

    logger.info("🌸 ¡SISTEMA DE REVENDEDORES INICIADO, PRECIOSO Y A PRUEBA DE FALLOS! ✨")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()