# Copyright (c) 2025, Sebin P Sabu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FlexiAttendSettings(frappe.model.document.Document):
    def validate(self):
        if self.enable_flexiattend:
            site_url = frappe.utils.get_url()
            self.erpnext_base_url = site_url
        else:
            self.erpnext_base_url = ""
            self.site_token = ""

