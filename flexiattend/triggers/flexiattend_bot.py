# Copyright (c) 2025, Sebin P Sabu and contributors
# For license information, please see license.txt

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import requests
import frappe


def run():
    app.run_polling()

# ---- HELPER FUNCTIONS ---- #
def get_erp_settings():
    """Read dynamic values from FlexiAttend Settings"""
    settings = frappe.get_single("FlexiAttend Settings")
    return {
        "BOT_TOKEN": settings.flexiattend_token,
        "ERP_URL": settings.erpnext_base_url,
        "SITE_TOKEN": settings.site_token
    }

def get_endpoints():
    settings = get_erp_settings()
    ERP_URL = settings["ERP_URL"]
    return {
        "VALIDATE_EMP_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.validate_employee",
        "CREATE_CHECKIN_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.create_employee_checkin"
    }

# ---- GLOBAL SETTINGS ---- #
settings = get_erp_settings()
BOT_TOKEN = settings["BOT_TOKEN"]
SITE_TOKEN = settings["SITE_TOKEN"]

endpoints = get_endpoints()
VALIDATE_EMP_ENDPOINT = endpoints["VALIDATE_EMP_ENDPOINT"]
CREATE_CHECKIN_ENDPOINT = endpoints["CREATE_CHECKIN_ENDPOINT"]

# ---- CONVERSATION STATES ---- #
SITE_VERIFICATION, EMPLOYEE_ID, MENU, LOCATION = range(4)

# ---- BOT HANDLERS ---- #

# 1️⃣ Site verification
async def verify_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter your 12-character site code to verify your site:")
    return SITE_VERIFICATION

async def check_site_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code != SITE_TOKEN:
        await update.message.reply_text("❌ Invalid site code. Try again:")
        return SITE_VERIFICATION
    await update.message.reply_text("✅ Site verified! Please enter your Employee ID:")
    return EMPLOYEE_ID

# 2️⃣ Employee ID input
async def employee_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter your Employee ID:")
    return EMPLOYEE_ID

# 3️⃣ Verify Employee ID
async def get_employee_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp_id = update.message.text.strip()
    context.user_data['employee_id'] = emp_id

    try:
        r = requests.post(VALIDATE_EMP_ENDPOINT, data={"employee_id": emp_id})
        resp = r.json()
        print("Validate response:", resp)  # Debug

        # Access nested message
        resp_msg = resp.get("message", {})
        if isinstance(resp_msg, dict):
            status = resp_msg.get("status")
        else:
            status = resp.get("status")

        if status != "success":
            await update.message.reply_text("❌ Employee not found. Enter again:")
            return EMPLOYEE_ID
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error verifying employee: {str(e)}")
        return EMPLOYEE_ID

    # Show menu buttons
    menu_keyboard = [["Check-In", "Check-Out"]]
    reply_markup = ReplyKeyboardMarkup(menu_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("✅ Employee verified. Choose an option:", reply_markup=reply_markup)
    return MENU

# 4️⃣ Menu choice
async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice not in ["Check-In", "Check-Out"]:
        await update.message.reply_text("❌ Please use the buttons only.")
        return MENU

    context.user_data['log_type'] = "IN" if choice == "Check-In" else "OUT"

    location_keyboard = [[KeyboardButton("Share Location 📍", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Please share your location:", reply_markup=reply_markup)
    return LOCATION

# 5️⃣ Handle location
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.location:
        await update.message.reply_text("❌ Please share your location using the button.")
        return LOCATION

    emp_id = context.user_data['employee_id']
    log_type = context.user_data['log_type']
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    payload = {
        "employee_id": emp_id,
        "log_type": log_type,
        "latitude": lat,
        "longitude": lon
    }

    try:
        r = requests.post(CREATE_CHECKIN_ENDPOINT, data=payload)
        print("Create Checkin response:", r.text)
        resp = r.json()

        resp_msg = resp.get("message", {})
        if isinstance(resp_msg, dict):
            status = resp_msg.get("status")
            message_text = resp_msg.get("message")
        else:
            status = resp.get("status")
            message_text = resp.get("message", "")

        if status == "success":
            await update.message.reply_text(f"✅ {message_text}")
        else:
            await update.message.reply_text(f"❌ Failed: {message_text}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

    return ConversationHandler.END

# 6️⃣ Ignore text outside flow
async def ignore_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Please use the buttons to interact with the bot.")

async def ignore_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and not update.message.location:
        await update.message.reply_text("❌ Please use the buttons only. Attachments or typing are not allowed.")

# ---- BOT SETUP ---- #
app = ApplicationBuilder().token(BOT_TOKEN).build()

# conv_handler = ConversationHandler(
#     entry_points=[CommandHandler("start", verify_site)],
#     states={
#         SITE_VERIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_site_code)],
#         EMPLOYEE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_employee_id)],
#         MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
#         LOCATION: [MessageHandler(filters.LOCATION, location_handler)]
#     },
#     fallbacks=[]
# )

# app.add_handler(conv_handler)

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", verify_site),
        CommandHandler("employee_id", employee_id)
    ],
    states={
        SITE_VERIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_site_code)],
        EMPLOYEE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_employee_id)],
        MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
        LOCATION: [MessageHandler(filters.LOCATION, location_handler)],
    },
    fallbacks=[MessageHandler(filters.ALL, ignore_unexpected)]
)

app.add_handler(conv_handler)
# app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ignore_text))
# app.add_handler(MessageHandler(filters.ALL, ignore_unexpected))

# app.run_polling()
# ---- ALLOW DIRECT RUNNING WITH PYTHON3 ---- #
if __name__ == "__main__":
    app.run_polling()