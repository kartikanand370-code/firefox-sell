import asyncio
import json
import logging
import os
import time
from datetime import datetime
from threading import Thread
from flask import Flask
import requests
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ==================== DUMMY WEB SERVER & KEEP-ALIVE ====================
app = Flask("")


@app.route("/")
def home():
    return "Meesho JSON Store Bot is Active & Running 24/7!"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def self_ping_loop():
    time.sleep(5)
    url = os.environ.get(
        "RENDER_EXTERNAL_URL",
        f"http://127.0.0.1:{os.environ.get('PORT', 8080)}/",
    )
    while True:
        try:
            requests.get(url, timeout=5)
        except Exception:
            pass
        time.sleep(15)


def start_keep_alive():
    Thread(target=run_flask, daemon=True).start()
    Thread(target=self_ping_loop, daemon=True).start()


# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

ADMIN_IDS = [7485181331, 8944961221]
SUPPORT_ADMIN_ID = 1111111111

UPI_ID = "mdsaifu4u-2@okaxis"
PRICE_PER_JSON = 20
ITEM_NAME = "Meesho Fresh Account (₹180 FLAT OFF)"

STOCK_FILE = "stock_data.json"
SOLD_FILE = "sold_data.json"
USERS_FILE = "users_data.json"

USER_ORDERS = {}
ADMIN_FLOW = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ==================== STORAGE FUNCTIONS ====================


def load_data(file_path, default):
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(default, f)
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_stock():
    return load_data(STOCK_FILE, [])


def save_stock(data):
    save_data(STOCK_FILE, data)


def get_sold():
    return load_data(SOLD_FILE, [])


def log_sold_order(user_id, user_name, qty, amount, items):
    sold_list = get_sold()
    sold_list.append(
        {
            "timestamp": datetime.now().strftime("%d-%m-%Y %I:%M %p"),
            "user_id": user_id,
            "user_name": user_name,
            "quantity": qty,
            "amount": amount,
            "items": items,
        }
    )
    save_data(SOLD_FILE, sold_list)


def save_user(user_id):
    users = set(load_data(USERS_FILE, []))
    if user_id not in users:
        users.add(user_id)
        save_data(USERS_FILE, list(users))


