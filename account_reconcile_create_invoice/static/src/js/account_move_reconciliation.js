/* This is Javascript extension of module account
   in order to add custom reconcile buttons in the
   Manual Reconcile view */
odoo.define('account_reconcile_create_invoice.reconciliation', function (require) {
    "use strict";

    var core = require('web.core');
    var basic_fields = require('web.basic_fields');
    var relational_fields = require('web.relational_fields');
    var reconciliation_renderer = require('account.ReconciliationRenderer');
    var reconciliation_model = require('account.ReconciliationModel');
    var qweb = core.qweb;
    var _t = core._t;
    var FieldMany2One = core.form_widget_registry.get('many2one');

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
        events: _.extend({}, reconciliation_renderer.LineRenderer.prototype.events, {
            // this removes the ability to change partner of a line
            // but this functionality may not be necessary for us.
            "click .partner_name": "open_partner"
        }),

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

        // obligé de surcharger toute la méthode juste pour ajouter la création du product_id....!
        // TODO: trouver une meilleure façon de surcharger la méthode parente...
        _renderCreate: function (state) {
            /*
            // ne fonctionne pas... ---> Uncaught TypeError: Cannot read property 'type' of undefined

            this._super(state);
            var self = this;
            this.model.makeRecord('account.bank.statement.line', [{
                relation: 'product.product',
                type: 'many2one',
                name: 'product_id',
            }], {
                product_id: {string: _t("Product")}
            }).then(function (recordID) {
                self.handleCreateRecord = recordID;
                var record = self.model.get(self.handleCreateRecord);

                self.fields.product_id = new relational_fields.FieldMany2One(self,
                    'product_id', record, {mode: 'edit'});

                var $create = $(qweb.render("reconciliation.line.create", {'state': state}));
                self.fields.product_id.appendTo($create.find('.create_product_id .o_td_field'));
                self.$('.create').append($create);
            });
            */
            var self = this;
            this.model.makeRecord('account.bank.statement.line', [{
                relation: 'account.account',
                type: 'many2one',
                name: 'account_id',
            }, {
                relation: 'product.product',
                type: 'many2one',
                name: 'product_id',
            }, {
                relation: 'account.journal',
                type: 'many2one',
                name: 'journal_id',
            }, {
                relation: 'account.tax',
                type: 'many2one',
                name: 'tax_id',
            }, {
                relation: 'account.analytic.account',
                type: 'many2one',
                name: 'analytic_account_id',
            }, {
                type: 'char',
                name: 'label',
            }, {
                type: 'float',
                name: 'amount',
            }], {
                account_id: {
                    string: _t("Account"),
                    domain: [['deprecated', '=', false]],
                },
                product_id: {string: _t("Product")},
                label: {string: _t("Label")},
                amount: {string: _t("Account")}
            }).then(function (recordID) {
                self.handleCreateRecord = recordID;
                var record = self.model.get(self.handleCreateRecord);

                self.fields.account_id = new relational_fields.FieldMany2One(self,
                    'account_id', record, {mode: 'edit'});

                self.fields.product_id = new relational_fields.FieldMany2One(self,
                    'product_id', record, {mode: 'edit'});

                self.fields.journal_id = new relational_fields.FieldMany2One(self,
                    'journal_id', record, {mode: 'edit'});

                self.fields.tax_id = new relational_fields.FieldMany2One(self,
                    'tax_id', record, {mode: 'edit'});

                self.fields.analytic_account_id = new relational_fields.FieldMany2One(self,
                    'analytic_account_id', record, {mode: 'edit'});

                self.fields.label = new basic_fields.FieldChar(self,
                    'label', record, {mode: 'edit'});

                self.fields.amount = new basic_fields.FieldFloat(self,
                    'amount', record, {mode: 'edit'});

                var $create = $(qweb.render("reconciliation.line.create", {'state': state}));
                self.fields.account_id.appendTo($create.find('.create_account_id .o_td_field'))
                    .then(addRequiredStyle.bind(self, self.fields.account_id));
                self.fields.product_id.appendTo($create.find('.create_product_id .o_td_field'));
                self.fields.journal_id.appendTo($create.find('.create_journal_id .o_td_field'));
                self.fields.tax_id.appendTo($create.find('.create_tax_id .o_td_field'));
                self.fields.analytic_account_id.appendTo($create.find('.create_analytic_account_id .o_td_field'));
                self.fields.label.appendTo($create.find('.create_label .o_td_field'))
                    .then(addRequiredStyle.bind(self, self.fields.label));
                self.fields.amount.appendTo($create.find('.create_amount .o_td_field'))
                    .then(addRequiredStyle.bind(self, self.fields.amount));
                self.$('.create').append($create);

                function addRequiredStyle(widget) {
                    widget.$el.addClass('o_required_modifier');
                }
            });
        },
    });

    reconciliation_model.StatementModel.include({
        quickCreateFields: ['account_id', 'amount', 'analytic_account_id', 'label', 'tax_id', 'product_id'],

        // obligé de surcharger toute la méthode juste pour changer le tableau fields et y ajouter product_id....!
        // TODO: trouver une meilleure façon de surcharger la méthode parente...
        quickCreateProposition: function (handle, reconcileModelId) {
            var line = this.getLine(handle);
            var reconcileModel = _.find(this.reconcileModels, function (r) {return r.id === reconcileModelId;});
            var fields = ['account_id', 'amount', 'amount_type', 'analytic_account_id', 'journal_id', 'label', 'tax_id', 'product_id'];
            this._blurProposition(handle);

            var focus = this._formatQuickCreate(line, _.pick(reconcileModel, fields));
            focus.reconcileModelId = reconcileModelId;
            line.reconciliation_proposition.push(focus);

            if (reconcileModel.has_second_line) {
                var second = {};
                _.each(fields, function (key) {
                    second[key] = ("second_"+key) in reconcileModel ? reconcileModel["second_"+key] : reconcileModel[key];
                });
                focus = this._formatQuickCreate(line, second);
                focus.reconcileModelId = reconcileModelId;
                line.reconciliation_proposition.push(focus);
                this._computeReconcileModels(handle, reconcileModelId);
            }
            line.createForm = _.pick(focus, this.quickCreateFields);
            return this._computeLine(line);
        },

        updateProposition: function (handle, values) {
            if (values.product_id) {
                var context = this;
                var parent = this._super;
                return this._rpc({
                    model: 'account.reconcile.model',
                    method: 'product_changed',
                    args:[{product_id: values.product_id.id}]
                }).then(function(changes) {
                    if (changes) {
                        values = {...values, ...changes}
                    }
                    return parent.call(context, handle, values)
                });
            } else {
                return this._super(handle, values);
            }
        },

        _formatLineProposition: function (line, props) {
            this._super(line, props);
            if (props.length) {
                var self = this;
                _.each(props, function (prop) {
                    prop.product_id = self._formatNameGet(prop.product_id || line.product_id);
                });
            }
        },

        _formatToProcessReconciliation: function (line, prop) {
            var result = this._super(line, prop);
            if (prop.product_id) {
                result.product_id = prop.product_id.id;
            }
            return result;
        },

        _formatQuickCreate: function(line, values) {
            values = values || {};
            var prop = this._super(line, values);

            prop.product_id = this._formatNameGet(values.product_id);
            return prop;
        },

        _formatLine: function (lines) {
            this._super(lines);
        },

        _formatMoveLine: function (handle, mv_lines) {
            this._super(handle, mv_lines);
        },

    });

    return {
        renderer: reconciliation_renderer,
        model: reconciliation_model
    }
});
