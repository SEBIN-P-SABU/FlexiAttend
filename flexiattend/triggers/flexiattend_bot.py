# Copyright (c) 2025, Sebin P Sabu and contributors
# For license information, please see license.txt


# Copyright (c) 2025, Sebin P Sabu and contributors
# For license information, please see license.txt

from telegram import Update, Bot, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
import frappe
import requests
import asyncio
import base64
import json

# ---- HELPER FUNCTIONS ---- #
def get_erp_settings():
    settings = frappe.get_single("FlexiAttend Settings")
    return {
        "BOT_TOKEN": settings.flexiattend_token,
        "ERP_URL": settings.erpnext_base_url,
        "SITE_TOKEN": settings.site_token,
        "ENABLE_FLEXIATTEND": getattr(settings, "enable_flexiattend", False),
        "MAX_ATTACHMENTS": getattr(settings, "maximum_file_attachments", 5),
        "ATTACHMENT_ENABLED": getattr(settings, "enable_attachment_feature_in_employee_checkin", False)
    }

settings = get_erp_settings()
BOT_TOKEN = settings["BOT_TOKEN"]
SITE_TOKEN = settings["SITE_TOKEN"]
ENABLE_FLEXIATTEND = settings["ENABLE_FLEXIATTEND"]
MAX_ATTACHMENTS = settings["MAX_ATTACHMENTS"]
ATTACHMENT_ENABLED = settings["ATTACHMENT_ENABLED"]

VALIDATE_EMP_ENDPOINT = f"{settings['ERP_URL']}/api/method/flexiattend.triggers.api.validate_employee"
CREATE_CHECKIN_ENDPOINT = f"{settings['ERP_URL']}/api/method/flexiattend.triggers.api.create_employee_checkin"

bot = Bot(BOT_TOKEN)

# ---- CONVERSATION STATES ---- #
SITE_VERIFICATION, EMPLOYEE_ID, MENU, LOCATION = range(4)

# ---- DUMMY CONTEXT ---- #
class DummyContext:
    def __init__(self, bot):
        self.bot = bot
        self.user_data = {}

# ---- HANDLER FUNCTIONS ---- #
async def verify_site(update, context, user_data):
    if not ENABLE_FLEXIATTEND:
        await context.bot.send_message(update.message.chat.id, "❌ FlexiAttend Bot is currently disabled. Please contact admin.")
        return
    await context.bot.send_message(update.message.chat.id, "Enter your site token to verify your site:", reply_markup=ReplyKeyboardRemove())
    user_data['state'] = SITE_VERIFICATION

async def check_site_code(update, context, user_data):
    code = update.message.text.strip()
    if code != SITE_TOKEN:
        await context.bot.send_message(update.message.chat.id, "❌ Invalid site code. Try again:")
        return
    await context.bot.send_message(update.message.chat.id, "✅ Site verified! Please enter your Employee ID:")
    user_data['state'] = EMPLOYEE_ID

