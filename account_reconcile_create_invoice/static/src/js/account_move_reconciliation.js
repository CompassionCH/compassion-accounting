/* This is Javascript extension of module account
   in order to add custom reconcile buttons in the
   Manual Reconcile view */
   // TODO CO-3189
odoo.define('account_reconcile_create_invoice.reconciliation', function (require) {
    "use strict";

    var core = require('web.core');
    var basic_fields = require('web.basic_fields');
    var relational_fields = require('web.relational_fields');
    var reconciliation_renderer = require('account.ReconciliationRenderer');
    var reconciliation_model = require('account.ReconciliationModel');
    var qweb = core.qweb;
    var _t = core._t;

    reconciliation_renderer.StatementRenderer.include({
        events: _.extend({}, reconciliation_renderer.StatementRenderer.prototype.events, {
            "click div:first h1.statement_name": "statementNameClickHandler"
        }),

        // Change behaviour when clicking on name of bank statement
        statementNameClickHandler: function() {
            this.do_action({
                views: [[false, 'form']],
                view_type: 'form',
                view_mode: 'form',
                res_model: 'account.bank.statement',
                type: 'ir.actions.act_window',
                target: 'current',
                res_id: this.model.bank_statement_id.id
            });
        }
    });

    // Extend the class written in module account (bank statement view)
    reconciliation_renderer.LineRenderer.include({

        // Add field product_id for invoice creation (this generates the field in the view)
        _renderCreate: function (state) {
            this._super(state);
            var self = this;
            this.model.makeRecord('account.bank.statement.line', [{
                relation: 'product.product',
                type: 'many2one',
                name: 'product_id',
            }], {
                product_id: {string: _t("Product")}
            }).then(function (recordID) {
                self.handleCreateProductRecord = recordID;
                var record = self.model.get(self.handleCreateProductRecord);
                self.fields.product_id = new relational_fields.FieldMany2One(self,
                    'product_id', record, {mode: 'edit'});
                var $create = self.$('.create');
                self.fields.product_id.appendTo($create.find('.create_product_id .o_td_field'));
            });
        },

        update: function (state) {
            this._super(state);
            // TODO attempt to render product_id value into view not working
            if (state.createForm) {
                var data = this.model.get(this.handleCreateProductRecord).data;
                this.model.notifyChanges(this.handleCreateRecord, state.createForm);
            }
        }
    });

    reconciliation_model.StatementModel.include({

        updateProposition: function (handle, values) {
            // Update other fields when product_id is changed
            var self = this;
            if ('product_id' in values) {
                var parent = this._super;
                return this._rpc({
                    model: 'account.reconcile.model',
                    method: 'product_changed',
                    args:[{product_id: values.product_id.id}]
                }).then(function(changes) {
                    if (changes) {
                        if (changes.account_id)
                            values.account_id = changes.account_id;
                        if (changes.tax_id)
                            values.tax_id = changes.tax_id;
                    }
                    return parent.call(self, handle, values)
                });
            } else {
                return this._super(handle, values);
            }
        },

        quickCreateProposition: function (handle, reconcileModelId) {
            // Add product field from the reconcile model into the proposition
            // TODO the value is correctly set into the JS variables but the field value
            // does not show the value set. The field in the view seems not linked to the
            // underlying data
            this._super(handle, reconcileModelId);
            var line = this.getLine(handle);
            var reconcileModel = _.find(this.reconcileModels, function (r) {return r.id === reconcileModelId;});
            line.reconciliation_proposition[0].product_id = this._formatNameGet(reconcileModel.product_id);
            if (reconcileModel.has_second_line) {
                line.reconciliation_proposition[1].product_id = line.reconciliation_proposition[0].product_id;
            }
            return this._computeLine(line);
        }

    });

    return {
        renderer: reconciliation_renderer,
        model: reconciliation_model
    }
});
