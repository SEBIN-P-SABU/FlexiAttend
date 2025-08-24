# Copyright (c) 2025, Sebin P Sabu and contributors
# For license information, please see license.txt

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import requests
import frappe
import asyncio
import base64

def run():
    app.run_polling()
    

# ---- HELPER FUNCTIONS ---- #
def get_erp_settings():
    settings = frappe.get_single("FlexiAttend Settings")
    return {
        "BOT_TOKEN": settings.flexiattend_token,
        "ERP_URL": settings.erpnext_base_url,
        "SITE_TOKEN": settings.site_token,
    }

def get_endpoints():
    settings = get_erp_settings()
    ERP_URL = settings["ERP_URL"]
    return {
        "VALIDATE_EMP_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.validate_employee",
        "CREATE_CHECKIN_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.create_employee_checkin"
    }

# ---- BOT RUNNER ---- #
def start_bot():
    """Check if FlexiAttend is enabled, then run Telegram bot"""
    try:
        settings = frappe.get_single("FlexiAttend Settings")
        if not getattr(settings, "enable_flexiattend", False):
            frappe.log_error("FlexiAttend disabled. Bot not started.", "FlexiAttend Bot")
            return

        app = ApplicationBuilder().token(settings.flexiattend_token).build()

        # Scheduler needs async start
        asyncio.get_event_loop().create_task(app.run_polling())
        frappe.log_error("FlexiAttend Bot started successfully.", "FlexiAttend Bot")

    except Exception as e:
        frappe.log_error(f"Failed to start FlexiAttend Bot: {str(e)}", "FlexiAttend Bot")
        
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

# 1️⃣ /start -> site verification
async def verify_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Enter your site code to verify your site:",
        reply_markup=ReplyKeyboardRemove()
    )
    return SITE_VERIFICATION

async def check_site_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code != SITE_TOKEN:
        await update.message.reply_text("❌ Invalid site code. Try again:")
        return SITE_VERIFICATION
    await update.message.reply_text("✅ Site verified! Please enter your Employee ID:")
    return EMPLOYEE_ID

# 2️⃣ Employee ID input
async def get_employee_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp_id = update.message.text.strip()
    context.user_data['employee_id'] = emp_id

    try:
        r = requests.post(VALIDATE_EMP_ENDPOINT, data={"employee_id": emp_id})
        resp = r.json()
        print("Validate response:", resp)

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

# 3️⃣ Menu choice
async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice not in ["Check-In", "Check-Out"]:
        await update.message.reply_text("❌ Please use the buttons only.")
        return MENU

    context.user_data['log_type'] = "IN" if choice == "Check-In" else "OUT"

    # Send location button
    location_keyboard = [[KeyboardButton("Share Location 📍", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Please share your location:", reply_markup=reply_markup)
    return LOCATION

# 4️⃣ Handle location & send check-in with attachments
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.location:
        await update.message.reply_text("❌ Please share your location using the button.")
        return LOCATION

    emp_id = context.user_data['employee_id']
    log_type = context.user_data['log_type']
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    attachments = context.user_data.get("attachments", [])

    # Convert attachments to base64
    encoded_attachments = []
    for att in attachments:
        file_id = att["file_id"]
        file_name = att["file_name"]
        file_obj = await context.bot.get_file(file_id)
        file_bytes = await file_obj.download_as_bytearray()
        encoded = base64.b64encode(file_bytes).decode()
        encoded_attachments.append({"filename": file_name, "filedata": encoded})

    payload = {
        "employee_id": emp_id,
        "log_type": log_type,
        "latitude": lat,
        "longitude": lon,
        "attachments": encoded_attachments
    }

    try:
        r = requests.post(CREATE_CHECKIN_ENDPOINT, json=payload)
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
            await update.message.reply_text(f"✅ {message_text}", reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text(f"❌ Failed: {message_text}", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}", reply_markup=ReplyKeyboardRemove())

    context.user_data.clear()
    return ConversationHandler.END

## 5️⃣ Capture attachments during the process (documents & all photos)
# 5️⃣ Capture attachments during the process
async def handle_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = frappe.get_single("FlexiAttend Settings")
    attachments_enabled = getattr(settings, "enable_attachment_feature_in_employee_checkin", False)

    if not attachments_enabled:
        await update.message.reply_text("⚠️ Attachment feature is disabled. File will not be saved.")
        print(f"[INFO] ⚠️ Attachment feature is disabled. File will not be saved.")
        return

    if "attachments" not in context.user_data:
        context.user_data["attachments"] = []

    current_count = len(context.user_data["attachments"])
    MAX_IMAGES = getattr(settings, "maximum_file_attachments", 5)

    new_files = []

    # Handle documents
    if update.message.document:
        if current_count >= MAX_IMAGES:
            await update.message.reply_text(f"❌ Maximum {MAX_IMAGES} images allowed per check-in.")
            return
        doc = update.message.document
        context.user_data["attachments"].append({"file_id": doc.file_id, "file_name": doc.file_name})
        print(f"[INFO] Document '{doc.file_name}' received. Total attachments: {len(context.user_data['attachments'])}")
        await update.message.reply_text(f"✅ Document '{doc.file_name}' received and will be attached.")
        return

    # Handle photos (attach only one version per photo)
    elif update.message.photo:
        if current_count >= MAX_IMAGES:
            await update.message.reply_text(f"❌ Maximum {MAX_IMAGES} images allowed per check-in.")
            return

        # Take the **last one in the list**, which is usually highest resolution
        file_id = update.message.photo[-1].file_id
        file_name = f"photo_{current_count + 1}.jpg"

        context.user_data["attachments"].append({"file_id": file_id, "file_name": file_name})
        new_files.append(file_name)
        current_count += 1

        print(f"[INFO] Photo received (file_id={file_id}). Total attachments: {current_count}")
        await update.message.reply_text(f"✅ Photo received and will be attached ({current_count}/{MAX_IMAGES})")
        return

    else:
        await update.message.reply_text("❌ Unsupported attachment type.")


# 6️⃣ Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled. You can start again with /start.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# 7️⃣ Ignore unexpected text (commented old validation for reference)
async def ignore_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        # # Old validation (commented) this includes attachment validation.
        # if update.message:
        #     await update.message.reply_text("❌ Please use the buttons only.", reply_markup=ReplyKeyboardRemove())
        # New logic: only warn if user types text instead of sharing location - this allows attachments if it's enabbled
        if context.user_data.get('log_type') and update.message.text != "/cancel":
            await update.message.reply_text("❌ Please share your location using the button.")
        else:
            await update.message.reply_text("❌ Please use the buttons only.")

# ---- BOT SETUP ---- #
async def set_commands_on_startup(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start the FlexiAttend Bot"),
        BotCommand("cancel", "Cancel Current Operation")
    ])

app = ApplicationBuilder().token(BOT_TOKEN).post_init(set_commands_on_startup).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", verify_site)],
    states={
        SITE_VERIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_site_code)],
        EMPLOYEE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_employee_id)],
        MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
        LOCATION: [
            MessageHandler(filters.LOCATION, location_handler),
            MessageHandler(filters.PHOTO | filters.Document.ALL, handle_attachments)
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        MessageHandler(filters.ALL & ~filters.COMMAND, ignore_unexpected)
    ]
)

