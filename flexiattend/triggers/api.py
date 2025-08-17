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
    if not frappe.db.exists("Employee", {"name": employee_id, "status": "Active"}):
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