# ==================== USER HANDLERS ====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id)

    stock_count = len(get_stock())
    status_emoji = "🟢 In Stock" if stock_count > 0 else "🔴 Out of Stock"

    text = (
        f"👋 **Namaste & Welcome to Meesho JSON Hub!**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛍️ **Product:** `{ITEM_NAME}`\n"
        f"⚡ **Feature:** 100% Fresh & Active Sessions\n"
        f"🔥 **Discount:** Flat ₹180 OFF applicable\n"
        f"💰 **Rate:** `₹{PRICE_PER_JSON}` / Account\n"
        f"📦 **Live Stock:** `{stock_count} units` ({status_emoji})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *Niche button par click karke order place karein:*"
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Now", callback_data="buy_json")],
        [InlineKeyboardButton("💬 24/7 Support Admin", callback_data="contact_support")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "contact_support":
        await query.message.reply_text(
            f"💬 **Support Admin Details:**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Admin ID: `{SUPPORT_ADMIN_ID}`\n"
            f"Kisi bhi query ya problem ke liye link par click karein:\n"
            f"👉 [Click Here to Chat with Support](tg://openmessage?user_id={SUPPORT_ADMIN_ID})",
            parse_mode="Markdown",
        )
        return

    if query.data == "buy_json":
        stock = get_stock()
        if len(stock) == 0:
            await query.message.reply_text(
                "⚠️ **Stock Khatam Ho Chuka Hai!**\n\n"
                "Abhi accounts available nahi hain. Naya stock aate hi bot aapko auto alert bhej dega.",
                parse_mode="Markdown",
            )
            return

        USER_ORDERS[user_id] = {"step": "WAITING_QTY"}
        await query.message.reply_text(
            f"🔢 **Quantity Selection**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Available Units: `{len(stock)}`\n"
            f"Price per Unit: `₹{PRICE_PER_JSON}`\n\n"
            f"Aapko kitne accounts chahiye? Kripya number reply karein (e.g. `1`, `2`, `5`):",
            parse_mode="Markdown",
        )


# ==================== ADMIN PANEL ====================


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    stock = get_stock()
    sold = get_sold()
    total_sold_units = sum(item.get("quantity", 0) for item in sold)
    total_revenue = sum(item.get("amount", 0) for item in sold)

    dashboard = (
        f"👑 **ADMIN CONTROL DASHBOARD**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 **Live Stock:** `{len(stock)}` accounts\n"
        f"📈 **Total Sold:** `{total_sold_units}` accounts\n"
        f"💵 **Total Revenue:** `₹{total_revenue}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Select an action:"
    )

    keyboard = [
        [
            InlineKeyboardButton("📦 Live Stock", callback_data="adm_stock"),
            InlineKeyboardButton("📈 Sold History", callback_data="adm_sold"),
        ],
        [
            InlineKeyboardButton("➕ Add JSON Stock", callback_data="adm_add"),
            InlineKeyboardButton("↩️ Remove Last Stock", callback_data="adm_remove_last"),
        ],
        [
            InlineKeyboardButton("🗑 Clear All Active Stock", callback_data="adm_clear"),
        ],
    ]

    await update.message.reply_text(
        dashboard,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        await query.answer("Access Denied", show_alert=True)
        return

    await query.answer()

    if query.data == "adm_stock":
        stock = get_stock()
        await query.message.reply_text(
            f"📊 **Current Live Stock Status**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Available Accounts: `{len(stock)}` units\n"
            f"Price per Unit: `₹{PRICE_PER_JSON}`",
            parse_mode="Markdown",
        )

    elif query.data == "adm_sold":
        sold = get_sold()
        if not sold:
            await query.message.reply_text("ℹ️ Abhi tak koi order sell nahi hua hai.")
            return

        total_units = sum(s.get("quantity", 0) for s in sold)
        total_cash = sum(s.get("amount", 0) for s in sold)

        recent = sold[-5:]
        history_txt = ""
        for s in reversed(recent):
            history_txt += (
                f"• `{s['timestamp']}` | User: `{s['user_id']}`\n"
                f"  Qty: `{s['quantity']}` | Paid: `₹{s['amount']}`\n"
            )

        report = (
            f"📈 **Sold Stock Analytics**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Total Sold: `{total_units}` accounts\n"
            f"💰 Total Earned: `₹{total_cash}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 **Last Recent Orders:**\n\n{history_txt}"
        )
        await query.message.reply_text(report, parse_mode="Markdown")

    elif query.data == "adm_add":
        ADMIN_FLOW[user_id] = {"step": "WAITING_TARGET_COUNT"}
        await query.message.reply_text(
            f"🔢 **Stock Count Confirmation**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Aapko **kitne JSON accounts** add karne hain?\n"
            f"Kripya count enter karein (e.g. `1`, `5`, `10`):",
            parse_mode="Markdown",
        )

    elif query.data == "adm_remove_last":
        stock = get_stock()
        if len(stock) == 0:
            await query.message.reply_text("⚠️ Stock already empty hai, delete karne ko kuch nahi hai.")
            return

        stock.pop()
        save_stock(stock)
        await query.message.reply_text(
            f"↩️ **1 Unit Stock Remove Kar Diya Gaya Hai!**\n"
            f"Ab Live Stock bacha hai: `{len(stock)}` units",
            parse_mode="Markdown",
        )

    elif query.data == "adm_clear":
        save_stock([])
        await query.message.reply_text(
            "🗑 **Live Stock reset ho gaya hai. (Active stock: 0)**"
        )


# ==================== TEXT & DOCUMENT HANDLING ====================


async def handle_incoming_messages(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.message.from_user
    user_id = user.id
    text = update.message.text.strip() if update.message.text else ""

    # ================= 1. ADMIN ADD STOCK FLOW =================
    if user_id in ADMIN_IDS and user_id in ADMIN_FLOW:
        admin_state = ADMIN_FLOW[user_id]

        if admin_state.get("step") == "WAITING_TARGET_COUNT":
            if not text.isdigit() or int(text) <= 0:
                await update.message.reply_text("❌ Kripya valid number enter karein (e.g. 1, 2, 5).")
                return

            target_count = int(text)
            ADMIN_FLOW[user_id] = {
                "step": "WAITING_FILES",
                "target": target_count,
                "added": 0,
            }

            await update.message.reply_text(
                f"📁 **Ab `.json` Files Send Karein**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Target: `{target_count}` files\n"
                f"*(1 `.json` file = 1 Stock account)*\n\n"
                f"File bhejein, upload progress yahan update hota rahega.",
                parse_mode="Markdown",
            )
            return

        elif admin_state.get("step") == "WAITING_FILES":
            if not update.message.document:
                await update.message.reply_text("❌ Kripya `.json` file document attach karke bhejein.")
                return

            doc = update.message.document
            if not doc.file_name.lower().endswith(".json"):
                await update.message.reply_text("⚠️ Kripya valid `.json` format wali file upload karein.")
                return

            file = await context.bot.get_file(doc.file_id)
            file_bytes = await file.download_as_bytearray()
            json_content = file_bytes.decode("utf-8", errors="ignore").strip()

            stock = get_stock()
            stock.append(json_content)
            save_stock(stock)

            admin_state["added"] += 1
            added = admin_state["added"]
            target = admin_state["target"]

            await update.message.reply_text(
                f"✅ **File Received!** ({added}/{target})\n"
                f"📄 `{doc.file_name}` added to live stock.\n"
                f"Live Total Stock: `{len(stock)}`",
                parse_mode="Markdown",
            )

            if added >= target:
                ADMIN_FLOW.pop(user_id, None)
                await update.message.reply_text(
                    f"🎉 **Batch Complete!**\n"
                    f"Aapne total `{target}` accounts successfully upload kar diye hain.",
                    parse_mode="Markdown",
                )

                users = load_data(USERS_FILE, [])
                broadcast_msg = (
                    f"🚨 **NEW STOCK ARRIVAL ALERT!**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Fresh **{ITEM_NAME}** accounts live ho chuke hain!\n"
                    f"📦 Total Available: `{len(stock)}` units\n"
                    f"💰 Price: `₹{PRICE_PER_JSON}` / unit\n\n"
                    f"Turant buy karne ke liye click karein: /start"
                )
                for u in users:
                    try:
                        await context.bot.send_message(
                            chat_id=u, text=broadcast_msg, parse_mode="Markdown"
                        )
                    except Exception:
                        pass
            return

    # ================= 2. BUYER ORDER FLOW =================
    if user_id not in USER_ORDERS:
        return

    order = USER_ORDERS[user_id]

    # Quantity Entered -> Dynamic QR Generation
    if order.get("step") == "WAITING_QTY":
        if not text.isdigit() or int(text) <= 0:
            await update.message.reply_text(
                "❌ Kripya ek valid number likhein (e.g. `1`, `2`, `3`)."
            )
            return

        qty = int(text)
        stock = get_stock()
        if qty > len(stock):
            await update.message.reply_text(
                f"⚠️ Humare paas abhi sirf `{len(stock)}` units bache hain!\nKripya kam number enter karein."
            )
            return

        total_amount = qty * PRICE_PER_JSON
        order["qty"] = qty
        order["amount"] = total_amount
        order["step"] = "WAITING_PAYMENT"

        # Dynamic UPI QR Code URL Generation
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data=upi://pay?pa={UPI_ID}%26pn=MeeshoStore%26am={total_amount}"

        pay_caption = (
            f"🧾 **ORDER INVOICE**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛍️ **Item:** `{ITEM_NAME}`\n"
            f"🔢 **Quantity:** `{qty}`\n"
            f"💵 **Total Amount:** `₹{total_amount}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📲 **Scan QR to Pay ₹{total_amount}**\n\n"
            f"🔗 **UPI ID:** `{UPI_ID}` *(Tap to copy)*\n\n"
            f"⚠️ **Payment Steps:**\n"
            f"1. Is QR code ko kisi bhi app (PhonePe/GPay/Paytm) se scan karein.\n"
            f"2. Pay karne ke baad **12-digit UTR** ya **Screenshot** yahan bhej dein."
        )

        await update.message.reply_photo(
            photo=qr_url, caption=pay_caption, parse_mode="Markdown"
        )

    # Verification / Proof Received
    elif order.get("step") == "WAITING_PAYMENT":
        order["step"] = "UNDER_VERIFICATION"
        await update.message.reply_text(
            "⏳ **Payment Proof Received!**\n\n"
            "Admin verify karke aapka account 1-2 minutes me deliver kar denge. Please wait karein.",
            parse_mode="Markdown",
        )

        user_name = user.full_name or "Buyer"
        username_str = f"@{user.username}" if user.username else "No Username"
        c_msg = text if text else "Screenshot Attached"

        admin_alert = (
            f"🔔 **NEW ORDER PAYMENT PROOF**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Customer:** {user_name} ({username_str})\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"📦 **Quantity:** `{order['qty']}`\n"
            f"💰 **Amount:** `₹{order['amount']}`\n"
            f"💬 **Proof / UTR:** `{c_msg}`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        buttons = [
            [
                InlineKeyboardButton(
                    "✅ Approve & Deliver", callback_data=f"app_{user_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject", callback_data=f"rej_{user_id}"
                ),
            ]
        ]

        for adm in ADMIN_IDS:
            try:
                if update.message.photo:
                    await context.bot.send_photo(
                        chat_id=adm,
                        photo=update.message.photo[-1].file_id,
                        caption=admin_alert,
                        reply_markup=InlineKeyboardMarkup(buttons),
                        parse_mode="Markdown",
                    )
                else:
                    await context.bot.send_message(
                        chat_id=adm,
                        text=admin_alert,
                        reply_markup=InlineKeyboardMarkup(buttons),
                        parse_mode="Markdown",
                    )
            except Exception:
                pass


# ==================== APPROVAL & AUTO-REMOVE/LOG ====================


async def process_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id

    if admin_id not in ADMIN_IDS:
        await query.answer("Access Denied", show_alert=True)
        return

    await query.answer()
    action, target_user_id = query.data.split("_")
    target_user_id = int(target_user_id)

    if target_user_id not in USER_ORDERS:
        await query.message.reply_text("⚠️ Ye order pehle hi process ho chuka hai.")
        return

    order = USER_ORDERS[target_user_id]
    qty = order["qty"]
    amount = order["amount"]

    if action == "app":
        stock = get_stock()
        if len(stock) < qty:
            await query.message.reply_text(
                "❌ Error: Live stock kam hai! Pehle new JSON add karein."
            )
            return

        delivered_items = [stock.pop(0) for _ in range(qty)]
        save_stock(stock)

        target_chat = await context.bot.get_chat(target_user_id)
        cust_name = target_chat.full_name or "Buyer"
        log_sold_order(
            target_user_id, cust_name, qty, amount, delivered_items
        )

        for idx, item in enumerate(delivered_items, 1):
            filename = f"meesho_fresh_{target_user_id}_{idx}.json"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(item)

            with open(filename, "rb") as f:
                await context.bot.send_document(
                    chat_id=target_user_id,
                    document=f,
                    caption=f"🎉 **Payment Verified!** ({idx}/{qty})\nAapka Fresh Meesho Account JSON file.",
                )
            if os.path.exists(filename):
                os.remove(filename)

        del USER_ORDERS[target_user_id]
        status_note = f"\n\n✅ **APPROVED & DELIVERED BY ADMIN ({admin_id})**"

        if query.message.photo:
            await query.edit_message_caption(
                caption=(query.message.caption or "") + status_note
            )
        else:
            await query.edit_message_text(
                text=(query.message.text or "") + status_note
            )

    elif action == "rej":
        del USER_ORDERS[target_user_id]
        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"❌ **Payment Verification Rejected!**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Aapki payment confirm nahi ho saki.\n"
                f"Kripya sahi UTR / Screenshot ke saath dubara try karein ya support se contact karein."
            ),
            parse_mode="Markdown",
        )
        status_note = f"\n\n❌ **REJECTED BY ADMIN ({admin_id})**"

        if query.message.photo:
            await query.edit_message_caption(
                caption=(query.message.caption or "") + status_note
            )
        else:
            await query.edit_message_text(
                text=(query.message.text or "") + status_note
            )


# ==================== MAIN ====================


def main():
    start_keep_alive()

    if not BOT_TOKEN:
        print("CRITICAL ERROR: BOT_TOKEN environment variable not set!")
        return

    print("Bot initializing...")
    app_tg = Application.builder().token(BOT_TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("admin", admin_panel))
    app_tg.add_handler(
        CallbackQueryHandler(process_approval, pattern="^(app|rej)_")
    )
    app_tg.add_handler(
        CallbackQueryHandler(admin_buttons, pattern="^adm_")
    )
    app_tg.add_handler(
        CallbackQueryHandler(user_callback, pattern="^(buy_json|contact_support)$")
    )
    app_tg.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_incoming_messages)
    )

    print("Bot is up and polling live!")
    app_tg.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
