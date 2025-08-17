import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def validate_employee(employee_id=None):
    """Validate Employee exists by document name"""
    if not employee_id:
        return {"status": "error", "message": _("Employee ID missing")}

    # Use exact document name
    if not frappe.db.exists("Employee", employee_id):
        return {"status": "error", "message": _("Invalid Employee ID")}

    return {"status": "success", "message": _(f"Employee {employee_id} exists")}


@frappe.whitelist(allow_guest=True)
def create_employee_checkin(employee_id, log_type, latitude=None, longitude=None):
    """Create Employee Checkin"""
    if not frappe.db.exists("Employee", employee_id):
        return {"status": "error", "message": _("Invalid Employee ID")}

    # Convert to float if possible
    try:
        latitude = float(latitude) if latitude else None
        longitude = float(longitude) if longitude else None
    except ValueError:
        latitude = longitude = None

    checkin = frappe.get_doc({
        "doctype": "Employee Checkin",
        "employee": employee_id,  # document name
        "log_type": log_type,     # "IN" or "OUT"
        "time": frappe.utils.now_datetime(),
        "device_id": "FlexiAttend",
        "latitude": latitude,
        "longitude": longitude
    })
    checkin.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "message": f"{log_type} recorded for {employee_id} at {latitude}, {longitude}",
        "checkin_id": checkin.name
    }
