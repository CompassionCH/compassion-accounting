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
            return this._super(...arguments);
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
        try {
            await loadJS(values.sdk_url);
            const payu = PayU(values.pos_id, { dev: values.dev });
            payu.secureForms({ lang: values.lang })
                .add("card")
                .render(`#${container.id}`);
            this.payuGpoSdks[paymentOptionId] = payu;
        } catch {
            // E.g. PayU's script blocked by a browser extension.
            this._displayErrorDialog(
                _t("Payment processing failed"),
                _t(
                    "The card form of PayU could not be loaded. Please reload the page.",
                ),
            );
        }
    },

    /**
     * Check the name on the card before the transaction is created: a
     * transaction left in draft blocks what it pays until it is cleaned up.
     *
     * @override method from @payment/js/payment_form
     */
    async _initiatePaymentFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        flow,
    ) {
        if (providerCode === "payu_gpo" && flow === "direct") {
            if (!this.payuGpoSdks?.[paymentOptionId]) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    _t(
                        "The card form of PayU could not be loaded. Please reload the page.",
                    ),
                );
                this._enableButton();
                return;
            }
            const cardholderInput = this._payuGpoCardholderInput();
            if (cardholderInput && !cardholderInput.value.trim()) {
                this._displayErrorDialog(
                    _t("Incorrect payment details"),
                    _t("Please enter the name on the card."),
                );
                this._enableButton();
                return;
            }
        }
        return await this._super(...arguments);
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Tokenize the card, pay with the token, and follow PayU to 3DS when the
     * bank asks for it.
     *
     * The card is tokenized once the transaction exists: only the server knows
     * whether it must be saved (the tokenization checkbox is hidden when the
     * context requires it). MULTI tokens can be stored for recurring charges,
     * SINGLE ones cannot.
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
        const cardholderName = (
            this._payuGpoCardholderInput()?.value || ""
        ).trim();
        let tokenization = null;
        try {
            tokenization = await this.payuGpoSdks[paymentOptionId].tokenize(
                processingValues.should_tokenize ? "MULTI" : "SINGLE",
            );
        } catch {
            tokenization = { status: "ERROR" };
        }
        if (tokenization.status !== "SUCCESS") {
            const messages = (tokenization.error?.messages ?? []).map(
                (error) => error.message,
            );
            this._displayErrorDialog(
                _t("Incorrect payment details"),
                messages.join("\n") ||
                    _t("The card could not be read. Please try again."),
            );
            await this._payuGpoCancelDraft(processingValues);
            this._enableButton();
            return;
        }
        try {
            const result = await rpc("/payment/payu_gpo/card_payment", {
                reference: processingValues.reference,
                access_token: processingValues.payu_gpo_access_token,
                card_token: tokenization.body.token,
                browser: this._payuGpoBrowserData(),
                cardholder_name: cardholderName,
                card_mask: tokenization.body.mask,
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
     * Cancel the transaction of a card the Secure Form refused, before the
     * buyer tries again: nothing reached PayU, and a draft left behind blocks
     * what it pays until it is cleaned up.
     *
     * @private
     * @param {Object} processingValues
     * @returns {Promise}
     */
    async _payuGpoCancelDraft(processingValues) {
        try {
            await rpc("/payment/payu_gpo/cancel", {
                reference: processingValues.reference,
                access_token: processingValues.payu_gpo_access_token,
            });
        } catch {
            // Best effort: the draft is then cleaned up later.
        }
    },

    /**
     * The "Name on card" input of the selected card option, if any.
     *
     * @private
     * @returns {HTMLInputElement|null}
     */
    _payuGpoCardholderInput() {
        return this._getInlineForm(
            document.querySelector('input[name="o_payment_radio"]:checked'),
        )?.querySelector('[name="o_payu_gpo_cardholder_name"]');
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
