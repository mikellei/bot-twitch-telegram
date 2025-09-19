# =================================================================================
# BOT GESTIONE ABBONAMENTI TWITCH per PRINSIPE - VERSIONE FINALE
# Funzionalità:
# - Verifica abbonamento tramite comando /verifica
# - Genera e invia un link d'invito monouso al gruppo privato
# - Controlla giornalmente gli abbonamenti
# - Rimuove gli utenti il cui abbonamento è scaduto da più di 2 giorni
# =================================================================================

import sqlite3
import requests
import schedule
import time
from datetime import datetime, timedelta
from telegram.ext import Updater, CommandHandler
from telegram import Bot
import os # Assicurati che questa riga sia all'inizio del file, con gli altri import

# --- CODICE PER TENERE IL BOT ATTIVO 24/7 ---
app = Flask('')

@app.route('/')
def home():
    return "Il bot è vivo!"

def run():
  app.run(host='0.0.0.0',port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# -----------------------------------------

# --- CONFIGURAZIONE: Legge le chiavi dall'ambiente del server ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TWITCH_CLIENT_ID = os.environ.get('TWITCH_CLIENT_ID')
TWITCH_OAUTH_TOKEN = os.environ.get('TWITCH_OAUTH_TOKEN')

# --- INFORMAZIONI PRE-COMPILATE ---
TWITCH_CHANNEL_NAME = 'prinsipe'
TELEGRAM_GROUP_ID = -1001298217863

# --- SETUP DEL DATABASE ---
def setup_database():
    conn = sqlite3.connect('subscribers.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            twitch_user_id TEXT NOT NULL,
            twitch_username TEXT,
            subscription_end_date DATE,
            notified_about_expiration BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.commit()
    return conn

# --- INTERAZIONE CON L'API DI TWITCH ---
def check_twitch_subscription(twitch_username):
    try:
        headers = {
            'Client-ID': TWITCH_CLIENT_ID,
            'Authorization': f'Bearer {TWITCH_OAUTH_TOKEN}'
        }
        channel_res = requests.get(f'https://api.twitch.tv/helix/users?login={TWITCH_CHANNEL_NAME}', headers=headers)
        channel_id = channel_res.json()['data'][0]['id']
        
        user_res = requests.get(f'https://api.twitch.tv/helix/users?login={twitch_username}', headers=headers)
        user_data = user_res.json().get('data')
        if not user_data: return None
        user_id = user_data[0]['id']
        
        sub_res = requests.get(f'https://api.twitch.tv/helix/subscriptions?broadcaster_id={channel_id}&user_id={user_id}', headers=headers)
        if sub_res.status_code == 401:
            print("[ERRORE GRAVE] Il tuo TWITCH_OAUTH_TOKEN non è valido o è scaduto. Rigeneralo.")
            return None
            
        if sub_res.json().get('data'):
            return {'is_subscribed': True, 'twitch_id': user_id}
        return None
    except Exception as e:
        print(f"[ERRORE TWITCH API] Controllo per {twitch_username}: {e}")
        return None

# --- COMANDI DEL BOT TELEGRAM ---
def start(update, context):
    update.message.reply_text(
        "Ciao! Sono il bot per gli abbonati di Prinsipe.\n"
        "Per verificare il tuo abbonamento e accedere al gruppo, usa il comando:\n"
        "/verifica IlTuoNomeUtenteTwitch"
    )

def verifica(update, context):
    telegram_id = update.message.from_user.id
    if not context.args:
        update.message.reply_text("Errore! Devi scrivere il tuo nome utente Twitch dopo il comando.\nEsempio: /verifica xMatteo")
        return

    twitch_username = context.args[0].lower()
    update.message.reply_text(f"Verifico l'abbonamento per '{twitch_username}'... attendi un momento.")
    
    sub_status = check_twitch_subscription(twitch_username)

    if sub_status and sub_status['is_subscribed']:
        end_date = datetime.now().date() + timedelta(days=30)
        cursor = db_connection.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (telegram_id, twitch_user_id, twitch_username, subscription_end_date) VALUES (?, ?, ?, ?)",
            (telegram_id, sub_status['twitch_id'], twitch_username, end_date)
        )
        db_connection.commit()
        
        update.message.reply_text(f"✅ Ottimo! Abbonamento per '{twitch_username}' verificato.")

        try:
            expire_date = datetime.now() + timedelta(hours=1)
            invite_link = context.bot.create_chat_invite_link(
                chat_id=TELEGRAM_GROUP_ID,
                expire_date=expire_date,
                member_limit=1
            )
            update.message.reply_text(
                "Benvenuto nella community! Clicca sul link qui sotto per entrare nel gruppo.\n"
                f"Attenzione: il link è valido solo per te e scadrà tra un'ora.\n\n"
                f"{invite_link.invite_link}"
            )
            print(f"Creato e inviato link d'invito all'utente con ID Telegram: {telegram_id}")

        except Exception as e:
            print(f"[ERRORE] Impossibile creare o inviare il link d'invito: {e}")
            update.message.reply_text("Ho verificato il tuo abbonamento, ma non sono riuscito a generare un link d'invito. Per favore, contatta un amministratore.")
            
    else:
        update.message.reply_text(
            f"❌ Mi dispiace, non ho trovato un abbonamento attivo per '{twitch_username}' al canale di Prinsipe. "
            "Controlla le maiuscole/minuscole o che l'abbonamento non sia privato."
        )

# --- PROCESSO AUTOMATICO GIORNALIERO ---
def daily_check():
    print(f"[{datetime.now()}] Avvio controllo giornaliero degli abbonamenti...")
    bot = Bot(token=TELEGRAM_TOKEN)
    cursor = db_connection.cursor()
    cursor.execute("SELECT telegram_id, twitch_username, subscription_end_date, notified_about_expiration FROM users")
    all_users = cursor.fetchall()
    today = datetime.now().date()

    for user in all_users:
        telegram_id, twitch_username, end_date_str, notified = user
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        # Notifica di scadenza (3 giorni prima)
        if not notified and (end_date - timedelta(days=3)) <= today < end_date:
            try:
                bot.send_message(chat_id=telegram_id, text=f"⚠️ Ciao! Il tuo abbonamento a Twitch per Prinsipe sta per scadere. Rinnovalo per restare nel gruppo!")
                cursor.execute("UPDATE users SET notified_about_expiration = TRUE WHERE telegram_id = ?", (telegram_id,))
                print(f"  -> Notifica di scadenza inviata a {twitch_username}")
            except Exception as e:
                print(f"  -> ERRORE invio notifica a {telegram_id}: {e}")

        # Rimozione dal gruppo (2 giorni dopo la scadenza)
        if today > (end_date + timedelta(days=2)):
            sub_status = check_twitch_subscription(twitch_username)
            if sub_status and sub_status['is_subscribed']:
                new_end_date = datetime.now().date() + timedelta(days=30)
                cursor.execute("UPDATE users SET subscription_end_date = ?, notified_about_expiration = FALSE WHERE telegram_id = ?", (new_end_date, telegram_id))
                print(f"  -> Utente {twitch_username} ha rinnovato! Data aggiornata.")
            else:
                try:
                    bot.kick_chat_member(chat_id=TELEGRAM_GROUP_ID, user_id=telegram_id)
                    cursor.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
                    print(f"  -> RIMOSSO utente {twitch_username} dal gruppo.")
                except Exception as e:
                    print(f"  -> ERRORE rimozione {telegram_id}: {e}.")

    db_connection.commit()
    print("Controllo giornaliero completato.")

# --- AVVIO DEL BOT ---
if __name__ == '__main__':
    keep_alive() # <-- AGGIUNGI QUESTA RIGA
    print("Avvio del bot vFINAL in corso...")
    db_connection = setup_database()
    # ... resto del codice ...
    
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("verifica", verifica))
    
    schedule.every().day.at("03:00").do(daily_check)
    print("Job giornaliero pianificato per le 03:00.")

    updater.start_polling()
    print("Bot avviato e in ascolto. Premi Ctrl+C per fermarlo.")

    while True:
        schedule.run_pending()
        time.sleep(60)