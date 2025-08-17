// Copyright (c) 2025, Sebin P Sabu and contributors
// For license information, please see license.txt

frappe.ui.form.on('FlexiAttend Settings', {
    generate_site_token: function(frm) {
        let d = new frappe.ui.Dialog({
            title: `<span style="color: #721c24;">Do you want to Generate the Site Token?</span>`,
            fields: [
                {
                    fieldtype: 'HTML',
                    fieldname: 'msg',
                    options: `<div style="padding:10px; background-color:#f9f9f9; color:#333; border-radius:5px;">
                                By confirming, a new site token will be generated and all the employees registered will have to reregister their bot access.
                              </div>`
                }
            ],
            primary_action_label: 'Confirm',
            primary_action(values) {
                let token_part_left = Array.from({length: 12}, () => 
                    Math.floor(Math.random() * 36).toString(36).toUpperCase()
                ).join('');
                let token_part_right = Array.from({length: 12}, () => 
                    Math.floor(Math.random() * 36).toString(36).toUpperCase()
                ).join('');
                let final_token = `${token_part_left}:${token_part_right}`;

                frm.set_value('site_token', final_token);
                frm.save().then(() => {
                    frappe.show_alert({message: __('New Site Token Generated and Saved'), indicator: 'green'});
                });

                d.hide();
            },
            secondary_action_label: 'Discard',
            secondary_action() {
                frappe.show_alert({message: __('Site Token generation cancelled'), indicator: 'red'});
                d.hide();
            }
        });

        d.show();

        setTimeout(() => {
            d.$wrapper.find('.modal-footer .btn-primary').css('background-color', '#28a745');
            d.$wrapper.find('.modal-footer .btn-secondary').css('background-color', '#f8d7da');
            d.$wrapper.find('.modal-footer .btn-secondary').css('color', '#721c24');
        }, 100);
    },

    refresh: function(frm) {
        // Update FlexiAttend Token button
        frm.add_custom_button(__('Update FlexiAttend Token'), function() {
            let d = new frappe.ui.Dialog({
                title: `<span style="color:#721c24;">Update FlexiAttend Token</span>`,
                fields: [
                    {
                        label: 'FlexiAttend Token',
                        fieldname: 'flexiattend_token',
                        fieldtype: 'Data',
                        default: frm.doc.flexiattend_token || ''
                    }
                ],
                primary_action_label: __('Update'),
                primary_action(values) {
                    frm.set_value('flexiattend_token', values.flexiattend_token);
                    frm.save().then(() => {
                        frappe.show_alert({message: __('FlexiAttend Token updated successfully'), indicator: 'blue'});
                        d.hide();
                    });
                },
                secondary_action_label: __('Discard'),
                secondary_action() {
                    frappe.show_alert({message: __('Updating FlexiAttend Token cancelled'), indicator: 'red'});
                    d.hide();
                }
            });

            d.show();

            setTimeout(() => {
                d.$wrapper.find('.modal-footer .btn-primary').css({'background-color': '#28a745','border-color': '#28a745','color': 'white'});
                d.$wrapper.find('.modal-footer .btn-secondary').css({'background-color': '#f8d7da','border-color': '#f8d7da','color': '#721c24'});
            }, 100);
        }, __('Actions'));

        // Toggle Attachment Feature Button
        const render_attachment_toggle = () => {
            // Remove previous toggle button if exists
            frm.page.remove_inner_button('Enable Attachment Feature in CheckIn');
            frm.page.remove_inner_button('Disable Attachment Feature in CheckIn');

            if (frm.doc.enable_attachment_feature_in_employee_checkin) {
                // Show Disable button
                frm.add_custom_button(__('Disable Attachment Feature in CheckIn'), () => {
                    frm.set_value('enable_attachment_feature_in_employee_checkin', 0);
                    frm.save().then(() => {
                        frappe.show_alert({message: __('Attachment Feature disabled in CheckIn'), indicator: 'red'});
                        render_attachment_toggle();
                    });
                }, __('Actions'));
            } else {
                // Show Enable button
                frm.add_custom_button(__('Enable Attachment Feature in CheckIn'), () => {
                    frm.set_value('enable_attachment_feature_in_employee_checkin', 1);
                    frm.save().then(() => {
                        frappe.show_alert({message: __('Attachment Feature enabled in CheckIn'), indicator: 'green'});
                        render_attachment_toggle();
                    });
                }, __('Actions'));
            }
        };

        // Render the toggle button on refresh
        render_attachment_toggle();
    }
});