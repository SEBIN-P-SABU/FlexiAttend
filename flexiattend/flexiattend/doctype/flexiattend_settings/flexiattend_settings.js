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
                // Generate 12-character random alphanumeric token (uppercase)
                let token_part_left = Array.from({length: 12}, () => 
                    Math.floor(Math.random() * 36).toString(36).toUpperCase()
                ).join('');

                // Generate 12-character random alphanumeric string for the right part
                let token_part_right = Array.from({length: 12}, () => 
                    Math.floor(Math.random() * 36).toString(36).toUpperCase()
                ).join('');

                // Combine both parts
                 let final_token = `${token_part_left}:${token_part_right}`;

                // Set the token in your field
                frm.set_value('site_token', final_token);

                // Save automatically
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

        // Apply button colors
        setTimeout(() => {
            d.$wrapper.find('.modal-footer .btn-primary').css('background-color', '#28a745'); // Confirm → green
            d.$wrapper.find('.modal-footer .btn-secondary').css('background-color', '#f8d7da'); // Discard → light red
            d.$wrapper.find('.modal-footer .btn-secondary').css('color', '#721c24'); // Discard text → dark red
        }, 100);
    },
    
    


     refresh: function(frm) {
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
                        frappe.show_alert({
                            message: __('FlexiAttend Token updated successfully'),
                            indicator: 'blue'
                        });
                        d.hide();
                    });
                },
                secondary_action_label: __('Discard'),
                secondary_action() {
                    frappe.show_alert({
                        message: __('Updating FlexiAttend Token cancelled'),
                        indicator: 'red'
                    });
                    d.hide();
                }
            });

            d.show();

            setTimeout(() => {
                // Update button → green
                d.$wrapper.find('.modal-footer .btn-primary')
                    .css({
                        'background-color': '#28a745',
                        'border-color': '#28a745',
                        'color': 'white'
                    });

                // Discard button → light red background, dark red text
                d.$wrapper.find('.modal-footer .btn-secondary')
                    .css({
                        'background-color': '#f8d7da',
                        'border-color': '#f8d7da',
                        'color': '#721c24'
                    });
            }, 100);
        }, __('Actions'));
    }
});