async def get_employee_id(update, context, user_data):
    emp_id = update.message.text.strip()
    user_data['employee_id'] = emp_id

    try:
        r = requests.post(VALIDATE_EMP_ENDPOINT, data={"employee_id": emp_id})
        resp = r.json()
        status = resp.get("status") or resp.get("message", {}).get("status")
        if status != "success":
            await context.bot.send_message(update.message.chat.id, "❌ Employee not found. Enter again:")
            return
    except Exception as e:
        await context.bot.send_message(update.message.chat.id, f"⚠️ Error verifying employee: {str(e)}")
        return

    menu_keyboard = [["Check-In", "Check-Out"]]
    reply_markup = ReplyKeyboardMarkup(menu_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await context.bot.send_message(update.message.chat.id, "✅ Employee verified. Choose an option:", reply_markup=reply_markup)
    user_data['state'] = MENU

async def menu_choice(update, context, user_data):
    choice = update.message.text
    if choice not in ["Check-In", "Check-Out"]:
        await context.bot.send_message(update.message.chat.id, "❌ Please use the buttons only.")
        return
    user_data['log_type'] = "IN" if choice == "Check-In" else "OUT"

    location_keyboard = [[KeyboardButton("Share Location 📍", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await context.bot.send_message(update.message.chat.id, "Please share your location:", reply_markup=reply_markup)
    user_data['state'] = LOCATION

# ---- Attachments ---- #
async def handle_attachments(update, context, user_data):
    if not ATTACHMENT_ENABLED:
        await context.bot.send_message(update.message.chat.id, "⚠️ Attachment feature is disabled. File will not be saved.")
        return

    if "attachments" not in user_data:
        user_data["attachments"] = []

    current_count = len(user_data["attachments"])

    # Documents
    if update.message.document:
        if current_count >= MAX_ATTACHMENTS:
            await context.bot.send_message(update.message.chat.id, f"❌ Maximum {MAX_ATTACHMENTS} files allowed.")
            return
        doc = update.message.document
        user_data["attachments"].append({"file_id": doc.file_id, "file_name": doc.file_name})
        await context.bot.send_message(update.message.chat.id, f"✅ Document '{doc.file_name}' received.")
        return

    # Photos
    elif update.message.photo:
        if current_count >= MAX_ATTACHMENTS:
            await context.bot.send_message(update.message.chat.id, f"❌ Maximum {MAX_ATTACHMENTS} photos allowed.")
            return
        file_id = update.message.photo[-1].file_id
        file_name = f"photo_{current_count+1}.jpg"
        user_data["attachments"].append({"file_id": file_id, "file_name": file_name})
        await context.bot.send_message(update.message.chat.id, f"✅ Photo received ({current_count+1}/{MAX_ATTACHMENTS})")
        return

    else:
        await context.bot.send_message(update.message.chat.id, "❌ Unsupported attachment type.")

# ---- Location ---- #
async def location_handler(update, context, user_data):
    if not update.message.location:
        await context.bot.send_message(update.message.chat.id, "❌ Please share your location using the button.")
        return

    emp_id = user_data['employee_id']
    log_type = user_data['log_type']
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    attachments = user_data.get("attachments", [])

    encoded_attachments = []
    for att in attachments:
        file_obj = await context.bot.get_file(att["file_id"])
        file_bytes = await file_obj.download_as_bytearray()
        encoded_attachments.append({
            "filename": att["file_name"],
            "filedata": base64.b64encode(file_bytes).decode()
        })

    payload = {
        "employee_id": emp_id,
        "log_type": log_type,
        "latitude": lat,
        "longitude": lon,
        "attachments": encoded_attachments
    }

    try:
        r = requests.post(CREATE_CHECKIN_ENDPOINT, json=payload)
        resp = r.json()
        status = resp.get("status") or resp.get("message", {}).get("status")
        message_text = resp.get("message") or resp.get("message", {}).get("message", "")
        if status == "success":
            await context.bot.send_message(update.message.chat.id, f"✅ {message_text}", reply_markup=ReplyKeyboardRemove())
        else:
            await context.bot.send_message(update.message.chat.id, f"❌ Failed: {message_text}", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await context.bot.send_message(update.message.chat.id, f"⚠️ Error: {str(e)}", reply_markup=ReplyKeyboardRemove())

    user_data.clear()

# ---- Cancel ---- #
async def cancel(update, context, user_data):
    await context.bot.send_message(update.message.chat.id, "❌ Operation cancelled. You can start again with /start.", reply_markup=ReplyKeyboardRemove())
    user_data.clear()

# ---- Ignore unexpected ---- #
async def ignore_unexpected(update, context, user_data):
    if update.message and update.message.text != "/cancel":
        if user_data.get('log_type'):
            await context.bot.send_message(update.message.chat.id, "❌ Please share your location using the button.")
        else:
            await context.bot.send_message(update.message.chat.id, "❌ Please use the buttons only.")

# ---- WEBHOOK ENTRYPOINT ---- #
@frappe.whitelist(allow_guest=True)
def webhook(**kwargs):
    if not ENABLE_FLEXIATTEND:
        return "FlexiAttend Bot disabled"

    raw_update = frappe.local.form_dict.get("update")
    frappe.log_error(f"Webhook payload: {raw_update}", "FlexiAttend Bot Debug")
    if not raw_update:
        return "No update"

    if not hasattr(frappe.local, "user_data_store"):
        frappe.local.user_data_store = {}

    try:
        update = Update.de_json(json.loads(raw_update), bot=bot)
        chat_id = update.message.chat.id
        user_data = frappe.local.user_data_store.setdefault(chat_id, {})
        context = DummyContext(bot)

        loop = asyncio.get_event_loop()
        state = user_data.get('state')

        # Handle /cancel anytime
        if update.message.text == "/cancel":
            loop.run_until_complete(cancel(update, context, user_data))
        # /start command always verifies site
        elif update.message.text == "/start":
            loop.run_until_complete(verify_site(update, context, user_data))
        # Attachment/location support
        elif state == LOCATION:
            if update.message.location:
                loop.run_until_complete(location_handler(update, context, user_data))
            else:
                loop.run_until_complete(handle_attachments(update, context, user_data))
        # MENU and other states
        elif state == MENU:
            loop.run_until_complete(menu_choice(update, context, user_data))
        elif state == EMPLOYEE_ID:
            loop.run_until_complete(get_employee_id(update, context, user_data))
        elif state == SITE_VERIFICATION:
            loop.run_until_complete(check_site_code(update, context, user_data))
        # Fallback for any other message
        else:
            loop.run_until_complete(ignore_unexpected(update, context, user_data))

        return "OK"

    except Exception as e:
        frappe.log_error(f"Webhook error: {str(e)}", "FlexiAttend Bot")
        return "Error"






















# from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
# from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
# import requests
# import frappe
# import asyncio
# import base64
# import json

# # ---- HELPER FUNCTIONS ---- #
# def get_erp_settings():
#     """Fetch FlexiAttend Settings"""
#     settings = frappe.get_single("FlexiAttend Settings")
#     return {
#         "BOT_TOKEN": settings.flexiattend_token,
#         "ERP_URL": settings.erpnext_base_url,
#         "SITE_TOKEN": settings.site_token,
#         "ENABLE_FLEXIATTEND": getattr(settings, "enable_flexiattend", False),
#         "MAX_ATTACHMENTS": getattr(settings, "maximum_file_attachments", 5),
#         "ATTACHMENT_ENABLED": getattr(settings, "enable_attachment_feature_in_employee_checkin", False)
#     }

# def get_endpoints():
#     settings = get_erp_settings()
#     ERP_URL = settings["ERP_URL"]
#     return {
#         "VALIDATE_EMP_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.validate_employee",
#         "CREATE_CHECKIN_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.create_employee_checkin"
#     }

# # ---- GLOBAL SETTINGS ---- #
# settings = get_erp_settings()
# BOT_TOKEN = settings["BOT_TOKEN"]
# SITE_TOKEN = settings["SITE_TOKEN"]
# ENABLE_FLEXIATTEND = settings["ENABLE_FLEXIATTEND"]
# MAX_ATTACHMENTS = settings["MAX_ATTACHMENTS"]
# ATTACHMENT_ENABLED = settings["ATTACHMENT_ENABLED"]

# endpoints = get_endpoints()
# VALIDATE_EMP_ENDPOINT = endpoints["VALIDATE_EMP_ENDPOINT"]
# CREATE_CHECKIN_ENDPOINT = endpoints["CREATE_CHECKIN_ENDPOINT"]

# # ---- CONVERSATION STATES ---- #
# SITE_VERIFICATION, EMPLOYEE_ID, MENU, LOCATION = range(4)

# # ---- BOT HANDLERS ---- #

# # 1️⃣ /start -> site verification
# async def verify_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not ENABLE_FLEXIATTEND:
#         await update.message.reply_text("❌ FlexiAttend Bot is currently disabled. Please contact admin.")
#         return ConversationHandler.END

#     await update.message.reply_text(
#         "Enter your site token to verify your site:",
#         reply_markup=ReplyKeyboardRemove()
#     )
#     return SITE_VERIFICATION

# async def check_site_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     code = update.message.text.strip()
#     if code != SITE_TOKEN:
#         await update.message.reply_text("❌ Invalid site code. Try again:")
#         return SITE_VERIFICATION

#     await update.message.reply_text("✅ Site verified! Please enter your Employee ID:")
#     return EMPLOYEE_ID

# # 2️⃣ Employee ID input
# async def get_employee_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     emp_id = update.message.text.strip()
#     context.user_data['employee_id'] = emp_id

#     try:
#         r = requests.post(VALIDATE_EMP_ENDPOINT, data={"employee_id": emp_id})
#         resp = r.json()

#         resp_msg = resp.get("message", {})
#         if isinstance(resp_msg, dict):
#             status = resp_msg.get("status")
#         else:
#             status = resp.get("status")

#         if status != "success":
#             await update.message.reply_text("❌ Employee not found. Enter again:")
#             return EMPLOYEE_ID
#     except Exception as e:
#         await update.message.reply_text(f"⚠️ Error verifying employee: {str(e)}")
#         return EMPLOYEE_ID

#     menu_keyboard = [["Check-In", "Check-Out"]]
#     reply_markup = ReplyKeyboardMarkup(menu_keyboard, one_time_keyboard=True, resize_keyboard=True)
#     await update.message.reply_text("✅ Employee verified. Choose an option:", reply_markup=reply_markup)
#     return MENU

# # 3️⃣ Menu choice
# async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     choice = update.message.text
#     if choice not in ["Check-In", "Check-Out"]:
#         await update.message.reply_text("❌ Please use the buttons only.")
#         return MENU

#     context.user_data['log_type'] = "IN" if choice == "Check-In" else "OUT"

#     location_keyboard = [[KeyboardButton("Share Location 📍", request_location=True)]]
#     reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
#     await update.message.reply_text("Please share your location:", reply_markup=reply_markup)
#     return LOCATION

# # 4️⃣ Handle location & send check-in with attachments
# async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not update.message.location:
#         await update.message.reply_text("❌ Please share your location using the button.")
#         return LOCATION

#     emp_id = context.user_data['employee_id']
#     log_type = context.user_data['log_type']
#     lat = update.message.location.latitude
#     lon = update.message.location.longitude
#     attachments = context.user_data.get("attachments", [])

#     encoded_attachments = []
#     for att in attachments:
#         file_obj = await context.bot.get_file(att["file_id"])
#         file_bytes = await file_obj.download_as_bytearray()
#         encoded_attachments.append({
#             "filename": att["file_name"],
#             "filedata": base64.b64encode(file_bytes).decode()
#         })

#     payload = {
#         "employee_id": emp_id,
#         "log_type": log_type,
#         "latitude": lat,
#         "longitude": lon,
#         "attachments": encoded_attachments
#     }

#     try:
#         r = requests.post(CREATE_CHECKIN_ENDPOINT, json=payload)
#         resp = r.json()

#         resp_msg = resp.get("message", {})
#         if isinstance(resp_msg, dict):
#             status = resp_msg.get("status")
#             message_text = resp_msg.get("message")
#         else:
#             status = resp.get("status")
#             message_text = resp.get("message", "")

#         if status == "success":
#             await update.message.reply_text(f"✅ {message_text}", reply_markup=ReplyKeyboardRemove())
#         else:
#             await update.message.reply_text(f"❌ Failed: {message_text}", reply_markup=ReplyKeyboardRemove())
#     except Exception as e:
#         await update.message.reply_text(f"⚠️ Error: {str(e)}", reply_markup=ReplyKeyboardRemove())

#     context.user_data.clear()
#     return ConversationHandler.END

# # 5️⃣ Capture attachments
# async def handle_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not ATTACHMENT_ENABLED:
#         await update.message.reply_text("⚠️ Attachment feature is disabled. File will not be saved.")
#         return

#     if "attachments" not in context.user_data:
#         context.user_data["attachments"] = []

#     current_count = len(context.user_data["attachments"])

#     if update.message.document:
#         if current_count >= MAX_ATTACHMENTS:
#             await update.message.reply_text(f"❌ Maximum {MAX_ATTACHMENTS} files allowed.")
#             return
#         doc = update.message.document
#         context.user_data["attachments"].append({"file_id": doc.file_id, "file_name": doc.file_name})
#         await update.message.reply_text(f"✅ Document '{doc.file_name}' received.")
#         return

#     elif update.message.photo:
#         if current_count >= MAX_ATTACHMENTS:
#             await update.message.reply_text(f"❌ Maximum {MAX_ATTACHMENTS} photos allowed.")
#             return
#         file_id = update.message.photo[-1].file_id
#         file_name = f"photo_{current_count+1}.jpg"
#         context.user_data["attachments"].append({"file_id": file_id, "file_name": file_name})
#         await update.message.reply_text(f"✅ Photo received ({current_count+1}/{MAX_ATTACHMENTS})")
#         return

#     else:
#         await update.message.reply_text("❌ Unsupported attachment type.")

# # 6️⃣ Cancel
# async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("❌ Operation cancelled. Start again with /start.", reply_markup=ReplyKeyboardRemove())
#     context.user_data.clear()
#     return ConversationHandler.END

# # 7️⃣ Ignore unexpected
# async def ignore_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if update.message:
#         if context.user_data.get('log_type') and update.message.text != "/cancel":
#             await update.message.reply_text("❌ Please share your location using the button.")
#         else:
#             await update.message.reply_text("❌ Please use the buttons only.")

# # ---- BOT SETUP ---- #
# async def set_commands_on_startup(app):
#     await app.bot.set_my_commands([
#         BotCommand("start", "Start the FlexiAttend Bot"),
#         BotCommand("cancel", "Cancel Current Operation")
#     ])

# app = ApplicationBuilder().token(BOT_TOKEN).post_init(set_commands_on_startup).build()

# conv_handler = ConversationHandler(
#     entry_points=[CommandHandler("start", verify_site)],
#     states={
#         SITE_VERIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_site_code)],
#         EMPLOYEE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_employee_id)],
#         MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
#         LOCATION: [
#             MessageHandler(filters.LOCATION, location_handler),
#             MessageHandler(filters.PHOTO | filters.Document.ALL, handle_attachments)
#         ],
#     },
#     fallbacks=[
#         CommandHandler("cancel", cancel),
#         MessageHandler(filters.ALL & ~filters.COMMAND, ignore_unexpected)
#     ]
# )

# app.add_handler(conv_handler)

# # # ---- RUN BOT (for local testing only) ---- #
# # if __name__ == "__main__":
# #     if ENABLE_FLEXIATTEND:
# #         asyncio.run(set_commands_on_startup(app))
# #         app.run_polling()


# # ---- WEBHOOK ENTRYPOINT ---- #
# @frappe.whitelist(allow_guest=True)
# def webhook(**kwargs):
#     import json
#     from telegram import Update
#     from telegram.ext import Application

#     raw_update = frappe.local.form_dict.get("update")
#     frappe.log_error(f"Webhook payload: {raw_update}", "FlexiAttend Bot Debug")

#     if not raw_update:
#         return "No update"

#     try:
#         update = Update.de_json(json.loads(raw_update), bot=BOT_TOKEN)
        
#         # Directly process the update with your handlers
#         # Example: call verify_site for /start command
#         if update.message and update.message.text == "/start":
#             # You can call your coroutine manually:
#             import asyncio
#             asyncio.run(verify_site(update, ContextTypes.DEFAULT_TYPE()))
        
#         return "OK"
#     except Exception as e:
#         frappe.log_error(f"Webhook error: {str(e)}", "FlexiAttend Bot")
#         return "Error"

# # @frappe.whitelist(allow_guest=True)
# # def webhook(**kwargs):
# #     """Telegram webhook entrypoint"""
    
# #     # Log the raw payload for debugging
# #     frappe.log_error(
# #         f"Webhook payload: {frappe.local.form_dict.get('update')}", 
# #         "FlexiAttend Bot Debug"
# #     )

# #     if not ENABLE_FLEXIATTEND:
# #         return "FlexiAttend Bot disabled"

# #     try:
# #         raw_update = frappe.local.form_dict.get("update")
# #         if not raw_update:
# #             return "No update"

# #         update = Update.de_json(json.loads(raw_update), bot=app.bot)
# #         app.update_queue.put(update)
# #         return "OK"
# #     except Exception as e:
# #         frappe.log_error(f"Webhook error: {str(e)}", "FlexiAttend Bot")
# #         return "Error"































# @@@@@@@@@@@@@@@@@@@@@@@@@@@@ - FOR LOCAL SERVER - @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
# from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
# import requests
# import frappe
# import asyncio
# import base64
# import json

# def run():
#     app.run_polling()
    

# # ---- HELPER FUNCTIONS ---- #
# def get_erp_settings():
#     settings = frappe.get_single("FlexiAttend Settings")
#     return {
#         "BOT_TOKEN": settings.flexiattend_token,
#         "ERP_URL": settings.erpnext_base_url,
#         "SITE_TOKEN": settings.site_token,
#     }

# def get_endpoints():
#     settings = get_erp_settings()
#     ERP_URL = settings["ERP_URL"]
#     return {
#         "VALIDATE_EMP_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.validate_employee",
#         "CREATE_CHECKIN_ENDPOINT": f"{ERP_URL}/api/method/flexiattend.triggers.api.create_employee_checkin"
#     }

# # # ---- BOT RUNNER ---- #
# # def start_bot():
# #     """Check if FlexiAttend is enabled, then run Telegram bot"""
# #     try:
# #         settings = frappe.get_single("FlexiAttend Settings")
# #         if not getattr(settings, "enable_flexiattend", False):
# #             frappe.log_error("FlexiAttend disabled. Bot not started.", "FlexiAttend Bot")
# #             return

# #         app = ApplicationBuilder().token(settings.flexiattend_token).build()

# #         # Scheduler needs async start
# #         asyncio.get_event_loop().create_task(app.run_polling())
# #         frappe.log_error("FlexiAttend Bot started successfully.", "FlexiAttend Bot")

# #     except Exception as e:
# #         frappe.log_error(f"Failed to start FlexiAttend Bot: {str(e)}", "FlexiAttend Bot")
        
# # ---- GLOBAL SETTINGS ---- #
# settings = get_erp_settings()
# BOT_TOKEN = settings["BOT_TOKEN"]
# SITE_TOKEN = settings["SITE_TOKEN"]
# endpoints = get_endpoints()
# VALIDATE_EMP_ENDPOINT = endpoints["VALIDATE_EMP_ENDPOINT"]
# CREATE_CHECKIN_ENDPOINT = endpoints["CREATE_CHECKIN_ENDPOINT"]

# # ---- CONVERSATION STATES ---- #
# SITE_VERIFICATION, EMPLOYEE_ID, MENU, LOCATION = range(4)

# # ---- BOT HANDLERS ---- #

# # 1️⃣ /start -> site verification
# async def verify_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text(
#         "Enter your site code to verify your site:",
#         reply_markup=ReplyKeyboardRemove()
#     )
#     return SITE_VERIFICATION

# async def check_site_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     code = update.message.text.strip()
#     if code != SITE_TOKEN:
#         await update.message.reply_text("❌ Invalid site code. Try again:")
#         return SITE_VERIFICATION
#     await update.message.reply_text("✅ Site verified! Please enter your Employee ID:")
#     return EMPLOYEE_ID

# # 2️⃣ Employee ID input
# async def get_employee_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     emp_id = update.message.text.strip()
#     context.user_data['employee_id'] = emp_id

#     try:
#         r = requests.post(VALIDATE_EMP_ENDPOINT, data={"employee_id": emp_id})
#         resp = r.json()
#         print("Validate response:", resp)

#         resp_msg = resp.get("message", {})
#         if isinstance(resp_msg, dict):
#             status = resp_msg.get("status")
#         else:
#             status = resp.get("status")

#         if status != "success":
#             await update.message.reply_text("❌ Employee not found. Enter again:")
#             return EMPLOYEE_ID
#     except Exception as e:
#         await update.message.reply_text(f"⚠️ Error verifying employee: {str(e)}")
#         return EMPLOYEE_ID

#     # Show menu buttons
#     menu_keyboard = [["Check-In", "Check-Out"]]
#     reply_markup = ReplyKeyboardMarkup(menu_keyboard, one_time_keyboard=True, resize_keyboard=True)
#     await update.message.reply_text("✅ Employee verified. Choose an option:", reply_markup=reply_markup)
#     return MENU

# # 3️⃣ Menu choice
# async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     choice = update.message.text
#     if choice not in ["Check-In", "Check-Out"]:
#         await update.message.reply_text("❌ Please use the buttons only.")
#         return MENU

#     context.user_data['log_type'] = "IN" if choice == "Check-In" else "OUT"

#     # Send location button
#     location_keyboard = [[KeyboardButton("Share Location 📍", request_location=True)]]
#     reply_markup = ReplyKeyboardMarkup(location_keyboard, one_time_keyboard=True, resize_keyboard=True)
#     await update.message.reply_text("Please share your location:", reply_markup=reply_markup)
#     return LOCATION

# # 4️⃣ Handle location & send check-in with attachments
# async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if not update.message.location:
#         await update.message.reply_text("❌ Please share your location using the button.")
#         return LOCATION

#     emp_id = context.user_data['employee_id']
#     log_type = context.user_data['log_type']
#     lat = update.message.location.latitude
#     lon = update.message.location.longitude

#     attachments = context.user_data.get("attachments", [])

#     # Convert attachments to base64
#     encoded_attachments = []
#     for att in attachments:
#         file_id = att["file_id"]
#         file_name = att["file_name"]
#         file_obj = await context.bot.get_file(file_id)
#         file_bytes = await file_obj.download_as_bytearray()
#         encoded = base64.b64encode(file_bytes).decode()
#         encoded_attachments.append({"filename": file_name, "filedata": encoded})

#     payload = {
#         "employee_id": emp_id,
#         "log_type": log_type,
#         "latitude": lat,
#         "longitude": lon,
#         "attachments": encoded_attachments
#     }

#     try:
#         r = requests.post(CREATE_CHECKIN_ENDPOINT, json=payload)
#         print("Create Checkin response:", r.text)
#         resp = r.json()

#         resp_msg = resp.get("message", {})
#         if isinstance(resp_msg, dict):
#             status = resp_msg.get("status")
#             message_text = resp_msg.get("message")
#         else:
#             status = resp.get("status")
#             message_text = resp.get("message", "")

#         if status == "success":
#             await update.message.reply_text(f"✅ {message_text}", reply_markup=ReplyKeyboardRemove())
#         else:
#             await update.message.reply_text(f"❌ Failed: {message_text}", reply_markup=ReplyKeyboardRemove())
#     except Exception as e:
#         await update.message.reply_text(f"⚠️ Error: {str(e)}", reply_markup=ReplyKeyboardRemove())

#     context.user_data.clear()
#     return ConversationHandler.END

# ## 5️⃣ Capture attachments during the process (documents & all photos)
# # 5️⃣ Capture attachments during the process
# async def handle_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     settings = frappe.get_single("FlexiAttend Settings")
#     attachments_enabled = getattr(settings, "enable_attachment_feature_in_employee_checkin", False)

#     if not attachments_enabled:
#         await update.message.reply_text("⚠️ Attachment feature is disabled. File will not be saved.")
#         print(f"[INFO] ⚠️ Attachment feature is disabled. File will not be saved.")
#         return

#     if "attachments" not in context.user_data:
#         context.user_data["attachments"] = []

#     current_count = len(context.user_data["attachments"])
#     MAX_IMAGES = getattr(settings, "maximum_file_attachments", 5)

#     new_files = []

#     # Handle documents
#     if update.message.document:
#         if current_count >= MAX_IMAGES:
#             await update.message.reply_text(f"❌ Maximum {MAX_IMAGES} images allowed per check-in.")
#             return
#         doc = update.message.document
#         context.user_data["attachments"].append({"file_id": doc.file_id, "file_name": doc.file_name})
#         print(f"[INFO] Document '{doc.file_name}' received. Total attachments: {len(context.user_data['attachments'])}")
#         await update.message.reply_text(f"✅ Document '{doc.file_name}' received and will be attached.")
#         return

#     # Handle photos (attach only one version per photo)
#     elif update.message.photo:
#         if current_count >= MAX_IMAGES:
#             await update.message.reply_text(f"❌ Maximum {MAX_IMAGES} images allowed per check-in.")
#             return

#         # Take the **last one in the list**, which is usually highest resolution
#         file_id = update.message.photo[-1].file_id
#         file_name = f"photo_{current_count + 1}.jpg"

#         context.user_data["attachments"].append({"file_id": file_id, "file_name": file_name})
#         new_files.append(file_name)
#         current_count += 1

#         print(f"[INFO] Photo received (file_id={file_id}). Total attachments: {current_count}")
#         await update.message.reply_text(f"✅ Photo received and will be attached ({current_count}/{MAX_IMAGES})")
#         return

#     else:
#         await update.message.reply_text("❌ Unsupported attachment type.")


# # 6️⃣ Cancel command
# async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("❌ Operation cancelled. You can start again with /start.", reply_markup=ReplyKeyboardRemove())
#     context.user_data.clear()
#     return ConversationHandler.END

# # 7️⃣ Ignore unexpected text (commented old validation for reference)
# async def ignore_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if update.message:
#         # # Old validation (commented) this includes attachment validation.
#         # if update.message:
#         #     await update.message.reply_text("❌ Please use the buttons only.", reply_markup=ReplyKeyboardRemove())
#         # New logic: only warn if user types text instead of sharing location - this allows attachments if it's enabbled
#         if context.user_data.get('log_type') and update.message.text != "/cancel":
#             await update.message.reply_text("❌ Please share your location using the button.")
#         else:
#             await update.message.reply_text("❌ Please use the buttons only.")

# # ---- BOT SETUP ---- #
# async def set_commands_on_startup(app):
#     await app.bot.set_my_commands([
#         BotCommand("start", "Start the FlexiAttend Bot"),
#         BotCommand("cancel", "Cancel Current Operation")
#     ])

# app = ApplicationBuilder().token(BOT_TOKEN).post_init(set_commands_on_startup).build()

# conv_handler = ConversationHandler(
#     entry_points=[CommandHandler("start", verify_site)],
#     states={
#         SITE_VERIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_site_code)],
#         EMPLOYEE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_employee_id)],
#         MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_choice)],
#         LOCATION: [
#             MessageHandler(filters.LOCATION, location_handler),
#             MessageHandler(filters.PHOTO | filters.Document.ALL, handle_attachments)
#         ],
#     },
#     fallbacks=[
#         CommandHandler("cancel", cancel),
#         MessageHandler(filters.ALL & ~filters.COMMAND, ignore_unexpected)
#     ]
# )

# app.add_handler(conv_handler)

# # ---- RUN BOT ---- #
# if __name__ == "__main__":
#     asyncio.run(set_commands_on_startup(app))
#     app.run_polling()



####@@@@@@@@@@@@@@@@@@@@@@@@@@@@@###################@@@@@@@@@@@@@@@@@@@@@@@@@@@
# ---- WEBHOOK ENTRYPOINT ---- #
# @frappe.whitelist(allow_guest=True)
# def webhook(**kwargs):
#     """Called by Telegram webhook when an update is received"""
#     try:
#         raw_update = frappe.local.form_dict.get("update")
#         if not raw_update:
#             return "No update"

#         update = Update.de_json(json.loads(raw_update), bot=app.bot)
#         app.update_queue.put(update)  # ✅ Push into already-built bot
#         return "OK"

#     except Exception as e:
#         frappe.log_error(f"Webhook error: {str(e)}", "FlexiAttend Bot")
#         return "Error"


