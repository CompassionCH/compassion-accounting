CREATE OR REPLACE VIEW mis_unpaid_invoice AS (
SELECT row_number() OVER () AS id,
    mis_unpaid_invoice.line_type,
    mis_unpaid_invoice.company_id,
    mis_unpaid_invoice.name,
    mis_unpaid_invoice.move,
    mis_unpaid_invoice.invoice,
    mis_unpaid_invoice.product_id,
    mis_unpaid_invoice.date,
    mis_unpaid_invoice.account_id,
    mis_unpaid_invoice.debit,
    mis_unpaid_invoice.credit
   FROM ( SELECT 'unpaid invoice' AS line_type,
            ai.company_id,
            aml.name,
            aml.move_id as move,
            ai.id AS invoice,
            aml.product_id,
            aml.date,
            aml.account_id,
            aml.debit,
            aml.credit
           FROM account_invoice ai
             left outer join account_move_line aml on ai.move_id=aml.move_id
          WHERE ai.state::text = 'open'::text AND (ai.type::text = ANY (ARRAY['out_invoice'::character varying, 'out_refund'::character varying]::text[]))
          ) mis_unpaid_invoice
)
