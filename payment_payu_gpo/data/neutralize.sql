-- wipe the PayU GPO keys: a copy of production must never reach its account
UPDATE payment_provider
   SET payu_gpo_pos_id = NULL,
       payu_gpo_client_id = NULL,
       payu_gpo_client_secret = NULL,
       payu_gpo_second_key = NULL
 WHERE code = 'payu_gpo';

-- and the public URL PayU notifies: a copy pointed at the sandbox would have
-- PayU send its notifications to production
DELETE FROM ir_config_parameter WHERE key = 'payment_payu_gpo.notify_base_url';
