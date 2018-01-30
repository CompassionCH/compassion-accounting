/* This is Javascript extension of module account
   in order to add custom reconcile buttons in the 
   Manual Reconcile view */
odoo.define('account_reconcile_create_invoice.reconciliation', function (require) {
    "use strict";

    var core = require('web.core');
    var reconciliation = require('account.reconciliation');
    var _t = core._t;
    var FieldMany2One = core.form_widget_registry.get('many2one');
    var Model = require('web.Model');

    // Extend the class written in module account (bank statement view)
    reconciliation.bankStatementReconciliationLine.include({
        events: _.extend({
            // this removes the ability to change partner of a line
            // //        but this functionality may not be necessary for us.
            "click .partner_name": "open_partner"
        }, reconciliation.bankStatementReconciliationLine.prototype.events),

        open_partner: function() {
            this.do_action({
                views: [[false, 'form']],
                view_type: 'form',
                view_mode: 'form',
                res_model: 'res.partner',
                type: 'ir.actions.act_window',
                target: 'current',
                res_id: this.partner_id
            });
        },

        // Return values of new fields to python.
        prepareCreatedMoveLinesForPersisting: function(lines) {
            var result = this._super(lines);
            for (var i = 0; i < result.length; i++) {
                if (lines[i].product_id) {
                    result[i].product_id = lines[i].product_id;
                }
            }
            return result;
        },

        // Update fields when product_id is changed.
        createdLinesChanged: function() {
            this._super();
            var model_presets = new Model("account.reconcile.model");
            var self = this;
            var product_id = self.product_id_field.get_value("product_id");
            if (product_id != this.product_selected) {
                this.product_selected = product_id;
                model_presets.call("product_changed", [product_id]).then(function(values) {
                    if (values) {
                        self.account_id_field.set_value(values.account_id);
                        if (self.analytic_account_id_field && values.analytic_id) {
                            self.analytic_account_id_field.set_value(values.analytic_id);
                        }
                    }
                });
            }
        }
    });

    reconciliation.abstractReconciliation.include({
        // Add fields in reconcile view
        init: function(parent, context) {
            this._super(parent, context);

            // Extend an arbitrary field/widget with an init function that
            // will set the options attribute to a given object.
            // This is useful to pass arguments for a field when using the
            // web_m2x_options module.
            function fieldWithOptions(fieldClass, options) {
                return fieldClass.extend({
                    // pylint: disable=W7903
                    init: function() {
                        this._super.apply(this, arguments);
                        this.options = options;
                    }
                });
            }

            this.create_form_fields.product_id = {
                id: "product_id",
                index: 5,
                corresponding_property: "product_id",
                label: _t("Product"),
                required: false,
                tabindex: 15,
                constructor: FieldMany2One,
                field_properties: {
                    relation: "product.product",
                    string: _t("Product"),
                    type: "many2one"
                }
            };
        },

        // Add product_id to statement operations.
        fetchPresets: function() {
            var self = this;
            return this._super().then(function() {
                self.model_presets.query().order_by('-sequence', '-id').all().then(function (data) {
                    _(data).each(function(datum){
                        self.presets[datum.id].lines[0].product_id = datum.product_id;
                    });
                });
            });

        },

        // Change behaviour when clicking on name of bank statement
        statementNameClickHandler: function() {
            this.do_action({
                views: [[false, 'form']],
                view_type: 'form',
                view_mode: 'form',
                res_model: 'account.bank.statement',
                type: 'ir.actions.act_window',
                target: 'current',
                res_id: this.statement_ids[0]
            });
        }

    });

    return {
        abstractReconciliation: reconciliation.abstractReconciliation,
        bankStatementReconciliationLine: reconciliation.bankStatementReconciliationLine
    }
});