app.add_handler(conv_handler)

# ---- RUN BOT ---- #
if __name__ == "__main__":
    asyncio.run(set_commands_on_startup(app))
    app.run_polling()











###########################

# import frappe
# import requests
# import logging
# from telegram import Update, ReplyKeyboardMarkup
# from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # ----------------------------
# # Helpers
# # ----------------------------

# def get_flexiattend_settings():
#     """Fetch latest FlexiAttend Settings from ERPNext"""
#     settings = frappe.get_single("FlexiAttend Settings")
#     return {
#         "enabled": settings.enable_flexiattend,
#         "bot_token": settings.flexiattend_token,
#         "base_url": settings.erpnext_base_url.strip("/") if settings.erpnext_base_url else "",
#         "site_token": settings.site_token
#     }

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text(
#         "👋 Welcome to FlexiAttend Bot!\n\nPlease enter your *Site Code* to verify.",
#         parse_mode="Markdown"
#     )

# async def verify_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     site_code = update.message.text.strip()
#     settings = get_flexiattend_settings()

#     if not settings["site_token"]:
#         await update.message.reply_text("⚠️ Site Token not configured in FlexiAttend Settings.")
#         return

#     if site_code == settings["site_token"]:
#         await update.message.reply_text("✅ Site verified! Now enter your *Employee ID* to continue.", parse_mode="Markdown")
#         context.user_data["site_verified"] = True
#     else:
#         await update.message.reply_text("❌ Invalid site code. Try again:")

# async def verify_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not context.user_data.get("site_verified"):
#         await update.message.reply_text("⚠️ Please verify your site code first.")
#         return

#     employee_id = update.message.text.strip()
#     settings = get_flexiattend_settings()

#     try:
#         url = f"{settings['base_url']}/api/method/flexiattend.triggers.api.validate_employee"
#         headers = {"Authorization": f"token {settings['site_token']}"}
#         res = requests.post(url, headers=headers, json={"employee_id": employee_id}, timeout=10)

#         if res.status_code == 200 and res.json().get("message") == "success":
#             await update.message.reply_text("✅ Employee verified! You can now use FlexiAttend features.")
#         else:
#             await update.message.reply_text("❌ Employee verification failed. Try again.")
#     except Exception as e:
#         logger.error(f"Error verifying employee: {e}")
#         await update.message.reply_text(f"⚠️ Error verifying employee: {e}")

# # ----------------------------
# # Main Bot Runner
# # ----------------------------

# def run_flexiattend_bot():
#     settings = get_flexiattend_settings()

#     if not settings["enabled"]:
#         logger.warning("⚠️ FlexiAttend Bot is disabled in settings.")
#         return

#     if not settings["bot_token"]:
#         logger.error("❌ Bot token missing in FlexiAttend Settings.")
#         return

#     application = ApplicationBuilder().token(settings["bot_token"]).build()

#     application.add_handler(CommandHandler("start", start))
#     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, verify_site))
#     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, verify_employee))

#     logger.info("🚀 FlexiAttend Bot started...")
#     application.run_polling()
