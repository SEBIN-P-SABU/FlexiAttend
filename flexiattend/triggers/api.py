# Copyright (c) 2025, Sebin P Sabu and contributors
# For license information, please see license.txt

import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def validate_employee(employee_id=None):
    """Validate Employee exists by document name and status"""
    if not employee_id:
        return {"status": "error", "message": _("Employee ID missing")}

    # Use exact document name
    if not frappe.db.exists("Employee", {"name": employee_id, "status": "Active", "custom_add_employee_to_flexiattend": 1}):
        return {"status": "error", "message": _("Invalid Employee ID")}

    return {"status": "success", "message": _(f"Employee {employee_id} exists")}


@frappe.whitelist(allow_guest=True)
def create_employee_checkin(employee_id, log_type, latitude=None, longitude=None, attachments=None):
    """Create Employee Checkin and attach files"""
    if not frappe.db.exists("Employee", employee_id):
        return {"status": "error", "message": _("Invalid Employee ID")}

    # Convert lat/lon to float
    try:
        latitude = float(latitude) if latitude else None
        longitude = float(longitude) if longitude else None
    except ValueError:
        latitude = longitude = None

    checkin = frappe.get_doc({
        "doctype": "Employee Checkin",
        "employee": employee_id,
        "log_type": log_type,
        "time": frappe.utils.now_datetime(),
        "device_id": "FlexiAttend",
        "latitude": latitude,
        "longitude": longitude
    })
    checkin.insert(ignore_permissions=True)
    
    # Handle attachments
    if attachments:
        # attachments should be a list of dicts: [{"filename": ..., "filedata": ...}]
        import base64
        import json

        if isinstance(attachments, str):
            try:
                attachments = json.loads(attachments)
            except Exception:
                attachments = []

        for att in attachments:
            filedata = att.get("filedata")
            filename = att.get("filename")
            if filedata and filename:
                # filedata should be base64 encoded string
                frappe.get_doc({
                    "doctype": "File",
                    "file_name": filename,
                    "attached_to_doctype": "Employee Checkin",
                    "attached_to_name": checkin.name,
                    "content": filedata,  # raw/base64 bytes
                    "decode": True
                }).insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "success",
        "message": f"{log_type} recorded for {employee_id} at {latitude}, {longitude}",
        "checkin_id": checkin.name
    }



# api.py

# import frappe
# import requests
# import base64
# import json
# from frappe.utils.redis_wrapper import RedisWrapper

# # --- Redis session helper ---
# def get_session(user_id):
#     return frappe.cache().hgetall(f"flexiattend_user_{user_id}") or {}

# def set_session(user_id, data):
#     frappe.cache().hmset(f"flexiattend_user_{user_id}", data)

# def clear_session(user_id):
#     frappe.cache().delete(f"flexiattend_user_{user_id}")

# # --- Telegram send helper ---
# def telegram_send(chat_id, text, reply_markup=None):
#     settings = frappe.get_single("FlexiAttend Settings")
#     bot_token = settings.flexiattend_token
#     url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
#     payload = {
#         "chat_id": chat_id,
#         "text": text,
#         "reply_markup": json.dumps(reply_markup) if reply_markup else None,
#     }
#     requests.post(url, data=payload)

# # --- Telegram Webhook Endpoint ---
# @frappe.whitelist(allow_guest=True)
# def telegram_webhook():
#     settings = frappe.get_single("FlexiAttend Settings")
#     site_token = settings.site_token
#     ERP_URL = settings.erpnext_base_url

#     update = frappe.request.get_json()
#     if not update:
#         return "no update"

#     message = update.get("message", {})
#     chat_id = message.get("chat", {}).get("id")
#     user_id = message.get("from", {}).get("id")

#     text = message.get("text")
#     location = message.get("location")
#     document = message.get("document")
#     photos = message.get("photo")

#     session = get_session(user_id)

#     # 1️⃣ /start
#     if text == "/start":
#         clear_session(user_id)
#         telegram_send(chat_id, "Enter your site code to verify your site:")
#         set_session(user_id, {"state": "SITE_VERIFICATION"})
#         return "ok"

#     # 2️⃣ Site verification
#     if session.get("state") == "SITE_VERIFICATION":
#         if text != site_token:
#             telegram_send(chat_id, "❌ Invalid site code. Try again:")
#             return "ok"
#         telegram_send(chat_id, "✅ Site verified! Please enter your Employee ID:")
#         set_session(user_id, {"state": "EMPLOYEE_ID"})
#         return "ok"

#     # 3️⃣ Employee ID input
#     if session.get("state") == "EMPLOYEE_ID":
#         emp_id = text.strip()
#         r = requests.post(
#             f"{ERP_URL}/api/method/flexiattend.triggers.api.validate_employee",
#             data={"employee_id": emp_id},
#         )
#         resp = r.json()
#         if resp.get("status") != "success":
#             telegram_send(chat_id, "❌ Employee not found. Enter again:")
#             return "ok"

#         keyboard = {"keyboard": [["Check-In", "Check-Out"]], "resize_keyboard": True}
#         telegram_send(chat_id, "✅ Employee verified. Choose an option:", reply_markup=keyboard)
#         set_session(user_id, {"state": "MENU", "employee_id": emp_id})
#         return "ok"

#     # 4️⃣ Menu choice
#     if session.get("state") == "MENU":
#         if text not in ["Check-In", "Check-Out"]:
#             telegram_send(chat_id, "❌ Please use the buttons only.")
#             return "ok"

#         log_type = "IN" if text == "Check-In" else "OUT"
#         keyboard = {
#             "keyboard": [[{"text": "Share Location 📍", "request_location": True}]],
#             "resize_keyboard": True,
#             "one_time_keyboard": True,
#         }
#         telegram_send(chat_id, "Please share your location:", reply_markup=keyboard)
#         set_session(user_id, {"state": "LOCATION", "employee_id": session["employee_id"], "log_type": log_type})
#         return "ok"

#     # 5️⃣ Location handler
#     if session.get("state") == "LOCATION" and location:
#         emp_id = session["employee_id"]
#         log_type = session["log_type"]
#         lat, lon = location["latitude"], location["longitude"]

#         payload = {
#             "employee_id": emp_id,
#             "log_type": log_type,
#             "latitude": lat,
#             "longitude": lon,
#         }
#         r = requests.post(f"{ERP_URL}/api/method/flexiattend.triggers.api.create_employee_checkin", json=payload)
#         resp = r.json()
#         if resp.get("status") == "success":
#             telegram_send(chat_id, f"✅ {resp.get('message')}")
#         else:
#             telegram_send(chat_id, f"❌ Failed: {resp.get('message')}")
#         clear_session(user_id)
#         return "ok"

#     # 6️⃣ Cancel
#     if text == "/cancel":
#         clear_session(user_id)
#         telegram_send(chat_id, "❌ Operation cancelled. Start again with /start")
#         return "ok"

#     return "ok"
