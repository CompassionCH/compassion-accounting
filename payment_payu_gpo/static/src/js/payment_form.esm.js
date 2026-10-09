/* global PayU, document, window, navigator */

import { RPCError, rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";
import paymentForm from "@payment/js/payment_form";

paymentForm.include({
    // #=== DOM MANIPULATION ===#

    /**
     * Mount the PayU Secure Form for cards; other methods keep the redirect flow.
     *
     * @override method from @payment/js/payment_form
     */
    async _prepareInlineForm(
        providerId,
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        flow,
    ) {
        if (providerCode !== "payu_gpo") {
            this._super(...arguments);
            return;
        }
        const radio = document.querySelector(
            'input[name="o_payment_radio"]:checked',
        );
        const container = this._getInlineForm(radio)?.querySelector(
            '[name="o_payu_gpo_card_container"]',
        );
        if (flow === "token" || !container) {
            // Saved cards and non-card methods: generic flows.
            return;
        }
        this._setPaymentFlow("direct");

        // One SDK instance per option: one Secure Form each.
        this.payuGpoSdks ??= {};
        if (this.payuGpoSdks[paymentOptionId]) {
            return;
        }
        const values = JSON.parse(container.dataset.payuGpoInlineFormValues);
        await loadJS(values.sdk_url);
        const payu = PayU(values.pos_id, { dev: values.dev });
        payu.secureForms({ lang: values.lang })
            .add("card")
            .render(`#${container.id}`);
        this.payuGpoSdks[paymentOptionId] = payu;
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Tokenize the card before creating the transaction.
     *
     * MULTI tokens can be stored for recurring charges, SINGLE ones cannot.
     *
     * @override method from @payment/js/payment_form
     */
    async _initiatePaymentFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        flow,
    ) {
        if (providerCode !== "payu_gpo" || flow !== "direct") {
            await this._super(...arguments);
            return;
        }
        const _super = this._super.bind(this);
        const result = await this.payuGpoSdks[paymentOptionId].tokenize(
            this.paymentContext.tokenizationRequested ? "MULTI" : "SINGLE",
        );
        if (result.status !== "SUCCESS") {
            const messages = (result.error?.messages ?? []).map(
                (error) => error.message,
            );
            this._displayErrorDialog(
                _t("Incorrect payment details"),
                messages.join("\n"),
            );
            this._enableButton();
            return;
        }
        this.payuGpoCardToken = result.body.token;
        await _super(...arguments);
    },

    /**
     * Pay with the card token; follow PayU to 3DS when the bank asks for it.
     *
     * @override method from @payment/js/payment_form
     */
    async _processDirectFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues,
    ) {
        if (providerCode !== "payu_gpo") {
            await this._super(...arguments);
            return;
        }
        try {
            const result = await rpc("/payment/payu_gpo/card_payment", {
                reference: processingValues.reference,
                access_token: processingValues.payu_gpo_access_token,
                card_token: this.payuGpoCardToken,
                browser: this._payuGpoBrowserData(),
            });
            window.location = result.redirect_url || "/payment/status";
        } catch (error) {
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    error.data.message,
                );
                this._enableButton();
            } else {
                return Promise.reject(error);
            }
        }
    },

    /**
     * Browser data PayU needs for 3DS 2 (HTTP headers and IP are added server-side).
     *
     * @private
     * @returns {Object}
     */
    _payuGpoBrowserData() {
        return {
            screenWidth: window.screen.width,
            screenHeight: window.screen.height,
            colorDepth: window.screen.colorDepth,
            // Navigator.javaEnabled() is always false in modern browsers.
            javaEnabled: false,
            timezoneOffset: new Date().getTimezoneOffset(),
            language: navigator.language.replace("-", "_"),
        };
    },
});
